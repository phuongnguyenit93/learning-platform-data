# Xử lý tác vụ định kỳ và dữ liệu hết hạn sau thời gian tạm dừng

Checkpoint CRaC lưu trạng thái tiến trình tại một thời điểm, nhưng thời gian bên ngoài vẫn tiếp tục trôi trong lúc tiến trình tạm dừng. Một tác vụ định kỳ có thể đã lỡ lịch chạy, access token có thể hết hạn, cache có thể stale, session có thể bị thu hồi và lease có thể đã được cấp cho replica khác. Sau restore, những object trong heap vẫn có thể mang giá trị cũ dù trạng thái thực tế của hệ thống đã thay đổi.

Vì vậy, ứng dụng cần xác định rõ điều gì phải xảy ra với scheduler và dữ liệu có thời hạn khi checkpoint/restore. Không thể chỉ khôi phục một thread đang chờ theo delay cũ rồi giả định lịch chạy vẫn đúng. Cũng không thể coi một cache entry, token hoặc lock còn nằm trong heap là còn hiệu lực.

Bài thực hành này xây dựng cách xử lý hai nhóm trạng thái:

- **Tác vụ định kỳ:** lịch chạy, lần chạy bị bỏ lỡ, công việc đang thực hiện, retry, scheduler và quyền sở hữu job.
- **Dữ liệu hết hạn:** TTL, cache, token, session, certificate, lease, lock và các deadline nghiệp vụ.

Mục tiêu là bảo đảm ứng dụng tiếp tục đúng sau khi thời gian đã trôi qua, không chạy bù vô hạn, không bỏ sót công việc bắt buộc, không lặp side effect và không sử dụng dữ liệu đã hết hạn.

## 1. Vì sao thời gian tạm dừng làm thay đổi trạng thái ứng dụng?

Giả sử một dịch vụ được checkpoint lúc 09:00. JVM được restore lúc 11:30. Trong hai tiếng rưỡi đó:

- Một job đồng bộ dữ liệu dự kiến chạy lúc 09:15, 09:30 và 09:45.
- Access token hết hạn lúc 10:00.
- Cache entry có TTL 20 phút đã hết hạn.
- Lease leader có thời hạn 60 giây đã được coordinator cấp cho replica khác.
- Certificate có thể đã được rotate.
- Một phiên đăng nhập đã bị thu hồi.
- Retry deadline của một operation có thể đã qua.

Heap snapshot vẫn chứa object được tạo lúc 09:00. Nếu ứng dụng dùng trực tiếp các giá trị này sau restore, có thể phát sinh hành vi sai:

- Scheduler chạy dồn ba lần hoặc không chạy lần nào dù nghiệp vụ cần xử lý.
- Client gửi token hết hạn tới dịch vụ ngoài.
- Cache trả dữ liệu cũ.
- Replica cũ tiếp tục ghi bằng lease đã mất.
- Một retry thực hiện lại side effect đã hoàn tất.
- Job có deadline đã hết hạn vẫn được xử lý như thể còn mới.

Điểm quan trọng là phân biệt **trạng thái đã được snapshot** với **trạng thái còn hợp lệ tại thời điểm hiện tại**. CRaC phục hồi trạng thái tiến trình; ứng dụng phải đánh giá lại các điều kiện phụ thuộc thời gian và hệ thống bên ngoài.

### 1.1. Các nhóm thời gian cần quan tâm

| Nhóm | Ví dụ | Điều cần xác minh sau restore |
|---|---|---|
| Lịch định kỳ | Cron, fixed-rate, fixed-delay | Lịch tiếp theo và chính sách xử lý lần chạy bị lỡ |
| Deadline nghiệp vụ | Hạn thanh toán, thời gian giữ chỗ | Deadline còn hiệu lực hay phải chuyển trạng thái |
| TTL dữ liệu | Cache, session, temporary record | Dữ liệu còn hạn hay cần loại bỏ |
| Credential | Access token, refresh token, certificate | Credential còn hợp lệ và có thể bị thu hồi không |
| Lease/lock | Leader lease, distributed lock | Quyền sở hữu còn tồn tại hay phải acquire lại |
| Retry/backoff | Lần thử tiếp theo của operation | Retry window còn mở và lần thử có còn cần thiết không |
| Timeout kỹ thuật | Connection idle timeout, DNS TTL | Kết nối hoặc cache cần được tạo lại |
| Thời gian đo | Duration của callback, job | Dùng monotonic clock để đo khoảng thời gian |

### 1.2. Không phải mọi tác vụ bị lỡ đều cần chạy bù

Một lần chạy bị lỡ có thể cần được:

- Bỏ qua nếu dữ liệu chỉ cần trạng thái mới nhất.
- Gộp thành một lần chạy để cập nhật trạng thái hiện tại.
- Chạy bù từng kỳ nếu mỗi kỳ có ý nghĩa nghiệp vụ.
- Đưa vào durable queue để xử lý theo thứ tự.
- Hủy nếu deadline hoặc retry window đã hết.

Ví dụ, job refresh cache có thể chỉ cần chạy một lần sau restore để nạp dữ liệu mới nhất. Job lập hóa đơn theo từng ngày có thể phải tạo đủ hóa đơn cho mọi ngày bị bỏ lỡ. Không dùng một chính sách catch-up chung cho tất cả scheduler.

## 2. Phân biệt thời gian tuyệt đối và thời gian tương đối

Thiết kế đúng bắt đầu từ việc chọn loại thời gian phù hợp.

### 2.1. Thời gian tuyệt đối

Thời gian tuyệt đối biểu diễn một thời điểm trên timeline, thường dùng Instant:

~~~java
Instant expiresAt = Instant.parse("2026-11-13T10:00:00Z");
~~~

Giá trị này có thể được lưu bền vững, truyền qua service và so sánh sau khi tiến trình tạm dừng. Sau restore, ứng dụng lấy thời gian hiện tại từ Clock rồi kiểm tra:

~~~java
boolean expired = !clock.instant().isBefore(expiresAt);
~~~

Thời gian tuyệt đối phù hợp cho:

- Hạn hết hiệu lực của token hoặc session.
- Deadline nghiệp vụ.
- Thời điểm chạy của một lịch cụ thể.
- Thời gian tạo hoặc hết hạn của cache entry.
- Lease expiration theo hợp đồng của coordinator.

### 2.2. Thời gian tương đối

Thời gian tương đối mô tả một khoảng như “chờ 30 giây” hoặc “chạy lại sau 5 phút”. Scheduler thường dùng delay tương đối để lên lịch một lần thực thi:

~~~java
executor.schedule(task, 30, TimeUnit.SECONDS);
~~~

Delay tương đối hữu ích trong một tiến trình đang chạy, nhưng không nên là nguồn dữ liệu duy nhất cho deadline nghiệp vụ qua checkpoint. Khi restore, hãy tính lại delay từ thời điểm tuyệt đối hoặc từ trạng thái bền vững.

