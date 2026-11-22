# scheduleAtFixedRate() và lịch theo chu kỳ trong Spring TaskScheduler

Một hệ thống Spring thường cần thực hiện công việc lặp lại: quét đơn hàng quá hạn mỗi 10 giây, làm mới cache mỗi phút, đọc hàng đợi định kỳ hoặc ghi chỉ số sức khỏe của một dịch vụ. Với API `org.springframework.scheduling.TaskScheduler`, phương thức **`scheduleAtFixedRate()`** cho phép lên lịch một `Runnable` lặp lại theo **chu kỳ cố định (fixed rate)**.

Điểm cốt lõi: **fixed rate gắn các mốc thực thi dự kiến với thời điểm bắt đầu và độ dài chu kỳ, không phải đợi công việc trước hoàn tất rồi mới đếm chu kỳ tiếp theo**. Tuy nhiên, “lên lịch mỗi 5 giây” **không có nghĩa chắc chắn thực thi đúng mỗi 5 giây**, không có bảo đảm thời gian thực (real-time), không tự đảm bảo job thành công, không tự tạo giao dịch hoặc bảo đảm chỉ chạy một lần trên toàn cụm máy.

Bài học này nằm trong nhóm **TaskScheduler** của module **Spring Framework – concurrency**. Mục tiêu là sử dụng đúng API, hiểu mô hình thực thi, xử lý tác vụ chạy lâu, lựa chọn so với fixed delay/cron, quản lý `ScheduledFuture` và áp dụng an toàn trong Spring Boot.

## 1. TaskScheduler là gì và khác TaskExecutor thế nào?

`TaskExecutor` tập trung vào **giao việc để thực thi**; `TaskScheduler` tập trung vào **quyết định lúc nào một việc được thực thi**, gồm chạy một lần tại thời điểm hẹn hoặc chạy lặp theo quy luật.

```text
TaskExecutor
  caller --execute(task)--> worker/queue --> run một task

TaskScheduler
  caller --scheduleAtFixedRate(task, period)-->
       bộ lập lịch giữ lịch trong bộ nhớ
       |   |   |   |   |
       v   v   v   v   v
     run run run run run ... cho đến khi hủy/đóng
```

Trong Spring, `ThreadPoolTaskScheduler` là một implementation phổ biến của `TaskScheduler`. Nó sử dụng `ScheduledExecutorService` của JDK phía dưới và thêm quản lý bean/lifecycle và khả năng tích hợp với trigger của Spring. Thread thực thi `Runnable` định kỳ **thường chính là scheduler worker**, không phải tự động được chuyển qua một `ThreadPoolTaskExecutor` khác.

Do đó:

- Nếu task rất ngắn, pool scheduler nhỏ có thể đủ.
- Nếu task chặn I/O lâu hoặc xử lý CPU nặng, scheduler worker sẽ bị chiếm; các lịch khác có thể bị trễ.
- Nếu task chỉ submit tiếp sang executor khác, thời gian task scheduler “hoàn tất” là **thời gian giao việc**, không nhất thiết là lúc nghiệp vụ ở executor kia hoàn thành.
- `TaskScheduler` không phải một job queue bền vững hoặc distributed coordinator; mỗi ứng dụng/replica có thể có lịch của riêng nó.

