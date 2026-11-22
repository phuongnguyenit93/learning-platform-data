# Lịch cron, tác vụ định kỳ và chính sách xử lý lần chạy bị bỏ lỡ

Ứng dụng Java thường chạy công việc theo lịch: đồng bộ dữ liệu mỗi vài phút, tổng hợp báo cáo lúc nửa đêm, làm sạch dữ liệu theo ngày hoặc gửi thông báo vào một thời điểm cố định. Khi ứng dụng sử dụng CRaC, tiến trình có thể tạm dừng tại checkpoint và tiếp tục sau một khoảng thời gian. Trong thời gian đó, các mốc cron vẫn trôi qua theo đồng hồ lịch. Nếu không thiết kế lại vòng đời scheduler, ứng dụng có thể chạy bù quá nhiều tác vụ cùng lúc, bỏ qua công việc cần thiết hoặc chạy một tác vụ hai lần.

Một scheduler an toàn cho checkpoint–restore cần xác định rõ ba điều: cách tạm dừng và tạo lại lịch, cách tính thời điểm chạy tiếp theo theo đồng hồ và múi giờ, và chính sách xử lý những lần chạy đã đến hạn trong lúc ứng dụng không hoạt động. Chính sách có thể là bỏ qua, chạy một lần ngay khi restore, chạy bù từng lần, gộp nhiều lần thành một lần hoặc chạy bù có giới hạn.

## 1. Phân biệt cron và tác vụ định kỳ theo khoảng thời gian

Không phải mọi lịch đều có cùng semantics.

| Kiểu lịch | Ví dụ | Cách xác định lần chạy tiếp theo |
|---|---|---|
| Fixed rate | Mỗi 10 giây theo nhịp định kỳ | Tính từ mốc bắt đầu và chu kỳ cố định |
| Fixed delay | Chờ 10 giây sau khi lần trước hoàn tất | Tính từ thời điểm hoàn tất lần chạy trước |
| Cron | Mỗi ngày lúc 02:30 theo múi giờ `Asia/Ho_Chi_Minh` | Tính từ biểu thức lịch và đồng hồ lịch |
| One-shot | Chạy tại một `Instant` cụ thể | Một thời điểm tuyệt đối |

`ScheduledExecutorService.scheduleAtFixedRate()` phù hợp với công việc có chu kỳ tương đối. `scheduleWithFixedDelay()` phù hợp khi khoảng nghỉ được tính sau khi lần trước hoàn tất. Hai phương thức này không thay thế cron calendar, vì cron thường phụ thuộc ngày trong tuần, ngày trong tháng, múi giờ và thay đổi giờ mùa hè (DST).

Ví dụ:

```java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

// Nhịp mục tiêu là mỗi 10 giây tính từ mốc ban đầu.
scheduler.scheduleAtFixedRate(
        this::refreshMetrics, 0, 10, TimeUnit.SECONDS);

// Chờ 10 giây sau khi mỗi lần refresh hoàn tất.
scheduler.scheduleWithFixedDelay(
        this::compactCache, 0, 10, TimeUnit.SECONDS);
```

Các lịch định kỳ của `ScheduledExecutorService` dùng thời lượng tương đối và không lưu lịch bền vững. Nếu ứng dụng cần lịch theo ngày/giờ hoặc cần xử lý chính xác các lần chạy bị lỡ trong lúc checkpoint, hãy lưu định nghĩa lịch và trạng thái lần chạy gần nhất, rồi tính lại lịch sau restore.

## 2. Đồng hồ lịch và đồng hồ đo thời lượng

Thiết kế scheduler cần phân biệt hai loại thời gian:

- **Wall-clock time:** thời gian lịch như `Instant`, ngày, giờ và múi giờ. Cron sử dụng thời gian này để xác định một lần chạy thuộc ngày nào và xảy ra lúc nào.
- **Monotonic time:** thời gian tăng đơn điệu dùng để đo thời lượng và deadline trong một tiến trình, thường lấy từ `System.nanoTime()`.

