# `ScheduledExecutorService`: fixedRate, fixedDelay và lịch bị bỏ lỡ

`ScheduledExecutorService` cho phép Java chạy một tác vụ sau một khoảng trễ hoặc chạy lặp lại theo chu kỳ. Hai chế độ định kỳ thường dùng là `scheduleAtFixedRate` và `scheduleWithFixedDelay`. Chúng có cách tính thời điểm chạy tiếp theo khác nhau, vì vậy lựa chọn đúng phụ thuộc vào ý nghĩa của công việc.

Khi ứng dụng dùng CRaC, lịch chạy còn chịu ảnh hưởng của thời gian tiến trình nằm trong trạng thái checkpoint. Một lần restore có thể diễn ra sau vài giây, vài phút hoặc lâu hơn. Trong khoảng thời gian đó, các thời điểm chạy dự kiến có thể đã trôi qua. Ứng dụng phải quyết định rõ nên bỏ qua các lần chạy bị lỡ, gộp chúng thành một lần, hay chạy bù từng lần. Không nên dựa vào giả định rằng mọi implementation `ScheduledExecutorService` và mọi CRaC runtime đều xử lý khoảng thời gian checkpoint giống nhau.

## 1. `scheduleAtFixedRate`: cố định khoảng cách giữa các thời điểm dự kiến

`scheduleAtFixedRate(task, initialDelay, period, unit)` lập lịch lần chạy đầu tiên sau `initialDelay`. Những lần tiếp theo được lên lịch theo nhịp cố định tính từ thời điểm bắt đầu dự kiến ban đầu:

```text
start 1       start 2       start 3       start 4
   |-------------|-------------|-------------|
        period        period        period
```

Ví dụ, với `initialDelay = 0` và `period = 10 giây`, các thời điểm bắt đầu dự kiến là 0s, 10s, 20s, 30s, ... Nếu một lần chạy kéo dài 13 giây, lần kế tiếp đã quá hạn khi lần hiện tại kết thúc. Executor có thể bắt đầu lần tiếp theo ngay sau đó để tiến gần lại nhịp đã định.

Các lần thực thi của **cùng một periodic task không chạy đồng thời**. Nếu một lần chạy mất nhiều thời gian hơn period, những lần sau có thể bắt đầu muộn, nhưng không chồng lấn với lần trước của chính task đó. Điều này không ngăn task tạo ra công việc bất đồng bộ rồi trả về sớm; nếu task submit một `CompletableFuture` và kết thúc ngay, lần schedule tiếp theo có thể bắt đầu trong khi future trước vẫn đang chạy.

Ví dụ:

```java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        this::refreshMetrics,
        0,
        10,
        TimeUnit.SECONDS
);
```

Chọn fixed rate khi nghiệp vụ cần một nhịp theo chu kỳ, chẳng hạn:

- Lấy mẫu metric mỗi 10 giây.
- Kiểm tra heartbeat theo chu kỳ cố định.
- Đồng bộ một trạng thái theo các mốc định kỳ.
- Chạy một tác vụ housekeeping mà khoảng cách giữa các thời điểm dự kiến có ý nghĩa.

Fixed rate không phải lịch cron theo múi giờ. Nó là lịch lặp theo khoảng thời gian tương đối của executor. Nếu cần chạy lúc 09:00 mỗi ngày theo giờ địa phương, cần tính lịch từ `Instant`, `ZoneId` và chính sách lịch ngày/giờ; không nên coi `scheduleAtFixedRate(..., 24, HOURS)` là tương đương với 09:00 mỗi ngày qua thay đổi DST.

## 2. `scheduleWithFixedDelay`: chờ một khoảng sau khi lần trước kết thúc

`scheduleWithFixedDelay(task, initialDelay, delay, unit)` tính lần chạy tiếp theo từ **thời điểm lần chạy trước kết thúc**:

```text
start 1       finish 1       start 2       finish 2
   |--------------|-------------|--------------|
       duration       delay         duration
```