### Các phương thức chính trong Spring Framework 6.x

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
ScheduledFuture<?> schedule(Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
```

Đây là **trích dạng chữ ký API để học**, không phải chương trình Java độc lập. Trong Spring 6.x, ưu tiên `Instant` và `Duration`; các overload kiểu `Date`/`long` tồn tại nhằm tương thích và nhiều overload đã bị deprecated từ Spring 6.0.

Nguồn: Javadoc chính thức của `TaskScheduler`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/TaskScheduler.html

## 2. “Fixed rate” chính xác có nghĩa gì?

Với chu kỳ `P` và mốc bắt đầu `T0`, những thời điểm **đủ điều kiện để chạy theo kế hoạch** có dạng:

```text
T0, T0 + P, T0 + 2P, T0 + 3P, ...
```

Ví dụ bắt đầu gần 10:00:00, `period = 5 giây`:

```text
Thời gian      00     05     10     15     20     25  (giây)
Mốc dự kiến    |------|------|------|------|------|
Thực thi ngắn  [job]  [job]  [job]  [job]  [job]
```

Nếu mỗi lần chạy mất khoảng 1 giây và scheduler có đủ tài nguyên, các lượt thường được bắt đầu gần mốc 0, 5, 10, 15 giây. **“Gần”** rất quan trọng: thread scheduler phải chịu GC pauses, CPU scheduling, contention, quota container và tác vụ khác.

**Fixed rate là cách xác định mốc lịch, không phải cam kết chính xác đến millisecond.**

### 2.1. Khi task chạy lâu hơn period

Giả sử chu kỳ là 5 giây nhưng một lượt mất 8 giây:

```text
Mốc dự kiến:  0s      5s      10s     15s     20s
             |-------|-------|-------|-------|
Thực tế:     [Run 1 ---------]
                              [Run 2 ----------]
                                               [Run 3 ...]
```

Mốc tiếp theo đã đến trong khi lượt trước chưa xong. Với `ThreadPoolTaskScheduler` dựa trên `ScheduledThreadPoolExecutor`, **các lần chạy kế tiếp của cùng một tác vụ định kỳ không chồng lấp nhau**: lượt sau **bắt đầu muộn** và có thể được lên chạy sớm ngay sau lượt trước hoàn tất để bắt kịp tiến độ. Điều này **không có nghĩa** scheduler tạo ra một bản sao task chạy song song chỉ vì pool có nhiều thread.

Có vài giới hạn cần ghi nhớ:

- Scheduler không tạo “thời gian bị mất” thành một danh sách giao dịch durable; shutdown/crash có thể làm bỏ lỡ các lượt.
- Không bảo đảm tại một thời điểm tải nặng hệ thống sẽ hoàn thành đúng số lần bằng công thức thời gian lý tưởng.
- Nếu nhiều **tác vụ định kỳ khác nhau** dùng cùng pool, chúng có thể song song khi `poolSize > 1`.
- Nếu một lượt **chỉ submit việc sang pool khác rồi return**, các công việc thực tế được giao **có thể chồng lấp**, dù chính invocation của Runnable định kỳ không chồng lấp.
- Nếu có nhiều bản sao ứng dụng, mỗi bản sao có thể chạy **một lịch riêng**, tạo concurrency liên máy.

### 2.2. Khi task nhẹ hơn period

Nếu task chạy 1 giây, chu kỳ 5 giây:

```text
0s         5s         10s        15s
[job]      [job]      [job]      [job]
|--1s      |--1s      |--1s      |--1s
```

Khoảng rảnh giữa lần 1 hoàn tất và lần 2 bắt đầu xấp xỉ **4 giây**. Đó là hành vi đặc trưng phân biệt fixed rate với fixed delay.

### 2.3. Đừng hiểu fixed rate như một timer “chính xác tuyệt đối”

Một process đang stop-the-world GC, CPU thiếu quota hoặc machine bị suspend có thể khiến lịch trễ đáng kể. Lập lịch periodic của JDK không bảo đảm real-time; nếu tác vụ dùng để tính tiền, chốt sổ hoặc trigger phải chính xác theo lịch nghiệp vụ, cần thiết kế **theo mốc và dữ liệu nghiệp vụ**, không suy luận kết quả từ số lần callback được gọi.

## 3. Hai overload scheduleAtFixedRate() nên dùng

### 3.1. Bắt đầu sớm nhất có thể

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::refreshCache,
        Duration.ofSeconds(5));
```

Đây là **fragment**, giả định `scheduler` là một bean `TaskScheduler` và `refreshCache` là method `void refreshCache()` không tham số. Nó tạo một lịch có **chu kỳ 5 giây**, lượt đầu được đăng ký để chạy **sớm nhất có thể**, không mặc nhiên chờ đủ 5 giây trước lượt đầu.

Nếu muốn **trễ 5 giây trước lượt đầu**, dùng overload có `Instant startTime`:

```java
Instant firstRun = Instant.now().plusSeconds(5);

ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::refreshCache,
        firstRun,
        Duration.ofSeconds(5));
```

Nhớ import `java.time.Instant`, `java.time.Duration` và `java.util.concurrent.ScheduledFuture`. `Instant` là một mốc thời gian tuyệt đối cho **lần chạy đầu**, còn `Duration` là khoảng cách fixed rate cho các lần tiếp theo.

### 3.2. Lịch theo mốc bắt đầu cụ thể

```java
Instant startsAt = Instant.parse("2030-01-01T00:00:00Z");

ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::reconcile,
        startsAt,
        Duration.ofMinutes(10));
```

Đây là một fragment minh họa với thời điểm UTC cụ thể. Chạy định kỳ mỗi 10 phút từ mốc đầu **không giống** “chạy vào phút 00, 10, 20, ... của mọi giờ theo múi giờ doanh nghiệp” nếu mốc khởi động/độ lệch không phù hợp. Nếu cần lịch theo **ngày, thứ, tháng, ngày lễ hoặc giờ địa phương**, cân nhắc `CronTrigger` hoặc hệ thống scheduler dành cho lịch nghiệp vụ.

### 3.3. Period hợp lệ

Chu kỳ phải là **Duration dương**. Đừng truyền `Duration.ZERO` hoặc giá trị âm để nói “chạy càng nhanh càng tốt”: dưới `ScheduledExecutorService.scheduleAtFixedRate`, period không dương không hợp lệ. Nếu muốn xử lý liên tục theo tốc độ tài nguyên, dùng consumer/worker loop có backpressure, thay vì biến scheduler thành busy spin.

### 3.4. ScheduledFuture dùng để làm gì?

`scheduleAtFixedRate` trả `ScheduledFuture<?>`:

- `cancel(false)`: hủy **các lượt định kỳ sau**, không yêu cầu interrupt lượt đang chạy.
- `cancel(true)`: có thể phát interrupt cho lượt đang chạy tùy implementation; dừng là best-effort.
- `isCancelled()`: biết trạng thái cancellation của Future.
- `isDone()`: với periodic schedule đang chạy bình thường, thường vẫn false; trở thành true nếu canceled hoặc chấm dứt bất thường.
- `get()`: **không dùng để “đợi một lần tick hoàn thành”**. Với periodic future của JDK, `get()` không trả về bình thường trong lúc lịch còn hoạt động; nó sẽ chờ tới khi lịch bị cancel/hoàn tất bất thường rồi có thể ném exception. Để quan sát từng lần chạy, dùng metric, trạng thái job hoặc một future riêng cho mỗi lần tick.

Nếu không giữ `ScheduledFuture` và không có reference tới scheduler, bạn có thể khó hủy một job cụ thể khi cấu hình thay đổi. Với một bean lifecycle, nên lưu handle trong field an toàn và cancel khi dừng.

## 4. Fixed rate, fixed delay, cron và @Scheduled khác nhau thế nào?

| Mô hình | Mốc chạy tiếp theo | Thích hợp với |
| --- | --- | --- |
| `scheduleAtFixedRate(task, period)` | Theo mốc `start + n × period`; có thể bị trễ khi task chạy lâu | Polling theo cadence, cập nhật cache, đo metric |
| `scheduleWithFixedDelay(task, delay)` | **Sau khi lượt trước hoàn tất + delay** | Tránh dồn nhịp, task phụ thuộc vào thời gian nghỉ giữa các lượt |
| `schedule(task, Instant)` | Một lần ở hoặc sau mốc thời gian chỉ định | Chạy một lần trong tương lai |
| `schedule(task, CronTrigger)` | Dựa trên lịch cron/trigger | Chạy lúc 08:00 ngày làm việc, lịch theo giờ/ngày |
| `@Scheduled(fixedRate = ...)` | Spring đăng ký một lịch fixed-rate cho annotated method | Lịch cố định biết từ cấu hình |
| `@Scheduled(fixedDelay = ...)` | Spring đăng ký một lịch fixed-delay | Chờ hoàn tất rồi nghỉ |
| `@Scheduled(cron = ...)` | Spring dùng cron trigger | Lịch theo calendar |

### Ví dụ so sánh bằng con số

Giả sử task mất **3 giây**, chu kỳ hoặc độ trễ cấu hình đều là **5 giây**, bắt đầu ở mốc 0.

**Fixed rate:**

```text
Lượt 1: start 0s, end 3s
Lượt 2: start gần 5s, end gần 8s
Lượt 3: start gần 10s, end gần 13s
```

**Fixed delay:**

```text
Lượt 1: start 0s, end 3s
Lượt 2: start gần 8s  (3 + 5), end gần 11s
Lượt 3: start gần 16s (11 + 5), end gần 19s
```

Các thời điểm trên là **mô hình minh họa không có tài nguyên tranh chấp**, không phải log chính xác từ một JVM thật.

### Lựa chọn thực dụng

- **Fixed rate:** muốn hệ thống cố kiểm tra/đo/đồng bộ với cadence đều, miễn là chấp nhận có thể trễ và cần xử lý quá tải.
- **Fixed delay:** muốn chắc chắn có một khoảng nghỉ sau mỗi lượt đã hoàn tất, tránh gửi tiếp quá sát nếu downstream chậm.
- **Cron:** muốn dựa vào đồng hồ kinh doanh, ví dụ 02:00 mỗi ngày hoặc thứ Hai, có chính sách timezone/DST rõ ràng.

Đừng chỉ đổi `fixedRate` sang `fixedDelay` để giải quyết mọi lỗi: nếu logic xử lý còn trùng lặp qua nhiều replica, chạy chồng lấp do async delegation hoặc không idempotent, đổi nhịp **không sửa được những nguyên nhân đó**.

## 5. @Scheduled là cách khai báo, TaskScheduler là API lập lịch chủ động

Trong Spring, có hai kiểu tổ chức thông dụng.

**Khai báo trực tiếp:**

```java
@Configuration
@EnableScheduling
class SchedulingConfig {}

@Component
class CacheRefreshJob {
    @Scheduled(fixedRate = 5, timeUnit = TimeUnit.SECONDS)
    public void refresh() {
        // Một lượt xử lý.
    }
}
```

Đây là **fragment**; cần imports `@Configuration`, `@EnableScheduling`, `@Component`, `@Scheduled` và `TimeUnit`. Với lịch khai báo như trên, Spring nhận diện method và đăng ký scheduling dựa trên metadata. Với method đồng bộ thông thường, return type nên là `void` và không nhận tham số.

**Lập lịch chủ động qua bean:**

```java
ScheduledFuture<?> handle = taskScheduler.scheduleAtFixedRate(
        () -> refreshCache(),
        Duration.ofSeconds(5));
```

Đây là fragment: code tự chọn **khi nào bắt đầu đăng ký**, chu kỳ bao lâu, và có handle để hủy cụ thể. Hữu ích khi cấu hình đến từ DB/feature flag hoặc cần start/stop linh hoạt.

### 5.1. Có cần @EnableScheduling để dùng scheduleAtFixedRate trực tiếp không?

**Không bắt buộc.** Nếu application đã có một bean `TaskScheduler` hợp lệ và code trực tiếp gọi `scheduleAtFixedRate(...)`, thao tác đăng ký lịch diễn ra thông qua API; không cần annotation processor của `@Scheduled` để làm việc đó.

`@EnableScheduling` cần khi bạn muốn Spring **phát hiện và đăng ký các method `@Scheduled`** tự động. Không bật cả hai cách cho **cùng một công việc** mà không có chủ đích, vì rất dễ tạo hai lịch độc lập và chạy trùng.

### 5.2. Tìm hiểu initial delay của @Scheduled

```java
@Scheduled(
        initialDelay = 2,
        fixedRate = 5,
        timeUnit = TimeUnit.SECONDS)
public void tick() {
    // Lượt đầu sau khoảng 2 giây, rồi cadence 5 giây.
}
```

Đây là fragment, được Spring hỗ trợ trong những phiên bản có thuộc tính `timeUnit`. Nó tương đương về **ý tưởng** với việc chỉ định một `Instant` cho lượt đầu, nhưng không cho bạn cùng quyền chủ động giữ `ScheduledFuture` trong method đang annotate.

`@Scheduled` cũng hỗ trợ các thuộc tính cấu hình chuỗi/placeholder (tùy version) và cron; nên chọn theo nhu cầu deploy, timezone và khả năng cần thay đổi schedule runtime.

## 6. ThreadPoolTaskScheduler và cách các worker được sử dụng

`ThreadPoolTaskScheduler` quản lý `ScheduledExecutorService` phía dưới. Đối với implementation này, cần hiểu sự khác nhau với `ThreadPoolTaskExecutor`:

| Thuộc tính | ThreadPoolTaskScheduler | ThreadPoolTaskExecutor |
| --- | --- | --- |
| Mục tiêu | Lập lịch theo thời gian/trigger | Giao công việc thực thi |
| Tham số chính | `poolSize`, error handler, shutdown, scheduler policies | `corePoolSize`, `maxPoolSize`, `queueCapacity` |
| Work chạy ở đâu? | Thường trên scheduler worker theo lịch | Worker của task executor |
| Nếu task giữ worker quá lâu | Các lịch khác có thể bị trễ | Queue/task khác có thể đợi hoặc bị từ chối |
| Future của periodic job | Đại diện **chuỗi lần chạy**, hủy lịch | Future thường đại diện **một task** |
| Chịu trách nhiệm persistence? | Không | Không |

### 6.1. Pool size có nghĩa gì?

```java
@Bean("billingScheduler")
ThreadPoolTaskScheduler billingScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("billing-schedule-");
    return scheduler;
}
```

Đây là fragment cho một Spring configuration class. Pool size 2 nghĩa là scheduler có khả năng chạy các công việc được kích hoạt **đồng thời trên hai worker**. Nhưng **không** có nghĩa một *đăng ký fixed-rate riêng lẻ* sẽ tự chồng hai lượt thực thi lên nhau nếu xử lý trễ. Một scheduler pool thường hỗ trợ nhiều lịch khác nhau, ví dụ quét hóa đơn và làm mới cache.

`ThreadPoolTaskScheduler` sử dụng kiểu scheduled executor có hàng chờ trì hoãn; không đánh đồng với queue hữu hạn `queueCapacity` của `ThreadPoolTaskExecutor`. Tạo hàng chục nghìn lịch sống lâu có thể tiêu tốn bộ nhớ/khó quản lý, dù vài lịch ít hoạt động không bão hòa CPU.

### 6.2. ThreadPoolTaskScheduler chạy việc trên scheduler threads

Nếu một `Runnable` fixed-rate gọi HTTP client blocking trong 10 giây, nó có thể giữ scheduler worker cả 10 giây. Khi pool nhỏ, lịch khác phải chờ.

Có thể tách lịch và xử lý:

```java
scheduler.scheduleAtFixedRate(
        () -> workExecutor.execute(this::processBatch),
        Duration.ofSeconds(5));
```

Nhưng lúc này **một “tick” chỉ giao việc**. Các batch trong `workExecutor` có thể chồng lấp dù scheduler wrapper chạy rất nhanh. Hãy định nghĩa giới hạn overlap và backpressure rõ ràng:

- Từ chối submit khi batch trước chưa xong hoặc dùng state machine/lease.
- Giới hạn queue và thread count của worker executor.
- Nếu cần bảo đảm không rơi job, ghi yêu cầu vào database/broker bền vững.
- Không coi sự thành công của `execute` là kết quả hoàn tất nghiệp vụ.
- Không mặc định mọi task được chạy đúng chu kỳ nếu worker pool đã đầy.

### 6.3. Không có thời gian thực và không có cluster leader tự động

Mỗi instance Spring chạy bean scheduler riêng. Nếu scale từ 1 lên 3 replica, một `@Scheduled(fixedRate=5000)` hoặc cùng lệnh đăng ký trên mỗi replica thường dẫn đến **ba lịch**; task có thể chạy ba lần tại những mốc gần nhau.

Muốn chỉ một instance thực hiện việc toàn cục, cần một cơ chế leader election, distributed lock/lease, coordinator/job store hoặc lựa chọn nền tảng scheduler thích hợp. Phải tính race giữa các replica, lease hết hạn trong khi worker chưa xong và idempotency khi retry.

## 7. Java 17 runnable: fixed-rate không chồng lấp một periodic task

Để chứng minh không dựa vào may rủi timing, demo sử dụng một `ScheduledThreadPoolExecutor` có **hai worker**, nhưng chỉ **một lịch recurring**. Task thứ ba cố ý chờ latch, main thread hủy lượt lặp tiếp theo rồi giải phóng latch. Ta đo số lượt và mức concurrency tối đa.

Lưu thành **FixedRateDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedRateDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(2);
        pool.setRemoveOnCancelPolicy(true);

        AtomicInteger runs = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxActive = new AtomicInteger();
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch releaseThird = new CountDownLatch(1);

        try {
            ScheduledFuture<?> schedule = pool.scheduleAtFixedRate(() -> {
                int concurrentlyRunning = active.incrementAndGet();
                maxActive.updateAndGet(
                        previous -> Math.max(previous, concurrentlyRunning));

                try {
                    int number = runs.incrementAndGet();
                    if (number == 3) {
                        thirdStarted.countDown();
                        try {
                            releaseThird.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                        }
                    }
                } finally {
                    active.decrementAndGet();
                }
            }, 0, 20, TimeUnit.MILLISECONDS);

            thirdStarted.await();           // Lượt 3 đã vào Runnable
            boolean cancelled = schedule.cancel(false);
            releaseThird.countDown();       // Cho lượt 3 hoàn tất
            pool.shutdown();

            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not stop");
            }

            System.out.println("runs=" + runs.get());
            System.out.println("maxConcurrent=" + maxActive.get());
            System.out.println("cancelled=" + cancelled);
        } finally {
            releaseThird.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac FixedRateDemo.java
java FixedRateDemo
```

**Stdout trong điều kiện demo bình thường:**

```text
runs=3
maxConcurrent=1
cancelled=true
```

### Vì sao ví dụ đáng tin?

1. `scheduleAtFixedRate` tạo **một periodic schedule** với lần đầu delay 0 và chu kỳ 20 ms. Không yêu cầu callback phải hoàn thành sau đúng 20 ms; đó là *lịch dự kiến*.
2. `thirdStarted.await()` đợi đến lúc lần chạy thứ ba đã được thực thi; nó không đoán bằng `Thread.sleep`.
3. Khi lượt ba đang chặn `releaseThird.await()`, main gọi `schedule.cancel(false)`. Tại thời điểm đó lịch chưa hoàn thành, nên cancellation có hiệu lực đối với những lần chạy tiếp theo.
4. `cancel(false)` không interrupt lượt ba; sau khi mở latch, lượt ba kết thúc bình thường.
5. `pool.shutdown()` và `awaitTermination` bảo đảm worker hoàn tất trước khi main in kết quả. `runs` chính xác là 3 vì các lượt sau đã bị hủy.
6. Hai thread sẵn có không khiến **cùng một periodic task** chạy đồng thời nhiều lượt; `maxConcurrent=1` cho thấy không có overlap trong demo.
7. `finally` luôn giải phóng latch và yêu cầu đóng pool để tránh giữ tiến trình nếu phần trước thất bại.

**Ranh giới kết luận:** demo này chứng minh behavior của **`ScheduledThreadPoolExecutor` trong Java 17** với một đăng ký fixed-rate. Nó không có nghĩa mọi thiết kế scheduler/job queue ngoài JDK đều cấm overlap, đặc biệt khi Runnable tự giao việc cho executor khác hoặc ứng dụng chạy nhiều replica. Ngoài ra, **tên thread và timestamp thực tế không phải hợp đồng** của scheduler.

## 8. Lỗi trong một lượt có làm dừng cả lịch?

Đây là khác biệt tinh vi giữa raw JDK periodic scheduling và cấu hình Spring:

### 8.1. ScheduledThreadPoolExecutor thuần JDK

Javadoc `ScheduledExecutorService.scheduleAtFixedRate` quy định nếu một lượt chạy ném exception không được xử lý, **các lượt tiếp theo bị ngăn lại**. Periodic `ScheduledFuture` hoàn tất bất thường; gọi `get()` có thể ném `ExecutionException` chứa nguyên nhân gốc.

```java
ScheduledFuture<?> future = pool.scheduleAtFixedRate(() -> {
    throw new IllegalStateException("tick failed");
}, 0, 1, TimeUnit.SECONDS);
```

Đây là fragment; `pool` cần là scheduled executor. Khi task ném exception không được bắt, chuỗi định kỳ theo JDK sẽ dừng.

### 8.2. Spring ThreadPoolTaskScheduler có ErrorHandler

Spring có lớp bọc xử lý lỗi cho task định kỳ. Với `ThreadPoolTaskScheduler`, **handler mặc định cho tác vụ lặp lại thường log rồi suppress lỗi** để một lần thất bại không ngăn các lần chạy sau. Ngược lại, nếu tự cấu hình handler để **ném lại exception**, lịch có thể chấm dứt như hành vi raw JDK.

Ví dụ cấu hình:

```java
scheduler.setErrorHandler(error ->
        log.error("Recurring task failed", error));
```

Đây là fragment, giả định `scheduler` và `log` đã tồn tại; lambda chỉ ghi lỗi rồi return, nên không yêu cầu propagate. **Không nên nhìn mỗi tên `scheduleAtFixedRate` rồi khẳng định một exception luôn dừng lịch** trên mọi implementation.

Tuy nhiên, việc tiếp tục scheduling không có nghĩa một lỗi nghiệp vụ đã được khắc phục. Nếu job thất bại 10.000 lần, log lỗi liên tục và tiếp tục chạy có thể làm hệ thống tệ hơn. Nên đo failed attempts, áp backoff/circuit breaker khi phù hợp, và quyết định có chuyển sang trạng thái PAUSED/FAILED theo quy tắc nghiệp vụ.

Tham khảo Spring `TaskUtils` và cơ chế error handling của recurring tasks:
https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/support/TaskUtils.html

### 8.3. Khác nhau giữa log lỗi và xử lý lỗi

Một error handler chỉ ghi log không tự tạo:

- Retry có backoff;
- Bảo đảm gửi đúng một email;
- Rollback thao tác đã commit;
- Lưu job vào queue bền vững;
- Cảnh báo vận hành khi lỗi vượt ngưỡng.

Hãy dùng trạng thái công việc, metric `success/failure` và cảnh báo riêng. Một lịch vẫn tiếp tục tick chỉ chứng minh **scheduler còn hoạt động**, không chứng minh nghiệp vụ các lượt trước đã thành công.

## 9. Spring Boot 3.x đầy đủ: đăng ký và hủy fixed-rate khi ứng dụng chạy

Ví dụ sau dùng **Java 17+, Spring Boot 3.x / Spring Framework 6.x** và dependency `spring-boot-starter-web`. Nó tạo một bean `ThreadPoolTaskScheduler` do Spring quản lý, đăng ký job fixed-rate **khi ứng dụng sẵn sàng** và giữ `ScheduledFuture` để hủy khi context đóng. Một endpoint đọc số lượt đã bắt đầu.

**Điểm cần ghi nhớ trước khi chạy:** job chỉ tăng bộ đếm và ghi log; **không thực hiện thao tác nghiệp vụ thực**. Không có bảo đảm thời điểm log chính xác đến millisecond hoặc job trạng thái bền vững qua restart.

Đặt toàn bộ nội dung vào **src/main/java/com/example/demo/PeriodicApplication.java**:

```java
package com.example.demo;

import java.time.Duration;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PeriodicApplication {
    private static final Logger log =
            LoggerFactory.getLogger(PeriodicApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(PeriodicApplication.class, args);
    }

    @Bean("periodicScheduler")
    ThreadPoolTaskScheduler periodicScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("periodic-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setErrorHandler(error ->
                log.error("Periodic task failed", error));
        return scheduler; // Spring quản lý initialize/shutdown của bean.
    }
}