Không lưu một giá trị `System.nanoTime()` vào checkpoint hoặc cơ sở dữ liệu để dùng lại sau restore. Giá trị này chỉ có ý nghĩa trong phạm vi một lần chạy của hệ thống và không phải timestamp có thể so sánh giữa các tiến trình hay lần khởi động.

Với cron, hãy lưu `Instant` của lần chạy được lập lịch và dùng `ZoneId` để diễn giải biểu thức lịch. Khi restore, đọc đồng hồ hiện tại và tính lại lần chạy tiếp theo. Dùng `Clock` có thể inject vào scheduler để kiểm thử tình huống nhảy thời gian mà không phải chờ đồng hồ thật.

```java
Clock clock = Clock.systemUTC();
Instant now = clock.instant();

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime localNow = now.atZone(zone);
```

Đồng hồ hệ thống có thể được điều chỉnh bởi NTP hoặc quản trị viên. Nếu thời gian nhảy tiến, một số mốc cron có thể trở thành quá hạn; nếu thời gian lùi, một mốc lịch có thể xuất hiện lại theo cách triển khai cron. Với tác vụ quan trọng, cần lưu `scheduledAt` hoặc khóa định danh lần chạy để tránh chạy trùng khi đồng hồ thay đổi.

## 3. Múi giờ và thay đổi giờ mùa hè (DST)