Nếu task mất 4 giây và fixed delay là 10 giây, lần kế tiếp bắt đầu sau khoảng 14 giây tính từ lúc lần trước bắt đầu. Nếu lần chạy mất 20 giây, lần tiếp theo bắt đầu sau khoảng 30 giây. Thời gian xử lý không làm các lần chạy chồng lấn.

Ví dụ:

```java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> future = scheduler.scheduleWithFixedDelay(
        this::pollRemoteQueue,
        0,
        10,
        TimeUnit.SECONDS
);
```

Fixed delay phù hợp với công việc mà ta muốn dành một khoảng nghỉ sau khi hoàn tất:

- Poll một dịch vụ ngoài, tránh gọi liên tục khi lần poll trước chậm.
- Dọn dẹp dữ liệu mà thời gian xử lý biến động.
- Kiểm tra một hệ thống phụ thuộc mà không cần giữ nhịp tuyệt đối.
- Chạy tác vụ bảo trì mà lần tiếp theo chỉ nên bắt đầu sau khi lần trước kết thúc cộng thêm thời gian nghỉ.

## 3. So sánh fixed rate và fixed delay

| Tiêu chí | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
|---|---|---|
| Mốc tính lần tiếp theo | Các thời điểm dự kiến theo nhịp ban đầu | Thời điểm lần trước kết thúc |
| Ảnh hưởng khi task chạy lâu | Lần sau có thể bắt đầu muộn và chạy bù nhịp đã trễ | Lần sau luôn đợi đủ delay sau khi lần trước kết thúc |
| Khoảng cách thực tế giữa hai lần bắt đầu | Có thể ngắn hơn bình thường khi executor đang bắt kịp lịch | Bằng thời gian chạy lần trước cộng delay |
| Chồng lấn cùng periodic task | Không | Không |
| Dùng khi | Nhịp chu kỳ quan trọng | Khoảng nghỉ sau khi xử lý quan trọng |
| Ví dụ | Lấy mẫu theo chu kỳ | Polling với thời gian nghỉ sau mỗi lần poll |

Giả sử period/delay là 10 giây và mỗi lần chạy mất 13 giây:

### Fixed rate

Các mốc dự kiến là 0s, 10s, 20s, 30s. Vì lần đầu kết thúc ở 13s, lần hai bắt đầu muộn ở 13s; lần tiếp theo có thể bắt đầu ngay khi lần hai hoàn tất ở 26s để bắt kịp nhịp đã trễ.

```text
Run 1: 0s -------- 13s
Run 2:              13s -------- 26s
Run 3:                           26s -------- 39s
```

### Fixed delay

Mỗi lần kết thúc, executor chờ thêm 10 giây. Vì vậy, lần hai bắt đầu ở 23s và lần ba ở 46s.

```text
Run 1: 0s -------- 13s
Wait:                13s --- 23s
Run 2:                         23s -------- 36s
Wait:                                      36s --- 46s
Run 3:                                               46s ...
```

Các mốc trên minh họa hợp đồng lập lịch thông thường. Khi tiến trình bị checkpoint, thời gian trôi qua trong lúc tiến trình không chạy tạo thêm một tình huống riêng; cần xem phần lịch bị bỏ lỡ bên dưới.

## 4. Điều gì xảy ra nếu periodic task ném exception?

Theo hợp đồng của `ScheduledExecutorService`, nếu một lần thực thi của periodic task ném exception, những lần thực thi tiếp theo của periodic task đó bị suppress (không tiếp tục chạy). `ScheduledFuture` thường chuyển sang trạng thái hoàn tất bất thường.