@Service
class PeriodicJob {
    private static final Logger log =
            LoggerFactory.getLogger(PeriodicJob.class);

    private final TaskScheduler scheduler;
    private final AtomicInteger attempts = new AtomicInteger();
    private volatile ScheduledFuture<?> schedule;

    PeriodicJob(
            @Qualifier("periodicScheduler") TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void start() {
        if (schedule != null) {
            return; // Không đăng ký lặp trong cùng bean.
        }
        schedule = scheduler.scheduleAtFixedRate(
                this::runOneTick, Duration.ofSeconds(5));
        log.info("Periodic job registered, period=5s");
    }

    private void runOneTick() {
        int attempt = attempts.incrementAndGet();
        log.info("Tick {} on {}", attempt,
                Thread.currentThread().getName());

        // Chỉ để minh họa handler; tick 3 cố tình thất bại.
        if (attempt == 3) {
            throw new IllegalStateException("Simulated tick failure");
        }
    }

    public int attempts() {
        return attempts.get();
    }

    public boolean isScheduled() {
        ScheduledFuture<?> current = schedule;
        return current != null
                && !current.isCancelled()
                && !current.isDone();
    }

    @PreDestroy
    public void stop() {
        ScheduledFuture<?> current = schedule;
        if (current != null) {
            current.cancel(false); // Không interrupt tick đang chạy.
        }
        log.info("Periodic job cancellation requested");
    }
}

record PeriodicStatus(int attempts, boolean scheduled) {}

@RestController
class PeriodicController {
    private final PeriodicJob job;