Biểu thức cron như `0 30 2 * * *` có thể mang ý nghĩa khác nhau tùy múi giờ. Nếu ứng dụng chạy trên nhiều máy, không nên dựa vào múi giờ mặc định của JVM. Hãy cấu hình `ZoneId` rõ ràng:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
```

Múi giờ cố định theo vùng địa lý có thể có quy tắc lịch sử và tương lai riêng. Ở vùng có DST, một giờ địa phương có thể bị bỏ qua khi đồng hồ tiến lên và có thể xuất hiện hai lần khi đồng hồ lùi lại.

Ví dụ, một lịch lúc 02:30 ở vùng chuyển sang DST có thể gặp ngày mà 02:30 không tồn tại. Một lịch lúc 01:30 ở ngày chuyển ngược có thể khớp hai `Instant` khác nhau. Thư viện cron có thể chọn bỏ qua, dịch chuyển hoặc chạy hai lần tùy semantics.

Hãy quyết định và kiểm thử:

- Khi giờ địa phương không tồn tại, có bỏ qua lần chạy, chuyển sang thời điểm hợp lệ tiếp theo hay dùng một quy tắc khác?
- Khi giờ địa phương xuất hiện hai lần, có chạy một lần hay hai lần?
- Định danh lần chạy dựa trên `Instant` hay local date-time cộng với zone?
- Khi thay đổi phiên bản timezone database (tzdb), lịch đã lưu có được tính lại theo quy tắc mới không?

Đối với tác vụ tài chính hoặc nghiệp vụ phụ thuộc ngày làm việc, nên lưu cả `scheduledAt` dạng `Instant`, `ZoneId` và khóa lịch nghiệp vụ (ví dụ ngày báo cáo) để audit và chống trùng.

## 4. Vì sao checkpoint có thể tạo ra lần chạy bị bỏ lỡ?

Giả sử một tác vụ chạy mỗi ngày lúc 01:00. Ứng dụng tạo checkpoint lúc 00:50 và được restore lúc 03:15. Trong khoảng tiến trình không hoạt động, mốc 01:00 đã trôi qua. Scheduler trong heap có thể vẫn giữ một `ScheduledFuture` hoặc delay được tính trước checkpoint, nhưng nó không thể tự quyết định liệu nghiệp vụ cần chạy bù hay bỏ qua lần 01:00.

Để xử lý đúng, cần tách hai câu hỏi:

1. **Lịch tiếp theo là khi nào?** Tính bằng cron expression, zone và wall clock sau restore.
2. **Các mốc đã qua cần được xử lý thế nào?** Áp dụng misfire policy được xác định cho từng loại tác vụ.

Không nên đơn giản cộng thêm một chu kỳ vào thời điểm cũ. Với cron, lịch tiếp theo phải được tính lại bằng thư viện cron từ thời gian hiện tại hoặc từ cursor đã lưu, tùy chính sách misfire.

## 5. Các chính sách xử lý lần chạy bị bỏ lỡ

Một *misfire* là một lần chạy theo lịch đã đến hạn nhưng scheduler không kích hoạt đúng thời điểm, ví dụ vì ứng dụng đang checkpoint, restore, khởi động hoặc bị quá tải.

Các chính sách phổ biến:

| Chính sách | Hành vi sau restore | Phù hợp với |
|---|---|---|
| Skip (bỏ qua) | Đánh dấu các mốc quá hạn là đã bỏ qua và chờ mốc tương lai | Refresh/cache hoặc tác vụ chỉ cần trạng thái mới nhất |
| Fire once now | Chạy một lần ngay sau restore, dù có nhiều mốc bị lỡ | Đồng bộ trạng thái hoặc báo cáo có thể gộp |
| Catch up all | Chạy từng mốc bị lỡ theo thứ tự | Tác vụ cần xử lý từng kỳ riêng biệt |
| Coalesce | Gộp nhiều mốc bị lỡ thành một lần xử lý một khoảng | Tổng hợp dữ liệu, tính lại snapshot |
| Bounded catch-up | Chạy bù tối đa N lần hoặc trong một ngân sách thời gian, phần còn lại skip/coalesce | Lịch có thể tích lũy nhiều lần trong downtime |

Không có một chính sách đúng cho mọi tác vụ. Ví dụ, job gửi email nhắc việc theo từng mốc có thể cần catch-up có giới hạn; job refresh cache thường chỉ cần chạy một lần; job tính doanh thu theo từng ngày có thể phải xử lý từng ngày chưa hoàn tất.

### 5.1. Skip

Skip bỏ qua tất cả lần chạy có `scheduledAt` nằm trong khoảng ứng dụng không hoạt động. Sau restore, scheduler tính mốc cron kế tiếp trong tương lai và tiếp tục bình thường.

Chính sách này phù hợp khi lần chạy cũ không còn giá trị. Ví dụ, refresh cache lúc 01:00 có thể được thay bằng refresh ngay sau restore hoặc đợi lịch kế tiếp. Nếu bỏ qua, nên ghi nhận khoảng thời gian và số lần chạy đã bỏ qua để quan sát.

### 5.2. Fire once now

Nếu có một hay nhiều mốc bị lỡ, chạy tác vụ một lần ngay sau khi dependency đã sẵn sàng. Nhiều mốc quá hạn được đại diện bằng một lần thực thi.

Chính sách này phù hợp với tác vụ đồng bộ trạng thái mới nhất. Tuy nhiên, task phải đọc trạng thái hiện tại hoặc xử lý cả khoảng thời gian bị lỡ. Nếu mỗi mốc đại diện cho một kỳ nghiệp vụ riêng, fire once now có thể làm mất dữ liệu kỳ.

### 5.3. Catch up all

Chạy từng mốc bị lỡ theo thứ tự thời gian. Cách này bảo toàn từng kỳ nhưng có thể tạo ra một đợt tải lớn sau restore. Nếu downtime kéo dài nhiều ngày, scheduler có thể tạo hàng nghìn lần chạy liên tiếp.

Chỉ dùng catch-up all khi từng mốc thực sự cần xử lý riêng và hệ thống có thể chịu được khối lượng bù. Cần có giới hạn về thời gian, số task đồng thời và khả năng resume nếu quá trình catch-up bị gián đoạn lần nữa.

### 5.4. Coalesce

Gộp một dãy mốc bị lỡ thành một lần chạy đại diện cho một khoảng. Ví dụ, nếu job tổng hợp chạy mỗi giờ và ứng dụng nghỉ 6 giờ, một lần chạy có thể nhận `from=lastCompletedAt` và `to=now` rồi tổng hợp toàn bộ dữ liệu thay đổi.

Coalescing chỉ đúng khi logic nghiệp vụ có thể xử lý một khoảng dữ liệu. Không nên gộp những công việc mà mỗi lần chạy có tác dụng phụ độc lập, như gửi một hóa đơn cho từng kỳ.

### 5.5. Bounded catch-up

Chạy bù tối đa N mốc gần nhất hoặc tối đa trong một khoảng thời gian. Những mốc cũ hơn được skip hoặc gộp theo quy tắc riêng. Cách này giới hạn tải phục hồi nhưng cần lưu rõ phần nào đã chạy, phần nào bị bỏ qua và lý do.

## 6. Lưu trạng thái lịch và lần chạy

Nếu lịch chỉ nằm trong bộ nhớ, restore có thể giữ lại trạng thái Java cũ nhưng không đủ để biết một lần chạy đã hoàn tất nghiệp vụ hay chưa. Với tác vụ quan trọng, hãy lưu trạng thái thực thi vào database hoặc durable store.

Một bảng trạng thái có thể chứa:

| Trường | Mục đích |
|---|---|
| `job_id` | Định danh ổn định của job |
| `schedule_version` | Phiên bản cron expression và cấu hình |
| `zone_id` | Múi giờ dùng để diễn giải lịch |
| `scheduled_at` | Instant của mốc dự kiến chạy |
| `started_at` | Thời điểm bắt đầu thực thi |
| `completed_at` | Thời điểm hoàn tất |
| `status` | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `SKIPPED` |
| `attempt` | Số lần thử cho cùng một mốc |
| `lease_owner` / `lease_until` | Chủ sở hữu và hạn lease khi chạy nhiều instance |

Định danh một lần chạy có thể là khóa duy nhất `(job_id, schedule_version, scheduled_at)`. Điều này giúp chống tạo bản ghi chạy trùng khi nhiều instance cùng restore hoặc scheduler được khởi động lại.

Khi worker bắt đầu, nó cần claim một lần chạy bằng transaction hoặc cơ chế lease có điều kiện. Khi hoàn tất, cập nhật `SUCCEEDED` cùng `completed_at`. Nếu tiến trình dừng giữa chừng, lần chạy có thể vẫn ở `RUNNING`; quy trình phục hồi phải xác định lease đã hết hạn và quyết định retry hay đối soát kết quả trước khi chạy lại.

Không nên chỉ lưu một biến `lastRun` trong heap nếu job cần bảo đảm không mất hoặc chạy trùng qua checkpoint, crash và nhiều instance. Trạng thái bền vững giúp phân biệt lần chạy đã được lập lịch, đã bắt đầu, đã hoàn tất hoặc bị bỏ qua.

## 7. Idempotency và tác vụ chạy lại

Catch-up, retry hoặc restore có thể khiến cùng một mốc lịch được thực thi lại. Tác vụ cần có thiết kế idempotent: chạy lại cùng một `job_id` và `scheduled_at` không làm phát sinh kết quả nghiệp vụ trùng.

Ví dụ, thay vì luôn thêm một dòng báo cáo mới, job có thể ghi kết quả theo khóa `(report_date, report_type)` bằng upsert. Với thao tác gửi message, dùng event ID ổn định hoặc outbox để bảo đảm message không bị phát hai lần ngoài ý muốn.

Idempotency cần bao phủ cả side effect bên ngoài. Một transaction database không thể tự rollback email đã gửi hoặc HTTP request đã được server khác xử lý. Với tác vụ gọi dịch vụ bên ngoài, hãy dùng idempotency key nếu API hỗ trợ và lưu kết quả thực hiện để đối soát.

## 8. Tạm dừng scheduler trước checkpoint

Scheduler là một producer công việc. Trước checkpoint, cần ngăn nó kích hoạt task mới và xử lý các task đang chạy theo deadline.

Một trình tự thường dùng:

1. Đóng admission của job để không nhận thêm lần chạy mới.
2. Pause trigger hoặc cancel future tiếp theo.
3. Chờ task đang chạy hoàn tất trong thời gian giới hạn.
4. Lưu trạng thái lần chạy và cursor misfire cần thiết.
5. Dừng scheduler thread hoặc đưa scheduler vào trạng thái an toàn theo API thư viện.
6. Cho phép checkpoint khi không còn callback nào có thể truy cập shared resource đã đóng.

Không nên chỉ gọi `future.cancel(false)` rồi giả định job đã dừng. Tham số `false` không interrupt task đang chạy; task đó vẫn có thể tiếp tục. Cần theo dõi task đang chạy và chờ hoàn tất hoặc có chính sách hủy an toàn.

Với Quartz, Spring Scheduler hoặc thư viện khác, dùng API pause/shutdown và misfire handling mà thư viện cung cấp. Không tự thao tác trực tiếp với thread nội bộ của scheduler. Nếu thư viện có CRaC integration, ưu tiên dùng integration đó để quản lý timer, worker và trạng thái trigger.

## 9. Tính lại lịch sau restore

Sau restore, scheduler cần đọc đồng hồ hiện tại và trạng thái durable, sau đó áp dụng misfire policy trước khi mở lịch.

Quy trình:

1. Phục hồi database, message broker và các dependency mà job cần.
2. Đọc cấu hình cron, `ZoneId`, schedule version và trạng thái lần chạy gần nhất.
3. Xác định khoảng thời gian bị bỏ lỡ từ cursor đã lưu tới thời điểm hiện tại.
4. Tạo các lần chạy bù theo policy: skip, fire once, catch-up, coalesce hoặc bounded catch-up.
5. Claim lần chạy bằng khóa hoặc lease để tránh nhiều instance cùng chạy.
6. Đăng ký mốc cron tiếp theo trong tương lai.
7. Mở admission và readiness cho scheduler.

Hãy đăng ký các resource theo chiều dependency: database và dịch vụ nền trước scheduler; scheduler trước ingress hoặc producer khác nếu chúng phụ thuộc vào lịch. Global context gọi `beforeCheckpoint` theo thứ tự đăng ký đảo ngược và `afterRestore` theo thứ tự đăng ký. Nhờ vậy, scheduler có thể dừng trước khi dependency bị đóng và chỉ chạy lại sau khi dependency đã phục hồi.

## 10. Ví dụ thiết kế CronResource

Ví dụ sau minh họa một adapter scheduler có trách nhiệm dừng lịch, lưu trạng thái và khôi phục lịch. Phần tính cron được trừu tượng hóa qua `CronPlan`, vì cú pháp và semantics khác nhau giữa thư viện cron.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CronResource implements Resource {
    private final CronPlan plan;
    private final JobStateStore stateStore;
    private final JobRunner runner;
    private final Clock clock;
    private final ZoneId zone;
    private final MissedRunPolicy policy;

    private volatile boolean paused;

    public CronResource(
            CronPlan plan,
            JobStateStore stateStore,
            JobRunner runner,
            Clock clock,
            ZoneId zone,
            MissedRunPolicy policy) {
        this.plan = plan;
        this.stateStore = stateStore;
        this.runner = runner;
        this.clock = clock;
        this.zone = zone;
        this.policy = policy;
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        paused = true;
        runner.stopAdmissionAndAwaitCompletion(Duration.ofSeconds(20));
        stateStore.flush();
        runner.stopScheduler();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        Instant now = clock.instant();
        JobCursor cursor = stateStore.loadCursor(plan.jobId());

        MissedRunDecision decision = policy.decide(
                plan, cursor, now, zone);

        runner.executeMissedRuns(decision);
        runner.scheduleNext(plan.nextAfter(now, zone));
        runner.startScheduler();
        paused = false;
    }
}
```

