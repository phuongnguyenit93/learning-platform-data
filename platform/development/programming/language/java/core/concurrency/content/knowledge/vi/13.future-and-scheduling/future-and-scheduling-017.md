# ScheduledThreadPoolExecutor.setRemoveOnCancelPolicy() và tác vụ bị hủy trong hàng đợi

Trong `java.util.concurrent.ScheduledThreadPoolExecutor`, một tác vụ được lên lịch **chưa đến hạn** có thể bị hủy bằng `ScheduledFuture.cancel(...)`. Hủy không có nghĩa task đang nằm trong **delayed queue** sẽ biến mất khỏi queue ngay: với chính sách mặc định, task bị hủy có thể **tiếp tục nằm trong queue cho đến khi tới thời điểm dự kiến chạy**. Nếu delay rất dài và ứng dụng hủy nhiều tác vụ, queue có thể giữ các task objects — cùng tham chiếu đến những object mà chúng mang theo — lâu hơn mong muốn.

Method **`setRemoveOnCancelPolicy(true)`** giải quyết đúng vấn đề đó: với tác vụ thuộc `ScheduledThreadPoolExecutor` còn nằm trong work queue, một lần hủy được chấp nhận sẽ khiến task **được loại khỏi queue tại thời điểm hủy**, thay vì chờ tới hạn chạy. Chính sách này giúp hạn chế **retention bộ nhớ và queue phình vì canceled tasks**, đặc biệt với timeout, retry, job định kỳ và scheduler tồn tại lâu.

Tuy nhiên, **remove khỏi queue không phải kill thread**, không phải rollback công việc đã bắt đầu, không tự đóng mọi resource, và không giải quyết queue tăng do **những task vẫn hợp lệ**. Bài này giải thích semantics, demo Java 17 chạy được, tác động với `scheduleAtFixedRate`/`scheduleWithFixedDelay`, quan hệ với `purge()` và shutdown, đo đạc và cách tránh hiểu nhầm trong Java concurrency nói chung.

## 1. ScheduledThreadPoolExecutor lưu tác vụ như thế nào?

`ScheduledThreadPoolExecutor` là một `ThreadPoolExecutor` chuyên xử lý các task cần chạy **sau một khoảng delay** hoặc **định kỳ**. Các API thường dùng:

- `schedule(Runnable, delay, unit)`: chạy một lần, **không sớm hơn** khoảng delay chỉ định.
- `schedule(Callable<V>, delay, unit)`: chạy một lần, trả kết quả qua `ScheduledFuture<V>`.
- `scheduleAtFixedRate(task, initialDelay, period, unit)`: cố gắng bắt đầu các lần thực thi theo chu kỳ cố định từ mốc lên lịch, nếu task không bị hủy/thất bại.
- `scheduleWithFixedDelay(task, initialDelay, delay, unit)`: chờ một khoảng delay sau khi **lần thực thi trước kết thúc** rồi mới chạy lần kế tiếp.
- `execute(...)` và `submit(...)` cũng được executor này thực hiện dưới dạng task có **zero delay**, với semantics queue/scheduling tương ứng.

Các task đang đợi được quản lý bằng một dạng **delay queue**, có thể chứa task chưa đến hạn. Chỉ task đủ điều kiện về thời gian mới được lấy ra để worker chạy; `getQueue().size()` vì thế có thể bao gồm những task còn đợi **nhiều giờ hoặc nhiều ngày**.

### Ví dụ hình dung

```text
Time now: 10:00

Task A: run at 10:01  --> delayed queue
Task B: run at 12:00  --> delayed queue
Task C: run tomorrow  --> delayed queue

Caller cancels Task C at 10:00:05
    |
    +-- default remove-on-cancel=false
    |      Task C may remain queued until scheduled time
    |
    +-- remove-on-cancel=true
           Task C is removed from queue promptly on cancellation
```

**Queue chứa object biểu diễn task**, không phải bản sao toàn bộ dữ liệu bên trong. Nhưng object task có thể giữ `Runnable`/`Callable` và các reference liên quan, khiến dữ liệu reachable lâu hơn. `cancel` vẫn ngăn **một task chưa chạy** thực thi sau đó theo contract; vấn đề cần sửa ở đây là **lưu giữ task đã cancel**, không phải “task đã cancel chắc chắn vẫn chạy”.

## 2. Chính sách mặc định và bật remove-on-cancel

API của `ScheduledThreadPoolExecutor`:

```java
ScheduledThreadPoolExecutor executor =
        new ScheduledThreadPoolExecutor(2);

executor.setRemoveOnCancelPolicy(true);
boolean enabled = executor.getRemoveOnCancelPolicy();
```

Đây là snippet, cần import `java.util.concurrent.ScheduledThreadPoolExecutor`. Với implementation JDK thông thường, mặc định của `getRemoveOnCancelPolicy()` là **`false`**. Khi bật:

- Các scheduled tasks **bị hủy khi còn trong queue** được gỡ khỏi queue ngay lúc hủy theo hợp đồng chính sách.
- Task đang thực thi trên worker **không thể được gỡ khỏi queue** vì nó đã được lấy ra để chạy. `cancel(true)` có thể **yêu cầu interrupt** nếu phù hợp; có dừng hay không tùy tác vụ.
- Tác vụ đã hoàn thành hoặc đã tự ra khỏi queue không có gì để remove khỏi queue.
- Setting **không tự dọn những task đã bị hủy trước khi setting được bật**; với số task cũ vẫn nằm queue, cân nhắc `purge()`.
- Setting **không** biến `ScheduledThreadPoolExecutor` thành executor có queue bounded, không làm queue các **task chưa bị hủy** tự nhỏ đi.
- Việc gỡ task cho queue giải phóng **một đường reference từ executor**, không bảo đảm object được GC ngay nếu caller, registry, callback hoặc thread khác vẫn giữ reference.