    PeriodicController(PeriodicJob job) {
        this.job = job;
    }

    @GetMapping("/schedule/status")
    public PeriodicStatus status() {
        return new PeriodicStatus(job.attempts(), job.isScheduled());
    }
}
```

Trong project có Spring Boot Gradle plugin và wrapper, chạy:

```bash
./gradlew bootRun
curl -s http://localhost:8080/schedule/status
```

Trên Windows, sử dụng `gradlew.bat bootRun`. Khi context đã phát sự kiện `ApplicationReadyEvent` và schedule được đăng ký thành công, một response ví dụ là:

```json
{"attempts":2,"scheduled":true}
```

**Đây là response minh họa, không phải output cố định**: số lần tick phụ thuộc thời điểm bạn gọi endpoint, lịch thực thi, việc dừng ứng dụng và điều kiện môi trường. Ở tick thứ ba, method cố ném `IllegalStateException`. Vì handler của `ThreadPoolTaskScheduler` trong ví dụ **ghi lỗi rồi return**, lịch có thể tiếp tục chạy các tick tiếp theo. Endpoint đo **số lần bắt đầu**, không phải số lần thành công; đây là chủ ý để thấy khác biệt giữa “đã chạy lịch” và “nghiệp vụ thành công”.

### 9.1. Phân tích vòng đời

1. Spring tạo `periodicScheduler` thành **bean có tên**, cấu hình pool và handler.
2. `PeriodicJob` inject `TaskScheduler` bằng `@Qualifier` để không phụ thuộc lựa chọn bean mặc định.
3. `@EventListener(ApplicationReadyEvent.class)` đăng ký lịch khi ứng dụng đã tới giai đoạn ready; không khởi động task trong constructor.
4. `scheduleAtFixedRate(this::runOneTick, Duration.ofSeconds(5))` đăng ký **một** periodic task, lượt đầu sớm nhất có thể.
5. `ScheduledFuture<?> schedule` được giữ lại để biết lịch đang tồn tại và hủy khi dừng.
6. `@PreDestroy` gọi `cancel(false)` để ngăn những lượt tiếp theo. Với một lượt đang chạy, `false` không phát interrupt.
7. Spring tiếp tục quản lý shutdown của bean scheduler; riêng cancellation ở service thể hiện rõ ranh giới sở hữu lịch.

**Không có `@EnableScheduling` trong ví dụ này** vì code **gọi TaskScheduler API trực tiếp**, không có method `@Scheduled`. Nếu thay bằng annotation thì cần bật scheduling annotation infrastructure một cách tương ứng.

### 9.2. Vì sao không phải dùng một biến boolean để biết job đã hoàn thành?

`isScheduled()` trong ví dụ cho biết **periodic future còn active**, không chứng minh đã có tick thành công. Nếu task mất kết nối DB 100 lần, lịch vẫn có thể active và mọi nghiệp vụ đều lỗi.

Một hệ thống thật nên có:

- Lần chạy gần nhất bắt đầu/kết thúc lúc nào;
- Số lần thành công và thất bại riêng;
- Thời gian chạy, độ trễ so với lịch, số lần bị skip;
- Tình trạng downstream và giới hạn retry;
- Job ID/attempt ID cho mỗi lần chạy nếu cần truy vết;
- Alert nếu quá lâu không có lượt thành công.

### 9.3. Có thể dùng @Scheduled thay cho API này không?

Có. Nếu lịch cố định từ cấu hình và không cần cancel từng handle một cách linh hoạt, ví dụ:

```java
@Configuration
@EnableScheduling
class EnableJobs {}

@Component
class ReconciliationTick {
    @Scheduled(fixedRate = 5000, initialDelay = 2000)
    public void reconcile() {
        // Job chạy ở khoảng thời gian do Spring lên lịch.
    }
}
```

Đây là **cấu hình thay thế**, không đặt thêm vào cùng ứng dụng nếu cùng nghiệp vụ đã được đăng ký thủ công và không muốn double scheduling. Trong Spring, `@Scheduled` không thể tự làm cho job **chỉ chạy trên một replica**. Nếu cần Cron, dùng `@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")` với chủ ý về lịch/ngày/giờ và DST theo khu vực cần thiết.

## 10. Fixed-rate và việc chạy chồng lấp: chính xác chỗ nào an toàn?

Thường nghe “fixed rate cứ đến giờ là mở thread chạy mới”. Điều này **không chính xác** đối với một registration định kỳ dựa trên `ScheduledThreadPoolExecutor`.

### 10.1. Một recurring task trực tiếp trên ThreadPoolTaskScheduler

```text
scheduleAtFixedRate(task, 5s)
       |
       +-- Runnable lượt 1 (chạy lâu 8s)
       +-- Runnable lượt 2 (bắt đầu trễ sau lượt 1)
       +-- Runnable lượt 3 (bắt đầu khi đủ điều kiện sau lượt 2)
```

Các lần thực thi liên tiếp của **chính periodic task này** không overlap, theo `ScheduledThreadPoolExecutor`. Pool size 4 không biến một recurring handle thành bốn bản sao song song.

### 10.2. Runnable chỉ giao việc sang @Async hoặc một pool khác

```java
scheduler.scheduleAtFixedRate(
        () -> reportService.startReportAsync(),
        Duration.ofSeconds(5));
```

Đây là fragment; `reportService` cần là **Spring bean khác** được inject và method được cấu hình `@Async` phù hợp. Lượt scheduler có thể return ngay sau khi submit. Nếu report mất 20 giây, sau 5 giây scheduler **vẫn có thể submit report khác**. Do đó hai nghiệp vụ report **có thể chạy đồng thời**.

Muốn tránh chồng lấp thật sự:

- Không submit mới khi job cũ chưa hoàn tất, sử dụng `AtomicBoolean`/state/lease phù hợp.
- Hoặc để scheduler chạy một công việc đồng bộ có thời gian chạy phù hợp và chấp nhận các lượt trễ.
- Hoặc dùng job store/queue độc lập, idempotency và giới hạn concurrency theo workload.

### 10.3. Nhiều lịch hoặc nhiều replica

Nếu đăng ký hai lần:

```java
scheduler.scheduleAtFixedRate(task, Duration.ofSeconds(5));
scheduler.scheduleAtFixedRate(task, Duration.ofSeconds(5));
```

Đây là **hai periodic registrations độc lập** dù dùng cùng một đối tượng `Runnable`. Chúng có thể overlap nếu scheduler có nhiều worker. Nếu một method vừa dùng `@Scheduled` vừa bị gọi đăng ký thủ công, tác động có thể lặp.

Nếu chạy ba replica, mỗi replica có thể có schedule riêng và cùng tác động DB. Muốn chỉ một instance thực hiện công việc toàn cụm, cần phối hợp phân tán **ngoài** TaskScheduler.

**Quy tắc:** khẳng định “non-overlap” chỉ có ý nghĩa khi bạn nói rõ **một handle, một executor implementation, phạm vi một process**.

## 11. Áp lực tải, trễ lịch và lựa chọn backpressure

Giả sử task quét hóa đơn chạy khoảng 12 giây nhưng fixed rate đặt 2 giây. Một scheduler worker gần như bị chiếm liên tục vì các lượt sau luôn đang đến hạn. Nếu không kiểm soát số lần làm việc, hệ thống có thể bị quá tải kéo dài hoặc downstream nhận request quá dày.

### 11.1. Tách ba loại độ trễ

| Chỉ số | Ý nghĩa |
| --- | --- |
| Scheduled time | Mốc mà task dự kiến đủ điều kiện chạy |
| Actual start | Khi worker thực sự bắt đầu thực thi |
| Completion time | Khi lượt đó kết thúc |
| Start lag | Actual start trừ scheduled time |
| Run duration | Completion trừ actual start |
| End-to-end job latency | Thời gian từ trigger tới kết quả nghiệp vụ có thể dùng |

Nếu chỉ log `"tick"` mà không đo duration/start lag, bạn khó biết vì sao lịch 5 giây nhưng nghiệp vụ cập nhật dữ liệu chậm 1 phút.

### 11.2. Cách giảm nghẽn

- **Rút ngắn tick:** chỉ chọn việc đủ điều kiện rồi chuyển sang pipeline có capacity control.
- **Batch có giới hạn:** xử lý từng nhóm nhỏ với state/offset để tránh một lượt giữ worker hàng chục phút.
- **Backpressure:** dùng semaphore/bulkhead, giới hạn số tác vụ cùng lúc và queue.
- **Skip có chủ đích:** nếu lần cũ chưa xong và nghiệp vụ cho phép, ghi metric `skipped_due_to_busy`, không tạo thêm job.
- **Điều chỉnh cadence:** một poller chờ downstream có thể thích hợp với fixed delay hơn.
- **Timeout ở dependency:** cấu hình HTTP/JDBC timeout phù hợp; `scheduleAtFixedRate` không tự chặn một task treo vô hạn.
- **Idempotency:** mỗi lần quét dùng khóa công việc để tránh tác động trùng khi restart/replica/retry.

### 11.3. Không tăng poolSize vô hạn

Nhiều scheduler workers giúp những **lịch độc lập** không làm nghẽn nhau, nhưng không làm task cũ nhanh hơn và không giải quyết sự quá tải của database/API. Việc mở rộng cần dựa trên đo lường CPU, latency, concurrency downstream và khả năng xử lý.

## 12. Hủy schedule và shutdown có nghĩa gì?

`ScheduledFuture.cancel(boolean)` hủy chuỗi lịch lặp khi được chấp nhận. Hai trường hợp:

**`cancel(false)`:** không yêu cầu interrupt lượt đang chạy, nhưng ngăn các lượt tiếp theo theo hợp đồng Future.

**`cancel(true)`:** có thể yêu cầu interrupt runner của lượt đang chạy trong implementation hỗ trợ. Interrupt là tín hiệu **hợp tác**; nếu task đang block ở API không hỗ trợ interrupt hoặc side effect đã được gửi ra ngoài, không thể đảm bảo dừng ngay hoặc rollback.

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::poll,
        Duration.ofSeconds(5));