Các interface trong ví dụ là abstraction do ứng dụng định nghĩa. Implementation thực tế cần bảo đảm `stopAdmissionAndAwaitCompletion()` có timeout và báo lỗi nếu job đang chạy chưa dừng; `executeMissedRuns()` cần claim từng lần chạy bằng transaction hoặc lease; `scheduleNext()` cần sử dụng thời điểm cron đã tính theo `Clock` và `ZoneId`.

Ví dụ cũng giả định các dependency của `CronResource` đã được phục hồi trước khi `afterRestore` chạy. Nếu scheduler có resource riêng cho database hoặc broker, hãy đăng ký các resource nền trước `CronResource` trong cùng context hoặc trong cây context tương ứng.

## 11. Mô hình quyết định misfire

Một policy có thể được cấu hình tường minh:

```java
public enum MisfireMode {
    SKIP,
    FIRE_ONCE_NOW,
    CATCH_UP_ALL,
    COALESCE,
    BOUNDED_CATCH_UP
}

public interface MissedRunPolicy {
    MissedRunDecision decide(
            CronPlan plan, JobCursor cursor, Instant now, ZoneId zone);
}
```

Khi tính các mốc đã quá hạn, policy nhận cursor và thời điểm hiện tại:

```java
public interface CronPlan {
    String jobId();

    Instant nextAfter(Instant instant, ZoneId zone);

    Instant nextAfterOrAt(Instant instant, ZoneId zone);
}

public interface JobStateStore {
    JobCursor loadCursor(String jobId);

    void flush() throws Exception;
}

public interface JobRunner {
    void stopAdmissionAndAwaitCompletion(Duration timeout) throws Exception;

    void executeMissedRuns(MissedRunDecision decision) throws Exception;

    void scheduleNext(Instant nextFireTime) throws Exception;

    void startScheduler() throws Exception;

    void stopScheduler() throws Exception;
}
```