Trong phần lớn ứng dụng **thường xuyên hủy tasks có delay dài**, bật `setRemoveOnCancelPolicy(true)` ngay sau khi tạo executor là lựa chọn thực dụng. Nhưng nó có tradeoff thao tác queue tại thời điểm cancel; nếu workload đặc biệt, đo chi phí cancel/scheduling và memory.

## 3. Ba trạng thái cần phân biệt: hủy, chờ queue, đang chạy

| Khái niệm | Nó trả lời câu hỏi nào? | Không thể kết luận |
| --- | --- | --- |
| `future.isCancelled()` | Future đã nhận trạng thái canceled chưa? | Worker chắc chắn đã dừng, cleanup đã xong |
| `future.isDone()` | Future đã ở trạng thái done (thành công, thất bại, canceled) chưa? | Object chắc chắn đã rời queue |
| `executor.getQueue().contains(task)` hoặc queue size | Task có còn trong work queue tại snapshot đó? | Task còn được phép chạy, hay đang chạy |
| `executor.getActiveCount()` | Số workers đang active theo thống kê gần đúng | Có bao nhiêu canceled tasks còn lưu trong queue |
| `executor.getRemoveOnCancelPolicy()` | Có yêu cầu remove scheduled task khi cancel không? | Các task cũ đã cancel trước đó tự biến mất |
| `executor.isTerminated()` | Executor đã kết thúc hẳn chưa? | Mọi external resource đều tự đóng đúng cách |

**Một task có thể vừa cancelled vừa queued** nếu remove-on-cancel chưa bật. Ngược lại, một task đã bị worker lấy ra thì **không queued**, dù đang chạy hoặc bị yêu cầu hủy.

Không sử dụng `isCancelled()` làm bằng chứng mọi side effect đã dừng. Với `FutureTask`/executor, cancellation có thể được ghi nhận trước khi worker thực sự hoàn tất `finally`. Cần handshake riêng hoặc chờ executor termination theo hợp đồng nếu cần chứng minh cleanup.

## 4. Java 17: so sánh default với `setRemoveOnCancelPolicy(true)`

Thí nghiệm này **không dùng `Thread.sleep` để trông đợi task chưa chạy**. Mỗi task được đặt delay một ngày; ngay sau khi submit, ta hủy trước khi đến hạn. Dùng một executor mới cho từng trường hợp và đọc queue **trước khi shutdown**, vì shutdown là một thao tác lifecycle khác có thể thay đổi queue.

Tạo **`RemoveOnCancelDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RemoveOnCancelDemo {
    static void runCase(boolean removeOnCancel) {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        pool.setRemoveOnCancelPolicy(removeOnCancel);

        try {
            List<ScheduledFuture<?>> futures = new ArrayList<>();

            for (int i = 0; i < 3; i++) {
                futures.add(pool.schedule(
                        () -> System.out.println("unexpected"),
                        1, TimeUnit.DAYS));
            }

            System.out.println("policy=" + removeOnCancel);
            System.out.println("beforeCancel="
                    + pool.getQueue().size());

            for (ScheduledFuture<?> f : futures) {
                if (!f.cancel(false)) {
                    throw new IllegalStateException("Cancel failed");
                }
            }

            System.out.println("afterCancel="
                    + pool.getQueue().size());
            System.out.println("allCancelled="
                    + futures.stream().allMatch(
                            ScheduledFuture::isCancelled));
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) {
        runCase(false);
        runCase(true);
    }
}
```

Biên dịch/chạy:

```bash
javac RemoveOnCancelDemo.java
java RemoveOnCancelDemo
```

**Stdout khi chương trình hoàn thành bình thường:**

```text
policy=false
beforeCancel=3
afterCancel=3
allCancelled=true
policy=true
beforeCancel=3
afterCancel=0
allCancelled=true
```

### Phân tích output

- Cả hai pool nhận ba task, delay một ngày, nên trước khi cancel queue chứa **3 task**.
- Với policy false, `cancel(false)` chuyển Future sang canceled nhưng **những task chưa tới hạn vẫn ở queue** trên đường chạy bình thường, do đó `afterCancel=3`.
- Với policy true, các task bị canceled sẽ **được remove khỏi queue**, nên `afterCancel=0`.
- `allCancelled=true` ở cả hai trường hợp: **cancellation state không đồng nghĩa queue membership**.
- Dòng `unexpected` không được in vì các tác vụ bị hủy trước khi tới hạn một ngày.
- `shutdownNow()` ở `finally` là cleanup executor; ví dụ **không đọc queue sau shutdown** để tránh trộn tác động của shutdown vào đo remove-on-cancel.

Không dùng mẫu này để benchmark tốc độ; delay một ngày chỉ giúp chọn đường thực thi chắc chắn còn queued trong khoảng test bình thường. Trong production, nếu một task rất gần thời điểm chạy, nó có thể bị worker lấy ra **trước khi bạn cancel**. Khi đó số queued thực tế khác vì race, không phải API remove-on-cancel sai.

## 5. Vì sao task canceled còn trong queue có thể làm tăng memory retention?

Giả sử task scheduled sau 24 giờ đóng gói một payload:

```java
byte[] payload = new byte[10_000_000];

ScheduledFuture<?> handle = pool.schedule(() -> {
    process(payload);
}, 24, TimeUnit.HOURS);
```

Đây là **snippet**, `pool` là `ScheduledThreadPoolExecutor`, `process` là method nghiệp vụ. Lambda giữ reference tới payload; executor giữ scheduled task; scheduled task có thể giữ lambda và theo đó giữ payload. Nếu caller gọi:

```java
handle.cancel(false);
```

mà policy false, canceled task **có thể còn nằm trong delayed queue**, khiến một đường reference từ executor vẫn tồn tại tới khi task được gỡ. Với rất nhiều task bị cancel, chi phí reachable objects có thể đáng kể, đặc biệt khi delay dài.

**Tuy nhiên, không được tuyên bố một canceled task luôn giữ trọn payload tới deadline ở mọi triển khai/JDK.** Một Future implementation có thể xóa hoặc thay đổi field references khi cancel; code khác cũng có thể giữ hoặc bỏ references. Điểm chắc chắn về policy là **queue retention đối với canceled task**, còn lượng heap chính xác phải đo bằng heap dump/profiler theo JDK thực tế.

### Không nhầm removal với Garbage Collection

Sau khi `setRemoveOnCancelPolicy(true)`, một task bị gỡ khỏi executor queue:

- Caller vẫn giữ `ScheduledFuture<?>` trong map/list? Object vẫn có thể reachable.
- Một registry giữ lambda hoặc state nghiệp vụ? Dữ liệu vẫn có đường reference khác.
- Task đã chạy và có thread giữ reference? Queue removal không ảnh hưởng phần đã chạy.
- GC chưa diễn ra? Heap usage có thể chưa giảm ngay dù object đã unreachable.

Vì vậy hãy **xem `getQueue().size()` và heap retention như hai tín hiệu khác nhau**. Chính sách đúng chỉ loại bỏ **một nguồn lưu giữ có thể tránh được**.

## 6. `purge()`: dọn task cũ đã canceled mà còn queued

`ThreadPoolExecutor.purge()` duyệt work queue và loại bỏ các `Future` đã bị canceled. Nó tồn tại để hỗ trợ dọn canceled tasks còn chờ khi không bật remove-on-cancel hoặc khi có task cũ đã cancel trước khi policy đổi.

```java
pool.purge();
```

Đây là snippet; `pool` là `ScheduledThreadPoolExecutor`. `purge()` **không cancel tasks mới**, không kill running threads và không phải lời hứa heap được GC. Vì phải xét các phần tử queue, đừng gọi `purge()` liên tục với tần suất cao trong hot path của scheduler rất bận, nếu không đo chi phí.

### Set policy sau khi đã cancel có dọn queue cũ ngay không?

**Không.** Setter thay đổi **hành vi của những lần cancel xảy ra sau khi bật**, không phải một lệnh retroactive scan xóa tất cả task đã canceled.

Ví dụ Java 17 minh họa:

Tạo **`PurgeAfterToggleDemo.java`**:

```java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PurgeAfterToggleDemo {
    public static void main(String[] args) {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);

        try {
            ScheduledFuture<?> old1 =
                    pool.schedule(() -> {}, 1, TimeUnit.DAYS);
            ScheduledFuture<?> old2 =
                    pool.schedule(() -> {}, 1, TimeUnit.DAYS);

            old1.cancel(false);
            old2.cancel(false);
            System.out.println("cancelledBeforeToggle="
                    + pool.getQueue().size());

            pool.setRemoveOnCancelPolicy(true);
            System.out.println("afterToggle="
                    + pool.getQueue().size());

            pool.purge();
            System.out.println("afterPurge="
                    + pool.getQueue().size());

            ScheduledFuture<?> fresh =
                    pool.schedule(() -> {}, 1, TimeUnit.DAYS);
            fresh.cancel(false);
            System.out.println("newCancelAfterToggle="
                    + pool.getQueue().size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac PurgeAfterToggleDemo.java
java PurgeAfterToggleDemo
```

Stdout khi hoàn thành bình thường:

```text
cancelledBeforeToggle=2
afterToggle=2
afterPurge=0
newCancelAfterToggle=0
```

Đây là cách so sánh rõ:

1. Hai task được cancel khi policy mặc định false, nên còn queued.
2. `setRemoveOnCancelPolicy(true)` **không dọn retroactively**.
3. `purge()` gỡ hai `Future` đã canceled.
4. Task mới được cancel **sau khi** bật policy thì được gỡ ngay.

Trong hệ thống lâu sống đã tích lũy nhiều canceled tasks, có thể bật policy mới **và purge một lần** để dọn backlog cũ, miễn là phù hợp phạm vi sử dụng queue và đã đo chi phí.

## 7. Tác vụ một lần so với tác vụ định kỳ

`ScheduledThreadPoolExecutor` xử lý cả **one-shot** và **periodic** scheduled tasks. Cả hai có thể có một task object đang nằm trong queue để chờ một lần chạy tiếp theo. Chính sách remove-on-cancel có ý nghĩa với task **đang queued** khi cancel.

| Kiểu lên lịch | Lần đầu chạy | Các lần tiếp theo | Cancellation |
| --- | --- | --- | --- |
| `schedule(...)` | Sau `delay` | Không có | Nếu chưa chạy và canceled, có thể remove khỏi queue |
| `scheduleAtFixedRate(...)` | Sau `initialDelay` | Theo mốc chu kỳ cố định, không overlap các lần cùng một periodic task | Canceled future sẽ không còn các lần chạy tiếp theo theo contract |
| `scheduleWithFixedDelay(...)` | Sau `initialDelay` | Đợi `delay` sau khi lần chạy trước kết thúc | Canceled future sẽ không còn các lần chạy tiếp theo theo contract |