Điều này dễ bị bỏ sót nếu chỉ ghi log ở nơi tạo lịch. Ví dụ:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        () -> updateRemoteState(),
        0,
        30,
        TimeUnit.SECONDS
);
```

Nếu `updateRemoteState()` ném `RuntimeException` ở lần đầu, ta không nên giả định executor sẽ tự chạy lại sau 30 giây. Nếu muốn tiếp tục định kỳ sau lỗi tạm thời, cần bắt lỗi trong thân task và xác định rõ chính sách retry:

```java
ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
        () -> {
            try {
                updateRemoteState();
            } catch (Exception failure) {
                logger.warn("Periodic state update failed", failure);
                recordFailure(failure);
            }
        },
        0,
        30,
        TimeUnit.SECONDS
);
```

Việc bắt exception giúp task không kết thúc bất thường, nhưng không có nghĩa nên nuốt mọi lỗi. Cần ghi log, metric, retry có giới hạn hoặc chuyển trạng thái hệ thống sang unhealthy nếu lỗi kéo dài. Với lỗi nghiêm trọng khiến các lần chạy sau không còn an toàn, hãy dừng lịch và yêu cầu phục hồi rõ ràng.

Có thể giữ `ScheduledFuture` để quan sát trạng thái. Nếu `isDone()` trả về `true` ngoài ý muốn, gọi `get()` để nhận nguyên nhân; một periodic future bình thường không trả về kết quả sau mỗi lần chạy mà tiếp tục chờ cho tới khi bị hủy hoặc kết thúc bất thường. Khi `get()` ném `ExecutionException`, kiểm tra `getCause()` để xác định lỗi làm lịch dừng.

## 5. Lịch bị bỏ lỡ trong lúc checkpoint

Giả sử một tác vụ được lên lịch mỗi phút. Ứng dụng chạy lúc 10:00, tạo checkpoint lúc 10:02, và restore lúc 10:07. Trong khoảng 5 phút, các mốc 10:03, 10:04, 10:05, 10:06 và 10:07 có thể đã đi qua.

Điều cần quyết định là: sau restore, ứng dụng có phải thực hiện lại từng mốc đã bỏ lỡ không? Câu trả lời phụ thuộc ý nghĩa nghiệp vụ:

- Nếu task chỉ refresh cache, một lần refresh mới thường đủ.
- Nếu task tổng hợp dữ liệu theo từng phút, có thể cần xử lý từng bucket bị thiếu.
- Nếu task gửi báo cáo đúng từng kỳ, bỏ qua kỳ đã lỡ có thể không chấp nhận được.
- Nếu task poll một endpoint để kiểm tra trạng thái hiện tại, chạy một lần ngay sau restore thường có ý nghĩa hơn việc chạy dồn nhiều lần.

**CRaC không định nghĩa một chính sách nghiệp vụ chung cho lịch bị bỏ lỡ.** `ScheduledExecutorService` quy định fixed-rate/fixed-delay khi executor đang vận hành, nhưng hành vi của delay queue, clock và tác vụ quá hạn qua checkpoint/restore còn phụ thuộc implementation JDK, CRaC runtime và nền tảng. Hãy kiểm thử trên đúng runtime triển khai và tự xác định missed-run policy ở tầng ứng dụng.

Không nên coi việc một callback `afterRestore` được gọi là bằng chứng rằng mọi lần chạy bị lỡ đã tự động được replay, hoặc rằng chúng chắc chắn bị bỏ qua.

## 6. Ba chính sách xử lý lịch bị lỡ

### Bỏ qua (skip)

Chỉ chạy lần tiếp theo có thời điểm nằm trong tương lai. Các mốc trong lúc checkpoint được bỏ qua.

Ví dụ: lịch mỗi phút, restore lúc 10:07:20, lần kế tiếp là 10:08. Chính sách này phù hợp với metric lấy mẫu, refresh cache hoặc tác vụ chỉ cần trạng thái mới nhất.

### Gộp (coalesce)

Nếu có một hoặc nhiều mốc bị lỡ, chạy một lần ngay sau restore để cập nhật trạng thái hiện tại, sau đó tiếp tục lịch bình thường.

Ví dụ: dù đã bỏ lỡ năm lần refresh, ứng dụng chỉ chạy một lần refresh lúc 10:07:20 rồi tiếp tục ở 10:08. Chính sách này phù hợp với việc đồng bộ snapshot hoặc tính toán mà lần chạy mới nhất bao phủ dữ liệu cũ.

### Chạy bù (catch-up)

Thực hiện từng kỳ bị lỡ theo thứ tự, có giới hạn tốc độ và số lượng mỗi đợt. Chính sách này phù hợp khi mỗi kỳ đại diện cho một phần dữ liệu nghiệp vụ cần được xử lý riêng.

Ví dụ: hệ thống phải tổng hợp từng bucket một phút. Sau restore lúc 10:07:20, nó xử lý các bucket 10:03 đến 10:07 rồi tiếp tục lịch hiện tại. Nên giới hạn batch, đặt deadline và theo dõi backlog để tránh một đợt catch-up quá lớn làm quá tải database hoặc dịch vụ phụ thuộc.

| Chính sách | Việc thực hiện sau restore | Trường hợp phù hợp |
|---|---|---|
| Skip | Bỏ các mốc đã qua, lên lịch mốc tương lai | Cache, sampling, health poll |
| Coalesce | Chạy một lần đại diện cho các mốc đã lỡ | Refresh snapshot, đồng bộ trạng thái hiện tại |
| Catch-up | Xử lý từng mốc bị lỡ, thường theo batch | Billing period, aggregation bucket, xử lý sự kiện theo kỳ |

Không chọn catch-up chỉ vì muốn “không mất lần chạy”. Nếu task có side effect, replay cần idempotency và dữ liệu nguồn bền vững. Ngược lại, skip chỉ an toàn khi nghiệp vụ cho phép bỏ qua các kỳ không chạy.

## 7. Tính lại thời điểm chạy từ dữ liệu bền vững

Nếu lịch quan trọng qua checkpoint, hãy lưu thông tin lịch cần thiết ngoài heap, ví dụ trong database:

- Tên job và phiên bản cấu hình lịch.
- Mốc thời gian dự kiến gần nhất hoặc `nextDueAt`.
- Mốc gần nhất đã xử lý thành công (`lastCompletedSlot`).
- Múi giờ nếu lịch dựa trên giờ địa phương.
- Trạng thái backlog hoặc cursor nếu có catch-up.
- Idempotency key cho mỗi kỳ nghiệp vụ.

Sau restore, đọc lại dữ liệu này, so sánh với thời gian hiện tại và áp dụng missed-run policy. Không chỉ dựa vào một `ScheduledFuture` hoặc biến `nextRun` trong heap vì checkpoint có thể giữ giá trị đã cũ.

### Fixed rate theo thời điểm dự kiến

Nếu fixed rate là 60 giây, có thể duy trì một mốc neo `anchor` và tính các slot theo khoảng cách cố định. Ví dụ dưới đây tính slot đầu tiên nằm sau `now`, dùng giây để minh họa:

```java
import java.time.Duration;
import java.time.Instant;