Ví dụ, nếu một token hết hạn lúc 10:00 và ứng dụng restore lúc 10:20, việc tiếp tục một bộ đếm “còn 5 phút” đã được tạo lúc 09:55 sẽ sai. Hãy đọc expiresAt, so sánh với thời gian hiện tại và lấy token mới.

### 2.3. System.nanoTime() và Instant

System.nanoTime() phù hợp để đo duration và timeout trong một lần chạy. Giá trị của nó có origin tùy ý và chỉ có ý nghĩa khi so sánh hiệu giữa các lần đọc trong cùng môi trường thực thi. Không lưu một giá trị nanoTime vào database hoặc checkpoint metadata rồi xem nó là timestamp tuyệt đối.

Quy tắc thực hành:

- Dùng Instant hoặc epoch timestamp cho thời điểm hết hạn và deadline cần tồn tại qua restore.
- Dùng System.nanoTime() để đo thời gian xử lý hoặc timeout ngắn trong tiến trình hiện tại.
- Sau restore, tạo lại timer tương đối từ deadline tuyệt đối và Clock hiện tại.
- Không trừ timestamp wall-clock từ hai máy nếu chưa xử lý clock skew.

### 2.4. Inject Clock để kiểm thử

Không gọi Instant.now() rải rác trong logic nghiệp vụ nếu cần test thời gian. Inject Clock:

~~~java
public final class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Trong production dùng Clock.systemUTC(). Trong test dùng Clock.fixed() hoặc một clock có thể điều khiển để tiến thời gian mà không phải chờ thật.

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-13T10:30:00Z"),
        ZoneOffset.UTC);

ExpirationPolicy policy = new ExpirationPolicy(fixedClock);
~~~

Clock injection giúp kiểm thử chính xác token hết hạn, TTL, missed schedule và deadline sau restore.

## 3. Xây dựng chính sách cho tác vụ định kỳ

Trước khi thay đổi code, hãy xác định semantics của lịch. Các kiểu lịch khác nhau cần cách phục hồi khác nhau.

### 3.1. Fixed-rate

Fixed-rate đặt lịch theo các mốc đều nhau tính từ một thời điểm gốc. Ví dụ: 10:00, 10:05, 10:10, 10:15.

~~~java
executor.scheduleAtFixedRate(
        task,
        0,
        5,
        TimeUnit.MINUTES);
~~~

Với scheduleAtFixedRate, lịch dựa trên nhịp định kỳ. Nếu một lần chạy lâu hơn chu kỳ, các lần chạy tiếp theo có thể bắt đầu muộn; cùng một periodic task không được thực thi đồng thời bởi chính executor đó. Sau thời gian tạm dừng, không nên giả định timer nội bộ sẽ tự tạo ra đúng hành vi nghiệp vụ mà hệ thống mong muốn.

### 3.2. Fixed-delay

Fixed-delay tính khoảng nghỉ sau khi lần chạy trước hoàn tất:

~~~java
executor.scheduleWithFixedDelay(
        task,
        0,
        5,
        TimeUnit.MINUTES);
~~~

Kiểu này phù hợp khi cần đợi một khoảng sau mỗi lần hoàn thành, ví dụ kiểm tra dependency 5 phút sau lần kiểm tra trước. Nó không tương đương lịch cố định theo đồng hồ.

Sau restore, hãy xác định liệu cần chờ 5 phút kể từ lúc job chạy lại, hay cần quay về mốc lịch cố định ban đầu. Đó là quyết định nghiệp vụ, không phải chi tiết triển khai của executor.

### 3.3. Calendar schedule và cron

Lịch như “02:00 mỗi ngày theo múi giờ Asia/Ho_Chi_Minh” là lịch theo calendar. Khoảng cách giữa hai lần chạy có thể không luôn là 24 giờ do daylight saving time ở một số vùng.

Lịch calendar cần lưu:

- Zone ID, ví dụ Asia/Ho_Chi_Minh hoặc Europe/Berlin.
- Quy tắc cron hoặc local time.
- Chính sách khi giờ địa phương không tồn tại do DST chuyển sang mùa hè.
- Chính sách khi một giờ địa phương xuất hiện hai lần khi DST kết thúc.
- Chính sách missed run sau khi ứng dụng dừng.

Không lưu một delay cố định 24 giờ rồi dùng nó thay thế lịch “mỗi ngày lúc 02:00” ở mọi múi giờ.

### 3.4. Chọn chính sách missed-run

| Chính sách | Hành vi sau restore | Ví dụ phù hợp |
|---|---|---|
| Skip | Bỏ các lần đã qua, lên lịch lần tương lai kế tiếp | Refresh cache, poll trạng thái hiện tại |
| Coalesce | Nếu có một hoặc nhiều lần bị lỡ, chạy một lần để bắt kịp trạng thái mới nhất | Đồng bộ snapshot, tổng hợp trạng thái |
| Catch-up | Chạy bù từng occurrence bị lỡ theo thứ tự | Tính lãi theo ngày, báo cáo theo kỳ |
| Durable replay | Đọc các occurrence chưa hoàn tất từ queue/store và xử lý idempotent | Billing, reconciliation, workflow |
| Expire | Hủy occurrence đã quá deadline | Notification hoặc offer có hạn |

Chính sách phải được ghi rõ trong tài liệu vận hành và acceptance criteria. Nếu job có side effect, cần xác định khóa nghiệp vụ cho mỗi occurrence để tránh xử lý lặp.

### 3.5. Lưu tiến độ bền vững

Với công việc quan trọng, không dựa vào biến lastRun chỉ nằm trong heap. Lưu tiến độ ở database hoặc durable scheduler:

| Trường | Ý nghĩa |
|---|---|
| job_name | Tên logic của job |
| scheduled_for | Thời điểm occurrence dự kiến |
| status | PENDING, RUNNING, SUCCEEDED, FAILED, EXPIRED |
| attempt | Số lần thử |
| lease_owner | Worker đang giữ quyền xử lý |
| lease_until | Thời điểm lease hết hạn |
| completed_at | Thời điểm hoàn tất |
| idempotency_key | Khóa chống side effect trùng |

Một occurrence có thể được định danh bằng (job_name, scheduled_for) hoặc một job key ổn định khác. Unique constraint giúp nhiều replica không tạo hai bản ghi cho cùng occurrence.

## 4. Chuẩn bị scheduler trước checkpoint

Scheduler là resource cần được quản lý có chủ đích. Trước checkpoint, ứng dụng cần dừng việc tạo task mới, xử lý task đang chạy và đưa scheduler về trạng thái có thể khởi tạo lại.

### 4.1. Ngừng nhận lịch mới

Khi bắt đầu quiesce:

1. Đánh dấu scheduler đang dừng.
2. Không đăng ký thêm task mới.
3. Hủy các lần chạy tương lai chỉ được lưu trong bộ nhớ nếu chúng sẽ được tính lại sau restore.
4. Giữ tiến độ của các job quan trọng trong durable store.
5. Chờ task đang chạy hoàn tất hoặc hủy theo chính sách.