Với periodic task, **không có nhiều bản sao xếp hàng tương ứng với mỗi chu kỳ tương lai**; sau một lần chạy, nếu còn hợp lệ, nó có thể được đặt lại vào queue cho lần tiếp theo. Nếu task chạy lâu hơn period, `scheduleAtFixedRate` có thể **bị trễ**; các lần thực thi của **cùng một periodic task không overlap** trong `ScheduledThreadPoolExecutor`.

### Java 17: hủy periodic tasks trước lần đầu

Tạo **`PeriodicCancelDemo.java`**:

```java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PeriodicCancelDemo {
    public static void main(String[] args) {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        pool.setRemoveOnCancelPolicy(true);

        try {
            ScheduledFuture<?> atRate =
                    pool.scheduleAtFixedRate(
                            () -> System.out.println("unexpected"),
                            1, 1, TimeUnit.DAYS);

            ScheduledFuture<?> withDelay =
                    pool.scheduleWithFixedDelay(
                            () -> System.out.println("unexpected"),
                            1, 1, TimeUnit.DAYS);

            System.out.println("beforeCancel="
                    + pool.getQueue().size());

            atRate.cancel(false);
            withDelay.cancel(false);

            System.out.println("afterCancel="
                    + pool.getQueue().size());
            System.out.println("bothCancelled="
                    + (atRate.isCancelled()
                    && withDelay.isCancelled()));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac PeriodicCancelDemo.java
java PeriodicCancelDemo
```

Stdout bình thường:

```text
beforeCancel=2
afterCancel=0
bothCancelled=true
```

Ở đây **initialDelay một ngày** bảo đảm task vẫn đang chờ trong bài kiểm tra bình thường. Khi cancel trước lần đầu, queue gỡ cả fixed-rate và fixed-delay tasks. Không dùng kết quả này để suy ra `cancel(true)` có thể ngắt ngay một periodic task **đã bắt đầu** làm việc; khả năng dừng vẫn phụ thuộc interrupt/cancellation và API đang blocking.

### Fixed-rate, fixed-delay có liên quan gì tới retention?

Trong ứng dụng có hàng nghìn periodic timers hoặc retry jobs được tạo rồi cancel trước lần chạy tiếp theo, một canceled scheduled future có thể bị giữ trong queue nếu không remove-on-cancel. Bật policy giảm backlog canceled tasks. Nó **không giảm số periodic jobs còn hợp lệ**, cũng không giảm chi phí việc chạy định kỳ của các jobs chưa cancel.

## 8. `cancel(false)` và `cancel(true)` khác nhau ra sao?

`Future.cancel(mayInterruptIfRunning)` có hai cách yêu cầu hủy:

- `cancel(false)`: nếu task **chưa chạy**, yêu cầu không chạy nó; nếu task đang chạy, không gửi interrupt tới worker qua tham số này.
- `cancel(true)`: nếu task đang chạy và implementation hỗ trợ, có thể yêu cầu interrupt thread thực thi; không có cam kết thread sẽ dừng ngay, và code task cần phản hồi interruption.
- Cả hai có thể đặt Future vào trạng thái canceled khi cancellation được chấp nhận. **Remove-on-cancel policy xử lý queue membership**, không phải quyết định API interrupt đã dừng worker hay chưa.

Ví dụ:

```java
ScheduledFuture<?> future =
        pool.schedule(() -> doWork(), 10, TimeUnit.MINUTES);

boolean accepted = future.cancel(false);
```

Đây là snippet, `pool` là `ScheduledThreadPoolExecutor` và `doWork()` là logic. Nếu chưa tới hạn và cancel thành công, task không còn được phép chạy theo contract. Với remove-on-cancel true, nó cũng được remove khỏi queue. Với policy false, future có thể canceled nhưng vẫn nằm queue tới hạn.

### Điều gì khi task đã bắt đầu?

Nếu worker đã lấy task ra khỏi delay queue, **không còn queued task để remove**. `cancel(true)` gửi yêu cầu interrupt nếu thích hợp; worker phải thoát bằng chính logic của nó. Một task xử lý interrupt đúng sẽ có cơ hội chạy `finally`/`try-with-resources`. Nhưng `future.isCancelled()` chưa chắc là bằng chứng cleanup đã hoàn tất.

**Không dùng `Thread.stop()` để “giúp remove-on-cancel làm việc”.** Cưỡng chế dừng thread có thể làm hỏng invariant. Nếu resource đang chặn I/O không phản hồi interrupt, cần timeout/cancel theo API resource cụ thể.

## 9. `getQueue().size()` không phải số business jobs còn cần chạy

Nếu một pool mặc định có 1.000 canceled delayed futures vẫn chờ trong queue, `getQueue().size()` có thể là 1.000 dù không còn một job nào thật sự cần thực thi. Ngược lại, `getQueue().size()==0` không có nghĩa executor idle: có thể có workers **đang chạy** các tasks đã được lấy khỏi queue.

