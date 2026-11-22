# ScheduledFuture để theo dõi và hủy lịch

## 1. Vì sao một TaskScheduler cần trả về ScheduledFuture?

Trong Spring Framework, `TaskScheduler` giúp đặt lịch cho một công việc `Runnable`: chạy một lần ở thời điểm xác định, chạy lặp theo chu kỳ cố định, chạy lại sau một khoảng nghỉ tính từ lần trước hoặc chạy theo `Trigger` như cron.

Khi công việc đã được đăng ký, ứng dụng thường cần **theo dõi trạng thái và chủ động hủy lịch**: người dùng tắt một báo cáo định kỳ, cấu hình tần suất thay đổi, tenant ngừng sử dụng dịch vụ, một tài nguyên được giải phóng, hoặc một job đang chờ không còn giá trị.

Các phương thức lập lịch programmatic của `TaskScheduler` thường trả về:

```java
java.util.concurrent.ScheduledFuture<?>
```

Đây là một **handle cho công việc đã lập lịch**. Nó không phải mã định danh job trong database, không phải bản ghi cron bền vững và không tự bảo đảm công việc đã hoàn thành. Nhưng nó cho phép sử dụng những API quan trọng:

- `cancel(boolean mayInterruptIfRunning)`: yêu cầu hủy lịch.
- `isCancelled()`: kiểm tra handle đã ở trạng thái bị hủy hay chưa.
- `isDone()`: kiểm tra một công việc đã kết thúc trạng thái của Future hay chưa.
- `getDelay(TimeUnit unit)`: ước lượng độ trễ còn lại tới lần kích hoạt phù hợp.
- `get()` hoặc `get(timeout, unit)`: chờ một Future hoàn tất; **đặc biệt phải phân biệt tác vụ một lần với tác vụ lặp**.

Ví dụ ý tưởng:

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        this::refreshCache,
        Duration.ofMinutes(5)
);

// Khi không muốn chạy các lượt tiếp theo:
boolean accepted = handle.cancel(false);
```

Đây là **mảnh code trong một class có `scheduler` và `refreshCache()`**, không phải chương trình độc lập. `cancel(false)` không buộc một lượt đã bắt đầu phải dừng ngay; nó thể hiện ý định hủy lịch mà không yêu cầu ngắt thread đang thực thi.

**Mục tiêu bài:** hiểu `ScheduledFuture` gắn với `TaskScheduler` như thế nào, đọc trạng thái chính xác, hủy one-shot/periodic/trigger task, phân biệt `cancel(false)` và `cancel(true)`, quản lý nhiều handle an toàn, xử lý lỗi và vòng đời Spring, kèm ví dụ Java 17 có kết quả kiểm chứng được.

## 2. Sơ đồ quan hệ: TaskScheduler → ScheduledFuture → vòng đời lịch

```text
Application / service
       |
       | scheduler.schedule*(Runnable, ...)
       v
    TaskScheduler
       |
       +--- nhận task, tính thời điểm chạy
       |
       +--- trả ScheduledFuture<?> cho caller
       |                       |
       |                       +-- getDelay(...)
       |                       +-- isDone()
       |                       +-- isCancelled()
       |                       +-- cancel(false/true)
       v
Scheduled executor / Trigger
       |
       +--- chưa đến hạn --> nằm trong cấu trúc chờ
       |
       +--- đến hạn --> worker chạy Runnable
       |                   |
       |                   +--- one-shot: kết thúc Future
       |                   |
       |                   +--- định kỳ: có thể lên lịch lượt tiếp
       |
       +--- cancel / shutdown / terminal failure
```

**Lịch là một đối tượng điều phối**, còn mỗi lần chạy `Runnable` là một lượt thực thi. Một handle của công việc lặp có thể vẫn “chưa xong” dù tác vụ đã chạy thành công hàng trăm lượt, vì lịch tiếp tục tồn tại cho tới khi hủy hoặc kết thúc bất thường.

Trong `ThreadPoolTaskScheduler` truyền thống, Spring sử dụng một `ScheduledThreadPoolExecutor` của Java và các tác vụ được thực thi trên scheduler thread(s). Điều đó khác với mô hình “scheduler chỉ đánh thức một executor phụ” ở các triển khai khác. Vì thế **thời gian tác vụ chiếm worker** ảnh hưởng trực tiếp khả năng thực thi các lịch khác. Không nên mặc định mọi `TaskScheduler` có cùng chiến lược thread hoặc cùng ngữ nghĩa quản lý lỗi.

## 3. ScheduledFuture có những phương thức nào?

`ScheduledFuture<V>` thuộc `java.util.concurrent`, **kế thừa `Delayed` và `Future<V>`**. Vì vậy nó có hai nhóm API.

| API | Nguồn | Ý nghĩa |
|---|---|---|
| `getDelay(TimeUnit)` | `Delayed` | Thời gian ước tính còn lại trước khi nhiệm vụ đủ điều kiện kích hoạt |
| `compareTo(Delayed)` | `Delayed`/`Comparable` | So sánh các trì hoãn theo hợp đồng |
| `cancel(false)` | `Future` | Hủy mà không yêu cầu ngắt một lượt đang chạy |
| `cancel(true)` | `Future` | Hủy và cho phép cố gắng ngắt thread nếu task đang chạy |
| `isCancelled()` | `Future` | Future đã bị hủy hay chưa |
| `isDone()` | `Future` | Future đã kết thúc bình thường, lỗi hoặc bị hủy hay chưa |
| `get()` | `Future` | Chờ kết thúc và nhận kết quả/exception |
| `get(timeout, unit)` | `Future` | Chờ hữu hạn và có thể báo `TimeoutException` |

Những quy tắc rất dễ nhầm:

1. **`isDone() == true` không đồng nghĩa “thành công”**. Nó cũng đúng khi Future bị hủy hoặc hoàn tất ngoại lệ.
2. **`isCancelled() == true` không chứng minh code trong một lượt đang chạy đã ngừng hoàn toàn**. Với `cancel(false)`, lượt đang thực thi có thể tiếp tục đến hết.
3. **`getDelay(...)` không phải timestamp tuyệt đối của lần chạy tiếp theo** và không phải phần trăm tiến độ. Giá trị có thể thay đổi ngay sau khi đọc; nếu thời hạn đã qua có thể bằng không hoặc âm, tùy implementation.
4. **`ScheduledFuture<?>` không mang kết quả nghiệp vụ từ một `Runnable`**. Với tác vụ one-shot `Runnable` hoàn tất bình thường trong Java `ScheduledExecutorService`, `get()` trả `null`; trong Spring `TaskScheduler` cũng không biến nó thành kết quả tính toán riêng.
5. Với **lịch lặp còn sống**, `get()` không phải “đợi một lượt chạy xong”. Nó thường chờ tới lúc toàn bộ chuỗi thực thi kết thúc — có thể là khi hủy hoặc lỗi.

### 3.1. Trạng thái một lượt không giống trạng thái cả lịch

Ví dụ cron chạy lúc 01:00 hằng ngày; hôm nay đã chạy xong. Nếu lịch ngày mai vẫn được duy trì:

```text
Một lần chạy hôm nay: SUCCEEDED
ScheduledFuture của lịch: vẫn ACTIVE / isDone() thường false
Lần kế tiếp: ngày mai 01:00
```

Không dùng `isDone()` để kết luận “hôm nay job đã xử lý xong chưa”. Muốn theo dõi từng lượt, hãy ghi nhận `lastStartedAt`, `lastCompletedAt`, `lastSucceededAt`, số lần chạy, lỗi và trạng thái theo mô hình riêng.

## 4. Những phương thức TaskScheduler trả handle

Với Spring Framework 6.x, `TaskScheduler` cung cấp các overload dựa trên `Instant`/`Duration` và `Trigger`. Các chữ ký tiêu biểu:

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);

@Nullable
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

Đây là **tóm lược chữ ký của API Spring**, không phải một interface độc lập để tự biên dịch. `Trigger` là `org.springframework.scheduling.Trigger`, còn `ScheduledFuture` là của Java. Trên các phiên bản Spring 6.x, nhiều overload `Date`/`long` cũ đã deprecated; ưu tiên `Instant` và `Duration` trong code mới.

### 4.1. Chạy một lần ở thời điểm xác định

```java
ScheduledFuture<?> once = scheduler.schedule(
        () -> publishReport(reportId),
        Instant.now().plusSeconds(30));