// Khi cấu hình không còn cần lịch:
boolean cancellationAccepted = handle.cancel(false);
```

Đây là fragment, cần `scheduler`, `poll` và imports.

**Đừng dùng `Future.get()`** để chờ “lần chạy đầu xong”. Với periodic future, nó đại diện **cả series**, có thể chờ vô hạn khi lịch còn active. Muốn biết một lượt đã hoàn tất, task cần công bố kết quả/metric hoặc trả một `CompletableFuture` riêng cho lượt đó.

### 12.1. Shutdown scheduler bean

Khi Spring context đóng, `ThreadPoolTaskScheduler` có lifecycle cleanup. Các lựa chọn như chờ task hiện có hoàn tất và chính sách có tiếp tục periodic tasks sau shutdown hay không phụ thuộc cấu hình implementation. Thông thường lịch sẽ không còn nhận lượt mới sau shutdown; nhưng không được mặc định tắt JVM sẽ ghi lại lịch để khôi phục sau restart.

Với application có job quan trọng, thiết kế shutdown:

1. Ngừng nhận/đăng ký schedule mới.
2. Hủy handle hoặc đánh dấu stop-requested theo nghiệp vụ.
3. Để lượt đang chạy kết thúc trong grace period hợp lý, hoặc gửi interrupt có kiểm soát.
4. Ghi trạng thái tiến độ/job offset vào nguồn bền vững.
5. Đảm bảo restart có thể tiếp tục công việc cần làm, không phụ thuộc những tick đã mất trong RAM.

### 12.2. Remove-on-cancel policy

`ScheduledThreadPoolExecutor` có cơ chế giữ cancelled delayed tasks trong queue cho tới thời điểm delay trôi qua theo mặc định; điều này có thể gây giữ tham chiếu lâu khi ứng dụng tạo/hủy rất nhiều lịch.

`ThreadPoolTaskScheduler#setRemoveOnCancelPolicy(true)` yêu cầu implementation bên dưới cố xóa task đã cancel sớm hơn khi có thể. Nó giúp giảm retention trong những workload đăng ký/hủy thường xuyên, nhưng không thay thế việc **quản lý handle, lifecycle và giám sát tài nguyên**.