| Metric | Đo gì? | Không đủ để suy ra |
| --- | --- | --- |
| `pool.getQueue().size()` | Số phần tử queued tại snapshot | Bao nhiêu job còn hợp lệ, bao nhiêu worker active |
| `pool.getActiveCount()` | Ước lượng worker đang thực thi task | Số canceled tasks còn queued |
| `pool.getCompletedTaskCount()` | Ước lượng số tasks pool ghi nhận hoàn tất | Số business requests hoàn tất |
| `future.isCancelled()` | Trạng thái Future | Đã gỡ khỏi queue hoặc cleanup xong |
| `pool.getRemoveOnCancelPolicy()` | Chính sách remove khi cancel | Không có task cũ bị giữ |
| `pool.getQueue().remainingCapacity()` | Với delayed queue của scheduled executor, không phải giới hạn backlog hữu dụng | Scheduler được bounded theo request load |

**Delayed queue của `ScheduledThreadPoolExecutor` về mặt thiết kế là unbounded.** `maximumPoolSize` hầu như không có vai trò tăng số worker hữu ích như một fixed/bounded ThreadPoolExecutor thông thường; core pool size là điều kiện quan trọng hơn. Không cố “giới hạn queue” bằng `maximumPoolSize`, và đừng nhầm `setRemoveOnCancelPolicy` với backpressure.

### Quan sát production

- Số schedule calls/giây.
- Số cancels/giây và tỷ lệ canceled trước khi đến hạn.
- Queue depth theo thời gian; nếu có thể, tách pending valid vs canceled.
- Heap retained size, GC pause, Old Gen growth qua JFR/heap dump.
- Delays dài hay ngắn, burst cancellations, số periodic tasks.
- Số workers đang active, task runtime, scheduling lateness.
- Tốc độ tạo task hợp lệ có vượt năng lực thực thi không.
- Downstream resource usage nếu task chạy API/DB.

**Không gọi `getQueue().size()` là “leak count” một cách tuyệt đối.** Queue có thể chứa valid future tasks. Hãy xác minh `isCancelled()` của phần tử, đo nguồn reference và dùng profiling phù hợp.

## 10. `setRemoveOnCancelPolicy(true)` không phải giải pháp cho mọi memory pressure

Một số nguyên nhân queue/memory tăng **không** được giải quyết chỉ bằng remove-on-cancel:

1. **Task chưa canceled:** tất nhiên còn queue đến khi được thực thi hoặc hủy.
2. **Tasks được schedule quá nhanh:** khối lượng accepted work vẫn tăng ngay cả khi không có canceled tasks.
3. **Future references nằm ở registry/map khác:** queue removal không xóa bản giữ ở nơi khác.
4. **Tasks đã bắt đầu và vẫn blocking:** chúng không còn queued; phải xét task runtime/interrupt/timeout.
5. **Recurring jobs còn active:** chúng tiếp tục schedule lần kế tiếp; chỉ cancel nếu không còn cần chạy.
6. **Task captures lớn:** lambda/closure giữ object lớn dù không cần; cần giới hạn capture.
7. **Periodic task không có giới hạn lifetime:** nếu không cancel và vẫn hợp lệ, nó còn tồn tại lâu theo thiết kế.
8. **Shutdown không đúng:** scheduler còn sống và chấp nhận/giữ jobs; phải quản lý lifecycle.
9. **Caller cứ giữ tất cả ScheduledFuture trong list:** retention còn do application state, không chỉ queue.
10. **Cancellation xảy ra quá trễ:** task đã chạy và tạo các tài nguyên phụ; remove-on-cancel không rollback side effects.

Cần phân biệt **memory leak** (tham chiếu giữ object không còn cần) với **memory retention do cache/queue còn chủ động giữ work**. Hai hiện tượng có thể giống nhau trong heap dump nhưng cần cách xử lý khác.

## 11. Quan hệ với `shutdown()`, `shutdownNow()` và chính sách shutdown

`ScheduledThreadPoolExecutor` còn có các settings khác, **độc lập** với remove-on-cancel:

| Policy | Default phổ biến | Ý nghĩa |
| --- | --- | --- |
| `setRemoveOnCancelPolicy(boolean)` | `false` | Có gỡ canceled scheduled tasks khỏi queue ngay lúc cancel không |
| `setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)` | `true` | Sau `shutdown()` có tiếp tục chạy one-shot delayed tasks đã lên lịch trước đó không |
| `setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)` | `false` | Sau `shutdown()` có tiếp tục periodic tasks đã schedule trước đó không |

**Những câu hỏi khác nhau:**

- Cancel một task đang queued → **remove-on-cancel**.
- Executor được shutdown nhẹ nhàng nhưng task delayed chưa tới hạn → **execute-existing-delayed-after-shutdown**.
- Executor shutdown trong khi periodic job đã được đăng ký → **continue-existing-periodic-after-shutdown**.
- Đề nghị dừng tasks ngay lập tức và không nhận thêm → `shutdownNow()`, nhưng chỉ **cố** interrupt những task đang chạy và trả về task chưa được thực thi.

**Lỗi thường gặp:** gọi `shutdown()` rồi mong executor terminate ngay khi nó còn một delayed job sẽ chạy vào ngày mai. Khi policy execute-existing-delayed mặc định true, scheduler vẫn có thể giữ job cần thực thi, nên `awaitTermination` chưa đạt. Nếu muốn shutdown bỏ các delayed jobs, hãy cấu hình đúng lifecycle policy hoặc cancel chúng theo ownership. `setRemoveOnCancelPolicy(true)` tự nó **không có nghĩa bỏ toàn bộ delayed valid tasks sau shutdown**.

### Mẫu lifecycle có ý thức

