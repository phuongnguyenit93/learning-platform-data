# Những tình huống bộ thực thi từ chối tác vụ trong Spring Framework

Trong ứng dụng Spring, công việc bất đồng bộ thường được đưa vào `TaskExecutor` hoặc một `ThreadPoolTaskExecutor`. Việc gọi `execute(...)`, `submit(...)` hoặc phương thức `@Async` **không tự bảo đảm task được nhận, được chạy hay hoàn tất thành công**. Khi executor quá tải hoặc đang đóng, một lời gọi giao việc mới có thể bị **từ chối (task rejection)**. Hiểu nguyên nhân từ chối giúp tránh mất việc âm thầm, backlog kéo dài và retry làm hệ thống càng quá tải.

Bài học này tập trung trả lời: **khi nào executor từ chối task, nhận biết ở đâu, Spring biểu diễn lỗi thế nào, và cần phản ứng ra sao theo yêu cầu nghiệp vụ**. Các ví dụ dùng Java 17+ và Spring Framework 6.x/Spring Boot 3.x. Những thuộc tính cụ thể cần đối chiếu với phiên bản framework ứng dụng đang chạy.

## 1. “Từ chối tác vụ” chính xác là gì?

Một executor **từ chối** khi có yêu cầu giao một task nhưng executor **không chấp nhận task đó để thực thi theo hợp đồng hiện tại**. Ở mức Java, `ThreadPoolExecutor.execute(Runnable)` chuyển yêu cầu không thể tiếp nhận tới `RejectedExecutionHandler`. Chính handler quyết định ném `RejectedExecutionException`, chạy ngay trên caller hoặc bỏ task theo chính sách.

Ba mốc thường bị nhầm lẫn:

```text
Producer / Caller
       |
       | submit(task)
       v
 [Executor xét nhận task] -- KHÔNG NHẬN --> Rejection policy
       |
       | ĐÃ NHẬN
       v
 [Đợi queue hoặc worker chạy]
       |
       +---> Thành công
       +---> Exception khi đang chạy
       +---> Bị hủy/gián đoạn
       +---> Chưa chạy trước lúc tiến trình dừng/crash
```

- **Accepted / đã nhận:** pool đã tiếp nhận để xếp hàng hoặc chạy. Chưa đồng nghĩa task đã hoàn thành.
- **Rejected / bị từ chối:** task không được nhận theo chính sách tiếp nhận thông thường. Với `AbortPolicy`, caller nhận exception ngay tại lúc giao việc.
- **Execution failure / lỗi lúc chạy:** task đã được nhận, nhưng code nghiệp vụ ném lỗi sau đó. Với `submit`, lỗi thường nằm trong `Future`; với `CompletableFuture`, lỗi đi qua cơ chế hoàn tất ngoại lệ.
- **Cancellation, timeout và shutdown:** là các trạng thái/vòng đời khác; có thể liên quan tới từ chối, nhưng không phải mọi timeout hay interrupt đều là rejection.
- **Discard policy:** vẫn là tình huống handler quyết định **bỏ task** sau khi không nhận được, nhưng caller có thể không thấy exception. Vì vậy “không có lỗi” không đồng nghĩa “đã nhận và sẽ chạy”.

Trong Spring, `ThreadPoolTaskExecutor` triển khai `TaskExecutor`; với chính sách ném lỗi, lời gọi có thể nhận **`TaskRejectedException`** của Spring, một subtype của `RejectedExecutionException`. Cách lỗi nổi lên khi dùng `@Async` phụ thuộc đường gọi và handler; không thể suy đoán từ việc method có annotation.

## 2. Tình huống 1: pool và hàng đợi đều bão hòa

Đây là nguyên nhân phổ biến khi chạy nền dưới tải cao. Pool có giới hạn `corePoolSize`, `maxPoolSize` và `queueCapacity`. Với `ThreadPoolTaskExecutor` bao quanh JDK `ThreadPoolExecutor`, thuật toán tổng quát khi task mới đến là:

1. Nếu số worker đang tồn tại thấp hơn **core**, tạo thêm worker cho task.
2. Khi đã đạt core, thử đưa task vào **queue**.
3. Nếu queue không còn chỗ, thử tăng worker tới **max**.
4. Nếu queue không nhận thêm và đã đạt max, chuyển task sang **rejection handler**.

Ví dụ:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(2);
```

Giả định **mọi task đang chạy đều bị giữ lại**, không có worker rảnh hoặc task nào kịp kết thúc:

| Task đến | Pool/queue tại lúc xét nhận | Hành động |
| --- | --- | --- |
| Task 1 | Worker chưa đạt core | Tạo worker 1 |
| Task 2 | Worker chưa đạt core | Tạo worker 2 |
| Task 3 | Đã đủ core, queue còn chỗ | Xếp vào queue (1/2) |
| Task 4 | Đã đủ core, queue còn chỗ | Xếp vào queue (2/2) |
| Task 5 | Queue đầy, worker chưa đạt max | Tạo worker 3 |
| Task 6 | Queue đầy, worker chưa đạt max | Tạo worker 4 |
| Task 7 | Queue đầy, đã đủ 4 worker | **Rejection handler** |

Sơ đồ:

```text
core=2, max=4, queueCapacity=2

            2 core workers           queue=2          2 extra workers