`MissedRunDecision` và `JobCursor` cần được định nghĩa theo nghiệp vụ. Ví dụ, cursor có thể giữ `lastCompletedScheduledAt`, còn decision chứa danh sách mốc cần chạy, khoảng thời gian cần coalesce và các mốc được đánh dấu skip. Có thể lưu cấu hình riêng bằng một record chứa `MisfireMode`, `maxCatchUpRuns` và `maxCatchUpWindow`, rồi triển khai `MissedRunPolicy` từ cấu hình đó. Không nên chỉ dùng `now` để ghi đè cursor nếu các lần chạy cũ chưa được xử lý hoặc đánh dấu rõ ràng.

## 12. Cấu hình misfire theo từng loại job

Một ứng dụng thường có nhiều loại job, mỗi loại cần một policy khác nhau:

| Loại job | Policy thường phù hợp | Lý do |
|---|---|---|
| Refresh cache | Fire once now hoặc skip | Chỉ cần trạng thái mới nhất |
| Đồng bộ snapshot hiện tại | Coalesce | Có thể đồng bộ một khoảng thay đổi thành một lần |
| Tính báo cáo theo từng ngày | Catch-up hoặc bounded catch-up | Mỗi ngày là một kỳ nghiệp vụ riêng |
| Gửi email nhắc việc | Bounded catch-up hoặc skip | Cần tránh gửi hàng loạt email cũ sau downtime |
| Xóa dữ liệu hết hạn | Fire once now hoặc coalesce | Có thể quét toàn bộ dữ liệu hiện hết hạn |
| Đối soát giao dịch | Catch-up có kiểm soát | Cần xử lý từng kỳ và giữ audit trail |
| Health check định kỳ | Skip | Không cần chạy bù những lần kiểm tra đã lỡ |