```

Đây là mảnh code nghiệp vụ; `scheduler` là `TaskScheduler`, `publishReport` và `reportId` do ứng dụng cung cấp. Tác vụ **một lần** sẽ chạy khi đến thời điểm thích hợp và Future hoàn tất sau lần chạy đó (hoặc bị hủy/lỗi).

### 4.2. Fixed rate — khoảng cách mục tiêu giữa thời điểm bắt đầu

```java
ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
        this::pollStatus,
        Duration.ofSeconds(10));
```

Với fixed rate, lịch cố gắng duy trì các thời điểm bắt đầu theo chu kỳ đã định. Nếu một lượt chạy lâu hơn period, lượt tiếp theo có thể bắt đầu muộn; trong `ScheduledThreadPoolExecutor` của Java, các lượt **của cùng một periodic task** không thực thi chồng nhau. Điều này không cấm hai **job khác nhau** chạy đồng thời trên các worker khác nhau.

### 4.3. Fixed delay — đợi sau khi lượt trước kết thúc

```java
ScheduledFuture<?> periodic = scheduler.scheduleWithFixedDelay(
        this::cleanup,
        Duration.ofSeconds(10));
```

Fixed delay đếm khoảng nghỉ giữa **kết thúc một lượt** và **bắt đầu lượt kế tiếp**. Nếu `cleanup` chạy 30 giây thì khoảng cách giữa hai thời điểm bắt đầu lớn hơn 10 giây. Với job có thời gian thực thi biến thiên và không cần bám sát đồng hồ, fixed delay thường dễ kiểm soát hơn fixed rate.

### 4.4. Trigger/cron — thời điểm được tính động

```java
import org.springframework.scheduling.support.CronTrigger;

ScheduledFuture<?> cron = scheduler.schedule(
        () -> refreshIndexes(),
        new CronTrigger("0 */5 * * * *"));
```

Đoạn minh họa chạy mỗi 5 phút theo biểu thức cron 6 trường của Spring (`giây phút giờ ngày tháng thứ`). Nếu dùng giờ địa phương/múi giờ kinh doanh, hãy cấu hình timezone/clock phù hợp và kiểm tra DST.

**Lưu ý đặc biệt:** `schedule(Runnable, Trigger)` **có thể trả `null`** nếu trigger không đưa ra lần thực thi nào (`Trigger.nextExecution(...)` trả `null`). Vì vậy:

```java
ScheduledFuture<?> handle = scheduler.schedule(work, trigger);

if (handle == null) {
    // Không có lượt chạy nào được kích hoạt.
} else {
    // Có thể quản lý handle.
}
```

Một `null` ở đây không giống `Future` đã hủy; nó có nghĩa **không có lịch được đăng ký tại thời điểm gọi**. Với các overload `Instant` và `Duration`, hợp đồng trả về là `ScheduledFuture<?>` không nullable theo `TaskScheduler` thông thường.

## 5. cancel(false) và cancel(true): hiểu đúng chữ mayInterruptIfRunning

`cancel(boolean mayInterruptIfRunning)` yêu cầu hủy Future. Hai cách gọi khác nhau chủ yếu về **điều đang xảy ra nếu một lượt đã bắt đầu**:

| Cách gọi | Trường hợp thường phù hợp | Tác động tới lượt đang chạy |
|---|---|---|
| `cancel(false)` | Ngừng các lượt **tiếp theo**, cho lượt hiện tại tự kết thúc | Không yêu cầu ngắt thread đang thực thi |
| `cancel(true)` | Muốn cố gắng dừng sớm nếu việc đang chạy hỗ trợ interruption | Có thể interrupt worker; không bảo đảm mọi tác vụ dừng tức thì |

**Không diễn giải `cancel(false)` là “đợi lượt hiện tại chạy xong”.** Nó không chờ. Ngay sau khi phương thức trả về, một lượt hiện tại vẫn có thể đang dùng CPU, I/O, kết nối hoặc tác động hệ thống ngoài.

`cancel(true)` cũng không phải lệnh “kill thread” cưỡng bức. Interruption trong Java là cơ chế hợp tác:

- `Thread.sleep`/`BlockingQueue.take`/`CountDownLatch.await` và nhiều thao tác chặn có thể phản ứng bằng `InterruptedException`.
- Tính toán CPU trong vòng lặp dài chỉ dừng nếu code có kiểm tra cờ interrupted hoặc cơ chế hủy riêng.
- Nhiều thao tác I/O và API của bên thứ ba có cách phản hồi interruption khác nhau; cần timeout và hành vi hủy của chính thư viện.
- Nếu task đã thực hiện một side effect, `cancel(true)` không tự rollback email, thanh toán, bản ghi database hay lệnh HTTP.

### 5.1. Đọc giá trị boolean của cancel

`boolean accepted = handle.cancel(false)` thường cho biết **yêu cầu hủy Future đã được chấp nhận**; không phải một biên bản chứng minh worker đã hết chạy. `cancel(...)` có thể trả `false` nếu Future đã kết thúc hoặc không thể bị hủy theo implementation. Khi nhiều caller cùng hủy, một caller có thể thấy `true` và caller khác thấy `false`.

Nếu cần biết trạng thái sau cùng, kiểm tra `isCancelled()` và theo dõi riêng mốc tác vụ đã thật sự thoát khỏi phần thực thi. Khi hủy để dừng một service, cần một cơ chế shutdown/drain riêng; không dùng một cờ Future làm bằng chứng rằng mọi tài nguyên đã được giải phóng.

### 5.2. Mẫu xử lý interruption trong Runnable

```java
Runnable cancellable = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doSmallUnitOfWork();
            Thread.sleep(100);
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        // Kết thúc tác vụ, để vòng ngoài không tiếp tục chạy.
    } finally {
        releaseOwnedResources();
    }
};
```

Đây là mảnh minh họa; `doSmallUnitOfWork` và `releaseOwnedResources` phải do ứng dụng định nghĩa. Code phải được thiết kế sao cho `doSmallUnitOfWork()` tự không chạy vô hạn. Trong phương thức `finally`, chỉ giải phóng tài nguyên mà task thực sự sở hữu; đừng đóng scheduler chung của cả ứng dụng.

## 6. isDone/isCancelled: bảng trạng thái cần ghi nhớ

| Tình huống | `isDone()` | `isCancelled()` | Giải thích |
|---|---|---|---|
| One-shot đã được nhận, chưa đến giờ | Thường `false` | `false` | Còn chờ đến thời điểm chạy |
| One-shot đang thực thi | Thường `false` | `false` | Chưa hoàn tất Future |
| One-shot chạy xong bình thường | `true` | `false` | Đã kết thúc thành công |
| One-shot chạy và ném exception được propagate | `true` | `false` | Đã kết thúc thất bại |
| Future đã được hủy thành công | `true` | `true` | Terminal state là cancel |
| Periodic còn hoạt động dù chạy nhiều lượt | Thường `false` | `false` | Cả chuỗi lịch vẫn còn |
| Periodic dừng do propagated error | Có thể `true` | `false` | Phụ thuộc error policy của scheduler |
| Periodic của Spring được mặc định log/suppress lỗi | Thường vẫn `false` | `false` | Chuỗi có thể tiếp tục sau lỗi của một lượt |

**Cẩn thận với trường hợp Spring mặc định:** `ThreadPoolTaskScheduler` truyền thống bọc task bằng cơ chế `TaskUtils`. Mặc định, exception của tác vụ **lặp** thường được **log và suppress** để lịch còn cơ hội chạy lượt sau; tác vụ **một lần** thường được log và propagate. Vì vậy không thể sao chép nguyên kết luận của `ScheduledThreadPoolExecutor` Java thuần rằng một exception trong periodic runnable luôn tự chấm dứt lịch. Cần xem `ErrorHandler` của scheduler đang dùng.

## 7. Một chương trình Java 17 thuần chứng minh việc hủy

`ScheduledFuture` là API Java tiêu chuẩn, nên có thể kiểm tra các trạng thái căn bản mà **không cần Spring**. Ví dụ dưới đây lập lịch một công việc sau một ngày, hủy trước khi nó chạy, rồi kiểm tra trạng thái và hành vi `get()`.

**Tệp `ScheduledFutureCancelDemo.java` — chạy độc lập bằng JDK 17:**

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ScheduledFutureCancelDemo {
    public static void main(String[] args) {
        ScheduledThreadPoolExecutor executor =
                new ScheduledThreadPoolExecutor(1);
        executor.setRemoveOnCancelPolicy(true);
        AtomicInteger executions = new AtomicInteger();

        try {
            ScheduledFuture<?> handle = executor.schedule(
                    executions::incrementAndGet,
                    1, TimeUnit.DAYS);

            System.out.println("Còn trì hoãn: "
                    + (handle.getDelay(TimeUnit.SECONDS) > 0));

            System.out.println("Hủy được: " + handle.cancel(false));
            System.out.println("Đã hủy: " + handle.isCancelled());
            System.out.println("Đã kết thúc: " + handle.isDone());

            try {
                handle.get();
            } catch (CancellationException expected) {
                System.out.println("get(): CancellationException");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(interrupted);
            } catch (java.util.concurrent.ExecutionException failure) {
                throw new IllegalStateException(failure);
            }

            System.out.println("Số lần chạy: " + executions.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ScheduledFutureCancelDemo.java
java ScheduledFutureCancelDemo
```