Task 1,2 -> [W1][W2]    Task 3,4 -> [Q3][Q4]   Task 5,6 -> [W3][W4]
Task 7  --------------------------------------------------> REJECT
```

**Điều kiện về thời gian rất quan trọng:** đây là trường hợp **cả sáu task đã nhận đều chưa hoàn thành**. Nếu worker xử lý xong một việc và lấy task khỏi queue trước khi task 7 đến, task 7 có thể được nhận. Không tính mức từ chối đơn giản bằng số lượng request trong cả một phút; phải nhìn **mức độ đồng thời và queue tại thời điểm submit**.

### 2.1. Vì sao chỉ đặt `maxPoolSize` lớn chưa đủ?

Nếu `core=2, max=20, queueCapacity=10_000`, sau khi đủ core, các task mới thường chờ trong queue. Pool **không tăng vượt core chỉ vì có nhiều task đang đợi**; nó thử queue trước khi tạo worker vượt core. Khi queue lớn, hệ thống có thể chậm khủng khiếp nhưng chưa hề phát sinh rejection do capacity.

Với queue gần như không giới hạn, nếu tốc độ nạp việc luôn cao hơn tốc độ xử lý, backlog tăng và có thể dẫn tới `OutOfMemoryError`. Đây là **lỗi cạn bộ nhớ**, không nên mô tả như một rejection bình thường có thể xử lý trơn tru.

### 2.2. Tình huống bão hòa do blocking I/O

Một thread pool có thể đầy ngay cả khi CPU rất thấp. Ví dụ có 8 worker cùng chờ database connection hoặc HTTP API chậm; các task mới nằm trong queue cho tới khi đầy. Tăng thêm thread lúc đó có thể làm DB/API càng quá tải.

Chẩn đoán phải xem **active worker, queue size, queue wait, downstream latency, connection pool** và số lần từ chối, không chỉ CPU.

## 3. Tình huống 2: executor đã shutdown hoặc đang chuyển sang trạng thái đóng

JDK `ThreadPoolExecutor` từ chối task mới sau khi `shutdown()` hoặc `shutdownNow()`. `shutdown()` bắt đầu quá trình đóng có trật tự: có thể tiếp tục xử lý task đã nhận, nhưng **không nhận task mới**. `shutdownNow()` cố ngừng task đang chạy bằng interrupt và rút các task chờ khỏi queue theo cơ chế best effort; không thể ép mọi tác vụ đang chặn I/O dừng ngay.

Ví dụ Java:

```java
ExecutorService pool = Executors.newFixedThreadPool(2);
pool.shutdown();
pool.execute(() -> System.out.println("work")); // Thường ném RejectedExecutionException
```

Đây là **fragment** minh họa với default `AbortPolicy` của executor JDK. Khi dùng custom rejection handler như `CallerRunsPolicy` hoặc `DiscardPolicy`, task gửi sau shutdown có thể bị **bỏ mà không ném exception**. Đừng khẳng định mọi policy đều ném cùng một lỗi.

Trong Spring, tình huống này có thể xảy ra khi:

- Application context đang đóng nhưng một HTTP request, listener hoặc scheduler vẫn cố giao việc mới.
- Một bean đang trong `@PreDestroy` lại gọi service `@Async`, trong khi executor đã vào giai đoạn shutdown.
- Một background callback giữ tham chiếu tới executor và submit sau khi context dừng.
- Ứng dụng chủ động gọi `shutdown()` trên một executor dùng chung quá sớm.
- Có race giữa thời điểm kiểm tra trạng thái `isShutdown()` và lúc submit: kiểm tra thấy chưa shutdown **không bảo đảm** một thread khác không đóng executor ngay sau đó.

**Cách xử lý:** trước hết phân biệt đây là shutdown hợp lệ hay lỗi thứ tự lifecycle. Không retry liên tục vào executor đã đóng; cần stop producer/ingress, phối hợp graceful shutdown, hoặc chuyển giao công việc chưa xử lý sang hệ thống bền vững nếu nghiệp vụ yêu cầu.

## 4. Tình huống 3: `queueCapacity=0` và không còn worker nhận việc

`ThreadPoolTaskExecutor#setQueueCapacity(0)` dùng `SynchronousQueue`, một cơ chế **bàn giao trực tiếp** thay vì lưu task vào hàng chờ có sức chứa dương.

Ví dụ:

```java
executor.setCorePoolSize(1);
executor.setMaxPoolSize(3);
executor.setQueueCapacity(0);
```

Nếu ba worker đang thực thi các task chưa hoàn thành, task thứ tư **không có chỗ để chờ** và pool không thể mở rộng quá max: xảy ra rejection theo handler.

```text
queueCapacity = 0
Task A -> Worker 1 bận
Task B -> Worker 2 bận
Task C -> Worker 3 bận
Task D -> Không có worker nhận trực tiếp -> REJECT
```