Không dùng một global misfire policy cho mọi job. Cấu hình policy cùng job definition, lưu schedule version và ghi nhận thay đổi policy để có thể giải thích vì sao một lần chạy bị bỏ qua hoặc gộp.

## 13. Giới hạn tải khi chạy bù

Catch-up có thể làm scheduler tạo ra một đợt tải lớn ngay sau restore. Hãy kiểm soát:

- Số job chạy đồng thời.
- Số lần chạy bù tối đa cho từng job.
- Tổng thời gian dành cho catch-up.
- Tốc độ phát task vào worker pool.
- Quota và rate limit của dịch vụ bên ngoài.
- Mức ưu tiên giữa job bù và request trực tiếp.

Có thể chia catch-up thành batch nhỏ, lưu cursor sau mỗi batch và tiếp tục ở lần chạy sau. Nếu restore tiếp theo xảy ra giữa chừng, cursor durable cho phép tiếp tục mà không phải chạy lại toàn bộ lịch sử.

Không nên cho tất cả job chạy bù cùng lúc. Có thể ưu tiên job cần thiết để mở readiness, sau đó chạy các job ít quan trọng ở nền. Tuy nhiên, readiness của từng chức năng cần được tách rõ để hệ thống không nhận request cần dữ liệu chưa được cập nhật.