Đầu ra trong điều kiện thời gian đồng hồ thông thường:

```text
Còn trì hoãn: true
Hủy được: true
Đã hủy: true
Đã kết thúc: true
get(): CancellationException
Số lần chạy: 0
```

Tại sao kết quả ổn định? Lịch được đặt cách một ngày, chương trình hủy ngay trong cùng luồng trước khi tới hạn. `cancel(false)` đánh dấu Future bị hủy, `get()` ném `CancellationException` thay vì đợi một ngày, và `executions` chưa được tăng. Với máy bị đóng băng tới hơn một ngày hoặc đồng hồ hệ thống bất thường, đầu ra về delay không còn là điều có thể bảo đảm; ví dụ cố ý dùng khoảng trì hoãn lớn để minh họa bình thường.

**`setRemoveOnCancelPolicy(true)`** giúp `ScheduledThreadPoolExecutor` loại bỏ task đã hủy khỏi queue kịp thời thay vì giữ nó tới khi hết thời gian trì hoãn. Đây là tùy chọn về quản lý queue, **không thay đổi ngữ nghĩa `cancel(false)`** và không xóa nghiệp vụ nào đã hoàn tất.

## 8. Một lần và nhiều lần: sử dụng get() như thế nào?

### 8.1. One-shot Runnable

Với lịch một lần, `get(timeout)` có thể dùng để chờ việc hoàn tất (hoặc phát hiện lỗi). Một `Runnable` không trả giá trị nghiệp vụ; khi hoàn tất bình thường, `get()` trả `null` theo hợp đồng của `ScheduledExecutorService`.

```java
ScheduledFuture<?> future = scheduler.schedule(
        () -> generateDailySnapshot(),
        Instant.now());

try {
    Object value = future.get(10, TimeUnit.SECONDS);
    // value thường null khi Runnable hoàn tất bình thường.
} catch (TimeoutException timeout) {
    future.cancel(true);
}
```

Đây là mảnh code đặt trong method có `scheduler`/`generateDailySnapshot` và import các lớp Java tương ứng; method còn phải xử lý `InterruptedException` và `ExecutionException` hoặc khai báo `throws`. `get(timeout)` chặn caller tới khi Future hoàn tất hoặc thời gian chờ hết. **Timeout không tự hủy**: gọi `cancel(...)` riêng nếu phù hợp, rồi xử lý deadline và side effect nghiệp vụ.

### 8.2. Periodic Runnable

Với công việc lặp đang hoạt động, **đừng gọi `get()` để “đợi một lượt cron vừa chạy xong”**. Future đại diện cho chuỗi, nên lời gọi có thể chặn vô thời hạn nếu lịch tiếp tục chạy bình thường. Trong Java `ScheduledExecutorService`, `get()` của periodic Future không trả bình thường; nó chỉ thoát bằng hủy/lỗi/đứt quãng theo hợp đồng.

Một mẫu sai:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        this::refresh, Duration.ofMinutes(1));
future.get(); // Có thể chờ mãi vì lịch còn chạy.
```

Đây là mảnh code **phản ví dụ**, không dùng trong luồng HTTP hay đường khởi tạo nếu chưa có kế hoạch dừng rõ. Với Spring, `ErrorHandler` mặc định có thể suppress lỗi lặp, làm Future tiếp tục tồn tại dù một lượt đã thất bại.

Nếu cần biết **lượt gần nhất** xong hay chưa, ghi nhận riêng: `AtomicInteger` đếm lượt, `CountDownLatch` cho một mốc cụ thể trong test, `CompletableFuture` per-run nếu API thiết kế như vậy, hoặc lưu `lastExecutionStatus` trong kho trạng thái có kiểm soát.

## 9. Dùng ScheduledFuture trong Spring ThreadPoolTaskScheduler

`ThreadPoolTaskScheduler` là triển khai thông dụng của Spring `TaskScheduler`, dùng `ScheduledThreadPoolExecutor` bên dưới. Nó có `setPoolSize(...)`, `setThreadNamePrefix(...)`, `setErrorHandler(...)`, `setRemoveOnCancelPolicy(...)` và các tùy chọn lifecycle/shutdown.

**Tệp `SchedulerConfig.java` — Spring Configuration, không độc lập:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class SchedulerConfig {

    @Bean("jobScheduler")
    public ThreadPoolTaskScheduler jobScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("job-clock-");
        scheduler.setRemoveOnCancelPolicy(true);

        return scheduler;
    }
}
```

Spring quản lý khởi tạo và đóng bean này theo `ApplicationContext`. Một method service inject bean:

```java
import java.time.Duration;
import java.util.concurrent.ScheduledFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class AuditScheduleService {
    private final TaskScheduler scheduler;

    public AuditScheduleService(
            @Qualifier("jobScheduler") TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public ScheduledFuture<?> start() {
        return scheduler.scheduleWithFixedDelay(
                () -> System.out.println("audit tick"),
                Duration.ofMinutes(2));
    }
}
```

Đây là một **Spring component**, không phải chương trình Java SE standalone. Ở production, hãy **giữ handle trả về** nếu muốn hủy chính lịch đã tạo; nếu `start()` tạo lịch mới trên mỗi request mà không ai sở hữu handle, ứng dụng có thể tạo nhiều lịch trùng nhau và không có cách quản lý thuận tiện.

**Không cần `@EnableScheduling` cho lời gọi programmatic `scheduler.schedule*(...)` trực tiếp.** `@EnableScheduling` chủ yếu bật xử lý annotation `@Scheduled`; đó là cơ chế đăng ký khác. Dù vậy, một ứng dụng có thể sử dụng đồng thời cả hai.

### 9.1. Thiết kế handle theo vòng đời nghiệp vụ