## 13. Lập lịch theo chu kỳ không đồng nghĩa lịch nghiệp vụ chính xác

### 13.1. Fixed rate là Duration, không phải “mỗi ngày đúng 02:00”

`Duration.ofHours(24)` là khoảng cách 24 giờ. Nó **không** đồng nghĩa “02:00 giờ địa phương mỗi ngày”, vì múi giờ/ngày đổi DST có thể có ngày dài 23 hoặc 25 giờ ở một số khu vực.

Nếu yêu cầu “mỗi ngày 02:00 theo một timezone”, dùng cron/trigger với timezone rõ ràng và xác định quy tắc khi giờ không tồn tại hoặc trùng lặp. Không dùng fixed rate mù quáng cho lịch cần xét ngày lễ hoặc calendar business.

### 13.2. Không dùng tick count làm nguồn sự thật

Ví dụ scheduler chạy mỗi 10 giây, một máy bị dừng 5 phút. Khi bật lại, tick count mới không tự biểu diễn tất cả các sự kiện nghiệp vụ trong 5 phút mất kết nối.

Đúng hơn, mỗi lượt **quét dữ liệu theo điều kiện**:

```sql
-- Chỉ là truy vấn minh họa, không phải schema hoàn chỉnh.
SELECT id
FROM pending_jobs
WHERE next_attempt_at <= CURRENT_TIMESTAMP
  AND status = 'PENDING'
ORDER BY next_attempt_at
LIMIT 100;
```

Worker xử lý có khóa/lease hoặc điều kiện cập nhật phù hợp để tránh nhiều replica lấy cùng job. **Database/job store là nguồn sự thật**, còn fixed-rate tick chỉ là cơ chế đánh thức poller.

### 13.3. Idempotency và nhiều instance

Với task quét invoice, nếu hai replica cùng phát hiện một invoice chưa xử lý, cả hai có thể cùng gửi request đến provider. `scheduleAtFixedRate` không có distributed lock. Cần optimistic locking, unique constraint, claim/lease hoặc job store đáng tin và idempotency key cho side effect. Không xem log “chỉ có một tick” ở một instance là bằng chứng toàn cluster chạy đúng một lần.

## 14. Quan sát, lỗi và ngữ cảnh thực thi

Trong production, theo dõi:

- **Registration count:** bao nhiêu lịch đang được đăng ký, có trùng hay không;
- **Actual tick count:** số lần callback bắt đầu;
- **Success/failure count:** số lượt đạt kết quả nghiệp vụ hoặc lỗi;
- **Duration và start lag:** việc xử lý có chậm hơn period không;
- **Skipped ticks/batches:** số lượt bỏ có chủ đích do job trước còn bận;
- **Worker active và pool size:** lịch khác có bị nghẽn không;
- **Shutdown/cancel:** khi nào hủy lịch, còn lượt đang chạy không;
- **Retry/duplicate processing:** đặc biệt trên nhiều replica.

### 14.1. Logging correlation ID cho scheduled job

Một scheduled task thường **không có HTTP request** và không nên mong MDC từ servlet thread tự đi theo. Có thể tạo `jobRunId` trong mỗi lượt chạy, đặt vào MDC trong scope rồi cleanup:

```java
String runId = UUID.randomUUID().toString();
String previous = MDC.get("jobRunId");
try {
    MDC.put("jobRunId", runId);
    log.info("Starting periodic reconciliation");
    reconcile();
} finally {
    if (previous == null) MDC.remove("jobRunId");
    else MDC.put("jobRunId", previous);
}
```

Đây là fragment, cần imports SLF4J `MDC`, `Logger`, UUID và implementation `reconcile`. Vì scheduler worker được tái sử dụng, thiếu `finally` có thể làm run sau mang sai ID.

Nếu job bền vững, có thể có `jobId` cố định cho logical job và `attemptId`/`runId` cho mỗi lần thực thi; không sử dụng request ID làm idempotency key thay cho job ID.

### 14.2. Với @Async hoặc CompletableFuture bên trong tick

`@Async` chuyển execution sang executor khác thông qua Spring proxy; `CompletableFuture.supplyAsync` không chỉ định executor có thể dùng common pool. MDC, transaction và security context **không tự được truyền** qua mọi thread. Nếu cần, dùng context-aware executor/TaskDecorator hoặc truyền metadata như dữ liệu.

**Tác vụ scheduler đã return không phải bằng chứng công việc ở async executor đã xong.** Điều này ảnh hưởng cả giới hạn overlap lẫn cách đếm thành công.

## 15. Kiểm thử scheduleAtFixedRate đúng cách

Timing test rất dễ flaky. Đừng viết test “ngủ 100 ms rồi chắc chắn có đúng ba lần chạy”; GC và scheduler có thể tạo lệch lớn.

### 15.1. Những kiểm thử cần có

1. **Registration:** task được đăng ký một lần, period và startTime đúng cấu hình.
2. **Activation:** có ít nhất một tick khi scheduler chạy; dùng `CountDownLatch`/condition có timeout tổng thay vì chờ vô hạn.
3. **Cancellation:** sau cancel, không có lượt mới được scheduling, trong khi lượt đang chạy với `cancel(false)` có thể kết thúc.
4. **Non-overlap:** với một recurring task của `ScheduledThreadPoolExecutor`, xác nhận concurrency tối đa là 1 dưới mô hình test.
5. **Exception:** một lượt lỗi có làm dừng lịch hay được handler suppress theo cấu hình không.
6. **Heavy task:** tick mất lâu hơn period làm tăng start lag, không tạo hai lượt overlap của cùng handle.
7. **Multiple schedules:** các job độc lập có thể song song theo pool size; không vô tình đăng ký một job hai lần.
8. **Shutdown:** context đóng, bean scheduler hủy task và thread được dọn.
9. **Cluster idempotency:** nếu nhiều replica cùng tick, không nhân đôi side effect khi claim một job logic.
10. **Observability:** metric số lượt thành công/thất bại tách riêng và có run ID.

### 15.2. Không kiểm tra timestamp như số tuyệt đối

Một test có thể ghi:

```java
long startedAtNanos = System.nanoTime();
// Trong callback: đo độ trễ, không khẳng định start đúng 5000 ms tuyệt đối.
```

Đây là fragment. Dùng `System.nanoTime()` để đo **khoảng thời gian**; không dùng nó làm wall-clock lịch nghiệp vụ. Khi so sánh actual time với target, chấp nhận jitter hợp lý và không ép độ chính xác mà Java scheduler không cam kết.

### 15.3. Test logic nghiệp vụ tách khỏi scheduler

Thay vì nhồi logic vào lambda không thể gọi riêng:

```java
scheduler.scheduleAtFixedRate(() -> {
    // Hàng trăm dòng business code.
}, Duration.ofSeconds(5));
```

Nên tổ chức:

```java
scheduler.scheduleAtFixedRate(
        jobService::runOneBatch,
        Duration.ofSeconds(5));
```

Các fragment trên giả định `jobService` là service đã inject. Test `runOneBatch` như một business unit độc lập bằng các fake repository/client; test scheduler chỉ xác nhận đúng trigger, cancellation và lifecycle. Điều đó giảm test phụ thuộc timing và giúp tái sử dụng job khi cần chạy manual/retry.

## 16. Các sai lầm thường gặp

**Lỗi 1 — Cho rằng fixed rate luôn đúng từng millisecond.** JVM scheduler không phải real-time; GC, CPU, queue và task lâu có thể gây trễ.

**Lỗi 2 — Cho rằng fixed rate = luôn overlap.** Với một periodic registration trên `ScheduledThreadPoolExecutor`, các lượt không overlap; có thể bắt đầu muộn.

**Lỗi 3 — Cho rằng fixed rate = không bao giờ overlap trong toàn hệ thống.** Nếu Runnable submit async work, có nhiều registrations hoặc replicas, nghiệp vụ vẫn có thể overlap.

**Lỗi 4 — Nhầm fixedRate với fixedDelay.** Fixed rate theo mốc bắt đầu dự kiến, fixed delay đếm từ lúc lượt trước hoàn tất.

**Lỗi 5 — Truyền `Duration.ZERO`/âm.** Chu kỳ không dương không hợp lệ; cần positive period.

**Lỗi 6 — Nghĩ `scheduleAtFixedRate(task, period)` sẽ chờ period rồi mới chạy lần đầu.** Overload này bắt đầu sớm nhất có thể. Muốn initial delay dùng `Instant startTime` hoặc `@Scheduled(initialDelay=...)`.

**Lỗi 7 — Gọi `ScheduledFuture.get()` để chờ “tick hiện tại”.** Future đại diện chuỗi định kỳ, có thể chờ tới cancel/error; cần completion riêng cho từng lượt.

**Lỗi 8 — Không giữ handle khi cần hủy riêng lịch.** Không có handle, việc thay cấu hình động hoặc dừng một job cụ thể khó khăn.

**Lỗi 9 — Không phân biệt default lỗi của JDK và Spring.** Raw JDK periodic task bị ngừng sau exception không bắt; Spring thường log/suppress cho repeating tasks. Cần xem ErrorHandler.

**Lỗi 10 — Chỉ tăng poolSize để khắc phục task chậm.** Pool lớn giúp các lịch độc lập, không tăng tốc một task CPU-bound/blocking hay sửa bottleneck downstream.

**Lỗi 11 — Tạo scheduler mới cho mỗi HTTP request.** Sinh nhiều pool và lịch sống lâu, khó shutdown, memory/thread retention. Ưu tiên Spring bean dùng chung.

**Lỗi 12 — Bật cả @Scheduled và đăng ký TaskScheduler thủ công cho cùng việc.** Có thể double schedule.

**Lỗi 13 — Giả định @Scheduled chạy một lần trên cả cluster.** Mỗi replica có lịch riêng; cần distributed coordination/idempotency nếu đó là yêu cầu.

**Lỗi 14 — Dùng fixed rate 24 giờ cho “02:00 địa phương hằng ngày”.** Một Duration 24 giờ không xử lý DST/calendar như cron.

**Lỗi 15 — Chỉ log tick mà không đo success/failure, duration và lag.** Có thể scheduler vẫn chạy nhưng business job thất bại liên tục.

**Lỗi 16 — Dùng cancel(true) như rollback.** Interrupt không tự hủy side effect đã xảy ra; cần cancellation hợp tác và reconciliation.

**Lỗi 17 — Nhầm ThreadPoolTaskScheduler với ThreadPoolTaskExecutor.** Scheduler có pool size và delayed queue semantics riêng, không dùng `queueCapacity` để mô tả chính xác nó.

**Lỗi 18 — Dùng một periodic tick làm nguồn sự thật về dữ liệu còn thiếu.** Khi shutdown/crash, các tick có thể mất; dùng job store với thời điểm `next_run`/`next_attempt` nếu cần phục hồi.