Khi có worker đang rảnh và sẵn sàng nhận, task mới vẫn có thể được nhận. `queueCapacity=0` không có nghĩa executor không làm việc; nó định nghĩa **không tích lũy backlog trong queue**. Nếu max đặt quá lớn, burst traffic có thể tạo rất nhiều platform threads và gây áp lực bộ nhớ/CPU; cần giới hạn rõ ràng.

## 5. Tình huống 4: burst, việc chậm và starvation tạo áp lực dồn

Capacity nhìn có vẻ đủ ở điều kiện bình thường vẫn có thể bão hòa bởi:

- **Burst traffic:** hàng nghìn task đến trong thời gian ngắn.
- **Downstream chậm:** mọi worker chờ JDBC, HTTP, tệp hoặc lock thay vì xử lý xong.
- **Tác vụ chạy rất lâu hoặc kẹt vô hạn:** worker không quay lại queue để lấy task khác.
- **Một pool dùng chung cho nhiều loại tải:** tác vụ gửi email chậm chiếm hết worker của báo cáo cần SLA ngắn.
- **Task phụ thuộc nhau:** task A chiếm worker và chờ Future của task B, nhưng B lại nằm trong cùng queue của pool đã đầy. Có thể xảy ra starvation deadlock mà không cần rejection ngay từ đầu.
- **Quá nhiều lần retry không giới hạn:** vừa gặp lỗi đã submit lại vào chính pool đang quá tải, làm queue và tốc độ đến tăng thêm.

Ví dụ producer tạo 200 task/giây, hệ thống chỉ xử lý ổn định 100 task/giây. Nếu vẫn nhận tất cả, backlog tăng xấp xỉ 100 task/giây trong mô hình đơn giản hóa. Queue 1.000 task có thể che giấu vấn đề khoảng 10 giây trước khi đầy; độ trễ của task nằm cuối queue đã tăng đáng kể từ trước khi bắt đầu reject.

**Tín hiệu rejection là hậu quả của áp lực tải**, không nhất thiết nguyên nhân gốc. Cần xác định bottleneck: CPU quota, thread, lock, DB pool, network timeout, downstream quota hay thiết kế producer.

## 6. Tình huống không nên nhầm thành rejection

| Hiện tượng | Có phải executor rejection? | Giải thích |
| --- | --- | --- |
| Task đã chạy nhưng ném `IllegalStateException` | Không | Lỗi nghiệp vụ/execution; thường quan sát qua Future/callback |
| Caller gọi `Future.get(1, SECONDS)` rồi timeout | Không tự động | Caller chờ quá hạn; task có thể vẫn chạy |
| Task bị `cancel(true)` | Không tự động | Yêu cầu hủy/interruption khác với từ chối lúc submit |
| Thread pool rất chậm do queue dài | Chưa chắc | Queue có thể chưa đầy, task vẫn được nhận |
| Queue không giới hạn dẫn đến hết bộ nhớ | Không phải tình huống reject thông thường | Cạn bộ nhớ cần xử lý capacity và admission trước đó |
| Đặt `core > max` và bean không khởi tạo được | Không | Lỗi cấu hình khi tạo pool, không phải task rejection |
| Gọi `@Async` nội bộ qua `this.method()` | Không | Self-invocation thường bỏ qua Spring proxy; method có thể chạy trực tiếp |
| Task gửi sau `shutdown()`, default `AbortPolicy` ném | Có | Executor đã đóng, không nhận task mới |
| Pool max đã bận, queue đầy, default `AbortPolicy` ném | Có | Executor bão hòa |
| `CallerRunsPolicy` chạy task trên caller | Là xử lý overload | Handler chọn thực thi trên caller thay vì ném |

Một custom `ThreadFactory` không thể tạo worker cũng có thể làm executor không tiến triển đúng cách; đây là một trường hợp tài nguyên/cấu hình bất thường, không nên đánh đồng với quy tắc bão hòa chuẩn. Phân biệt `OutOfMemoryError`, timeout, interruption và rejection để tránh retry sai.

## 7. Chính sách xử lý khi từ chối

JDK cung cấp bốn `RejectedExecutionHandler` thường gặp. Spring `ThreadPoolTaskExecutor` có thể nhận handler thông qua `setRejectedExecutionHandler(...)`.

| Handler | Nếu pool không thể nhận task | Ý nghĩa/rủi ro |
| --- | --- | --- |
| `ThreadPoolExecutor.AbortPolicy` | Ném `RejectedExecutionException` (Spring adapter thường chuyển thành `TaskRejectedException`) | Caller thấy rõ quá tải, có cơ hội trả lỗi hoặc retry có kiểm soát |
| `ThreadPoolExecutor.CallerRunsPolicy` | Nếu chưa shutdown, **thread submit chạy task ngay** | Tạo backpressure, nhưng có thể chặn HTTP request thread hoặc scheduler thread |
| `ThreadPoolExecutor.DiscardPolicy` | Bỏ task không có thông báo | Chỉ hợp với tác vụ thực sự chấp nhận mất; nguy cơ mất việc âm thầm |
| `ThreadPoolExecutor.DiscardOldestPolicy` | Nếu chưa shutdown, bỏ task đầu queue rồi thử submit lại | Có thể làm rơi việc cũ, phá thứ tự; rất khó bảo đảm completion |