Một service nhận lệnh “bật/tắt lịch cho report-X” cần giữ một handle theo report ID thay vì một biến dùng chung:

```text
Report-A  -> ScheduledFuture-A
Report-B  -> ScheduledFuture-B
Report-C  -> ScheduledFuture-C
```

Nếu client muốn tắt `Report-B`, service tra handle của B và `cancel(...)` đúng đối tượng. `ScheduledFuture` chỉ có hiệu lực trong tiến trình/container tạo lịch. Nó không phải ID có thể gửi ra ngoài để JVM khác tự tìm được Future, và nó không tồn tại sau khi ứng dụng restart.

## 10. Ví dụ Maven hoàn chỉnh: chạy một lần, hủy lịch định kỳ và hủy lịch chưa đến hạn

Ví dụ sau dùng **JDK 17+**, Maven và **Spring Framework 6.2.7**. Nó chứng minh cùng một `ThreadPoolTaskScheduler` có thể:

1. Chạy `Runnable` một lần, rồi `get(...)` chờ kết quả `null`.
2. Chạy lịch fixed delay với chu kỳ rất dài, đợi lượt đầu qua `CountDownLatch` rồi gọi `cancel(false)` để ngăn lượt kế tiếp.
3. Đăng ký một job cách một giờ và hủy trước khi chạy.

Lý do dùng chu kỳ dài và latch là để có **stdout có thể kiểm chứng mà không dựa vào `Thread.sleep` hoặc cuộc đua giữa worker**.

### 10.1. Cấu trúc thư mục

```text
scheduled-handle-demo/
├── pom.xml
└── src/main/java/lesson/ScheduledHandleDemo.java
```

### 10.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>scheduled-handle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. Tệp src/main/java/lesson/ScheduledHandleDemo.java

```java
package lesson;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class ScheduledHandleDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskScheduler scheduler = context.getBean(
                    "demoScheduler", TaskScheduler.class);

            AtomicInteger onceCount = new AtomicInteger();
            ScheduledFuture<?> once = scheduler.schedule(
                    onceCount::incrementAndGet,
                    Instant.now());

            Object oneResult = once.get(5, TimeUnit.SECONDS);
            System.out.println("Một lần xong: " + once.isDone());
            System.out.println("Kết quả Runnable là null: "
                    + (oneResult == null));
            System.out.println("Số lượt một lần: "
                    + onceCount.get());

            CountDownLatch firstTick = new CountDownLatch(1);
            AtomicInteger tickCount = new AtomicInteger();

            ScheduledFuture<?> recurring =
                    scheduler.scheduleWithFixedDelay(() -> {
                        tickCount.incrementAndGet();
                        firstTick.countDown();
                    }, Duration.ofHours(1));

            if (!firstTick.await(5, TimeUnit.SECONDS)) {
                recurring.cancel(true);
                throw new IllegalStateException("Không có lượt đầu");
            }

            System.out.println("Hủy lịch lặp: "
                    + recurring.cancel(false));
            System.out.println("Lịch lặp đã hủy: "
                    + recurring.isCancelled());
            System.out.println("Số lượt đã chạy: "
                    + tickCount.get());

            AtomicInteger lateRuns = new AtomicInteger();
            ScheduledFuture<?> later = scheduler.schedule(
                    lateRuns::incrementAndGet,
                    Instant.now().plus(Duration.ofHours(1)));

            System.out.println("Hủy lịch chờ: "
                    + later.cancel(false));
            System.out.println("Lịch chờ đã chạy: "
                    + lateRuns.get());
        }
    }

    @Configuration
    public static class Config {
        @Bean("demoScheduler")
        public ThreadPoolTaskScheduler demoScheduler() {
            ThreadPoolTaskScheduler scheduler =
                    new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(2);
            scheduler.setThreadNamePrefix("schedule-demo-");
            scheduler.setRemoveOnCancelPolicy(true);
            return scheduler;
        }
    }
}
```

### 10.4. Biên dịch và chạy

Trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.ScheduledHandleDemo
```

**Tám dòng do chương trình in ra trong môi trường chạy bình thường:**

```text
Một lần xong: true
Kết quả Runnable là null: true
Số lượt một lần: 1
Hủy lịch lặp: true
Lịch lặp đã hủy: true
Số lượt đã chạy: 1
Hủy lịch chờ: true
Lịch chờ đã chạy: 0
```

Các dòng trên do chương trình in theo các lệnh `println`, không tính log riêng của Maven/Spring. Timeout 5 giây làm chương trình báo lỗi rõ ràng khi worker không được thực thi kịp trên máy quá tải, thay vì treo vô hạn.

Giải thích tính ổn định:

- `once.get(5, TimeUnit.SECONDS)` chờ một task one-shot đã hoàn tất; `Runnable` không trả giá trị nên `oneResult` là `null`, còn `onceCount` là 1.
- `scheduleWithFixedDelay(..., Duration.ofHours(1))` cho lượt đầu chạy ngay; `firstTick.await` xác nhận nó đã increment và báo chốt. Lượt tiếp theo chỉ đến sau **một giờ kể từ khi lượt trước kết thúc**.
- `recurring.cancel(false)` yêu cầu chấm dứt chuỗi định kỳ, không cần interrupt worker. Khi vẫn còn lịch tương lai, Future chưa tự hoàn tất bình thường sau lượt đầu.
- `later` là lịch một lần sau một giờ, được hủy trước khi đến hạn. Vì vậy `lateRuns` bằng 0 khi in.
- `try-with-resources` đóng Spring context, giao trách nhiệm kết thúc bean scheduler cho Spring; service không tự shutdown một scheduler dùng chung.

Ví dụ này minh họa **hợp đồng handle và hủy**, không phải cách triển khai một hệ thống job bền vững. Số worker 2, thời gian 1 giờ và các timeout được chọn cho tính minh họa, không có nghĩa phù hợp với production.

## 11. Tránh hiểu lầm: cancel(false) không chờ lượt hiện tại kết thúc

Hãy tưởng tượng một task đang chạy:

```text
T=0s       worker bắt đầu gửi file lớn
T=1s       caller gọi future.cancel(false)
T=1.001s   future.isCancelled() có thể true
T=10s      worker gửi file xong và giải phóng connection
```

`cancel(false)` có thể đánh dấu lịch bị hủy tại T=1s để ngăn lần lặp sau, nhưng **không ép dừng lượt đang chạy**. Nếu code quản lý job lập tức xóa tất cả trạng thái và giải phóng tài nguyên dùng chung ngay T=1.001s, worker vẫn có thể truy cập những tài nguyên đó và xảy ra race.

Một giao thức stop thường cần **hai giai đoạn**:

1. **Không lên lịch thêm lượt mới**: giữ handle và hủy lịch, thường với `cancel(false)` nếu muốn graceful.
2. **Chờ/quan sát các lượt đang chạy kết thúc**: dùng `CountDownLatch`, `Phaser`, bộ đếm active, trạng thái job hoặc shutdown/await termination ở cấp tài nguyên phù hợp.

Không sử dụng `future.get()` cho lịch periodic để chờ một lượt đã bắt đầu vì nó theo dõi **cả chuỗi**. Với task có I/O, thêm timeout và chính sách hủy/đối soát riêng.

## 12. Khi nào nên dùng cancel(true)?

Một trường hợp phù hợp là task hỗ trợ interruption, công việc có thể hủy giữa chừng và không có side effect nửa vời nguy hiểm.

```java
Runnable job = () -> {
    try {
        for (int i = 0; i < 100; i++) {
            if (Thread.currentThread().isInterrupted()) {
                return;
            }
            performSmallBatch(i);
        }
    } finally {
        closeOwnedResources();
    }
};
```

Đây là **mảnh code minh họa**, với `performSmallBatch`/`closeOwnedResources` thuộc ứng dụng. Người gọi có thể yêu cầu `handle.cancel(true)`; task phải kiểm tra interrupted một cách có chủ đích, đồng thời bảo đảm tài nguyên được giải phóng.

Nếu mỗi batch thao tác database rồi commit từng phần, interruption không rollback các batch trước. Vì vậy hủy một job quan trọng phải có trạng thái `CANCEL_REQUESTED`, `CANCELLED`, `PARTIAL` hoặc tương đương nếu nghiệp vụ yêu cầu; không đồng nhất cờ Future với kết quả nghiệp vụ cuối cùng.

**Cẩn thận:** Một số thư viện dùng interruption để điều phối nội bộ. Hãy đọc contract trước khi interrupt worker của scheduler chung, đặc biệt khi tác vụ có callback hoặc tài nguyên dùng chung.

## 13. Quản lý nhiều lịch trong service bằng handle registry

Nếu người dùng có thể bật/tắt nhiều lịch, không thể chỉ giữ một biến `ScheduledFuture<?> last`. Một cách đơn giản trong **một JVM** là map từ job ID sang handle.

**Tệp `ManagedScheduleService.java` — Spring-managed component minh họa:**

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ScheduledFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class ManagedScheduleService {

    private final TaskScheduler scheduler;
    private final Map<String, ScheduledFuture<?>> handles =
            new HashMap<>();

    public ManagedScheduleService(
            @Qualifier("jobScheduler") TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public synchronized void replace(
            String jobId, Runnable work, Duration delay) {

        Objects.requireNonNull(jobId);
        Objects.requireNonNull(work);
        if (delay.isZero() || delay.isNegative()) {
            throw new IllegalArgumentException(
                    "Delay phải dương");
        }

        ScheduledFuture<?> fresh =
                scheduler.scheduleWithFixedDelay(work, delay);

        ScheduledFuture<?> previous = handles.put(jobId, fresh);
        if (previous != null) {
            previous.cancel(false);
        }
    }

    public synchronized boolean stop(String jobId) {
        ScheduledFuture<?> handle = handles.remove(jobId);
        return handle != null && handle.cancel(false);
    }

    public synchronized boolean isRegistered(String jobId) {
        return handles.containsKey(jobId);
    }
}
```