static Instant nextFixedRateSlot(
        Instant anchor,
        Instant now,
        long periodSeconds) {
    if (periodSeconds <= 0) {
        throw new IllegalArgumentException("periodSeconds must be positive");
    }

    if (now.isBefore(anchor)) {
        return anchor;
    }

    long elapsedSeconds = Duration.between(anchor, now).getSeconds();
    long completedIntervals = elapsedSeconds / periodSeconds;
    long nextInterval = Math.addExact(completedIntervals, 1);
    long offset = Math.multiplyExact(nextInterval, periodSeconds);

    return anchor.plusSeconds(offset);
}
```

Đây là phép tính cho lịch interval theo giây, không phải lịch cron theo múi giờ. Với lịch calendar, cần tính theo `ZonedDateTime`/`ZoneId` và xác định rõ cách xử lý DST, giờ bị lặp hoặc giờ không tồn tại.

Khi đã xác định `nextDueAt`, tính delay không âm rồi tạo một lịch mới:

```java
Instant now = clock.instant();
Instant nextDueAt = scheduleStore.calculateNextDue(now);
long delayNanos = Math.max(
        0L,
        Duration.between(now, nextDueAt).toNanos()
);

future = scheduler.schedule(
        this::runOneSlot,
        delayNanos,
        TimeUnit.NANOSECONDS
);
```

Sau lần chạy đó, ứng dụng có thể tự tính slot kế tiếp từ anchor và dữ liệu đã lưu, hoặc tạo periodic schedule mới nếu semantics phù hợp. Cách tính cụ thể phải tránh overflow khi chuyển `Duration` lớn sang nanosecond.

### Fixed delay theo thời điểm hoàn tất

Với fixed delay, mốc tham chiếu là thời điểm hoàn tất lần chạy trước. Nếu ứng dụng muốn giữ đúng semantics qua checkpoint, cần lưu `lastCompletedAt` bền vững. Sau restore, thời điểm kế tiếp là:

```text
nextDueAt = lastCompletedAt + configuredDelay
```

Nếu `nextDueAt` đã qua, ứng dụng vẫn phải chọn skip, coalesce hoặc catch-up theo nghiệp vụ. Nếu chính sách là “nghỉ đủ delay kể từ khi restore”, hãy đặt `nextDueAt = restoreTime + delay` và ghi rõ rằng đây là chính sách resume mới, không phải khôi phục nguyên nhịp trước checkpoint.

## 8. Tích hợp với CRaC: dừng lịch cũ và tạo lịch mới

Một cách dễ kiểm soát là quản lý scheduler như một resource có vòng đời rõ ràng:

### Trước checkpoint

1. Đóng cổng tạo công việc mới nếu job có thể được kích hoạt từ nhiều nguồn.
2. Hủy lịch định kỳ để ngăn những lần chạy tiếp theo được phát sinh.
3. Chờ lần chạy hiện tại và các công việc bất đồng bộ mà nó tạo ra hoàn tất.
4. Lưu tiến độ hoặc `lastCompletedAt` vào nơi lưu trữ bền vững.
5. Dừng scheduler executor riêng nếu nó không còn được dùng.

### Sau restore

1. Tạo `ScheduledExecutorService` mới.
2. Đọc cấu hình và trạng thái lịch từ nguồn bền vững.
3. Tính các kỳ bị lỡ và áp dụng skip/coalesce/catch-up.
4. Lên lịch lần chạy đầu tiên theo chính sách đã chọn.
5. Chỉ cho phép job nhận trigger mới sau khi dependency và trạng thái phục hồi đã sẵn sàng.

Ví dụ wrapper CRaC:

```java
import java.time.Duration;