```java
ScheduledThreadPoolExecutor scheduler =
        new ScheduledThreadPoolExecutor(2);

scheduler.setRemoveOnCancelPolicy(true);
scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
```

Đây là snippet khởi tạo, không phải một chính sách bắt buộc cho mọi ứng dụng. Có những business tasks delayed bắt buộc được thực thi trước khi shutdown hoàn tất, nên việc đặt `setExecuteExistingDelayedTasksAfterShutdownPolicy(false)` có thể làm mất công việc cần làm. **Chọn policy từ contract**, không copy nguyên snippet vào mọi service.

Phương án graceful shutdown:

```java
scheduler.shutdown();
try {
    if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
        scheduler.shutdownNow();
        if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
            reportStillRunning();
        }
    }
} catch (InterruptedException e) {
    scheduler.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Snippet cần `TimeUnit` và method `reportStillRunning()` của ứng dụng. `shutdownNow()` không bảo đảm mọi task dừng hoặc mọi resource đã đóng; phải báo nếu timeout.

## 12. Tác vụ periodic, lỗi và cancellation

Với một periodic task:

- Nếu body ném exception không được xử lý theo hợp đồng của `scheduleAtFixedRate`/`scheduleWithFixedDelay`, các lần thực thi tiếp theo bị ngăn.
- Nếu một lần thực thi kéo dài hơn period của fixed-rate, những lần kế tiếp có thể chạy trễ nhưng **không overlap với lần trước của cùng một periodic task**.
- Nếu task bị cancel trong khi đang chạy, future có thể chuyển canceled trước khi body thực sự rời worker; `mayInterruptIfRunning` quyết định yêu cầu interrupt.
- Khi periodic task đã hoàn thành một lần và requeue để chờ lần sau, remove-on-cancel true giúp gỡ nó nếu bị cancel **khi đang queued**.
- Nếu cancel và run race sát nhau, `getQueue().size()` là snapshot, không phải lịch sử chắc chắn. Viết test với delay đủ dài hoặc checkpoint rõ.

Không biến một periodic task thành hàng nghìn queued instances chỉ vì nó có period 1 giây trong tương lai: scheduler không tạo trước một bản sao cho mọi tick. Vấn đề retention ở đây là **nhiều futures bị canceled còn queued**, không phải “một job periodic 100 lần tương đương 100 queue nodes”.

## 13. Tránh nhầm cancellation với quét queue thủ công

Một số code sai dùng vòng lặp tự xóa mọi task mà application cho rằng không còn cần:

```java
for (Runnable task : scheduler.getQueue()) {
    if (shouldCancel(task)) {
        scheduler.getQueue().remove(task);
    }
}
```

Đây là **snippet sai về giao thức**. Xóa queue node không tương đương gọi `ScheduledFuture.cancel`. Bạn có thể xóa một task khỏi scheduler nhưng `Future` của caller vẫn không chuyển trạng thái canceled, khiến caller chờ `get()` mãi hoặc đánh giá sai lifecycle. Còn có race với worker và với periodic requeue.

**Hãy cancel qua đúng `ScheduledFuture` handle**, rồi dùng remove-on-cancel policy hoặc `purge()` để xử lý queue retention. Nếu cần owner registry, giữ handle của job và dọn registry khi job kết thúc/hủy, không dùng queue nội bộ như kho dữ liệu nghiệp vụ.

### Cần tự gọi `getQueue().remove(future)` không?

Thường **không cần** khi đã bật remove-on-cancel true. Hơn nữa, các implementation có thể decorate scheduled tasks, khiến type/identity của queued object khác điều bạn dự đoán. Dựa vào public API `cancel` và `setRemoveOnCancelPolicy`, thay vì viết code phụ thuộc nội bộ queue.

## 14. Giữ references và ownership của ScheduledFuture

Khi một request/business job schedule timeout:

```java
ScheduledFuture<?> timeoutTask =
        scheduler.schedule(() -> onTimeout(), 30, TimeUnit.SECONDS);