Đây là **class Spring**, không có `main` độc lập. Khóa `synchronized` bảo vệ các thao tác map khi nhiều request cùng gọi `replace/stop` trong cùng instance. Nó **không** giữ khóa trong lúc chạy `work`; phần nghiệp vụ được scheduler thực hiện bên ngoài khóa.

Các giới hạn của mẫu cần được nói rõ:

- `scheduleWithFixedDelay` có thể chạy lượt đầu **rất sớm**. Vì vậy khi thay lịch, có một khoảng ngắn cả `fresh` và lượt cũ có thể tồn tại/chạy đồng thời trước khi `previous.cancel(false)` có tác dụng.
- `cancel(false)` trên lịch cũ không ngắt lượt cũ đang thực thi. Nếu tuyệt đối không được chồng tác động của hai phiên bản job, cần cơ chế serialization/lease/idempotency ở cấp nghiệp vụ.
- `isRegistered` chỉ nói map có handle, không bảo đảm lịch còn sống. Có thể bổ sung logic kiểm tra `isCancelled`/`isDone` hoặc một registry trạng thái chặt hơn.
- Khi `scheduleWithFixedDelay` bị từ chối, phương thức ném exception trước khi thay map, nên handle cũ vẫn được giữ. Phải xử lý lỗi gửi lịch tại biên API.
- Map và Future chỉ sống trong **một tiến trình**. Chạy nhiều pod sẽ có các registry khác nhau; không có cơ chế chọn leader hoặc đồng bộ hủy ở đây.
- Không giữ `ScheduledFuture` vô thời hạn trong map sau khi one-shot đã xong; cần dọn những entry không còn dùng để tránh giữ tham chiếu và tài nguyên.
- Mẫu dùng `HashMap + synchronized` là minh họa quản lý một registry nhỏ. Với tải lớn, lifecycle nhiều trạng thái hoặc yêu cầu cluster, nên xây abstraction chuyên dụng và test nhiều luồng.

### 13.1. API hủy theo job ID

Một controller có thể gọi `managedScheduleService.stop(jobId)` để gửi yêu cầu hủy. HTTP response nên phản ánh **yêu cầu hủy ở scheduler cục bộ đã được chấp nhận hay chưa**, không tuyên bố mọi side effect đã dừng tức thì.

Nếu người dùng cần biết dừng hoàn toàn, API thường phải có trạng thái công việc và cơ chế đối soát với lượt đang chạy. Đối với hệ phân tán, một job ID nên được lưu ở kho bền vững và gắn với scheduler owner/lease thay vì trả đối tượng `ScheduledFuture` trực tiếp cho client.

## 14. CronTrigger và trường hợp không có lịch tiếp theo

`TaskScheduler.schedule(Runnable, Trigger)` có thể trả `null` khi `Trigger.nextExecution(...)` không cho thời điểm nào. Ví dụ một `Trigger` giới hạn số lượt hoặc không còn thỏa điều kiện nghiệp vụ.

```java
import java.util.concurrent.ScheduledFuture;
import org.springframework.scheduling.Trigger;

public ScheduledFuture<?> register(
        Runnable work, Trigger trigger) {
    return scheduler.schedule(work, trigger);
}
```

Đây là method minh họa trong class có `scheduler`. API có thể trả `null`, nên caller cần kiểm tra:

```java
ScheduledFuture<?> handle = register(work, trigger);
if (handle == null) {
    System.out.println("Không có lịch kế tiếp");
} else {
    saveHandle(handle);
}
```

Không nên gọi `handle.cancel(false)` khi `handle == null`. Đồng thời, `getDelay(...)` trên một ScheduledFuture của trigger chỉ là thông tin trì hoãn theo implementation tại thời điểm đọc, **không phải API metadata toàn bộ lịch cron**. Để hiển thị lịch theo timezone và rule, quản lý riêng biểu thức cron, vùng thời gian và lần chạy gần nhất.

Với `CronTrigger` chạy theo thời gian thực, các sự kiện **DST**, sửa giờ hệ thống, restart, một lượt kéo dài hoặc giờ không tồn tại ở một timezone có thể thay đổi thời điểm thực thi thực tế. Không giả định “cron lúc 02:30” chắc chắn xảy ra đúng một lần mỗi ngày ở mọi timezone.

## 15. @Scheduled và TaskScheduler programmatic khác nhau

Spring có hai mô hình tương tự nhưng khác cách quản lý handle:

| Cách dùng | Ai đăng ký lịch? | Handle đi đâu? | Khi nào phù hợp? |
|---|---|---|---|
| `taskScheduler.schedule(...)` trong service | Code ứng dụng | Được trả trực tiếp dưới dạng `ScheduledFuture<?>` | Cần bật/tắt/thay lịch theo job ID lúc runtime |
| `@Scheduled(fixedDelay=...)` trên method Spring | Hạ tầng annotation scheduling | Không trả ScheduledFuture trực tiếp từ lời gọi method | Lịch tĩnh theo cấu hình, do container quản lý |
| `ScheduledTaskRegistrar`/`ScheduledTask` | Spring scheduling registration API | Handle `ScheduledTask` riêng, có `cancel(...)` | Khi quản lý các task đăng ký qua registrar |

Ví dụ annotation:

```java
import org.springframework.scheduling.annotation.Scheduled;

@Scheduled(fixedDelay = 60000)
public void cleanCache() {
    // Spring tự đăng ký và lập lịch dựa trên annotation.
}
```

Đây là **mảnh method Spring**, cần bean hợp lệ và `@EnableScheduling` hoặc cơ chế tương đương để annotation được xử lý. Lời gọi bình thường `cleanCache()` **không trả ScheduledFuture**. Nếu cần hủy theo lựa chọn người dùng mà không phải ngừng cả bean, cân nhắc chuyển phần lập lịch sang service dùng `TaskScheduler` programmatic.