import org.crac.Context;
import org.crac.Resource;

final class ScheduledJobsResource implements Resource {
    private final PeriodicJobLifecycle jobs;
    private final Duration drainTimeout;

    ScheduledJobsResource(
            PeriodicJobLifecycle jobs,
            Duration drainTimeout) {
        this.jobs = jobs;
        this.drainTimeout = drainTimeout;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        jobs.stopSchedulingAndDrain(drainTimeout);
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        jobs.recreateExecutorAndApplyMissedRunPolicy();
    }
}
```

`PeriodicJobLifecycle` là abstraction do ứng dụng triển khai. Nó nên giữ `ScheduledFuture`, executor, trạng thái task đang chạy và thông tin lịch bền vững. `stopSchedulingAndDrain` cần hủy các trigger tương lai, đợi task hiện tại kết thúc trong deadline, rồi shutdown executor riêng. `recreateExecutorAndApplyMissedRunPolicy` tạo executor mới và tính lại lịch từ nguồn dữ liệu chuẩn.

Nếu `beforeCheckpoint` timeout, callback phải báo lỗi để checkpoint bị từ chối. Phần điều phối cần có cách phục hồi scheduler nếu tiến trình tiếp tục chạy sau lần checkpoint thất bại. Đừng giả định một executor đã shutdown có thể được khởi động lại; thường cần tạo executor mới và schedule lại task. Nếu checkpoint engine thất bại sau khi callback đã hoàn tất, controller quản lý attempt phải xử lý việc đưa instance về phục vụ hoặc thay thế nó.

## 9. Hủy lịch và chờ task đang chạy

`ScheduledFuture.cancel(false)` ngăn các lần thực thi tương lai của task và không yêu cầu interrupt lần đang chạy. Đây thường là lựa chọn phù hợp khi muốn task hiện tại tự hoàn tất trước checkpoint.

`cancel(true)` có thể yêu cầu interrupt thread đang thực thi. Không dùng nó như cách mặc định để drain: task có thể đang commit transaction, ghi file hoặc cập nhật trạng thái. Chỉ dùng interrupt nếu task được thiết kế cooperative và có thể dừng an toàn.

Với executor riêng cho scheduler, một trình tự đơn giản là:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

future.cancel(false);
scheduler.shutdown();

if (!scheduler.awaitTermination(30, TimeUnit.SECONDS)) {
    throw new TimeoutException("Scheduled work did not finish in time");
}
```