```

Đây là snippet với `scheduler` đã định nghĩa và callback `onTimeout` thuộc ứng dụng. Khi request kết thúc bình thường trước timeout, phải:

1. Hủy timeout task nếu không cần callback nữa: `timeoutTask.cancel(false)`.
2. Đảm bảo scheduler có policy phù hợp nếu nhiều timeout tương tự bị hủy.
3. Xóa handle khỏi registry/map của ứng dụng nếu registry không còn cần nó.
4. Đảm bảo callback timeout và đường completed bình thường có **giao thức quyết định một lần** (ví dụ CAS state machine) nếu chúng race.
5. Không suy ra `cancel(false)` đã rollback callback nếu callback **đã bắt đầu chạy**.

Một phép cancel thành công không thể giải quyết tình huống callback đã tạo side effect. Để hạn chế double-completion, dùng state như `AtomicReference<State>` hoặc một khóa chung để chuyển `PENDING → TIMED_OUT` hoặc `PENDING → COMPLETED` chỉ một lần, rồi xử lý effect phù hợp. Policy queue chỉ giải quyết **retention**, không quyết định ai thắng business race.

## 15. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “`cancel` làm task biến mất khỏi queue ngay” | Default có thể giữ canceled task tới delay | Bật `setRemoveOnCancelPolicy(true)` khi cần |
| “Task canceled còn queued nghĩa là vẫn sẽ chạy” | Nhầm queue retention với execution eligibility | Phân biệt Future state và queue membership |
| “`setRemoveOnCancelPolicy(true)` giết running thread” | Task đã chạy không còn queued | Cooperative interrupt/timeout riêng |
| “Bật policy sau cancel sẽ dọn task cũ” | Canceled objects cũ vẫn có thể queued | `purge()` một lần khi phù hợp |
| “`purge()` hủy tác vụ” | Nó chỉ loại canceled futures khỏi queue | Gọi `cancel` trước |
| “remove khỏi queue chắc chắn heap giảm ngay” | Registry/caller/GC vẫn có thể giữ | Xem heap retainers và references |
| “`queue.size()` là số jobs còn cần chạy” | Gồm delayed và canceled tasks | Đo pending valid, canceled, running riêng |
| “`maximumPoolSize` sẽ giới hạn delayed queue” | Queue scheduled executor về cơ bản unbounded | Admission/bounded registry ở tầng trên |
| “`shutdown()` luôn dừng tất cả delayed tasks” | Delayed-after-shutdown default true | Chọn đúng lifecycle policies |
| “`shutdownNow()` bảo đảm worker đã dừng” | Chỉ cố interrupt, có thể không đáp ứng | Đợi termination và cleanup |
| “Periodic schedule sẵn hàng trăm lần tương lai” | Không hiểu requeue định kỳ | Một future được lên lịch lại |
| “`cancel(true)` đã đóng resource” | Future state không đồng nghĩa cleanup | Theo dõi worker completion riêng |
| “Dùng `getQueue().remove` thay cancel” | Future lifecycle có thể sai | Hủy bằng ScheduledFuture handle |
| “Task không cancel thì remove-on-cancel vẫn giúp queue nhỏ” | Policy chỉ tác động canceled tasks | Backpressure, giới hạn số schedules |
| “`execute/submit` không liên quan scheduler” | STPE cũng đóng gói zero-delay tasks | Hiểu queue và wrapper semantics |

## 16. Kiểm thử chính sách đúng cách

Một test tốt nên bao phủ:

1. **Default false**: schedule với delay rất dài, cancel, quan sát queued canceled future.
2. **Enabled true**: cùng workload, cancel, quan sát queue node được gỡ.
3. **Toggle sau khi cancel**: bật true không tự dọn backlog cũ; `purge()` dọn.
4. **Periodic before-first-run**: fixed-rate và fixed-delay canceled futures được gỡ.
5. **Cancel khi task đang chạy**: không nhầm removal với interrupt/termination; dùng latch để điều phối.
6. **Shutdown policy**: kiểm tra one-shot delayed và periodic có tiếp tục sau `shutdown` hay không.
7. **Queue valid tasks**: remove-on-cancel không làm queue các task chưa cancel biến mất.
8. **Memory retention**: đo queue và heap dump/profile, không assert GC chạy trong một mốc thời gian.
9. **Concurrent scheduling/cancellation**: không dựa vào queue snapshot không ổn định để khẳng định race outcome.
10. **Cleanup**: đóng scheduler ở `finally`, dừng tasks theo policy thay vì để thread pool giữ JVM sống ngoài ý muốn.

**Không dùng `Thread.sleep(10)` để đoán task chưa chạy hoặc đã được gỡ.** Ví dụ trong bài chọn delay một ngày và đọc ngay sau cancel, tránh race scheduling ở điểm cần minh họa; test concurrency phức tạp hơn nên dùng `CountDownLatch` hoặc cơ chế điều phối khác.

## 17. Khi nào thực sự nên bật chính sách?

**Rất phù hợp** nếu:

- Scheduler chạy lâu và tạo nhiều **one-shot timeout tasks** mà phần lớn sẽ được hủy khi việc hoàn thành sớm.
- Retry/backoff jobs có delay dài và được cancel khi workflow kết thúc.
- Nhiều periodic tasks được đăng ký rồi dừng trước lần chạy kế tiếp.
- Queue depth và heap retained objects do canceled futures tăng theo thời gian.
- Bạn muốn giảm nhu cầu gọi `purge()` định kỳ chỉ để dọn canceled tasks.

**Không phải phương thuốc chính** nếu:

- Queue tăng vì tasks hợp lệ được schedule nhanh hơn executor xử lý.
- Worker đang chặn I/O, không giải phóng tài nguyên.
- Registry vẫn giữ mọi future đã canceled.
- Task payload quá lớn dù không cancel.
- Chính sách shutdown chưa phù hợp.
- Job phải survive process crash và cần persistent scheduling; `ScheduledThreadPoolExecutor` là scheduler **trong bộ nhớ**, không tự cung cấp durability.

Về hiệu năng, bật remove-on-cancel có chi phí quản lý queue tại thời điểm cancel. Nhưng tradeoff thường đáng cân nhắc khi canceled tasks có delay dài, vì giữ nhiều task sống sẽ tốn heap và làm các hoạt động quản lý queue khó chịu hơn. Cần đo thực tế nếu lượng cancels cực lớn.

## 18. Java 21+ và virtual threads

Virtual threads không thay đổi cơ chế cơ bản của `ScheduledThreadPoolExecutor`: scheduled futures vẫn được quản lý theo queue và cancellation policy của executor. Nếu callback tạo virtual threads hoặc task khác, cần tách **queue của scheduler** với **số công việc đang chạy ở executor khác**.

`newVirtualThreadPerTaskExecutor()` có trên Java 21+ nhưng không thay thế scheduler delayed/periodic chuẩn theo nghĩa cung cấp một `ScheduledExecutorService` với queue/cancel policy giống hệt. Chọn đúng API theo loại tác vụ.

Dù dùng virtual threads, **canceled delayed tasks** vẫn có thể tạo retention nếu còn queued, trong khi memory/threads cho callback còn thuộc hệ thống khác. Mọi demo trong bài chỉ dùng API chạy được bằng Java 17.

## 19. Câu hỏi tự kiểm tra

**1. Mặc định `getRemoveOnCancelPolicy()` là gì?** Thông thường `false` đối với `ScheduledThreadPoolExecutor`. Điều này cho phép canceled scheduled futures còn nằm delayed queue tới thời điểm dự kiến chạy.

**2. Vì sao canceled task còn queued không có nghĩa nó sẽ thực thi?** Trạng thái canceled của `Future` là một chuyện; giữ object trong queue để quản lý deadline/cleanup queue là chuyện khác.

**3. Khi bật `setRemoveOnCancelPolicy(true)`, điều gì thay đổi?** Task bị cancel khi vẫn queued sẽ được gỡ ngay khi cancellation diễn ra, giảm queue retention.

**4. Tác vụ đã chạy được `cancel(true)` có lập tức dừng do policy này không?** Không. Remove-on-cancel chỉ ảnh hưởng queued task; running code cần cooperative interruption/timeout.

**5. Bật policy true sau khi đã cancel 1.000 jobs có tự dọn 1.000 jobs đó?** Không retroactively. Có thể dùng `purge()` để gỡ các futures đã canceled còn queue.

**6. `purge()` có gọi cancel cho valid tasks không?** Không. Nó tìm và loại canceled futures khỏi queue.

**7. `getQueue().size()==0` chứng minh không có task đang chạy không?** Không. Worker có thể đã lấy task ra khỏi queue và vẫn đang chạy.

**8. `getQueue().size()==1.000` chứng minh có 1.000 jobs hợp lệ không?** Không. Queue có thể chứa canceled delayed futures, nhất là khi policy false.

**9. `setRemoveOnCancelPolicy(true)` có làm queue bounded không?** Không. Delayed queue của scheduled executor về cơ bản unbounded; cần admission control để giới hạn valid pending jobs.

**10. `shutdown()` có bỏ mọi delayed one-shot tasks chưa tới hạn không?** Không mặc định; `executeExistingDelayedTasksAfterShutdownPolicy` thường true. Phải cấu hình theo lifecycle contract.

**11. Hủy periodic future khi nó đang chờ lần tiếp theo có được remove ngay không?** Có theo policy true khi task còn queued. Hủy trong lúc task đang chạy là tình huống khác.

**12. Khi queue đã gỡ task, có chắc payload được GC không?** Không. Có thể còn references từ registry/caller; GC không được cam kết chạy ngay.

**13. Có nên tự `getQueue().remove(future)` mà không cancel không?** Không. Xóa queue node không thay thế Future cancellation semantics và dễ gây sai lifecycle.

**14. Nếu bị cancel ở thời điểm gần hạn chạy, queue size có luôn theo một lịch cố định không?** Không. Worker có thể đã lấy task ra trước khi cancel; cần phân biệt race với policy.

**15. Có thể dùng scheduled executor làm durable job scheduler qua JVM crash không?** Không. Đây là scheduler trong process; nếu cần persist/khôi phục jobs, phải thiết kế storage/recovery riêng.

## 20. Checklist cấu hình và vận hành

- Đã xác định scheduler là **ScheduledThreadPoolExecutor** và owner của nó chưa?
- Có đọc/đặt `getRemoveOnCancelPolicy/setRemoveOnCancelPolicy` theo workload không?
- Với scheduler có tỷ lệ cancel cao, đã bật policy **sớm khi khởi tạo** chưa?
- Nếu mới bật trên scheduler cũ, có cần `purge()` để dọn canceled backlog trước đó không?
- Có giữ `ScheduledFuture` handles trong registry quá lâu dù đã cancel không?
- Có phân biệt **Future state**, **queue membership**, **worker executing**, **actual cleanup** không?
- Với periodic jobs, đã hiểu fixed-rate/fixed-delay và cancellation giữa hai lần chạy chưa?
- Có chính sách hủy và timeout I/O riêng cho tasks đã bắt đầu không?
- Queue có tăng vì **valid tasks** hay canceled tasks? Đã xem heap dump/JFR và metrics?
- Đã chọn `executeExistingDelayedTasksAfterShutdownPolicy` và `continueExistingPeriodicTasksAfterShutdownPolicy` theo đúng nghiệp vụ chưa?
- Shutdown có `awaitTermination` và fallback hữu hạn thay vì chỉ gọi một method rồi giả định xong không?
- Khi chạy test có đặt delay đủ dài/handshake để tránh dựa vào scheduler may rủi không?
- Nếu callback có side effects, có state machine/idempotency để xử lý race giữa hoàn thành bình thường và timeout không?

**Kết luận:** `setRemoveOnCancelPolicy(true)` là **công cụ quản lý retention của canceled scheduled tasks** trong `ScheduledThreadPoolExecutor`. Nó giúp **gỡ task còn queued ngay khi hủy**, đặc biệt hữu ích với nhiều tác vụ delay dài hoặc periodic timers bị cancel; mặc định false có thể để các canceled futures ở queue đến lúc đến hạn. Nhưng **cancellation, queue removal, worker interruption, cleanup và GC là những sự kiện khác nhau**. Dùng policy đúng từ khi tạo scheduler, `purge()` khi cần dọn backlog cũ, đo queue và heap theo thời gian, đồng thời thiết kế shutdown/cancellation và giới hạn pending valid work độc lập.