Không tự lấy một `ScheduledFuture` giả định từ `@Scheduled` nếu code chưa đăng ký/thu giữ handle; và không shutdown scheduler toàn ứng dụng chỉ để tắt một lịch cụ thể.

## 16. Exception của task định kỳ: khác biệt Spring và Java chuẩn

Đây là một điểm quan trọng khi dùng `ScheduledFuture` để **theo dõi lỗi**.

### 16.1. Java ScheduledExecutorService thuần

Với `ScheduledThreadPoolExecutor.scheduleAtFixedRate(...)` và `scheduleWithFixedDelay(...)`, nếu một lượt thực thi ném exception ra ngoài, Java ghi nhận **kết thúc bất thường của chuỗi periodic**. Những lượt tiếp theo bị dừng; `isDone()` có thể chuyển `true` và `get()` ném `ExecutionException` chứa nguyên nhân.

### 16.2. Spring ThreadPoolTaskScheduler mặc định

Spring thường bọc `Runnable` bằng error-handling wrapper. `TaskUtils.getDefaultErrorHandler(isRepeatingTask)` trả chính sách khác nhau:

- **Task lặp:** ghi log và **suppress** exception theo mặc định, để lịch có thể tiếp tục.
- **Task một lần:** ghi log và **propagate** exception theo mặc định, vì caller có thể quan sát lỗi qua Future.

Do đó, ngay cả khi một lượt `@Scheduled`/programmatic periodic xảy ra lỗi, `ScheduledFuture.isDone()` vẫn có thể là `false` và lịch vẫn có lượt tiếp theo. **Không dựa vào `isDone()` để tính số lượt lỗi**, mà nên ghi nhận kết quả của từng lần chạy.

### 16.3. Cấu hình ErrorHandler nếu cần chính sách khác

`ThreadPoolTaskScheduler` có:

```java
scheduler.setErrorHandler(error -> {
    logScheduledFailure(error);
});
```

Đây là **mảnh cấu hình** với `logScheduledFailure` do ứng dụng định nghĩa. Nếu handler chỉ log và không ném tiếp, nó có thể **suppress lỗi**. Nếu muốn chấm dứt lịch sau một exception, cần chính sách propagate và phải hiểu điều này ảnh hưởng đến Future/chuỗi periodic.

Spring có `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` để log rồi ném lại, nhưng sử dụng nó phải là **quyết định nghiệp vụ có chủ đích**. Dùng một handler global kiểu propagate có thể khiến nhiều lịch vốn phải tự phục hồi bị dừng vì lỗi tạm thời.

Không nhầm `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` dành cho `@Async void` với `ThreadPoolTaskScheduler.setErrorHandler(...)` dành cho scheduler. Đây là hai đường xử lý lỗi khác nhau.

## 17. Hủy lịch và loại bỏ task khỏi queue

Trong `ThreadPoolTaskScheduler` dựa trên `ScheduledThreadPoolExecutor`, một task đã bị hủy nhưng chưa đến hạn có thể còn được giữ trong queue tới thời điểm xử lý, tùy **remove-on-cancel policy**.

Cấu hình:

```java
ThreadPoolTaskScheduler scheduler =
        new ThreadPoolTaskScheduler();

scheduler.setPoolSize(2);
scheduler.setRemoveOnCancelPolicy(true);
```

Đây là mảnh cấu hình trước khi Spring khởi tạo bean. `setRemoveOnCancelPolicy(true)` yêu cầu underlying `ScheduledThreadPoolExecutor` loại bỏ task bị cancel khỏi queue sớm khi có thể. Điều này hữu ích nếu ứng dụng liên tục tạo rồi hủy hàng nghìn lịch tương lai.

Tuy nhiên:

- Nó **không hủy tất cả lịch**; chính code gọi `handle.cancel(...)` mới lựa chọn lịch cần hủy.
- Nó **không ngắt task đang chạy**; `cancel(true)` và khả năng hợp tác của task quyết định việc yêu cầu interruption.
- Nó **không tạo giới hạn dung lượng queue** như `queueCapacity` của `ThreadPoolTaskExecutor`.
- Nó **không thay thế cleanup map/registry** chứa handle do ứng dụng lưu.
- Khi dùng một implementation `TaskScheduler` khác, cần kiểm tra API chính sách tương ứng; không giả định setter này tồn tại trên interface `TaskScheduler`.

Đối với hệ thống nhiều tenant, hãy đo `queue depth`, số lịch active/cancelled và retained heap. Không dùng việc để queue không giới hạn như một cơ chế giữ job bền vững qua restart.

## 18. Shutdown: hủy từng lịch khác với đóng scheduler

`future.cancel(...)` nhắm tới **một handle cụ thể**. Ngược lại, `scheduler.shutdown()` ở tầng executor/scheduler có tác động tới toàn bộ tập công việc của pool và chính sách nhận lịch mới.

Trong Spring, một `ThreadPoolTaskScheduler` được khai báo `@Bean` được quản lý bởi `ApplicationContext`. Một service nghiệp vụ **không nên gọi `shutdown()` trên bean chung** khi chỉ muốn dừng một job của mình. Làm vậy có thể khiến các service khác bị `TaskRejectedException` khi cố đặt lịch.

Các chính sách cần chú ý:

- `setContinueExistingPeriodicTasksAfterShutdownPolicy(...)`: có tiếp tục các tác vụ periodic hiện có sau shutdown hay không.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(...)`: có thực thi những one-shot đã đặt lịch nhưng chưa đến hạn sau shutdown hay không.
- `setWaitForTasksToCompleteOnShutdown(...)` và các cấu hình lifecycle của Spring: quyết định đợi/không đợi như thế nào khi đóng context.

Trong Spring `ThreadPoolTaskScheduler` 6.2.7, `continueExistingPeriodicTasksAfterShutdown` mặc định là `false`; `executeExistingDelayedTasksAfterShutdown` mặc định là `true` trên ScheduledThreadPoolExecutor. Ứng dụng có yêu cầu **không chạy tác vụ sau khi bắt đầu shutdown** cần thiết kế chính sách rõ, kiểm tra version và thử nghiệm hành vi thật.

Hãy kiểm thử tắt ứng dụng khi có: one-shot chưa đến hạn, periodic đang chạy, periodic đang chờ, task bị interrupt, và lịch đang được thay đổi. Đối với job không được mất khi restart, cần persistence/broker hoặc distributed scheduler, không chỉ giữ `ScheduledFuture` trong heap.

## 19. Giám sát lịch: trạng thái handle chưa đủ

Một dashboard tốt cần phân biệt **đăng ký lịch**, **lần chạy**, **hủy**, **lỗi** và **kết thúc vòng đời**.

| Chỉ số/trường | Ý nghĩa | Nguồn có thể lấy |
|---|---|---|
| `schedule.registered` | Lịch được đăng ký thành công | Service quản lý handle |
| `schedule.cancel.requested` | Có yêu cầu hủy | Lệnh điều khiển |
| `schedule.cancel.accepted` | `cancel(...)` trả `true` | Kết quả Future |
| `schedule.active` | Lịch còn hoạt động theo nghiệp vụ | Registry + trạng thái Future |
| `run.started` | Một lượt đã bắt đầu | Wrapper quanh Runnable |
| `run.succeeded` | Một lượt hoàn tất thành công | Wrapper/logic nghiệp vụ |
| `run.failed` | Một lượt ném exception | Wrapper/ErrorHandler |
| `run.duration` | Thời gian thực thi một lượt | Timer per run |
| `run.lastSucceededAt` | Lần hoàn tất thành công gần nhất | State store |
| `schedule.nextDue` | Lần kích hoạt dự kiến | Trigger/metadata do ứng dụng quản lý |

`isDone()`/`isCancelled()` trả snapshot trạng thái Future, không tự cung cấp `lastSucceededAt`, số lượt và lỗi. `getDelay(...)` có thể gợi ý khoảng chờ kế tiếp nhưng không phải cách đáng tin cậy để tính SLO hoặc SLA từng job.

Một wrapper đo số lần chạy minh họa:

```java
AtomicInteger successCount = new AtomicInteger();