`awaitTermination` chờ executor kết thúc sau shutdown; nó không thay thế việc theo dõi các công việc bất đồng bộ đã được task submit sang executor khác. Nếu periodic task chỉ tạo future rồi trả về, cần chờ cả future con hoặc dùng một work tracker chung.

Khi timeout, không được âm thầm tiếp tục checkpoint. Cần ghi nhận task nào còn chạy, quyết định có thể phục hồi scheduler trên tiến trình hiện tại hay phải đánh dấu instance unhealthy. Nếu task không thể bị interrupt an toàn, đừng cưỡng bức đóng tài nguyên mà task còn sử dụng.

## 10. Lịch định kỳ trong môi trường nhiều replica

Khi nhiều instance cùng restore từ một checkpoint, tất cả có thể khởi tạo cùng một periodic job. Nếu mỗi replica đều chạy công việc có side effect, hệ thống có thể gửi email trùng, tổng hợp dữ liệu trùng hoặc cập nhật cùng một bản ghi đồng thời.

`ScheduledExecutorService` chỉ điều phối task bên trong một JVM. Nó không cung cấp distributed lock, leader election hay bảo đảm chỉ một replica chạy job.

Với job chỉ được phép chạy một lần trên toàn hệ thống, cần cơ chế phối hợp bên ngoài:

- Distributed lock hoặc lease có thời hạn.
- Leader election với fencing token để instance cũ không tiếp tục ghi sau khi mất quyền.
- Bảng job schedule có unique key theo `jobName + scheduledSlot`.
- Queue/work partition để mỗi kỳ hoặc mỗi partition chỉ có một consumer sở hữu.
- Idempotency key để retry hoặc catch-up không tạo side effect trùng.

Không giữ một cờ `isLeader` trong heap rồi tin rằng nó vẫn hợp lệ sau restore. Lease có thể hết hạn khi checkpoint; hãy xác minh hoặc giành lease mới sau restore trước khi chạy job có quyền ghi.

## 11. Chọn chính sách theo loại tác vụ

| Loại tác vụ | Gợi ý lịch | Chính sách khi restore |
|---|---|---|
| Refresh cache từ nguồn chuẩn | Fixed delay hoặc fixed rate tùy yêu cầu freshness | Coalesce: refresh một lần sau restore |
| Thu thập metric theo nhịp | Fixed rate | Skip các sample bị lỡ nếu không cần dữ liệu liên tục; hoặc ghi rõ gap |
| Poll queue | Fixed delay | Chạy lại một lần sau restore; broker giữ message chưa ack |
| Tổng hợp theo bucket thời gian | Lịch theo slot cố định | Catch-up theo batch, có cursor và idempotency |
| Gửi báo cáo hàng ngày | Lịch calendar theo `ZoneId` | Xác định gửi bù hay bỏ kỳ; lưu idempotency key theo ngày/kỳ |
| Dọn dữ liệu cũ | Fixed delay hoặc lịch calendar | Thường coalesce, nhưng phải dựa trên cutoff bền vững |
| Heartbeat/lease renewal | Theo giao thức của hệ thống phụ thuộc | Cấp/renew lease mới sau restore trước khi coi instance là healthy |

Đây là gợi ý thiết kế. Quyết định cuối cùng phải theo cam kết nghiệp vụ, yêu cầu dữ liệu và khả năng retry của từng tác vụ.

## 12. Quan sát và kiểm thử

Nên theo dõi các tín hiệu sau:

| Metric/log | Ý nghĩa |
|---|---|
| Thời điểm dự kiến và thời điểm bắt đầu thực tế | Đo scheduler lag |
| Thời gian chạy mỗi lần | Phát hiện task lâu hơn period/delay |
| Số slot bị lỡ | Định lượng missed schedule sau checkpoint |
| Số lần chạy bù và backlog còn lại | Theo dõi catch-up |
| Task failure và trạng thái `ScheduledFuture` | Phát hiện periodic execution bị suppress |
| Checkpoint time và restore time | Tính khoảng thời gian scheduler bị gián đoạn |
| Instance ID/lease owner | Phát hiện nhiều replica chạy cùng một job |

Kịch bản kiểm thử nên gồm:

1. Task chạy nhanh hơn period để quan sát fixed-rate và fixed-delay.
2. Task chạy lâu hơn period để xác nhận không có overlap của cùng periodic task và hiểu scheduler lag.
3. Task ném exception để xác nhận các lần chạy tiếp theo bị suppress nếu exception thoát ra ngoài.
4. Checkpoint khi task đang chạy để xác nhận callback đợi drain hoặc từ chối checkpoint khi timeout.
5. Restore sau khoảng thời gian dài hơn nhiều chu kỳ và xác nhận chính sách skip/coalesce/catch-up.
6. Restore sau khi đổi timezone hoặc qua thời điểm DST nếu job dùng lịch calendar.
7. Khôi phục nhiều replica và xác nhận distributed coordination ngăn side effect trùng.
8. Làm database hoặc dependency tạm thời không truy cập được để xác nhận retry và readiness.

Hãy chạy các thử nghiệm trên đúng JDK/CRaC runtime và executor implementation sẽ dùng trong production. Ghi lại hành vi thực tế của delay queue qua checkpoint thay vì suy luận từ một lần chạy trên máy phát triển.

## 13. Checklist triển khai

- [ ] Đã chọn fixed rate hay fixed delay theo ý nghĩa của tác vụ.
- [ ] Đã hiểu rằng các lần chạy của cùng periodic task không chồng lấn, nhưng công việc async được submit có thể vẫn chồng lấn.
- [ ] Task xử lý exception rõ ràng để không vô tình suppress toàn bộ lịch.
- [ ] Đã xác định task có được phép bỏ lỡ một hoặc nhiều chu kỳ hay không.
- [ ] Đã chọn chính sách skip, coalesce hoặc catch-up cho khoảng thời gian checkpoint.
- [ ] Lịch quan trọng và tiến độ nghiệp vụ được lưu bền vững ngoài heap.
- [ ] `beforeCheckpoint` hủy trigger mới và chờ công việc hiện tại kết thúc trong deadline.
- [ ] `afterRestore` tạo executor mới và tính lại lịch theo nguồn dữ liệu chuẩn.
- [ ] Catch-up có giới hạn batch, rate limit và idempotency.
- [ ] Job có side effect được phối hợp giữa các replica bằng lease/lock/partition phù hợp.
- [ ] Đã kiểm thử hành vi missed schedule trên đúng CRaC JDK và nền tảng triển khai.

## 14. Kết luận

`scheduleAtFixedRate` giữ nhịp theo các thời điểm bắt đầu dự kiến; `scheduleWithFixedDelay` đợi đủ một khoảng sau khi lần chạy trước kết thúc. Fixed rate phù hợp khi nhịp chu kỳ quan trọng, fixed delay phù hợp khi cần khoảng nghỉ sau mỗi lần xử lý. Cả hai đều không cho phép các lần thực thi của cùng periodic task chồng lấn, nhưng task bất đồng bộ mà chúng tạo ra cần được quản lý riêng.

Với CRaC, hãy coi thời gian checkpoint là một khoảng gián đoạn mà lịch có thể bị lỡ. Dừng trigger và drain task trước checkpoint; sau restore, đọc trạng thái lịch bền vững và áp dụng chính sách skip, coalesce hoặc catch-up. Nếu job có side effect hoặc chạy trên nhiều replica, cần thêm idempotency và cơ chế phối hợp phân tán. Như vậy, lịch chạy phản ánh đúng yêu cầu nghiệp vụ thay vì phụ thuộc vào trạng thái timer còn nằm trong heap.