**Đặc biệt khi shutdown:** `CallerRunsPolicy` và `DiscardOldestPolicy` có thể **bỏ task** thay vì chạy lại hoặc ném lỗi. Không dùng policy này rồi mặc nhiên tin rằng mọi lời gọi không ném lỗi đã hoàn tất.

Với `DiscardPolicy` hoặc `DiscardOldestPolicy`, một `Future` do `submit(...)` trả về có thể không bao giờ chuyển sang trạng thái completed nếu task bị bỏ nhưng Future không được cancel. Khi đó `get()` không timeout có thể chờ mãi. Vì vậy **chỉ dùng các policy bỏ task khi thiết kế đã chấp nhận mất việc và hiểu cách thông báo completion/cancellation**.

### 7.1. Khi nào cân nhắc `CallerRunsPolicy`?

Nếu producer nhanh hơn consumer, chuyển task quá tải về caller khiến caller bị chặn và giảm tốc độ nạp task. Nó là cơ chế backpressure đơn giản:

```text
Caller submit -> pool còn chỗ -> trả về nhanh
Caller submit -> pool bão hòa -> CallerRunsPolicy chạy ngay trên caller
Caller bận chạy task -> chưa tiếp tục submit các task khác
```

Tuy nhiên, nếu caller là HTTP request thread, response có thể chậm bất ngờ và timeout. Nếu caller là thread lập lịch, lần trigger tiếp theo có thể bị trễ. Với xử lý cần latency thấp và quy tắc SLA rõ ràng, **AbortPolicy + phản hồi overload** thường dễ kiểm soát hơn.

### 7.2. Nên dùng policy nào?

Không có policy phù hợp mọi nghiệp vụ. Có thể bắt đầu bằng default **AbortPolicy** để không che giấu overload, sau đó chọn hành vi theo khả năng mất việc, độ ưu tiên, giới hạn nguồn lực và giao thức gọi. Hệ thống cần đảm bảo thực thi sau restart phải dùng **persistent queue/job store** chứ không chỉ đổi rejection policy.

## 8. Java 17+ runnable: tái hiện saturation, shutdown và CallerRuns

Ví dụ JDK thuần dùng `CountDownLatch` để **giữ task đang chạy**, tạo điều kiện bão hòa xác định. Không cần Spring và không dựa vào `Thread.sleep(...)` để đoán lịch CPU.