Runnable monitored = () -> {
    long startNs = System.nanoTime();
    try {
        executeBusinessStep();
        successCount.incrementAndGet();
    } finally {
        long elapsedNs = System.nanoTime() - startNs;
        recordDuration(elapsedNs);
    }
};
```

Đây là mảnh code với `executeBusinessStep`/`recordDuration` do ứng dụng định nghĩa. Để đếm lỗi, thêm `catch` phù hợp và quyết định ném lại hay suppress theo error policy của lịch. Nếu job có side effect, “không ném exception” chưa chắc là thành công cuối cùng ở dịch vụ ngoài.

## 20. Quản lý cron sau restart hoặc nhiều instance

`ScheduledFuture` là handle cục bộ trong JVM, không phải một cơ chế điều phối phân tán. Nếu một ứng dụng chạy trên ba pod và cả ba cùng gọi `scheduleAtFixedRate(...)` khi khởi động, thông thường sẽ có **ba lịch** độc lập và task có thể chạy ba lần.

Hủy Future ở pod A không tự hủy Future ở pod B/C. Cũng không có bảo đảm job sống qua:

- JVM crash hoặc kill -9.
- Pod bị thay thế/rolling deployment.
- Toàn bộ Spring ApplicationContext được tạo lại.
- Thay đổi người sở hữu job trong cluster.

Nếu công việc phải được bảo đảm và thực thi một lần theo hợp đồng nghiệp vụ, cân nhắc **leader election, distributed lock/lease, kho công việc bền vững, outbox hoặc scheduler chuyên dụng**. Dù chọn giải pháp nào, vẫn cần idempotency và chính sách retry/đối soát.

Nếu người dùng có nút “Tắt lịch”, hệ thống nhiều instance phải có giao thức truyền lệnh đến đúng owner hoặc đổi trạng thái trong kho phân tán để các owner tuân theo. `cancel(false)` tại một tiến trình không phải một API hủy cluster.

## 21. Các lỗi thường gặp khi sử dụng ScheduledFuture

| Sai lầm | Vì sao sai? | Cách làm đúng |
|---|---|---|
| Lập lịch nhưng bỏ Future trả về | Không còn handle thuận tiện để hủy riêng lịch | Lưu handle theo job ID nếu có yêu cầu điều khiển |
| Dùng `get()` của periodic Future để đợi một lượt | Có thể chờ mãi khi chuỗi lịch còn hoạt động | Dùng latch/counter/trạng thái per-run |
| Coi `isDone()` là “lượt gần nhất thành công” | Future của lịch lặp bao quát cả chuỗi | Đo từng lượt chạy riêng |
| Coi `isCancelled()` là worker đã dừng | `cancel(false)` không ngắt lượt đang chạy | Chờ mốc task hoàn tất nếu cần graceful stop |
| Gọi `cancel(true)` và tin đã rollback dữ liệu | Interruption là hợp tác; side effect không tự hoàn tác | Timeout, kiểm tra interrupted, idempotency |
| Không kiểm tra `null` từ `schedule(task, trigger)` | Trigger có thể không cho next execution | Xử lý nullable trước khi lưu/hủy |
| Cùng job ID đăng ký lặp mà không hủy lịch cũ | Nhiều handle cùng kích hoạt | Quản lý registry và chính sách replace |
| Chỉ tăng poolSize khi lịch chậm | Có thể do task blocking hoặc tài nguyên ngoài | Đo run duration, queue wait, downstream |
| Dùng scheduler cho I/O chặn lâu | Giữ thread lập lịch, làm trễ job khác | Giới hạn/chuyển tác vụ nặng qua executor phù hợp |
| Không hiểu Spring ErrorHandler | Lỗi periodic có thể bị suppress và vẫn chạy | Cấu hình/giám sát lỗi per-run |
| Gọi `scheduler.shutdown()` để tắt một report | Làm hỏng các lịch dùng chung pool | Gọi `handle.cancel(...)` |
| Không dọn handle one-shot đã xong | Map giữ tham chiếu và tăng memory | Cleanup registry theo lifecycle |
| Tưởng removeOnCancelPolicy là queueCapacity | Nó chỉ thay chính sách loại bỏ task bị cancel | Quản lý tải/worker/retained heap riêng |
| Ghi `@Scheduled` rồi gọi method để lấy Future | Annotation registration không trả Future cho caller method | Chọn programmatic TaskScheduler khi cần handle |
| Lưu ScheduledFuture vào database | Đây là object JVM không phải ID bền vững | Lưu job metadata/trạng thái/cron, tạo handle mới sau restart |

## 22. Kiểm thử scheduled cancellation có thể lặp lại

Concurrency test dựa vào `Thread.sleep(100)` rồi dự đoán trạng thái rất dễ flake trên CI. Dùng `CountDownLatch`/`Future.get(timeout)` để chứng minh mốc thực tế.

Những kịch bản tối thiểu:

1. **One-shot chưa đến hạn:** đăng ký xa trong tương lai, hủy trước khi chạy; khẳng định `isCancelled`/`isDone` và side effect chưa xảy ra.
2. **One-shot hoàn tất:** đặt lịch ngay, dùng `get(timeout)`; kỳ vọng `get()` trả `null` cho `Runnable` và side effect đã xảy ra.
3. **Periodic đã chạy một lượt:** latch báo lần đầu, gọi `cancel(false)`, xác nhận không có lần tiếp theo trong cửa sổ thử hợp lý; không dùng sleep làm bằng chứng duy nhất.
4. **Periodic đang chạy:** giữ task ở latch, gọi `cancel(false)`; giải phóng latch rồi quan sát worker kết thúc. Chứng minh Future có thể đã cancelled trước khi logic task thoát.
5. **Hủy có interrupt:** task chặn ở API hỗ trợ interruption, gọi `cancel(true)`; xác minh task nhận interruption và cleanup chạy. Đặt timeout để test không treo.
6. **Trigger không có lần chạy:** xây Trigger trả `null`, xác minh `schedule(...)` có thể trả `null`.
7. **Lỗi periodic:** test cả chính sách Spring suppress mặc định và handler propagate nếu nghiệp vụ muốn dừng.
8. **Đăng ký lại cùng job ID:** bảo đảm không tạo nhiều lịch ngoài dự định khi hai caller cùng cập nhật.
9. **Shutdown:** xác minh tác vụ đã nhận và task chưa đến hạn được xử lý theo policy đã cấu hình.
10. **Nhiều node:** test hợp đồng điều phối riêng nếu dùng cluster, không giả định Future được chia sẻ.

Một test có thể dùng một scheduler chỉ một worker với latch để tạo thứ tự kiểm soát được; nhưng đừng để task trong scheduler duy nhất chờ một Future khác cùng scheduler vì có thể gây starvation deadlock.

### 22.1. Một test minh họa cancellation trong lúc task đang chạy

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);
CountDownLatch exited = new CountDownLatch(1);

ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(() -> {
    started.countDown();
    try {
        release.await();
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    } finally {
        exited.countDown();
    }
}, Duration.ofHours(1));

if (!started.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Không thấy lượt đầu");
}

boolean cancelled = handle.cancel(false);
// Ở đây handle có thể đã cancelled, nhưng task vẫn chờ release.
release.countDown();

if (!exited.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Task chưa thoát");
}
```