## 14. Framework scheduler và misfire semantics

Các framework có cách biểu diễn cron và xử lý misfire riêng. Trước khi tích hợp CRaC, hãy xác định:

- Trigger có được lưu bền vững hay chỉ nằm trong heap?
- Scheduler có API pause/resume và shutdown an toàn không?
- Trigger misfire được định nghĩa theo threshold nào?
- Khi scheduler khởi động lại, nó tự fire một lần, bỏ qua hay catch-up?
- Có thể đặt timezone trực tiếp cho cron trigger không?
- Job có được chạy đồng thời ở nhiều node không?
- Có cơ chế cluster lock hoặc misfire recovery nào sẵn có không?

Với Quartz, kiểm tra `CronTrigger` misfire instruction và cấu hình job store; không giả định `SMART_POLICY` mang nghĩa giống nhau cho mọi trigger type. Với Spring, kiểm tra `@Scheduled` và `TaskScheduler` đang dùng executor nào, timezone của cron được cấu hình ra sao và task đang chạy được xử lý thế nào khi context dừng. Nếu framework hoặc thư viện cung cấp CRaC integration, hãy dùng integration đó thay vì tự đóng thread nội bộ.

Một scheduler persistent vẫn cần chính sách nghiệp vụ cho lần chạy bị lỡ. Việc trigger được lưu trong database không tự quyết định có nên chạy bù tất cả mốc hay gộp chúng.

## 15. Kiểm thử lịch qua checkpoint–restore

Nên dùng `Clock` giả hoặc time provider có thể điều khiển để kiểm thử mà không phải chờ tới giờ cron thật.

Các trường hợp cần kiểm thử:

1. Restore trước mốc cron tiếp theo: scheduler tính đúng thời điểm tương lai.
2. Restore ngay sau một mốc: policy xử lý đúng một lần bị lỡ.
3. Restore sau nhiều mốc: skip, fire once, catch-up, coalesce và bounded catch-up cho kết quả khác nhau đúng cấu hình.
4. Job đang chạy khi checkpoint bắt đầu: admission đóng và task hoàn tất hoặc checkpoint thất bại theo deadline.
5. Checkpoint thất bại giữa quá trình quiesce: các scheduler đã pause được phục hồi an toàn.
6. Restore lặp lại khi catch-up chưa xong: cursor durable tránh mất hoặc chạy trùng kỳ.
7. Hai instance restore cùng lúc: chỉ một instance claim được cùng một scheduled run.
8. Đồng hồ nhảy tiến hoặc lùi: khóa lần chạy và cursor ngăn xử lý trùng hoặc bỏ sót ngoài ý muốn.
9. DST gap và overlap: lịch theo zone tuân thủ chính sách đã chọn.
10. Job gọi API bên ngoài: idempotency key giữ side effect ổn định qua retry.