Không để một thread scheduler tiếp tục tạo side effect trong lúc các Resource khác đang đóng database pool hoặc broker client.

### 4.2. Drain task đang chạy

Với mỗi job, xác định:

- Có thể hoàn tất trong thời hạn trước checkpoint không?
- Có thể dừng an toàn tại ranh giới transaction không?
- Nếu bị interrupt, job có thể retry không?
- Tiến độ hiện tại đã được ghi bền vững chưa?
- Side effect có idempotent không?

Nếu task không thể drain trong thời hạn, checkpoint nên bị từ chối hoặc job phải lưu checkpoint nghiệp vụ bền vững. Không checkpoint một task đang ở trạng thái không rõ commit/rollback.

### 4.3. Tránh giữ ScheduledFuture như nguồn sự thật

ScheduledFuture là trạng thái điều phối trong process. Nó không nên là nguồn có thẩm quyền cho biết một occurrence nghiệp vụ đã hoàn tất hay chưa.

Sau restore, hãy tái dựng lịch từ:

- Rule schedule.
- Clock hiện tại.
- Lần chạy thành công cuối cùng được lưu bền vững.
- Các occurrence đang pending.
- Chính sách missed-run.

Future chỉ là phương tiện để executor thực hiện lần chạy tiếp theo sau khi chính sách đã được tính toán.

### 4.4. Xử lý callback lỗi

Nếu callback beforeCheckpoint không thể drain task hoặc đóng scheduler, hãy làm cho checkpoint thất bại rõ ràng. Ứng dụng cần có cách rollback trạng thái quiescing nếu checkpoint bị hủy: khởi động lại scheduler hoặc đưa instance vào shutdown có kiểm soát.

Không đánh dấu callback thành công khi vẫn còn job chạy hoặc scheduler có thể phát sinh side effect trong lúc checkpoint. Với job không thể interrupt an toàn, ưu tiên đợi hoàn tất trong deadline hoặc từ chối checkpoint.

## 5. Khởi tạo lại scheduler sau restore

Sau restore, không chỉ tiếp tục một delay cũ. Tạo scheduler mới hoặc tái cấu hình scheduler theo lifecycle được hỗ trợ, tính lần chạy kế tiếp từ thời gian hiện tại và áp dụng missed-run policy.

### 5.1. Quy trình phục hồi

1. Tạo scheduler/executor mới.
2. Đọc schedule configuration hiện hành.
3. Đọc durable job progress.
4. Xác định occurrence bị lỡ trong khoảng tạm dừng.
5. Áp dụng Skip, Coalesce, Catch-up, Durable replay hoặc Expire.
6. Xác minh dependency và quyền sở hữu job.
7. Lên lịch các lần chạy hợp lệ.
8. Mở readiness khi ứng dụng có thể phục vụ theo policy.

Nếu scheduler chạy job cần database, broker hoặc secret manager, hãy bảo đảm các dependency đó đã sẵn sàng trước khi cho job bắt đầu. Không dựa vào thứ tự callback ngẫu nhiên giữa các resource để bảo đảm dependency luôn khởi tạo trước scheduler.

### 5.2. Ví dụ: tính lần chạy kế tiếp theo giờ địa phương

Ví dụ sau tính thời điểm chạy kế tiếp hằng ngày theo một ZoneId và LocalTime:

~~~java
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class DailySchedule {
    private final ZoneId zone;
    private final LocalTime runAt;

    public DailySchedule(ZoneId zone, LocalTime runAt) {
        this.zone = zone;
        this.runAt = runAt;
    }

    public Instant nextOccurrence(Instant now) {
        ZonedDateTime localNow = now.atZone(zone);
        ZonedDateTime candidate = localNow.toLocalDate()
                .atTime(runAt)
                .atZone(zone);

        if (!candidate.toInstant().isAfter(now)) {
            candidate = localNow.toLocalDate()
                    .plusDays(1)
                    .atTime(runAt)
                    .atZone(zone);
        }

        return candidate.toInstant();
    }
}
~~~

atZone() áp dụng quy tắc xử lý DST của Java cho local time không tồn tại hoặc bị lặp. Nếu nghiệp vụ cần quy tắc khác, phải xử lý rõ ràng và kiểm thử theo ZoneId tương ứng. Với dịch vụ cần lịch toàn cầu, lưu cả instant của occurrence và zone/rule dùng để tạo nó.

### 5.3. Ví dụ: scheduler CRaC dùng one-shot schedule

Ví dụ dưới đây minh họa một job cleanup chạy mỗi ngày tại giờ địa phương. Scheduler hủy lần chạy tương lai trước checkpoint, chờ task hiện tại hoàn tất, rồi tạo executor mới sau restore. Mỗi lần chạy nhận scheduledFor để có thể ghi nhận occurrence và thực hiện idempotent.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class DailyCleanupResource implements Resource {
    @FunctionalInterface
    public interface CleanupJob {
        void run(Instant scheduledFor) throws Exception;
    }

    private final Object lock = new Object();
    private final Clock clock;
    private final DailySchedule schedule;
    private final CleanupJob job;

    private ScheduledThreadPoolExecutor executor;
    private ScheduledFuture<?> nextRun;
    private boolean stopping;

    public DailyCleanupResource(
            Clock clock,
            ZoneId zone,
            LocalTime runAt,
            CleanupJob job) {
        this.clock = clock;
        this.schedule = new DailySchedule(zone, runAt);
        this.job = job;
        Core.getGlobalContext().register(this);
        start();
    }

    private void start() {
        synchronized (lock) {
            if (executor != null && !executor.isShutdown()) {
                return;
            }

            stopping = false;
            executor = new ScheduledThreadPoolExecutor(1);
            executor.setRemoveOnCancelPolicy(true);
            executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
            executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
            scheduleNextLocked(executor);
        }
    }

    private void scheduleNextLocked(ScheduledThreadPoolExecutor current) {
        Instant now = clock.instant();
        Instant scheduledFor = schedule.nextOccurrence(now);
        long delayMillis = Math.max(
                0L,
                Duration.between(now, scheduledFor).toMillis());

        nextRun = current.schedule(
                () -> executeAndReschedule(current, scheduledFor),
                delayMillis,
                TimeUnit.MILLISECONDS);
    }

    private void executeAndReschedule(
            ScheduledThreadPoolExecutor current,
            Instant scheduledFor) {
        synchronized (lock) {
            if (stopping || executor != current) {
                return;
            }
            nextRun = null;
        }

        try {
            job.run(scheduledFor);
        } catch (Exception failure) {
            // Ghi log/metric và lưu trạng thái lỗi theo chính sách của job.
            // Không được đánh dấu occurrence thành công khi job thất bại.
        } finally {
            synchronized (lock) {
                if (!stopping
                        && executor == current
                        && !current.isShutdown()) {
                    scheduleNextLocked(current);
                }
            }
        }
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        ScheduledThreadPoolExecutor current;

        synchronized (lock) {
            stopping = true;
            current = executor;
            executor = null;

            if (nextRun != null) {
                nextRun.cancel(false);
                nextRun = null;
            }
        }

        if (current == null) {
            return;
        }

        current.shutdown();
        if (!current.awaitTermination(30, TimeUnit.SECONDS)) {
            current.shutdownNow();
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Cleanup scheduler did not stop before checkpoint");
            }

            // Checkpoint sẽ bị hủy do callback ném exception.
            // Re-arm scheduler sau khi executor cũ đã dừng.
            start();
            throw new IllegalStateException(
                    "Cleanup task exceeded checkpoint drain deadline");
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        start();
    }
}
~~~