Đây là **mảnh integration test** với `scheduler` đã được khởi tạo; method test cần xử lý `InterruptedException` và import concurrent classes. Latch `exited` tách biệt “Future đã bị hủy” với “thân Runnable đã thực sự kết thúc”. Nên dùng `try/finally` trong test thật để luôn giải phóng `release` kể cả khi assertion thất bại.

## 23. Bài tập thực hành

### Bài 1 — Phân biệt một lượt và cả lịch

Một `ScheduledFuture` từ `scheduleAtFixedRate(...)` đã có 20 lượt thành công. `isDone()` vẫn `false`. Đây có phải lỗi không?

**Đáp án định hướng:** Không. Handle đại diện cho chuỗi periodic, chưa kết thúc; số lượt thành công phải được lưu riêng.

### Bài 2 — Hủy không interrupt

Một job đang gửi tệp, caller dùng `cancel(false)` và nhận `true`. Có thể xóa ngay tài nguyên tệp được worker giữ không?

**Đáp án định hướng:** Chưa chắc. Lượt đang chạy có thể tiếp tục; cần phối hợp dừng hoàn toàn, cleanup và ownership của tài nguyên.

### Bài 3 — Hủy trước khi đến hạn

Đặt lịch one-shot sau một giờ. Hủy ngay bằng `cancel(false)`. `isDone` và `isCancelled` nên biểu diễn điều gì? `get()` hành xử ra sao?

**Đáp án định hướng:** Với Future bị hủy thành công, cả hai là `true`; `get()` ném `CancellationException` thay vì trả kết quả.

### Bài 4 — Spring khác Java thuần

Tại sao một periodic task ném exception nhưng vẫn chạy lượt sau trong `ThreadPoolTaskScheduler`, dù Java `ScheduledThreadPoolExecutor` thuần có thể dừng chuỗi?

**Đáp án định hướng:** Spring dùng error-handling wrapper; mặc định với task lặp thường log/suppress exception. Tìm `ThreadPoolTaskScheduler.setErrorHandler(...)` và `TaskUtils`.

### Bài 5 — @Scheduled và TaskScheduler

Muốn một người dùng tắt riêng lịch báo cáo của chính họ mà không dừng các lịch của người dùng khác. Chọn `@Scheduled` cố định hay API `TaskScheduler` programmatic?

**Đáp án định hướng:** Programmatic `TaskScheduler` thuận tiện hơn nếu cần lưu/cancel handle theo job ID, nhưng còn phải giải quyết concurrency và cluster ownership.

### Bài 6 — Cron Trigger nullable

Một custom Trigger không cho thời điểm kế tiếp. `scheduler.schedule(work, trigger)` trả `null`. Có nên đưa null vào registry rồi gọi `cancel(false)`?

**Đáp án định hướng:** Không. Xử lý tình huống “không có lịch” ngay từ đăng ký, trả trạng thái phù hợp cho caller.

### Bài 7 — Thiết kế graceful shutdown

Một job đang ở lượt thực thi dài, người dùng bấm “Stop”. Thiết kế hai giai đoạn sao cho không thông báo đã dừng hoàn toàn khi worker vẫn làm việc.

**Đáp án định hướng:** Cancel handle để ngừng lượt tiếp theo; theo dõi active run và đợi/quan sát thoát của lượt hiện tại, có timeout và chính sách ngắt/compensation riêng.

### Bài 8 — Chạy demo Java 17 và Spring

Chạy `ScheduledFutureCancelDemo.java` và `ScheduledHandleDemo.java`. Giải thích vì sao cả hai có thể hủy lịch tương lai, nhưng ví dụ Spring còn xử lý một lịch periodic sau khi đã có lượt đầu.

**Đáp án định hướng:** Cả hai dùng hợp đồng ScheduledFuture; ví dụ Spring trả handle từ `TaskScheduler`, dùng latch để đánh dấu lượt periodic đầu tiên trước khi hủy.

### Bài 9 — Nhiều pod

Ba pod cùng lập lịch một job. Một pod hủy Future nội bộ và trả “đã hủy toàn bộ”. Kết luận có chính xác không?

**Đáp án định hướng:** Không. Mỗi pod có scheduler và Future khác nhau. Cần cơ chế điều phối phân tán, trạng thái lưu bền vững và idempotency.

## 24. Checklist review trước khi triển khai

Khi một PR thêm lịch động có thể hủy, hãy kiểm tra:

1. Mỗi lịch có **owner** và một nơi lưu `ScheduledFuture<?>` theo job ID cục bộ.
2. Overload `TaskScheduler` được chọn đúng: one-shot, fixed rate, fixed delay hay Trigger.
3. `schedule(Runnable, Trigger)` xử lý trường hợp trả `null`.
4. `cancel(false)`/`cancel(true)` được chọn theo khả năng interruption và side effect của task.
5. Không tuyên bố “worker đã dừng” chỉ vì `isCancelled` là `true`.
6. Không gọi `get()` trên periodic Future để đợi một lượt đơn lẻ.
7. `isDone` được hiểu là terminal state của **cả Future**, không phải kết quả lượt cuối.
8. Có thống kê từng lượt chạy/thất bại nếu nghiệp vụ cần theo dõi.
9. ErrorHandler của Spring được xác định rõ; không nhầm với ngữ nghĩa lỗi của Java executor thuần.
10. `setRemoveOnCancelPolicy` được cân nhắc nếu có nhiều lịch chờ lâu bị hủy.
11. Scheduler có thread pool và chính sách shutdown được kiểm thử theo yêu cầu.
12. Không shutdown bean scheduler chung khi chỉ cần ngừng một handle.
13. Registry quản lý concurrency/replace/cancel, dọn handle đã xong và không bị rò tham chiếu.
14. Tác vụ không chặn scheduler thread quá lâu; có timeout/downstream bulkhead nếu cần.
15. Trong cluster, có cơ chế owner/leader/lease/idempotency nếu yêu cầu tránh chạy trùng.
16. Lịch quan trọng được lưu metadata ở nơi bền vững nếu phải sống qua restart.
17. Test dùng latch và Future với timeout, không phụ thuộc vào `Thread.sleep` và thứ tự in log.

## 25. Tổng kết

- **`ScheduledFuture<?>` là handle của lịch tạo bằng `TaskScheduler`**, dùng để quan sát trạng thái và yêu cầu hủy mà không cần dừng toàn bộ scheduler.
- **`isDone()` là trạng thái kết thúc Future, không phải “lượt định kỳ gần nhất thành công”.** `isCancelled()` chỉ biểu diễn trạng thái hủy của Future.
- **`cancel(false)` ngăn lượt tiếp theo nhưng không yêu cầu ngắt lượt đang chạy; `cancel(true)` chỉ cố gắng interrupt**, không bảo đảm hard stop hay rollback.
- **`getDelay(...)` là ước lượng độ trễ đến hạn**, không phải timestamp tuyệt đối, lịch sử hay SLO.
- **`get()` hữu dụng với one-shot**, nhưng có thể chờ vô hạn với chuỗi periodic còn sống; cần theo dõi từng lượt bằng state/callback riêng.
- **`schedule(task, Trigger)` có thể trả `null`**; phải xử lý trước khi lưu hoặc hủy.
- **Spring có error policy khác Java thuần ở lịch lặp**: exception có thể bị log/suppress để lịch tiếp tục, nên phải quan sát lỗi per-run.
- **Giữ handle theo job ID và quản lý lifecycle**, phân biệt cancel một job với shutdown scheduler chung; trong cluster cần giải pháp điều phối bền vững.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework Javadoc — TaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework 6.2.7 Javadoc — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework Javadoc — TaskUtils and ErrorHandler](https://docs.spring.io/spring-framework/docs/6.0.1/javadoc-api/org/springframework/scheduling/support/TaskUtils.html)
- [Java SE 17 Javadoc — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)
- [Java SE 17 Javadoc — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 Javadoc — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java SE 17 Javadoc — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