Lưu toàn bộ chương trình vào **RejectionCasesDemo.java**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class RejectionCasesDemo {
    private static ThreadPoolExecutor newPool(
            RejectedExecutionHandler handler) {
        return new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), handler);
    }

    private static Runnable heldTask(
            CountDownLatch started, CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor abort =
                newPool(new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> running =
                    abort.submit(heldTask(started, release));
            started.await();                 // Worker đang bận
            Future<?> queued = abort.submit(() -> {});

            try {
                abort.execute(() -> {});
                System.out.println("unexpected acceptance");
            } catch (RejectedExecutionException e) {
                System.out.println("rejected: saturated");
            }

            release.countDown();
            running.get();
            queued.get();
            System.out.println("accepted completed: 2");

            abort.shutdown();
            try {
                abort.execute(() -> {});
                System.out.println("unexpected after shutdown");
            } catch (RejectedExecutionException e) {
                System.out.println("rejected: shutdown");
            }
        } finally {
            release.countDown();
            abort.shutdownNow();
        }

        ThreadPoolExecutor caller =
                newPool(new ThreadPoolExecutor.CallerRunsPolicy());
        CountDownLatch started2 = new CountDownLatch(1);
        CountDownLatch release2 = new CountDownLatch(1);

        try {
            Future<?> running =
                    caller.submit(heldTask(started2, release2));
            started2.await();                // Worker đang bận
            Future<?> queued = caller.submit(() -> {});

            Thread submittingThread = Thread.currentThread();
            AtomicBoolean onCaller = new AtomicBoolean(false);
            caller.execute(() -> onCaller.set(
                    Thread.currentThread() == submittingThread));
            System.out.println("caller ran: " + onCaller.get());

            release2.countDown();
            running.get();
            queued.get();
        } finally {
            release2.countDown();
            caller.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RejectionCasesDemo.java
java RejectionCasesDemo
```

**Stdout xác định với chương trình chạy bình thường:**

```text
rejected: saturated
accepted completed: 2
rejected: shutdown
caller ran: true
```

**Vì sao kết quả này xác định?**

1. `abort` chỉ có **một worker** và **một vị trí queue**. `started.await()` bảo đảm worker đã bắt đầu `heldTask` và đang chờ `release`.
2. `queued` chiếm vị trí hàng chờ; task thứ ba không còn worker/queue nên `AbortPolicy` ném `RejectedExecutionException` **ngay lúc `execute`**.
3. Sau `release.countDown()`, worker xử lý hết hai task đã nhận. `Future.get()` đợi hoàn tất trước khi in dòng `accepted completed: 2`.
4. `abort.shutdown()` ngừng nhận task mới; lệnh `execute` tiếp theo bị từ chối dù không còn task đang chạy.
5. Với `caller`, worker đang bị giữ và queue đã đầy; `CallerRunsPolicy` chạy task thứ ba ngay trên **main thread đang submit**, nên `caller ran: true`.
6. `finally` luôn giải phóng latch và yêu cầu đóng pool để tránh treo tiến trình nếu có lỗi trước khi cleanup.

Ví dụ này minh họa chính xác cơ chế của **JDK `ThreadPoolExecutor`**. Spring `ThreadPoolTaskExecutor` dùng pool JDK bên dưới nhưng còn có lifecycle và loại exception theo hợp đồng Spring.

## 9. Spring Boot: bắt rejection tại điểm giao việc `@Async`

Trong Spring Framework 6.x, có thể tạo `ThreadPoolTaskExecutor` với queue hữu hạn và handler tường minh, rồi dùng `@Async("notificationExecutor")`. Ví dụ dưới đây dùng **Spring Boot 3.x, Java 17+**, dependency `spring-boot-starter-web` và một application class.

Đặt toàn bộ mã vào **src/main/java/com/example/demo/RejectionApplication.java**:

```java
package com.example.demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class RejectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(RejectionApplication.class, args);
    }

    @Bean("notificationExecutor")
    ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(2);
        executor.setThreadNamePrefix("notify-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}

@Service
class NotificationService {
    @Async("notificationExecutor")
    public CompletableFuture<String> sendAsync(String id) {
        try {
            Thread.sleep(500); // Chỉ giả lập blocking I/O
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task interrupted", e);
        }
        return CompletableFuture.completedFuture("sent:" + id);
    }
}

@RestController
class NotificationController {
    private final NotificationService service;

    NotificationController(NotificationService service) {
        this.service = service;
    }

    @PostMapping("/notifications/{id}")
    public ResponseEntity<String> submit(@PathVariable String id) {
        try {
            CompletableFuture<String> future = service.sendAsync(id);

            future.whenComplete((value, error) -> {
                if (error != null) {
                    System.err.println("Failed " + id + ": " + error);
                } else {
                    System.out.println(value);
                }
            });

            return ResponseEntity.accepted().body("accepted:" + id);
        } catch (TaskRejectedException rejected) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("executor overloaded");
        }
    }
}
```

Chạy bằng plugin Spring Boot trong dự án, ví dụ `./gradlew bootRun` (trên Windows: `gradlew.bat bootRun`), rồi thử:

```bash
curl -i -X POST http://localhost:8080/notifications/N1
```

**Trường hợp nhận việc thành công**, response có HTTP **202 Accepted**, body:

```text
accepted:N1
```

**Trường hợp executor ném `TaskRejectedException` tại lúc submit**, controller đáp HTTP **503 Service Unavailable** với body:

```text
executor overloaded
```

Kết quả nào xảy ra tùy tải, thứ tự thread và thời điểm submit. **Một request đơn lẻ khi pool rảnh thường được chấp nhận**, không có cách suy ra chắc chắn 503 chỉ từ ví dụ một lệnh `curl`. Để tái hiện rejection ổn định, cần dùng latch/load-test hoặc gửi đồng thời đủ task sao cho worker và queue đều bận; ví dụ JDK ở mục 8 là test xác định.

### 9.1. Những điểm quan trọng trong ví dụ Spring

- `@EnableAsync` bật xử lý async qua proxy; controller gọi **bean khác** là `NotificationService` nên method `@Async` đi qua proxy.
- `@Async("notificationExecutor")` chọn đúng bean pool, tránh vô tình dùng executor mặc định khác.
- `AbortPolicy` cho phép submit thất bại **có tín hiệu**; Spring adapter phát `TaskRejectedException` theo hợp đồng.
- Lỗi **tại submit** được bắt bởi `catch` quanh `service.sendAsync(id)`; lỗi **trong quá trình chạy** phải quan sát qua `future.whenComplete(...)` hoặc cơ chế Future khác. Đây là hai đường lỗi khác nhau.
- HTTP 202 ở ví dụ **chỉ xác nhận được giao cho executor trong bộ nhớ**. Nó **không cam kết đã gửi thông báo**, không có job status bền vững, không tự lưu sau crash. Trong nghiệp vụ thật cần job ID, lưu trạng thái, idempotency và cơ chế lấy kết quả/retry phù hợp.
- `Thread.sleep` ở đây là mô phỏng I/O blocking; worker bị chiếm khi chờ. `@Async` chuyển việc chờ sang pool, **không biến JDBC/HTTP blocking thành non-blocking I/O**.
- `this.sendAsync(...)` gọi từ chính service sẽ bỏ qua proxy theo chế độ proxy mặc định, nên không nên dùng để kiểm thử hành vi rejection của `@Async`.

### 9.2. Thực thi trực tiếp bằng `TaskExecutor`

Nếu không dùng `@Async`, có thể inject bean `ThreadPoolTaskExecutor` hoặc `TaskExecutor` và submit trực tiếp. Fragment:

```java
try {
    notificationExecutor.execute(task);
} catch (TaskRejectedException ex) {
    // Chỉ xử lý việc CHƯA được executor nhận.
    // Ví dụ: ghi metric rejection và phản hồi overload.
}
```

Đây là fragment, không phải Java class độc lập: `notificationExecutor` và `task` phải được inject/tạo trước. Với một execution path chỉ sử dụng JDK `ThreadPoolExecutor`, loại exception thường là `RejectedExecutionException`; với Spring `TaskExecutor` nên xét `TaskRejectedException`.

Không ép mọi exception vào một `catch (Exception e)` rồi retry: exception nghiệp vụ, timeout và rejection có căn nguyên khác nhau.

## 10. Dấu hiệu vận hành và cách chẩn đoán

Khi có `TaskRejectedException`, hãy kiểm tra **đúng executor được chọn**, vì ứng dụng thường có nhiều pool cho notification, report, scheduler hoặc request handling. Các getter hữu ích của `ThreadPoolTaskExecutor`:

| Thông tin | Câu hỏi chẩn đoán |
| --- | --- |
| `getCorePoolSize()` | Core cấu hình là bao nhiêu? |
| `getMaxPoolSize()` | Có giới hạn max rõ ràng không? |
| `getPoolSize()` | Pool đã tăng tới bao nhiêu worker? |
| `getActiveCount()` | Bao nhiêu worker đang bận? |
| `getThreadPoolExecutor().getQueue().size()` | Có bao nhiêu task đang chờ? |
| Queue remaining capacity | Hàng đợi còn chỗ không? |
| `getThreadPoolExecutor().isShutdown()` | Executor đã bắt đầu shutdown chưa? |
| Rejection count | Bao nhiêu lần submit thất bại? |
| Queue wait / task duration | Task chậm do xếp hàng hay do xử lý? |

Các getter về pool/queue là **snapshot**, có thể thay đổi ngay sau mỗi lần đọc. Không đưa quyết định nghiệp vụ “có chỗ, chắc chắn nhận được” chỉ vì vừa thấy queue chưa đầy; giữa lúc kiểm tra và submit có thể có thêm task hoặc shutdown.

### Phân tích theo triệu chứng

| Quan sát | Nguyên nhân cần kiểm tra |
| --- | --- |
| Active gần max, queue đầy, reject tăng | Capacity saturation; workload chậm; burst |
| CPU thấp, active cao, queue lớn | Worker chờ DB/HTTP/lock, cần kiểm tra downstream |
| CPU cao, active cao, throughput giảm | CPU contention, quá nhiều worker, task CPU-bound |
| Reject đột ngột đúng lúc deploy/shutdown | Producer vẫn submit vào executor đang đóng |
| Không thấy reject nhưng queue wait tăng mãi | Queue quá lớn hoặc chính sách discard đang che mất việc |
| Request đột ngột mất nhiều giây, không exception | Có thể `CallerRunsPolicy` đang chạy task trên caller |
| Future chờ mãi nhưng không có worker làm | Có thể task bị discard hoặc starvation; xem policy và queue |

Khi có Micrometer/Actuator, nên ghi metric về active worker, queue depth, task accepted/completed/failed/rejected, thời gian chờ queue và thời gian chạy. Bổ sung correlation ID và tên executor để phân biệt tải; chỉ có log “thread pool full” thường chưa đủ để tìm nguyên nhân.

## 11. Ứng xử đúng khi task bị từ chối

### 11.1. Không retry vô hạn ngay trong caller

Giả sử queue đã đầy vì downstream chậm. Nếu 100 request cùng retry không giới hạn liên tục, chúng tiếp tục tranh chấp CPU, RAM và khiến hệ thống khó phục hồi.

Chiến lược tốt hơn tùy mục tiêu:

1. **Giới hạn đầu vào:** rate limit, bulkhead/semaphore, quota theo người dùng/loại việc hoặc giảm số producer.
2. **Báo lỗi có nghĩa:** API có thể trả HTTP 503 khi hạ tầng tạm quá tải; HTTP 429 khi chính sách giới hạn tốc độ của client bị vượt. Cân nhắc `Retry-After` khi có lịch retry xác định.
3. **Retry có giới hạn:** exponential backoff, jitter, timeout tổng và giới hạn số lần; không retry nếu operation không idempotent và chưa có cơ chế chống trùng.
4. **Giữ job quan trọng bền vững:** ghi vào database/job store hoặc message broker có ack và cơ chế xử lý lại; worker pool chỉ là một consumer.
5. **Tách nhóm công việc:** dùng pool riêng cho tải ưu tiên cao và tải chậm để tránh starvation.
6. **Giảm kích thước/batch load:** nếu 1.000 task rất nhỏ tạo overhead quá cao, có thể gom batch khi nghiệp vụ cho phép.

**Retry không tự tăng capacity.** Nếu dependency đang chết hoặc pool đã shutdown, retry liên tục vào cùng nơi không cải thiện khả năng xử lý.

### 11.2. Phải định nghĩa ý nghĩa “accepted” theo hợp đồng API

Một endpoint trả 202 ngay sau khi executor nhận task chỉ biết **đã giao vào pool trong RAM**. Nếu process crash trước khi worker chạy, tác vụ có thể mất. Với tác vụ quan trọng, cần quyết định:

- Chỉ cần **best effort**: có thể chấp nhận rơi task khi quá tải, nhưng phải ghi metric và hiển thị trạng thái.
- Cần **at least once**: đưa job vào nguồn lưu bền vững trước khi xác nhận, consumer ack sau khi xử lý, và hỗ trợ retry.
- Cần **không gây tác động trùng**: dùng idempotency key, deduplication hoặc transaction/outbox phù hợp. “Exactly once” end-to-end không tự có chỉ vì dùng executor.
- Cần **hoàn thành trong thời hạn**: admission control và deadline rõ ràng; queue dài có thể khiến task hết hạn trước khi bắt đầu.

### 11.3. Đừng quên request đã được nhận nhưng chưa chạy

Cấu hình graceful shutdown có thể cho task đang chạy và task trong queue hoàn tất khi context đóng có trật tự. Tuy nhiên timeout shutdown, kill signal hoặc crash vẫn có thể làm mất in-memory tasks. Vì vậy cần đánh giá cả **accepted-but-pending** và **rejected-before-acceptance** thay vì chỉ đếm các exception lúc submit.

## 12. Spring @Scheduled, @Async và vòng đời liên quan

Một method `@Scheduled` có thể gửi việc vào `@Async` executor:

```java
@Scheduled(fixedDelay = 5_000)
public void scheduleBatch() {
    notificationService.sendAsync("daily");
}
```

Đây là fragment và giả định `notificationService` là **bean khác** được inject. Khi scheduler kích hoạt đúng lúc executor đã đầy, method `sendAsync(...)` có thể bị từ chối. Nếu không bắt và quan sát rejection, lần kích hoạt này có thể **không gửi được việc**. Nếu dùng `CallerRunsPolicy`, thread scheduler có thể tự xử lý task và làm chậm các lượt lịch khác.

Quan trọng:

- **Scheduler quyết định khi nào kích hoạt**, executor quyết định task được xử lý trên worker/queue nào.
- `fixedDelay` tính độ trễ sau khi **method scheduled kết thúc**, không tự đợi background task `@Async` hoàn tất nếu method chỉ submit rồi return.
- Khi shutdown, scheduler có thể còn trigger trong lúc executor đã bắt đầu đóng nếu lifecycle không phối hợp; cần tránh producer tiếp tục gửi việc vào pool đã dừng.
- Nếu job phải chạy đúng một lần trên nhiều replica, `@Scheduled` và `ThreadPoolTaskExecutor` riêng lẻ **không cung cấp bảo đảm phân tán**. Phải dùng cơ chế coordination riêng.

Không xử lý overload bằng cách tăng `maxPoolSize` tới vô hạn: giảm rejection trước mắt có thể gây cạn thread hoặc làm hệ thống downstream sập nhanh hơn.

## 13. Những lỗi phổ biến

**Lỗi 1 — Nghĩ một task không ném exception tức là đã chạy xong.** Lời gọi `execute` thành công chỉ là accepted. Task có thể đang đợi queue, còn chạy hoặc lỗi sau đó.

**Lỗi 2 — Chỉ cấu hình `maxPoolSize` mà không để ý queue.** `ThreadPoolExecutor` ưu tiên queue sau khi đủ core; max lớn không tự tăng worker nếu queue chưa đầy.

**Lỗi 3 — Dùng queue không giới hạn để “tránh từ chối”.** Điều này chuyển áp lực sang RAM và queue wait; có thể OOM, không phải khả năng xử lý vô hạn.

**Lỗi 4 — Nhầm lỗi nghiệp vụ với TaskRejectedException.** Exception từ code task sau khi chạy cần xử lý qua Future/callback; không retry chỉ vì một exception chung chung.

**Lỗi 5 — Dùng `DiscardPolicy` cho công việc phải hoàn thành.** Task có thể mất âm thầm. Một Future có thể chờ mãi nếu task bị loại mà không được cancel.

**Lỗi 6 — Dùng `CallerRunsPolicy` mà không chấp nhận caller chậm.** Khi overload, HTTP/scheduler thread có thể bị giữ lại; phía client thấy latency tăng đột ngột.

**Lỗi 7 — Retry ngay không giới hạn vào pool đã đầy.** Gây retry storm và khiến backlog trầm trọng hơn.

**Lỗi 8 — Chạy tác vụ blocking trên ít worker nhưng chỉ nhìn CPU.** CPU thấp không có nghĩa pool còn năng lực; worker có thể đang chờ I/O.

**Lỗi 9 — Submit trong `@PreDestroy` sau khi executor đóng.** Không phối hợp lifecycle làm task bị từ chối đúng lúc shutdown.

**Lỗi 10 — Thấy `@Async` nên mặc định mọi self-invocation cũng chạy nền.** `this.method()` thường bỏ qua proxy. Không thể dựa vào test self-invocation để đánh giá executor.

**Lỗi 11 — Bắt rejection xong trả 202 “đã nhận”.** Khi `AbortPolicy` từ chối, phải phản ánh trạng thái thất bại hoặc lưu việc vào cơ chế khác trước khi xác nhận.

**Lỗi 12 — Coi rejection policy là giải pháp bền vững dữ liệu.** Mọi policy xử lý overload chỉ nằm ở đường submit trong tiến trình. Muốn khôi phục sau crash cần lưu trạng thái/persistent queue.

## 14. Checklist xử lý sự cố ngoài thực tế

Khi phát hiện executor từ chối tác vụ, có thể đi theo trình tự:

1. **Xác định đúng executor và thời điểm:** tên pool, tên task, caller, shutdown hay runtime bình thường.
2. **Đọc cấu hình thực tế:** `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection handler, thời gian shutdown.
3. **Đo trạng thái:** active/pool size, queue depth/remaining capacity, queue wait, task run time, số lần reject.
4. **Xác định bottleneck:** CPU, DB connection pool, HTTP timeout, lock, I/O, burst traffic hoặc starvation.
5. **Phân loại tác động:** task chưa nhận, task đang chờ, task bị lỗi sau khi nhận, task có thể mất sau restart.
6. **Áp chính sách theo nghiệp vụ:** 503/429 khi phù hợp, retry có backoff và idempotency, rate limit, admission control hoặc job store bền vững.
7. **Kiểm tra tình huống shutdown:** không còn producer submit khi pool đóng, có thời hạn graceful shutdown và phương án khôi phục.
8. **Load test lại:** dùng latch/benchmark có kiểm soát để tái hiện saturation, xác nhận số task được chấp nhận, bị từ chối và hoàn tất.

Không dùng vài lần chạy `Thread.sleep(...)` rồi suy ra chắc chắn queue đầy; lịch chạy thread không cố định. Khi cần minh chứng, hãy giữ worker bằng `CountDownLatch` để đảm bảo điều kiện saturation như ví dụ Java ở trên.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Pool có core=2, max=4, queue=2. Sáu task đã nhận và chưa task nào hoàn thành. Task thứ bảy có chắc được nhận không?

**Đáp án:** Trong điều kiện cả bốn worker đang bận, queue chứa đủ hai task và không worker rảnh, task thứ bảy **không có capacity** nên đi vào rejection handler. Handler có thể ném, chạy ở caller hoặc bỏ task tùy cấu hình.

**Câu 2.** Vì sao `maxPoolSize=100` không giúp tăng worker nếu `queueCapacity` cực lớn?

**Đáp án:** Sau khi đạt core, executor ưu tiên đưa task vào queue; nó chỉ tăng worker vượt core khi queue không còn nhận được task.

**Câu 3.** Task mới gửi sau `shutdown()` có được tự động chờ để chạy sau khi restart không?

**Đáp án:** Không. Executor đã shutdown không nhận task mới theo cơ chế thông thường. Không có persistence/restart queue tự động.

**Câu 4.** `CallerRunsPolicy` có ném `RejectedExecutionException` khi pool bão hòa không?

**Đáp án:** Thường nó chạy task trên chính caller nếu executor chưa shutdown. Caller có thể bị chặn và đó là backpressure. Nếu executor đã shutdown, policy có thể bỏ task.

**Câu 5.** Một task được submit thành công nhưng ném exception sau 2 giây. Đây có phải rejection không?

**Đáp án:** Không. Task đã được nhận rồi **failed during execution**; cần quan sát `Future`/`CompletableFuture` hoặc handler của kiểu task tương ứng.

**Câu 6.** Có thể giải quyết overload chỉ bằng retry ngay trong vòng lặp vô hạn không?

**Đáp án:** Không. Retry storm tăng tải. Cần backoff, giới hạn, jitter, idempotency và admission control hoặc queue bền vững khi nghiệp vụ cần.

**Câu 7.** `queueCapacity=0` có nghĩa executor luôn từ chối?

**Đáp án:** Không. Nó dùng handoff trực tiếp; task được nhận khi worker có thể nhận hoặc pool còn mở rộng được. Khi max workers đều bận thì mới đi vào handler.

**Câu 8.** Vì sao HTTP 202 ngay sau `@Async` submit không chắc công việc sẽ hoàn thành?

**Đáp án:** Nó chỉ phản ánh việc giao thành công vào executor trong bộ nhớ; task có thể lỗi sau đó, bị ngắt hoặc mất khi process crash. Cần persistent job tracking nếu muốn cam kết thực thi.

## Tài liệu tham khảo

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework Javadoc — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Javadoc — TaskRejectedException: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskRejectedException.html
- Java SE 17 API — ThreadPoolExecutor, phần Rejected Tasks: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 API — RejectedExecutionHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html