## 17. Checklist sử dụng trên hệ thống thật

- [ ] Xác định task cần **fixed rate**, **fixed delay** hay **cron**; viết rõ ý nghĩa nghiệp vụ.
- [ ] Đặt `Duration` dương và thời gian bắt đầu chính xác; đừng nhầm “run immediately” với “initial delay”.
- [ ] Cấu hình bean `TaskScheduler`/`ThreadPoolTaskScheduler` dùng chung; chọn `poolSize` dựa trên số job độc lập và blocking duration.
- [ ] Không đăng ký trùng một job (do start callback chạy hai lần, nhiều configuration hoặc cùng lúc có `@Scheduled`).
- [ ] Giữ `ScheduledFuture<?>` nếu cần hủy/start/stop động; cancel có chủ đích khi shutdown.
- [ ] Phân biệt `cancel(false)` với interrupt best-effort ở `cancel(true)`; có cleanup và timeout dependency.
- [ ] Hiểu error handler của **implementation thực tế**, không giả định một exception luôn dừng hoặc luôn giữ lịch.
- [ ] Không coi tick count là success count; log/metric kết quả nghiệp vụ theo mỗi run.
- [ ] Giám sát **start lag**, duration, pool utilization và số lượt bị skip do bận.
- [ ] Nếu Runnable dispatch async work, giới hạn số job đang xử lý và queue; chặn overlap ở tầng nghiệp vụ.
- [ ] Nếu ứng dụng có nhiều replica, dùng distributed lock/lease/leader hoặc idempotency khi cần xử lý duy nhất.
- [ ] Với công việc cần khôi phục sau restart, dùng persistent job store/message queue; fixed rate chỉ đánh thức consumer.
- [ ] Với lịch theo giờ địa phương/thứ/ngày, dùng cron/trigger với timezone chính xác thay vì cộng Duration mù quáng.
- [ ] Không dựa vào request MDC/transaction/security context trong scheduler worker; tạo run ID/context phù hợp và cleanup.
- [ ] Viết test có latch/timeout tổng; tránh kiểm tra mốc tuyệt đối hoặc `Thread.sleep` để suy ra thứ tự.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `scheduleAtFixedRate(task, Duration.ofSeconds(5))` có chờ 5 giây trước lần đầu không?

**Đáp án:** Không mặc định. Overload này đăng ký task bắt đầu sớm nhất có thể; dùng overload `Instant startTime` nếu muốn chỉ rõ lần đầu sau 5 giây.

**Câu 2.** Task chạy 8 giây, period 5 giây, `ThreadPoolTaskScheduler` có tạo hai lần thực thi cùng một recurring handle chồng lấp không?

**Đáp án:** Với backend `ScheduledThreadPoolExecutor` của implementation đó, các lượt liên tiếp của **cùng một periodic task** không overlap; lượt sau bị trễ, có thể được chạy sớm sau lượt trước.

**Câu 3.** Vậy nếu task chỉ gọi `@Async` rồi return sau 1 ms, business job có thể overlap không?

**Đáp án:** Có. Scheduler đã hoàn tất phần submit; business work trong executor khác có thể vẫn chạy khi tick kế tiếp đến. Cần limit concurrency/idempotency nếu không muốn chồng lấp.

**Câu 4.** Fixed-rate period 5 giây và fixed-delay 5 giây khác nhau thế nào khi task mất 3 giây?

**Đáp án:** Fixed rate thường bắt đầu ở các mốc gần 0, 5, 10,... giây; fixed delay bắt đầu các lượt gần 0, 8, 16,... giây vì đợi hoàn tất rồi thêm 5 giây.

**Câu 5.** Với JDK ScheduledThreadPoolExecutor, một periodic Runnable ném RuntimeException không bắt thì sao?

**Đáp án:** Những lượt sau của chuỗi định kỳ bị ngăn lại; periodic future có thể hoàn tất ngoại lệ. Nhưng Spring `ThreadPoolTaskScheduler` có error handler mặc định cho repeating tasks thường suppress/log, nên cần kiểm tra configuration thực tế.

**Câu 6.** `ScheduledFuture.get()` có phải API đúng để chờ một lượt tick thành công không?

**Đáp án:** Không. Future đó đại diện cả chuỗi lịch recurring; không hoàn tất bình thường sau từng tick. Dùng trạng thái/metric/future riêng theo từng run.

**Câu 7.** Muốn chỉ một replica chạy job mỗi 5 giây, có thể chỉ đặt `poolSize=1` không?

**Đáp án:** Không. Pool size 1 chỉ giới hạn worker **trong một scheduler process**. Nhiều replica vẫn có lịch riêng. Cần distributed coordination hoặc idempotency thích hợp.

**Câu 8.** Có cần `@EnableScheduling` để gọi trực tiếp `taskScheduler.scheduleAtFixedRate(...)` không?

**Đáp án:** Không. Annotation này cần cho việc tự phát hiện `@Scheduled`. Với API trực tiếp và scheduler bean có sẵn, code tự đăng ký lịch.

**Câu 9.** Hủy `handle.cancel(false)` có chắc dừng lượt đang chạy ngay không?

**Đáp án:** Không. Nó không yêu cầu interrupt lượt hiện tại; cancellation ngăn lần chạy tiếp theo theo hợp đồng Future. Nếu cần dừng sớm, phải có cơ chế hợp tác với deadline/interrupt.

**Câu 10.** Fixed rate 24 giờ có luôn đồng nghĩa 02:00 mỗi ngày trong mọi timezone không?

**Đáp án:** Không. Duration 24 giờ khác lịch theo giờ địa phương khi có đổi DST/calendar. Dùng cron/trigger với timezone phù hợp cho lịch nghiệp vụ.

## Kết luận

**`TaskScheduler.scheduleAtFixedRate()` lập lịch thực thi `Runnable` theo những mốc cách nhau một `Duration` cố định**. Khi task chạy quá lâu, các lượt sau của cùng periodic registration trong `ThreadPoolTaskScheduler` thường **bắt đầu trễ chứ không overlap**; nếu task chuyển công việc sang executor khác hoặc nhiều replica có lịch độc lập thì business operations vẫn có thể chồng lấp.

- Dùng `scheduleAtFixedRate(task, period)` để bắt đầu sớm nhất có thể; dùng overload `Instant startTime` để đặt thời điểm chạy đầu.
- Phân biệt **fixed rate** (mốc cố định), **fixed delay** (nghỉ sau khi xong), **cron** (theo lịch/calendar).
- Giữ `ScheduledFuture` để hủy; không dùng `get()` như kết quả một tick.
- Kiểm soát exception handler, worker capacity, blocking duration, retry/idempotency và shutdown.
- Với hệ thống phân tán hoặc công việc quan trọng, lịch định kỳ chỉ là **cơ chế kích hoạt**; cần một nguồn sự thật và bảo đảm xử lý ở tầng nghiệp vụ.

## Tài liệu tham khảo

1. Spring Framework Reference — Task Execution and Scheduling / TaskScheduler: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
2. Spring Framework 6.2 Javadoc — TaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/TaskScheduler.html
3. Spring Framework Javadoc — ThreadPoolTaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
4. Spring Framework Javadoc — TaskUtils error handling: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/support/TaskUtils.html
5. Java SE 17 — ScheduledExecutorService.scheduleAtFixedRate: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
6. Java SE 17 — ScheduledThreadPoolExecutor, no-overlap và remove-on-cancel: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
7. Java SE 17 — ScheduledFuture / cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html
8. Spring Framework Javadoc — @Scheduled: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