Khi đo hiệu năng, ghi nhận thời gian từ restore tới lúc scheduler ready, số lần chạy bị lỡ, số lần catch-up, thời gian xử lý catch-up và tải lên dependency. Đừng chỉ đo thời gian JVM restore mà bỏ qua phần backlog công việc lịch.

## 16. Logging và quan sát

Mỗi lần chạy nên có các trường log có thể truy vết:

- `job_id` và `schedule_version`.
- `scheduled_at` và `zone_id`.
- `started_at`, `completed_at` và duration.
- `run_id` hoặc idempotency key ổn định.
- Trạng thái: success, failed, skipped, misfired hoặc coalesced.
- Misfire policy và khoảng thời gian bị ảnh hưởng.
- Số lần catch-up còn lại và số lần đã xử lý.
- Instance hoặc lease owner đã claim lần chạy.

Metric hữu ích gồm số lần chạy bị lỡ, số lần chạy bù, số job bị skip, thời gian catch-up, độ trễ scheduler và số job đang chạy. Tránh dùng `run_id` hoặc timestamp đầy đủ làm metric label vì cardinality có thể tăng rất lớn; dùng log hoặc trace cho định danh chi tiết.

## 17. Checklist triển khai

- [ ] Đã phân biệt cron calendar với fixed rate và fixed delay.
- [ ] Cron expression có `ZoneId` tường minh, không phụ thuộc timezone mặc định của JVM.
- [ ] DST gap và overlap có quy tắc đã được quyết định và kiểm thử.
- [ ] Không lưu `System.nanoTime()` làm timestamp dùng qua restore.
- [ ] Scheduler dừng nhận job mới trước checkpoint.
- [ ] Task đang chạy được drain hoặc xử lý theo deadline.
- [ ] Lịch và cursor lần chạy quan trọng được lưu bền vững.
- [ ] Mỗi job có misfire policy phù hợp: skip, fire once, catch-up, coalesce hoặc bounded catch-up.
- [ ] Catch-up có giới hạn tải và có thể resume qua nhiều lần restore.
- [ ] Mỗi scheduled run có định danh ổn định và xử lý idempotent.
- [ ] Nhiều instance không thể claim cùng một lần chạy nếu job yêu cầu single execution.
- [ ] Sau restore, dependency sẵn sàng trước scheduler và scheduler trước ingress phụ thuộc.
- [ ] Đã kiểm thử đồng hồ nhảy, DST, job chạy dở và restore lặp lại.
- [ ] Có log và metric về misfire, catch-up và độ trễ lịch.

## 18. Tài liệu tham khảo

- [Java `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): semantics của fixed-rate và fixed-delay scheduling.
- [Java `Clock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): abstraction đồng hồ để đọc thời gian hiện tại và kiểm thử.
- [Java `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): định danh múi giờ và quy tắc chuyển đổi thời gian địa phương.
- [CRaC API — `Resource`](https://javadoc.io/doc/org.crac/crac/latest/org/crac/Resource.html): callback quản lý tài nguyên trước checkpoint và sau restore.
- [Quartz Scheduler — CronTrigger Tutorial](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-06.html): cấu hình cron trigger và timezone.

Lịch cron cần được tính lại theo wall clock sau restore, còn deadline và thời lượng trong một lần chạy nên dùng monotonic clock. Hãy dừng scheduler và xử lý task đang chạy trước checkpoint; sau restore, phục hồi dependency, đọc cursor bền vững và áp dụng misfire policy theo từng job. Skip, fire once, catch-up, coalesce và bounded catch-up có tác động nghiệp vụ khác nhau, vì vậy cần kết hợp idempotency, giới hạn tải và quan sát để lịch định kỳ tiếp tục đúng sau mỗi chu kỳ checkpoint–restore.