Đây là skeleton minh họa. CleanupJob cần ghi trạng thái occurrence vào nguồn bền vững, có idempotency key và xử lý lỗi rõ ràng. Trong ứng dụng thực tế, việc khởi động scheduler nên được điều phối sau khi các dependency bắt buộc đã phục hồi; không để task chạy trước database, secret hoặc coordinator.

Ví dụ chọn chính sách Skip cho lịch hằng ngày: nextOccurrence() trả về lần chạy tương lai kế tiếp. Nếu ứng dụng cần Catch-up hoặc Durable replay, phải truy vấn các occurrence bị lỡ từ database/queue thay vì chỉ tính một lần chạy kế tiếp.

Nếu callback bị timeout và shutdownNow() interrupt job, job phải hỗ trợ interruption và idempotency. Khi task không dừng được, không khởi động một scheduler thứ hai chạy cùng job; cần giữ instance chưa sẵn sàng và để hệ thống vận hành xử lý theo policy.

## 6. Xử lý lần chạy bị bỏ lỡ

### 6.1. Skip

Skip bỏ mọi occurrence đã qua và chỉ lên lịch lần kế tiếp trong tương lai.

Phù hợp với:

- Refresh cache từ nguồn hiện tại.
- Poll trạng thái mới nhất.
- Dọn dữ liệu có thể quét lại toàn bộ.
- Job không tạo ra một kết quả riêng cho mỗi kỳ.

Ví dụ: job đồng bộ cấu hình chạy mỗi 5 phút. Sau khi dừng 2 giờ, chạy một lần để lấy cấu hình mới nhất rồi tiếp tục chu kỳ.

### 6.2. Coalesce

Coalesce gộp nhiều occurrence bị lỡ thành một lần chạy đại diện. Job cần biết khoảng thời gian bị lỡ để xử lý dữ liệu tương ứng.

Ví dụ: job tổng hợp số liệu mỗi 10 phút có thể nhận from và to, rồi tổng hợp toàn bộ dữ liệu trong khoảng bị lỡ trong một lần.

Không coalesce nếu mỗi occurrence cần một side effect riêng, ví dụ gửi một hóa đơn cho mỗi ngày.

### 6.3. Catch-up

Catch-up chạy bù từng occurrence theo thứ tự. Cần giới hạn:

- Số occurrence tối đa trong một batch.
- Thời gian tối đa dành cho catch-up.
- Concurrency và thứ tự phụ thuộc.
- Retry và backoff.
- Điều kiện bỏ qua occurrence quá cũ.

Nếu job bị lỡ 1.000 lần, không tạo 1.000 thread hoặc request đồng thời ngay sau restore. Chạy theo batch, có backpressure và theo dõi backlog.

### 6.4. Durable replay

Với nghiệp vụ quan trọng, lưu occurrence trong database hoặc message queue. Mỗi occurrence có trạng thái, idempotency key và lease. Sau restore, worker query các occurrence chưa hoàn tất và claim theo transaction/locking.

Ví dụ:

~~~sql
CREATE TABLE scheduled_occurrence (
    job_name       VARCHAR(100) NOT NULL,
    scheduled_for  TIMESTAMP WITH TIME ZONE NOT NULL,
    status         VARCHAR(20) NOT NULL,
    attempt        INTEGER NOT NULL DEFAULT 0,
    lease_until    TIMESTAMP WITH TIME ZONE,
    completed_at   TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (job_name, scheduled_for)
);
~~~

Primary key ngăn tạo hai occurrence cho cùng job và thời điểm. Worker cần claim bằng một thao tác atomic hoặc transaction có locking phù hợp. Khi job hoàn tất, cập nhật trạng thái trong cùng ranh giới transaction với kết quả nghiệp vụ nếu có thể.

### 6.5. Expire

Một occurrence có thể không còn giá trị sau deadline. Ví dụ gửi thông báo trước giờ hẹn hoặc áp dụng ưu đãi chỉ có hiệu lực trong một cửa sổ ngắn. Sau restore, nếu deadline đã qua, đánh dấu EXPIRED thay vì chạy bù.

Tiêu chí cần định nghĩa:

- Deadline lấy từ đâu.
- So sánh bằng thời gian nào.
- Có cho phép grace period không.
- Có cần audit việc bỏ qua không.
- Có cần thông báo hoặc bù trừ nghiệp vụ không.

## 7. Dữ liệu hết hạn: TTL và expiration

TTL thường biểu diễn khoảng thời gian dữ liệu được xem là hợp lệ kể từ một thời điểm tạo hoặc cập nhật. Với ứng dụng có thể checkpoint, nên lưu thời điểm hết hạn tuyệt đối hoặc dữ liệu đủ để tính lại.

### 7.1. Lưu expiresAt thay vì chỉ lưu remainingSeconds

Không chỉ lưu:

~~~java
long remainingSeconds = 300;
~~~

vì giá trị này không tự giảm khi JVM dừng. Thay vào đó, lưu:

~~~java
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(5));
~~~

Sau restore:

~~~java
Duration remaining = Duration.between(clock.instant(), expiresAt);
if (remaining.isNegative() || remaining.isZero()) {
    expireEntry();
} else {
    scheduleExpiration(remaining);
}
~~~

expiresAt là nguồn xác định hiệu lực. Timer chỉ giúp thực hiện cleanup gần thời điểm đó; mọi lần đọc dữ liệu vẫn phải kiểm tra expiry.

### 7.2. Lazy expiration và background cleanup

Có hai cơ chế bổ trợ:

- **Lazy expiration:** kiểm tra thời điểm hết hạn khi đọc hoặc sử dụng dữ liệu. Nếu đã hết hạn, không trả dữ liệu và đánh dấu/xóa entry.
- **Background cleanup:** scheduler quét và xóa dữ liệu hết hạn để giải phóng bộ nhớ hoặc dung lượng.

Background cleanup không nên là cơ chế duy nhất bảo đảm dữ liệu hết hạn không được dùng. Scheduler có thể bị dừng, lỗi hoặc chạy trễ. Kiểm tra expiration tại điểm sử dụng mới là hàng rào đúng đắn.

### 7.3. Cache entry

Một cache entry có thể lưu:

~~~java
public record CacheEntry<V>(
        V value,
        Instant expiresAt,
        long sourceVersion) {

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Khi đọc:

~~~java
public Optional<CacheEntry<String>> getValid(
        String key,
        Clock clock) {
    CacheEntry<String> entry = cache.get(key);
    if (entry == null || entry.isExpired(clock)) {
        cache.remove(key);
        return Optional.empty();
    }
    return Optional.of(entry);
}
~~~

Sau restore, cache entry hết hạn phải được loại bỏ hoặc refresh. Nếu nguồn dữ liệu có version, hãy xác minh version trước khi sử dụng cache quan trọng.

### 7.4. Cache TTL dựa trên monotonic time

Một số cache dùng System.nanoTime() để tính TTL vì monotonic clock tránh ảnh hưởng của việc wall clock bị điều chỉnh. Cách này phù hợp trong một lần chạy, nhưng không nên xem giá trị nanoTime snapshot là timestamp bền vững.

Khi restore:

- Rebuild cache deadline từ expiresAt tuyệt đối nếu cần giữ expiry xuyên pause.
- Hoặc invalidate cache và nạp lại nếu không thể xác minh deadline.
- Không lấy một deadlineNanos cũ rồi trừ cho nanoTime hiện tại như thể origin chắc chắn không đổi.

Nếu cache chỉ là dữ liệu có thể tái tạo, invalidate toàn bộ cache sau restore thường đơn giản và an toàn hơn việc cố giữ lại trạng thái TTL phức tạp.

## 8. Access token, refresh token và session

Credential là dữ liệu có thời hạn và có thể bị thu hồi độc lập với expiry timestamp.

### 8.1. Access token

Không chỉ kiểm tra object token còn khác null. Sau restore, kiểm tra:

- exp và nbf nếu token có các claim đó.
- Issuer, audience và scope.
- Clock skew giữa client và issuer.
- Token có bị revoke hoặc policy thay đổi không.
- Credential có gắn với workload/replica identity cũ không.

Nên refresh trước expiry một khoảng an toàn, nhưng quyết định sử dụng token vẫn phải dựa trên thời gian hiện tại và phản hồi từ dịch vụ.

### 8.2. Refresh token

Refresh token cũng có thể hết hạn hoặc bị rotate. Một refresh token cũ có thể bị vô hiệu sau khi dùng thành công. Nếu nhiều replica restore từ cùng ảnh và cùng refresh token, chúng có thể đồng thời refresh; một số provider sẽ chỉ chấp nhận lần đầu hoặc rotate token khiến các lần sau thất bại.

Giải pháp:

- Cấp credential theo instance hoặc workload identity nếu provider hỗ trợ.
- Dùng một refresh coordinator hoặc single-flight mechanism có phạm vi phân tán khi token được chia sẻ.
- Lưu token mới theo cách atomic và bảo vệ secret.
- Không để nhiều replica cùng ghi đè refresh token mới bằng token cũ.
- Kiểm tra trạng thái token trước khi mở readiness nếu credential là dependency bắt buộc.

### 8.3. Session và cookie

Session có thể hết hạn hoặc bị thu hồi trong thời gian dừng. Session ID còn trong heap không chứng minh server-side session còn tồn tại.

Sau restore:

- Xác minh session với store có thẩm quyền.
- Không khôi phục trạng thái authenticated chỉ từ một cờ boolean trong heap.
- Nếu session không còn hợp lệ, yêu cầu đăng nhập lại hoặc thực hiện refresh theo giao thức.
- Không log session ID hoặc cookie nhạy cảm.

### 8.4. TLS certificate và connection

TLS connection đang mở thường không nên được xem là có thể tiếp tục vô điều kiện sau một thời gian dừng. Đóng và tạo lại connection giúp thực hiện handshake với certificate, trust store và endpoint hiện tại.

Nếu certificate hoặc CA được rotate trong thời gian dừng, client sau restore phải dùng trust material mới theo policy. Kiểm tra cả hostname, chain và validity period; chỉ kiểm tra socket còn mở là chưa đủ.

## 9. Lease, distributed lock và leader state

Lease là quyền sở hữu có thời hạn do một coordinator hoặc storage cấp. Một lease có thể hết hạn khi JVM đang dừng. Heap snapshot có thể vẫn chứa isLeader = true, lock handle hoặc lease token cũ.

### 9.1. Không tin cờ leader trong heap

Ví dụ nguy hiểm:

~~~java
if (leader) {
    performLeaderWork();
}
~~~

Nếu leader được đặt true trước checkpoint, replica có thể tiếp tục chạy công việc leader sau khi lease đã được cấp cho instance khác.

Sau restore, hãy:

1. Đánh dấu quyền sở hữu trong heap là chưa xác minh.
2. Kết nối coordinator.
3. Acquire lease mới hoặc xác minh lease theo giao thức.
4. Nhận fencing token/generation mới.
5. Chỉ thực hiện write nếu storage xác nhận token hiện tại.

### 9.2. Fencing token

Fencing token là giá trị tăng đơn điệu hoặc generation do coordinator cấp. Storage kiểm tra token trên mỗi thao tác được bảo vệ. Khi replica cũ restore với token N trong khi owner mới có N+1, write từ token N bị từ chối.

Không chỉ kiểm tra lease trong ứng dụng rồi tin rằng nó còn hiệu lực tới cuối transaction. Quyền có thể hết hạn ngay sau lần kiểm tra. Nơi nhận side effect cần xác minh fencing token hoặc cơ chế compare-and-set tương đương.

### 9.3. Distributed lock

Nếu lock có TTL, lock có thể hết hạn trong lúc pause. Sau restore:

- Không gọi unlock với token cũ nếu lock đã thuộc owner khác.
- Không tiếp tục critical section dựa trên lock handle snapshot.
- Acquire lại lock bằng owner identity hiện tại.
- Sử dụng fencing token nếu thao tác có thể ghi vào tài nguyên dùng chung.
- Đảm bảo cleanup khi acquire thất bại.

## 10. Retry, backoff và deadline nghiệp vụ

Retry state cũng phụ thuộc thời gian. Một task có thể đang chờ backoff khi checkpoint; khi restore, delay cũ không nhất thiết còn đúng.

### 10.1. Lưu retryAt tuyệt đối

Lưu nextAttemptAt hoặc retryDeadline thay vì chỉ lưu remaining delay:

~~~java
Instant nextAttemptAt =
        clock.instant().plus(Duration.ofMinutes(2));
~~~

Sau restore:

~~~java
Instant now = clock.instant();
if (!now.isBefore(nextAttemptAt)) {
    enqueueRetryIfStillNeeded();
} else {
    scheduleRetry(Duration.between(now, nextAttemptAt));
}
~~~

Trước khi retry, truy vấn trạng thái operation để xác định lần thử trước có thực hiện side effect hay chưa. Nếu kết quả không rõ, dùng idempotency key hoặc reconciliation.

### 10.2. Retry window đã hết

Nếu retryDeadline đã qua, không tiếp tục retry vô hạn. Chuyển operation sang trạng thái hết hạn hoặc cần can thiệp theo policy.

Ví dụ:

- Gửi OTP chỉ còn hiệu lực 5 phút.
- Gọi API giữ chỗ chỉ cho retry trong 10 phút.
- Thanh toán phải được reconciliation trước khi gửi lại.
- Notification cho một sự kiện cũ có thể không còn ý nghĩa.

### 10.3. Backoff và jitter

Sau khi nhiều replica restore cùng lúc, nếu tất cả retry ngay lập tức, dependency có thể bị retry storm. Tính lại backoff từ trạng thái bền vững, thêm jitter và giới hạn concurrency.

Không dùng cùng một random seed được snapshot cho mọi replica nếu seed đó tạo ra cùng chuỗi jitter. Nguồn randomness và lịch retry cần phù hợp với mô hình nhiều replica.

## 11. Bài thực hành: phục hồi scheduler và TTL cache

Bài thực hành xây dựng một service có job làm mới cache mỗi 5 phút và cache entry hết hạn sau 15 phút. Sau checkpoint, ta giả lập JVM dừng 25 phút rồi restore.

### 11.1. Yêu cầu

- Cache entry có expiresAt tuyệt đối.
- Mọi lần đọc cache đều kiểm tra expiration.
- Scheduler không dùng một ScheduledFuture snapshot làm nguồn sự thật.
- Job refresh có idempotency và có thể chạy lại.
- Sau restore, cache hết hạn bị loại bỏ hoặc refresh.
- Scheduler tính lần chạy kế tiếp từ Clock hiện tại.
- Readiness chỉ mở khi dependency bắt buộc sẵn sàng.

### 11.2. Model cache

~~~java
import java.time.Clock;
import java.time.Instant;

public record TimedValue<V>(
        V value,
        Instant expiresAt,
        String version) {

    public boolean validAt(Clock clock) {
        return clock.instant().isBefore(expiresAt);
    }
}
~~~

### 11.3. Repository cache

~~~java
import java.time.Clock;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class TimedCache<V> {
    private final ConcurrentHashMap<String, TimedValue<V>> values =
            new ConcurrentHashMap<>();
    private final Clock clock;

    public TimedCache(Clock clock) {
        this.clock = clock;
    }

    public Optional<TimedValue<V>> get(String key) {
        TimedValue<V> entry = values.get(key);
        if (entry == null) {
            return Optional.empty();
        }

        if (!entry.validAt(clock)) {
            values.remove(key, entry);
            return Optional.empty();
        }

        return Optional.of(entry);
    }

    public void put(
            String key,
            V value,
            java.time.Duration ttl,
            String version) {
        Instant expiresAt = clock.instant().plus(ttl);
        values.put(key, new TimedValue<>(value, expiresAt, version));
    }

    public void removeExpired() {
        values.entrySet().removeIf(
                entry -> !entry.getValue().validAt(clock));
    }

    public void invalidateAll() {
        values.clear();
    }
}
~~~

Đây là cache trong bộ nhớ để minh họa. Trong hệ thống thực tế, nếu cache có thể tái tạo và không cần giữ qua restore, có thể gọi invalidateAll() sau restore. Nếu cần giữ cache, lưu expiresAt và version của nguồn dữ liệu, sau đó xác minh trước khi trả kết quả.

### 11.4. Kiểm thử thời gian tạm dừng

Giả sử:

- Cache entry được tạo lúc 09:00 với TTL 15 phút.
- Checkpoint tạo lúc 09:05.
- Restore lúc 09:30.

Kết quả mong đợi:

- Entry hết hạn lúc 09:15.
- Sau restore lúc 09:30, get() không trả entry cũ.
- Background cleanup có thể xóa entry, nhưng tính đúng đắn không phụ thuộc cleanup đã chạy hay chưa.
- Refresh job chạy theo missed-run policy đã chọn.

### 11.5. Kiểm thử job refresh

Nếu refresh chỉ cần trạng thái mới nhất, chọn Coalesce: sau restore, nếu có một hoặc nhiều lần chạy bị lỡ, thực hiện một lần refresh và ghi nhận khoảng thời gian đã bỏ qua.

Nếu job tạo một báo cáo riêng cho từng kỳ 5 phút, dùng Durable replay: tạo occurrence cho từng kỳ và xử lý idempotent.

Không dùng cùng một scheduler policy cho hai loại công việc chỉ vì chúng cùng chạy mỗi 5 phút.

## 12. Kiểm thử thời gian và tình huống biên

### 12.1. Pause ngắn và dài

Chạy test với nhiều khoảng dừng:

- Ngắn hơn chu kỳ scheduler.
- Dài hơn một chu kỳ.
- Dài hơn nhiều chu kỳ.
- Dài hơn TTL cache.
- Dài hơn access token expiry.
- Dài hơn lease duration.
- Dài hơn retry window.

Mỗi test phải xác định expected missed-run policy và trạng thái expiry.

### 12.2. Clock skew

Trong hệ thống phân tán, máy ứng dụng và dependency có thể lệch giờ. Nếu token expiry hoặc lease được đánh giá ở nhiều nơi, cần có clock synchronization và safety margin.

Không tùy tiện tăng grace period đến mức chấp nhận credential đã hết hạn. Với token, dùng skew allowance theo giao thức và issuer; với lease, ưu tiên coordinator/fencing semantics thay vì so sánh giờ cục bộ.

### 12.3. DST và múi giờ

Kiểm thử lịch calendar ở các thời điểm:

- Giờ địa phương bị bỏ qua khi chuyển sang DST.
- Giờ địa phương xuất hiện hai lần khi kết thúc DST.
- Ngày chuyển tháng, năm nhuận và cuối tháng.
- Thay đổi ZoneId hoặc cấu hình lịch.

Nếu lịch mang ý nghĩa toàn cầu, lưu thời điểm tuyệt đối. Nếu lịch mang ý nghĩa địa phương như “mỗi ngày lúc 02:00 theo giờ chi nhánh”, lưu cả ZoneId và policy DST.

### 12.4. Wall clock bị điều chỉnh

NTP có thể slew hoặc step wall clock. Timer dựa trên monotonic clock và deadline dựa trên wall clock có mục tiêu khác nhau. Với deadline nghiệp vụ, dùng thời điểm có thẩm quyền và kiểm tra skew. Với duration nội bộ, dùng monotonic clock.

Trong test, dùng injected Clock để mô phỏng thời gian nhảy tới trước hoặc lùi. Không thay đổi đồng hồ hệ điều hành production để kiểm thử expiration.

### 12.5. Restore nhiều replica cùng lúc

Nếu cùng checkpoint được restore thành nhiều replica:

- Tất cả có thể tính cùng next schedule.
- Tất cả có thể cùng phát hiện một occurrence bị lỡ.
- Tất cả có thể cùng refresh token.
- Tất cả có thể cùng dọn một tập dữ liệu.
- Tất cả có thể cùng retry một operation.

Dùng distributed claim, unique occurrence key, idempotency key, lease/fencing và jitter. Một biến alreadyRan trong heap không thể điều phối nhiều tiến trình.

## 13. Observability cho scheduler và expiration

### 13.1. Log lifecycle

Ghi các sự kiện:

- Scheduler quiescing bắt đầu/kết thúc.
- Số task đang chạy và số occurrence pending.
- Task bị hủy hoặc hoàn tất trước checkpoint.
- Checkpoint preparation thất bại do task chưa drain.
- Restore bắt đầu/kết thúc.
- Missed occurrence được skip, coalesce, catch-up hoặc expire.
- Scheduler mới được tạo và lần chạy kế tiếp được tính.
- Cache entry bị expire hoặc refresh.
- Credential refresh thành công/thất bại.
- Lease acquire/reacquire và fencing token generation.
- Readiness mở sau khi dependency sẵn sàng.

Mỗi log nên có job name, occurrence key, service ID, replica ID và process incarnation ID. Không ghi token, session cookie hoặc secret.

### 13.2. Metric gợi ý

| Metric | Ý nghĩa |
|---|---|
| crac_scheduler_quiesce_duration_seconds | Thời gian dừng và drain scheduler |
| scheduled_occurrence_missed_total | Số occurrence bị lỡ |
| scheduled_occurrence_skipped_total | Số occurrence bị bỏ qua theo policy |
| scheduled_occurrence_coalesced_total | Số occurrence được gộp |
| scheduled_occurrence_replayed_total | Số occurrence được chạy bù |
| scheduled_occurrence_expired_total | Số occurrence hết hạn |
| scheduled_job_duration_seconds | Thời gian thực thi job |
| scheduled_job_failure_total | Số lần job thất bại |
| scheduled_job_backlog | Số occurrence chưa xử lý |
| cache_entry_expired_total | Số cache entry hết hạn |
| credential_refresh_failure_total | Số lần refresh credential thất bại |
| lease_reacquire_failure_total | Số lần acquire lease sau restore thất bại |
| restore_to_scheduler_ready_seconds | Thời gian tới khi scheduler được phép chạy |

Tên metric là gợi ý. Tránh dùng occurrence ID, user ID hoặc token ID làm label có cardinality cao; giữ chúng trong log/trace có kiểm soát.

### 13.3. Dashboard

Dashboard sau restore nên thể hiện:

- Restore-to-ready và scheduler-ready time.
- Số occurrence bị lỡ theo job.
- Backlog và thời gian xử lý catch-up.
- Job duration và failure rate.
- Cache hit ratio và số entry hết hạn.
- Credential refresh latency/error.
- Lease reacquire success/failure.
- Readiness và traffic được nhận.

Nếu backlog tăng liên tục hoặc missed occurrence không giảm, scheduler có thể không bắt kịp tải dù process đã restore thành công.

## 14. Test matrix

| Nhóm | Điều kiện | Hành động | Kết quả mong đợi |
|---|---|---|---|
| Skip policy | Dừng qua nhiều chu kỳ | Restore scheduler | Chỉ chạy occurrence tương lai |
| Coalesce policy | Có nhiều lần refresh bị lỡ | Restore | Chạy một lần cập nhật trạng thái mới nhất |
| Catch-up | Nhiều kỳ nghiệp vụ bị lỡ | Restore | Chạy bù theo thứ tự và giới hạn batch |
| Durable replay | Occurrence còn PENDING | Restore nhiều worker | Claim atomic, không tạo business effect trùng |
| Expire policy | Deadline đã qua | Restore | Occurrence chuyển EXPIRED |
| Cache TTL | TTL hết trong thời gian dừng | Đọc sau restore | Entry không được trả |
| Token expiry | Access token hết hạn | Gọi API sau restore | Refresh trước khi dùng |
| Refresh token rotation | Nhiều replica restore | Refresh đồng thời | Một flow hợp lệ, không ghi đè token mới |
| Session revoke | Session bị thu hồi khi dừng | Restore | Không chấp nhận session cũ |
| Lease expiry | Lease hết hạn và owner mới được cấp | Restore owner cũ | Acquire lại hoặc ở follower |
| Retry deadline | Retry window đã hết | Restore | Không retry; chuyển trạng thái theo policy |
| Scheduler drain | Job đang chạy lâu | Checkpoint | Chờ hoàn tất hoặc từ chối checkpoint |
| Dependency unavailable | DB chưa sẵn sàng | Restore | Scheduler chưa chạy job cần DB |
| DST | Restore qua mốc DST | Tính next occurrence | Tuân thủ ZoneId và policy DST |
| Clock adjustment | Clock nhảy trước/lùi | Restore và kiểm tra TTL | Không dùng deadline nanoTime cũ |
| Multi-replica | N replica cùng image | Tất cả cùng thấy occurrence pending | Chỉ một claim hoặc effect idempotent |

## 15. Acceptance criteria

**AC-01 — Scheduler không dùng delay cũ**

- Điều kiện: tạo checkpoint khi scheduler đã có một task tương lai được lên lịch.
- Hành động: dừng tiến trình lâu hơn khoảng delay ban đầu rồi restore.
- Kết quả: lần chạy kế tiếp được tính lại từ schedule rule và thời gian hiện tại.
- Bằng chứng: scheduledFor, nextRun và log scheduler lifecycle.

**AC-02 — Task đang chạy được xử lý an toàn**

- Điều kiện: một job đang chạy khi bắt đầu checkpoint.
- Hành động: yêu cầu checkpoint.
- Kết quả: job hoàn tất ở ranh giới an toàn hoặc checkpoint bị từ chối; không có side effect dở dang bị coi là thành công.
- Bằng chứng: job status, transaction record và callback result.

**AC-03 — Missed-run policy**

- Điều kiện: ứng dụng dừng qua ít nhất ba occurrence.
- Hành động: restore.
- Kết quả: Skip, Coalesce, Catch-up, Durable replay hoặc Expire diễn ra đúng policy đã cấu hình.
- Bằng chứng: occurrence records và số business effect.

**AC-04 — Cache TTL**

- Điều kiện: cache entry hết hạn trong thời gian JVM dừng.
- Hành động: restore và đọc entry.
- Kết quả: entry không được trả; dữ liệu được refresh hoặc báo cache miss.
- Bằng chứng: expiresAt, cache lookup và source version.

**AC-05 — Credential hết hạn**

- Điều kiện: access token hết hạn trước restore.
- Hành động: thực hiện request được bảo vệ.
- Kết quả: token cũ không được gửi; credential mới được cấp trước khi request tiếp tục.
- Bằng chứng: audit metadata của issuer/service, không lưu token rõ.

**AC-06 — Lease cũ**

- Điều kiện: lease hết hạn và owner khác nhận fencing token mới.
- Hành động: restore replica cũ và yêu cầu write bằng token cũ.
- Kết quả: write bị từ chối; replica cũ chỉ hoạt động sau khi acquire quyền mới.
- Bằng chứng: coordinator record và storage response.

**AC-07 — Multi-replica schedule**

- Điều kiện: ít nhất ba replica restore từ cùng checkpoint và cùng thấy một occurrence pending.
- Hành động: tất cả cùng thử claim.
- Kết quả: một owner hợp lệ xử lý occurrence hoặc mọi lần thực thi được deduplicate theo business key.
- Bằng chứng: unique occurrence record, lease owner và effect ledger.

**AC-08 — Readiness**

- Điều kiện: dependency bắt buộc chưa sẵn sàng sau restore.
- Hành động: quan sát scheduler và readiness.
- Kết quả: job phụ thuộc không chạy và instance chưa nhận traffic cho tới khi dependency đạt điều kiện.
- Bằng chứng: readiness probe, dependency health và job execution log.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Job chạy dồn sau restore | Timer/fixed-rate tiếp tục catch-up ngoài ý muốn | Tính missed-run policy từ lịch và durable progress |
| Job không chạy lại | Executor đã shutdown trước checkpoint và không được tạo mới | Tạo scheduler mới sau restore |
| Hai replica chạy cùng job | Dựa vào cờ trong heap hoặc local lock | Durable claim, unique occurrence key và fencing |
| Cache trả dữ liệu cũ | Chỉ dựa vào timer cleanup | Kiểm tra expiresAt tại mỗi lần đọc |
| Token bị từ chối sau restore | Token hết hạn/revoke trong thời gian dừng | Refresh hoặc xác minh credential trước khi dùng |
| Nhiều replica refresh cùng token | Refresh token dùng chung và bị rotate | Coordinator/single-flight phân tán hoặc credential riêng |
| Replica cũ vẫn ghi sau lease expiry | Tin leader flag hoặc lock handle snapshot | Acquire lease mới và kiểm tra fencing tại storage |
| Retry storm | Nhiều replica cùng retry ngay sau restore | Backoff, jitter, concurrency limit và idempotency |
| Job chạy trước khi DB sẵn sàng | Scheduler start trước dependency recovery | Gate scheduler bằng readiness/dependency state |
| Expiration sai sau clock adjustment | Trộn nanoTime và wall-clock deadline | Lưu Instant, dùng Clock và monotonic clock cho duration |
| Lịch lệch một giờ quanh DST | Dùng delay 24 giờ cho calendar schedule | Tính occurrence bằng ZoneId và policy DST |
| Checkpoint bị treo khi scheduler drain | Job không có deadline hoặc không interruptible | Deadline, cooperative cancellation và durable progress |

## 17. Quy trình triển khai

1. Liệt kê tất cả scheduler, job, cache, token, session, lease và retry state.
2. Với từng trạng thái, xác định nguồn có thẩm quyền và thời hạn.
3. Chọn lịch fixed-rate, fixed-delay hay calendar.
4. Chọn missed-run policy cho từng job.
5. Lưu occurrence/progress quan trọng ở database hoặc durable queue.
6. Dùng idempotency key và unique constraint cho side effect.
7. Trước checkpoint, quiesce scheduler, drain task và hủy timer tương lai.
8. Tạo checkpoint sau khi callback resource hoàn tất.
9. Sau restore, đọc Clock hiện tại và tính lại deadline.
10. Làm mới credential, cache, session và lease theo policy.
11. Khởi tạo scheduler mới sau khi dependency bắt buộc sẵn sàng.
12. Claim occurrence một cách atomic và xử lý theo missed-run policy.
13. Mở readiness sau khi ứng dụng có thể phục vụ an toàn.
14. Theo dõi missed-run, backlog, expiry, retry và restore-to-ready metrics.
15. Kiểm thử nhiều thời gian dừng, nhiều replica và các tình huống clock/DST.

## 18. Checklist thực hành

### Scheduler

- [ ] Liệt kê lịch và semantics của từng job.
- [ ] Chọn Skip, Coalesce, Catch-up, Durable replay hoặc Expire.
- [ ] Lưu tiến độ job quan trọng ngoài heap.
- [ ] Dừng nhận task mới trước checkpoint.
- [ ] Drain task đang chạy trong deadline.
- [ ] Hủy timer tương lai được tính lại sau restore.
- [ ] Tạo scheduler mới sau restore.
- [ ] Gate job theo readiness của dependency.
- [ ] Dùng claim/lease/idempotency cho multi-replica.

### Dữ liệu hết hạn

- [ ] Lưu expiresAt tuyệt đối thay vì chỉ remaining delay.
- [ ] Kiểm tra TTL tại điểm đọc/sử dụng.
- [ ] Dùng background cleanup như tối ưu, không phải hàng rào duy nhất.
- [ ] Invalidate hoặc refresh cache sau restore.
- [ ] Kiểm tra access token và refresh token.
- [ ] Xác minh session và certificate hiện hành.
- [ ] Acquire lại lease và lock.
- [ ] Tính lại retry deadline và backoff.

### Thời gian và kiểm thử

- [ ] Inject Clock vào logic phụ thuộc thời gian.
- [ ] Dùng nanoTime chỉ để đo duration trong process.
- [ ] Kiểm thử pause ngắn và dài.
- [ ] Kiểm thử qua TTL, token expiry và lease expiry.
- [ ] Kiểm thử missed-run và retry window.
- [ ] Kiểm thử DST và clock skew nếu dùng calendar schedule.
- [ ] Restore nhiều replica từ cùng image.
- [ ] Kiểm tra unique occurrence và business side effect.
- [ ] Thu thập log/metric theo job, replica và incarnation.

## 19. Nguyên tắc cần nhớ

- Thời gian bên ngoài vẫn trôi trong khi JVM tạm dừng; heap snapshot không làm mới dữ liệu có thời hạn.
- Lưu deadline tuyệt đối bằng Instant; tính lại delay sau restore.
- Dùng System.nanoTime() cho duration trong process, không làm timestamp bền vững.
- Chọn missed-run policy riêng cho từng job: Skip, Coalesce, Catch-up, Durable replay hoặc Expire.
- Job quan trọng cần durable occurrence/progress, unique key và idempotency.
- Trước checkpoint, dừng scheduler, hủy timer tương lai và drain task đang chạy.
- Sau restore, tạo scheduler mới và tính lịch từ rule cùng thời gian hiện tại.
- Kiểm tra TTL tại điểm sử dụng; background cleanup chỉ giúp giải phóng tài nguyên.
- Refresh hoặc xác minh token, session, certificate, cache và lease trước khi dùng.
- Không tin cờ leader hoặc lock handle còn trong heap; dùng coordinator và fencing token.
- Dùng Clock injection để kiểm thử expiry, deadline, missed-run và DST.
- Khi nhiều replica restore cùng lúc, dùng claim phân tán, idempotency và backoff có jitter.
- Chỉ mở readiness khi scheduler và dependency có thể hoạt động theo policy.

Xử lý đúng tác vụ định kỳ và dữ liệu hết hạn giúp ứng dụng không bị lệch lịch, chạy lặp hoặc sử dụng trạng thái cũ sau CRaC restore. Khi lưu thời điểm có thẩm quyền, xác định chính sách missed-run, quản lý scheduler qua Resource lifecycle và xác minh TTL/credential/lease tại thời điểm sử dụng, tiến trình có thể tiếp tục an toàn dù đã tạm dừng trong vài phút hay nhiều giờ.
