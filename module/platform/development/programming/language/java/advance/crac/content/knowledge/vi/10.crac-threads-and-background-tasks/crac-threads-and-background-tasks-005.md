# Hủy lịch trước checkpoint và đăng ký lịch lại sau restore

Trong Java, các tác vụ chạy định kỳ thường được quản lý bằng ScheduledExecutorService, ScheduledThreadPoolExecutor hoặc scheduler của framework. Chúng có thể dùng thread nền, hàng đợi tác vụ, bộ đếm thời gian và trạng thái Future để quyết định lần chạy tiếp theo.

Khi ứng dụng dùng CRaC (Coordinated Restore at Checkpoint), không nên giả định một lịch đã đăng ký trước checkpoint sẽ tiếp tục đúng sau restore. Thread scheduler có thể đã dừng, thời gian chờ tương đối có thể không còn phù hợp, dependency như database hoặc HTTP client cần được tạo lại, và một lần chạy có thể bị trùng nếu ứng dụng đăng ký lịch mới mà không quản lý lịch cũ.

Cách tổ chức thường dùng là dừng trigger và chờ tác vụ đang chạy hoàn tất trước checkpoint, lưu trạng thái lịch nghiệp vụ, rồi tạo scheduler mới và đăng ký lại tác vụ sau restore. Nếu checkpoint bị hủy, ứng dụng cần khởi động lại lịch trong tiến trình ban đầu.

## 1. Scheduler, task và schedule khác nhau như thế nào?

Java cung cấp ScheduledExecutorService để lên lịch chạy tác vụ sau một khoảng thời gian hoặc lặp lại theo chu kỳ.

Các thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| ScheduledExecutorService | API lập lịch tác vụ theo thời gian |
| ScheduledThreadPoolExecutor | Implementation phổ biến dùng một nhóm thread để chạy tác vụ đã lên lịch |
| Runnable / Callable | Công việc được thực thi |
| ScheduledFuture | Đại diện cho tác vụ đã được lên lịch; có thể hủy hoặc kiểm tra trạng thái |
| Trigger / schedule metadata | Quy tắc nghiệp vụ quyết định khi nào tác vụ cần chạy tiếp |

Ví dụ:

~~~java
ScheduledExecutorService scheduler =
    Executors.newScheduledThreadPool(2);

ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
    this::refreshCache,
    0,
    5,
    TimeUnit.MINUTES
);
~~~

Trong ví dụ, scheduler quản lý thread và hàng đợi; future đại diện cho lịch đã đăng ký; refreshCache() là công việc thực tế.

Cần phân biệt **lịch nghiệp vụ** với **đối tượng ScheduledFuture**. Lịch nghiệp vụ có thể là “đồng bộ dữ liệu lúc 02:00 mỗi ngày theo múi giờ Asia/Ho_Chi_Minh”. ScheduledFuture chỉ là một đăng ký cụ thể trong một scheduler đang chạy. Sau restore, ứng dụng nên tái tạo đăng ký từ lịch nghiệp vụ thay vì phụ thuộc vào future cũ.

## 2. Vì sao cần hủy lịch trước checkpoint?

Một scheduler có thể giữ:

- Thread nền đang chờ hoặc đang thực thi.
- Hàng đợi các tác vụ one-shot và periodic.
- Trạng thái của ScheduledFuture.
- Delay được tính theo đồng hồ monotonic.
- Runnable có thể tham chiếu đến DataSource, HTTP client, file channel hoặc bean khác.
- Trạng thái thực thi của một lần chạy chưa hoàn tất.

Nếu checkpoint được tạo trong khi tác vụ đang chạy, sau restore có thể xuất hiện các vấn đề:

- Tác vụ chạy tiếp trong khi dependency bên ngoài đã bị đóng hoặc timeout.
- Lịch cũ và lịch mới cùng đăng ký, khiến tác vụ chạy hai lần.
- Một tác vụ đang ghi dữ liệu dở bị thực thi lại.
- Lần chạy tiếp theo bị trễ hoặc chạy ngay lập tức ngoài ý muốn.
- Scheduler giữ tham chiếu đến resource cũ sau khi resource mới được tạo.

Dừng lịch trước checkpoint giúp ứng dụng kiểm soát ranh giới giữa hai vòng đời. Mục tiêu không chỉ là ngừng thread scheduler; còn phải bảo đảm công việc đang chạy đã kết thúc hoặc được hủy theo chính sách nghiệp vụ.

### Hủy lịch không đồng nghĩa với dừng ngay tác vụ đang chạy

Với ScheduledFuture:

- cancel(false) ngăn các lần thực thi tiếp theo nhưng không yêu cầu ngắt lần chạy đang thực hiện.
- cancel(true) yêu cầu interrupt thread đang thực thi nếu có thể.
- Cả hai không bảo đảm tác vụ dừng ngay lập tức. Runnable phải hợp tác với tín hiệu interrupt và không bị kẹt vô hạn trong I/O hoặc lock.

Vì vậy, một quy trình an toàn thường gồm: ngừng tạo lần chạy mới, cancel future, chờ tác vụ đang chạy kết thúc, rồi shutdown scheduler.

## 3. Chọn cách lập lịch phù hợp

ScheduledExecutorService có ba cách lập lịch thường gặp.

### schedule(): chạy một lần sau delay

~~~java
scheduler.schedule(
    this::runReport,
    30,
    TimeUnit.SECONDS
);
~~~

Phù hợp với một tác vụ chỉ cần chạy một lần sau một khoảng thời gian. Nếu cần khôi phục sau checkpoint, ứng dụng phải lưu thời điểm hoặc deadline nghiệp vụ để tính delay mới.

### scheduleAtFixedRate(): chu kỳ theo thời điểm bắt đầu

~~~java
scheduler.scheduleAtFixedRate(
    this::poll,
    0,
    10,
    TimeUnit.SECONDS
);
~~~

Lịch cố gắng giữ khoảng cách giữa thời điểm bắt đầu các lần chạy theo chu kỳ đã chỉ định. Nếu một lần chạy kéo dài hơn chu kỳ, các lần chạy sau bắt đầu muộn hơn; cùng một periodic task không chạy chồng lấn lên chính nó trong executor này.

Cách này phù hợp khi cần nhịp chạy đều theo thời gian. Tuy nhiên, sau một khoảng checkpoint dài, ứng dụng cần quyết định có thực hiện các lần chạy bị lỡ hay chỉ chạy một lần để bắt kịp trạng thái hiện tại.

### scheduleWithFixedDelay(): chờ một khoảng sau khi lần trước hoàn tất

~~~java
scheduler.scheduleWithFixedDelay(
    this::syncData,
    0,
    10,
    TimeUnit.SECONDS
);
~~~

Khoảng delay được tính từ khi lần thực thi trước kết thúc đến lần tiếp theo. Cách này phù hợp với công việc polling hoặc đồng bộ mà không cần bám một nhịp đồng hồ tuyệt đối.

### So sánh

| Tiêu chí | Fixed rate | Fixed delay |
|---|---|---|
| Mốc tính chu kỳ | Thời điểm bắt đầu theo nhịp cố định | Sau khi lần trước hoàn tất |
| Khi tác vụ chạy lâu | Lần sau có thể bắt đầu ngay khi lần trước kết thúc nếu đã trễ nhịp | Luôn chờ đủ delay sau khi kết thúc |
| Phù hợp | Polling theo nhịp, đo lường định kỳ | Đồng bộ, dọn dẹp hoặc công việc cần nghỉ giữa các lần chạy |
| Khi restore | Cần quyết định xử lý các nhịp bị lỡ | Có thể bắt đầu lại với delay đã định nghĩa |

Không dùng fixed rate chỉ vì muốn “mỗi N giây chạy một lần”. Nếu thời gian xử lý biến động và không muốn các lần chạy nối sát nhau sau khi bị trễ, fixed delay thường dễ dự đoán hơn.

## 4. Lưu lịch nghiệp vụ thay vì dựa vào delay cũ

Delay của scheduler thường là thời gian tương đối. Trong khi đó, lịch nghiệp vụ thường được mô tả bằng thời điểm tuyệt đối hoặc quy tắc theo múi giờ.

Ví dụ:

- Chạy báo cáo lúc 02:00 mỗi ngày.
- Đồng bộ dữ liệu mỗi 15 phút.
- Làm mới token trước thời điểm hết hạn.
- Chạy cleanup vào Chủ nhật đầu tiên mỗi tháng.

Nếu checkpoint tồn tại trong một khoảng thời gian, một delay được tính trước checkpoint có thể không còn biểu diễn đúng thời điểm cần chạy sau restore.

Nên lưu thông tin như:

~~~text
jobId            = daily-report
scheduleVersion  = 4
zoneId           = Asia/Ho_Chi_Minh
nextRunAt        = 2026-11-14T02:00:00+07:00
lastSuccessfulAt= 2026-11-13T02:00:12+07:00
missedRunPolicy  = SKIP_AND_RUN_ONCE
~~~

Sau restore, dùng Clock hiện tại để tính delay:

~~~java
Duration remaining = Duration.between(
    clock.instant(),
    nextRunAt
);

long delayMillis = Math.max(0, remaining.toMillis());
~~~

Nếu nextRunAt đã ở trong quá khứ, ứng dụng cần một chính sách rõ ràng:

- **SKIP:** bỏ lần chạy đã lỡ và tính lần tiếp theo.
- **RUN_ONCE:** chạy một lần ngay sau restore, không chạy bù từng chu kỳ.
- **CATCH_UP:** chạy bù những lần bị lỡ nếu mỗi lần có ý nghĩa nghiệp vụ.
- **COALESCE:** gộp nhiều lần bị lỡ thành một lần xử lý trạng thái mới nhất.

Không nên mặc định chạy bù tất cả. Sau một thời gian dài, hàng trăm tác vụ dồn lại có thể làm quá tải database hoặc dịch vụ phụ thuộc.

### Lịch theo múi giờ và giờ mùa hè

Với lịch theo giờ địa phương, lưu ZoneId cùng quy tắc lịch. Không lưu một chuỗi “02:00” rồi giả định nó luôn tương ứng cùng một Instant. Quy tắc múi giờ có thể thay đổi; ở một số vùng, giờ địa phương có thể bị bỏ qua hoặc lặp lại khi chuyển giờ mùa hè.

Ở Việt Nam, ứng dụng thường dùng múi giờ Asia/Ho_Chi_Minh. Dù vậy, nên dùng ZoneId thay vì tự cộng hoặc trừ số giờ cố định để tính lịch ngày/tuần/tháng.

## 5. Dừng scheduler an toàn trước checkpoint

Một quy trình chuẩn bị có thể gồm:

1. Chặn việc đăng ký lịch mới và ngừng nhận yêu cầu kích hoạt tác vụ.
2. Hủy ScheduledFuture để ngăn các lần chạy tiếp theo.
3. Chờ lần chạy hiện tại hoàn tất hoặc gửi interrupt theo chính sách.
4. Shutdown scheduler để không nhận thêm tác vụ.
5. Chờ executor kết thúc trong thời gian giới hạn.
6. Lưu nextRunAt, trạng thái nghiệp vụ và thông tin cần thiết để đăng ký lại.
7. Đánh dấu thành phần đã chuẩn bị cho checkpoint.

Không giữ lock của component trong khi chờ executor kết thúc nếu Runnable có thể cần cùng lock để hoàn tất. Hãy chuyển trạng thái sang STOPPING trong một đoạn đồng bộ ngắn, sau đó nhả lock trước khi awaitTermination().

### Ví dụ dừng ScheduledThreadPoolExecutor

~~~java
private void stopScheduler() throws InterruptedException {
    ScheduledThreadPoolExecutor old;

    synchronized (this) {
        old = scheduler;
        if (old == null) {
            return;
        }

        if (scheduledFuture != null) {
            scheduledFuture.cancel(false);
        }

        old.shutdown();
    }

    if (!old.awaitTermination(30, TimeUnit.SECONDS)) {
        old.shutdownNow();

        if (!old.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Scheduled tasks did not terminate"
            );
        }
    }

    synchronized (this) {
        if (scheduler == old) {
            scheduler = null;
            scheduledFuture = null;
        }
    }
}
~~~

Nên cấu hình ScheduledThreadPoolExecutor để xử lý các task đã lên lịch khi shutdown:

~~~java
ScheduledThreadPoolExecutor executor =
    new ScheduledThreadPoolExecutor(1);

executor.setRemoveOnCancelPolicy(true);
executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
~~~

Các cấu hình này giúp loại bỏ task đã hủy khỏi hàng đợi và không tiếp tục thực thi delayed/periodic task khi executor shutdown theo chính sách tương ứng.

Nếu task không dừng sau shutdownNow(), không tạo scheduler mới chạy cùng một công việc. Hai lần chạy song song có thể ghi trùng dữ liệu hoặc tranh chấp tài nguyên. Giữ ứng dụng ở trạng thái chưa sẵn sàng, ghi log task chưa kết thúc và xử lý theo chính sách vận hành.

## 6. Hủy lịch bằng CRaC Resource

CRaC cung cấp Resource để thành phần đăng ký callback:

- beforeCheckpoint(): hủy lịch, dừng executor và lưu trạng thái cần thiết.
- afterRestore(): tạo scheduler mới và đăng ký lại lịch.

Ví dụ dưới đây minh họa một job chạy định kỳ bằng fixed delay. Job và các dependency được truyền vào resource; trong ứng dụng thực tế, job nên lấy dependency hiện tại khi thực thi thay vì giữ Connection hoặc client đã mở từ trước.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ScheduledJobResource implements Resource {
    private final Clock clock;
    private final Runnable job;
    private final Duration interval;

    private Instant nextRunAt;
    private ScheduledThreadPoolExecutor scheduler;
    private ScheduledFuture<?> scheduledFuture;

    public ScheduledJobResource(
            Clock clock,
            Runnable job,
            Duration interval,
            Instant nextRunAt) {
        this.clock = clock;
        this.job = job;
        this.interval = interval;
        this.nextRunAt = nextRunAt;

        startScheduler();
        Core.getGlobalContext().register(this);
    }

    private synchronized void startScheduler() {
        if (scheduler != null) {
            if (!scheduler.isShutdown()) {
                return;
            }

            if (!scheduler.isTerminated()) {
                throw new IllegalStateException(
                    "Previous scheduler has not terminated"
                );
            }
        }

        ScheduledThreadPoolExecutor next =
            new ScheduledThreadPoolExecutor(1);

        next.setRemoveOnCancelPolicy(true);
        next.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        next.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);

        long delayMillis = Math.max(
            0,
            Duration.between(clock.instant(), nextRunAt).toMillis()
        );

        scheduler = next;
        scheduledFuture = next.scheduleWithFixedDelay(
            this::runOneSafely,
            delayMillis,
            interval.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }

    private void runOneSafely() {
        try {
            job.run();
        } catch (RuntimeException failure) {
            // Ghi log và áp dụng chính sách lỗi của job.
            reportFailure(failure);
        } finally {
            synchronized (this) {
                nextRunAt = clock.instant().plus(interval);
            }
        }
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopScheduler();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        startScheduler();
    }

    public void restartAfterAbortedCheckpoint() {
        startScheduler();
    }

    private void stopScheduler() throws InterruptedException {
        ScheduledThreadPoolExecutor old;

        synchronized (this) {
            old = scheduler;
            if (old == null) {
                return;
            }

            if (scheduledFuture != null) {
                scheduledFuture.cancel(false);
            }

            old.shutdown();
        }

        if (!old.awaitTermination(30, TimeUnit.SECONDS)) {
            old.shutdownNow();

            if (!old.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Scheduled job is still running"
                );
            }
        }

        synchronized (this) {
            if (scheduler == old) {
                scheduler = null;
                scheduledFuture = null;
            }
        }
    }

    private void reportFailure(RuntimeException failure) {
        // Ghi log và cập nhật metric lỗi.
    }
}
~~~

Đây là khung minh họa; cần bổ sung logger, xử lý lỗi theo chính sách ứng dụng và bảo đảm job không giữ tài nguyên đã lỗi thời. Constructor gọi startScheduler() trước khi đăng ký Resource để thể hiện lifecycle; trong ứng dụng thực tế, cần bảo đảm job không bắt đầu trước khi các dependency của nó sẵn sàng.

### Tại sao tạo scheduler mới sau restore?

Sau beforeCheckpoint(), scheduler cũ đã shutdown và các thread của nó đã kết thúc. Vì vậy, afterRestore() tạo một ScheduledThreadPoolExecutor mới rồi đăng ký future mới.

Không nên dựa vào ScheduledFuture cũ để tiếp tục lịch. Future gắn với executor và hàng đợi cũ; nó không phải metadata lịch nghiệp vụ độc lập.

Mỗi lần khởi động lại cần bảo đảm chỉ có một scheduler và một future cho cùng job. Hàm startScheduler() nên idempotent để nhiều lời gọi trong cùng lifecycle không tạo lịch trùng.

## 7. Đăng ký lại lịch đúng thời điểm sau restore

Sau restore, không phải job nào cũng nên chạy ngay. Trước khi đăng ký lịch, ứng dụng có thể cần:

1. Tạo lại DataSource, HTTP client, file channel hoặc resource khác.
2. Xác minh dependency sẵn sàng.
3. Đọc lại cấu hình lịch và secret nếu cần.
4. Tính thời điểm chạy tiếp theo từ nextRunAt và chính sách missed-run.
5. Tạo scheduler mới.
6. Đăng ký một future duy nhất.
7. Mở lại cơ chế nhận yêu cầu hoặc kích hoạt job.

Nếu scheduler resource phụ thuộc vào database resource, cần bảo đảm database đã sẵn sàng trước khi job được phép chạy. Có thể điều phối thứ tự bằng một lifecycle coordinator thay vì để các callback độc lập tự khởi động công việc quá sớm.

### Không giữ Connection trong Runnable

Một Runnable có thể tồn tại trong heap qua checkpoint. Nếu Runnable giữ một Connection, EntityManager, HTTP response hoặc file channel đã đóng, việc đăng ký lại future không làm các dependency đó trở nên hợp lệ.

Nên để mỗi lần thực thi lấy dependency hiện tại:

~~~java
Runnable refreshJob = () -> {
    DataSource current = dataSourceProvider.current();

    try (Connection connection = current.getConnection()) {
        refreshFromDatabase(connection);
    } catch (SQLException failure) {
        throw new IllegalStateException(failure);
    }
};
~~~

dataSourceProvider là abstraction của ứng dụng trả về DataSource hiện tại. Cách này giúp job sử dụng pool mới sau restore thay vì giữ reference tới pool cũ.

## 8. Xử lý tác vụ đang chạy và tránh chạy trùng

Hủy future không tự hoàn tác công việc mà task đã thực hiện. Ví dụ, một job có thể đã gửi email, cập nhật database hoặc ghi file rồi mới bị interrupt.

Nên thiết kế task theo các nguyên tắc:

- Xử lý theo batch hoặc record có ranh giới commit rõ ràng.
- Dùng transaction cho nhóm thay đổi cần nhất quán.
- Dùng idempotency key để một lần chạy lại không tạo hiệu ứng phụ trùng lặp.
- Ghi nhận lastSuccessfulAt hoặc checkpoint nghiệp vụ sau khi hoàn tất.
- Kiểm tra interrupt tại các điểm an toàn nếu task hỗ trợ dừng.
- Không nuốt InterruptedException; khôi phục cờ interrupt hoặc kết thúc theo giao thức dừng.

Ví dụ:

~~~java
public void runBatch() {
    for (Record record : loadPendingRecords()) {
        if (Thread.currentThread().isInterrupted()) {
            return;
        }

        processIdempotently(record);
        markCompleted(record.id());
    }
}
~~~

Nếu task không thể dừng giữa chừng, hãy để nó hoàn tất trước khi checkpoint. Nếu task bị buộc dừng, cần lưu trạng thái để sau restore có thể tiếp tục từ record chưa commit.

### Đảm bảo một job không chạy ở hai instance

Khi restore từ cùng checkpoint image thành nhiều instance, mỗi instance có thể đăng ký cùng lịch. Nếu công việc tác động lên tài nguyên dùng chung, tất cả instance có thể chạy cùng một job.

Trong trường hợp đó, lịch trong bộ nhớ không đủ để bảo đảm chỉ có một người thực thi. Cần một cơ chế điều phối ngoài tiến trình, ví dụ:

- Database lease hoặc distributed lock.
- Leader election.
- Hàng đợi công việc có cơ chế consumer coordination.
- Job scheduler tập trung.
- Idempotency key và ràng buộc unique ở nơi lưu kết quả.

Lock trong Java chỉ phối hợp các thread trong một tiến trình; nó không ngăn instance khác chạy cùng job.

## 9. Xử lý lịch bị lỡ trong thời gian checkpoint

Giả sử job chạy mỗi 10 phút. Ứng dụng checkpoint lúc 10:02 và restore lúc 10:47. Có bốn lần chạy theo lịch có thể đã bị lỡ.

Không nên lấy future cũ và cố tiếp tục mà không xác định chính sách. Thay vào đó, dùng nextRunAt hoặc lastSuccessfulAt để quyết định:

| Chính sách | Hành vi sau restore | Ví dụ phù hợp |
|---|---|---|
| Skip | Bỏ các lần chạy đã lỡ, chờ mốc tiếp theo | Làm mới cache định kỳ |
| Run once | Chạy ngay một lần rồi tiếp tục lịch | Đồng bộ trạng thái mới nhất |
| Catch up | Chạy bù từng lần bị lỡ | Xử lý từng kỳ dữ liệu bắt buộc |
| Coalesce | Gộp nhiều kỳ thành một tác vụ | Tổng hợp số liệu hoặc cleanup |

Nếu dùng catch-up, cần giới hạn số lần chạy bù trong một đợt và kiểm soát tải. Nếu dùng run once, task phải lấy trạng thái mới nhất thay vì giả định mỗi tick đại diện một khoảng dữ liệu riêng.

### Tính thời điểm chạy tiếp theo

Ví dụ với lịch fixed delay dựa trên thời gian hiện tại:

~~~java
Instant nextRunAt = clock.instant().plus(interval);
~~~

Với lịch chạy theo giờ địa phương:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime now = ZonedDateTime.now(clock.withZone(zone));

ZonedDateTime nextRun = now
    .toLocalDate()
    .plusDays(1)
    .atTime(LocalTime.of(2, 0))
    .atZone(zone);

Instant nextRunAt = nextRun.toInstant();
~~~

Đây chỉ là minh họa cho lịch hàng ngày lúc 02:00; cần xử lý trường hợp thời điểm đã qua trong ngày và quy tắc chuyển giờ của ZoneId. Dùng java.time thay vì lưu một delay cố định cho lịch nghiệp vụ.

## 10. Nếu checkpoint bị hủy thì đăng ký lại lịch thế nào?

Một tình huống có thể xảy ra:

1. Resource A hủy lịch và shutdown scheduler trong beforeCheckpoint().
2. Resource B chạy callback sau đó và ném exception.
3. CRaC hủy checkpoint.
4. Tiến trình Java ban đầu tiếp tục, nhưng scheduler A đã dừng.

afterRestore() không phải callback rollback cho checkpoint bị hủy. Nó được dùng khi tiến trình thực sự được khôi phục từ checkpoint image.

Nếu ứng dụng gọi Core.checkpointRestore(), có thể bắt CheckpointException ở luồng điều phối và gọi restartAfterAbortedCheckpoint():

~~~java
try {
    Core.checkpointRestore();

    // Khi restore thành công, afterRestore() đã đăng ký lịch mới.
    resumeApplication();

} catch (CheckpointException checkpointFailure) {
    try {
        scheduledJobResource.restartAfterAbortedCheckpoint();
    } catch (RuntimeException restartFailure) {
        checkpointFailure.addSuppressed(restartFailure);
        markApplicationNotReady();
    }

    throw checkpointFailure;

} catch (RestoreException restoreFailure) {
    // Đây là lỗi ở instance đã restore.
    // Không xử lý như checkpoint bị hủy.
    markApplicationNotReady();
    throw restoreFailure;
}
~~~

Nếu restart lịch thất bại, ứng dụng không nên đánh dấu ready. Ghi log lỗi gốc và lỗi khởi động lại, giữ job ở trạng thái stopped/failed và để cơ chế giám sát xử lý.

### Khi checkpoint được yêu cầu bằng jcmd

Có thể gửi yêu cầu từ bên ngoài:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Trong trường hợp này, mã ứng dụng không có lời gọi Core.checkpointRestore() để bao quanh bằng try/catch. Vì vậy, coordinator trong ứng dụng không tự nhận được CheckpointException theo luồng gọi API của nó.

Nếu việc khôi phục lịch sau checkpoint bị hủy là yêu cầu bắt buộc, nên dùng endpoint hoặc cơ chế quản trị nội bộ để ứng dụng tự gọi Core.checkpointRestore() và thực hiện rollback. Nếu vận hành bằng jcmd trực tiếp, cần một quy trình quản trị riêng để xác định checkpoint thất bại và đưa scheduler trở lại trạng thái hoạt động. Không giả định CRaC sẽ tự gọi afterRestore() cho trường hợp hủy checkpoint.

## 11. Lịch do framework quản lý

Không phải ứng dụng nào cũng tạo ScheduledExecutorService trực tiếp. Framework có thể quản lý scheduler và đăng ký task qua annotation hoặc bean.

Ví dụ, Spring có thể dùng @Scheduled:

~~~java
@Scheduled(fixedDelayString = "PT5M")
public void refreshCache() {
    // Làm mới cache.
}
~~~

Nếu dùng framework, cần xác định:

- Scheduler bean nào thực thi phương thức.
- Thread pool được tạo và đóng ở đâu.
- Có thể pause/resume hoặc shutdown scheduler theo lifecycle API nào.
- Việc khởi tạo lại bean sau restore có đăng ký lịch trùng hay không.
- Các dependency được inject vào job có được cập nhật sau restore không.

Không nên gọi một phương thức khởi tạo scheduler thủ công trong afterRestore() nếu framework cũng tự khởi tạo lại scheduler. Điều đó có thể tạo hai thread pool hoặc hai lịch cho cùng một method.

Với Quartz hoặc scheduler lưu trigger trong database, cần phân biệt lịch được lưu bền vững với thread scheduler trong tiến trình. Sau restore, không tạo trigger trùng trong JobStore; hãy để scheduler kết nối lại JobStore theo lifecycle của framework và kiểm tra misfire policy. Nếu nhiều instance cùng chạy Quartz, cấu hình clustering và database lock phải được duy trì đúng.

## 12. Quản lý shutdown và lỗi khi dừng task

### Task không kết thúc trong timeout

Nếu task không kết thúc sau khi cancel(false), có thể gửi shutdownNow() để interrupt các thread. Tuy nhiên, interrupt chỉ là yêu cầu hợp tác. Task đang kẹt trong thư viện không hỗ trợ interrupt có thể vẫn chạy.

Không tạo executor mới trong khi executor cũ vẫn thực thi cùng công việc. Chọn một trong các hướng:

- Chờ task kết thúc trong giới hạn vận hành và hủy checkpoint nếu quá hạn.
- Thiết kế task kiểm tra interrupt tại các điểm an toàn.
- Đưa công việc dài sang một hàng đợi bền vững để có thể resume.
- Giữ instance ở trạng thái not-ready nếu không thể bảo đảm không chạy trùng.

### Task ném exception

Một periodic task được đăng ký bằng scheduleAtFixedRate() hoặc scheduleWithFixedDelay() sẽ không tiếp tục các lần chạy tiếp theo nếu một lần thực thi kết thúc bằng exception không được xử lý. Cần quyết định rõ:

- Ghi log và tiếp tục lịch.
- Dừng lịch và chuyển trạng thái job sang failed.
- Retry có giới hạn và backoff.
- Đưa công việc vào dead-letter queue hoặc cơ chế vận hành.

Nếu chọn bắt RuntimeException trong wrapper để tiếp tục, cần log và cập nhật metric; không nên nuốt lỗi hoàn toàn.

### Shutdown policy của ScheduledThreadPoolExecutor

Hai policy đáng chú ý:

- setExecuteExistingDelayedTasksAfterShutdownPolicy(false): không thực thi delayed one-shot task đã xếp hàng khi executor shutdown.
- setContinueExistingPeriodicTasksAfterShutdownPolicy(false): không tiếp tục periodic task sau shutdown.

setRemoveOnCancelPolicy(true) giúp xóa task đã hủy khỏi hàng đợi, tránh giữ các Runnable hoặc tham chiếu không cần thiết lâu hơn.

Cấu hình cần được áp dụng khi tạo mỗi scheduler mới, kể cả sau restore.

## 13. Quan sát lịch trước và sau restore

Nên log các thông tin sau:

- jobId và scheduleVersion.
- Thời điểm bắt đầu hủy lịch.
- Thời điểm future được cancel.
- Số tác vụ đang chạy.
- Kết quả awaitTermination.
- nextRunAt trước checkpoint.
- Thời điểm đăng ký lịch mới.
- Chính sách xử lý missed-run.
- Kết quả lần chạy đầu tiên sau restore.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| scheduled_job_active | Job có đang được đăng ký hay không |
| scheduled_job_running | Số lần chạy hiện tại |
| scheduled_job_cancel_total | Số lần lịch bị hủy |
| scheduled_job_restart_total | Số lần lịch được đăng ký lại |
| scheduled_job_failure_total | Số lần task thất bại |
| scheduled_job_last_success | Thời điểm chạy thành công gần nhất |
| scheduled_job_next_run | Thời điểm dự kiến chạy tiếp theo |
| scheduler_termination_timeout_total | Số lần scheduler không dừng đúng hạn |

Dùng jobId ổn định để liên kết log trước và sau restore. Nếu có nhiều instance, thêm instance ID và leader/lease owner để phân biệt lịch cục bộ với quyền thực thi job toàn hệ thống.

## 14. Quy trình triển khai

### Trước checkpoint

1. Chuyển job sang trạng thái không nhận trigger mới.
2. Lưu nextRunAt và trạng thái nghiệp vụ cần tiếp tục.
3. Cancel ScheduledFuture để ngăn lần chạy tiếp theo.
4. Chờ tác vụ đang chạy hoàn tất; dùng interrupt nếu chính sách cho phép.
5. Xác nhận transaction và tài nguyên của job đã được giải phóng.
6. Shutdown scheduler và chờ thread kết thúc.
7. Đánh dấu resource đã sẵn sàng cho checkpoint.

### Sau restore

1. Chờ DataSource, HTTP client, file resource và dependency khác sẵn sàng.
2. Đọc lại cấu hình lịch và trạng thái nghiệp vụ.
3. Tính delay mới từ nextRunAt hoặc chính sách lịch.
4. Tạo ScheduledThreadPoolExecutor mới.
5. Áp dụng shutdown policy và remove-on-cancel policy.
6. Đăng ký đúng một future cho mỗi job.
7. Mở lại khả năng thực thi job sau khi scheduler sẵn sàng.

### Khi checkpoint bị hủy

Nếu ứng dụng gọi Core.checkpointRestore():

1. Bắt CheckpointException.
2. Kiểm tra scheduler cũ đã kết thúc hay chưa.
3. Nếu scheduler cũ đã dừng, tạo scheduler mới.
4. Tính lại lần chạy tiếp theo từ trạng thái lịch đã lưu.
5. Bảo đảm không đăng ký trùng job.
6. Chỉ đánh dấu ready khi lịch đã hoạt động và dependency sẵn sàng.

Nếu checkpoint được yêu cầu từ jcmd bên ngoài, cần quy trình quản trị riêng vì luồng ứng dụng không bắt được exception của lệnh đó.

## 15. Nguyên tắc cần ghi nhớ

- Phân biệt lịch nghiệp vụ với ScheduledFuture và scheduler thread.
- Hủy future trước checkpoint để ngăn lần chạy tiếp theo.
- cancel(false) không dừng lần chạy hiện tại; phải drain hoặc chờ task kết thúc.
- Không giữ lock của component trong lúc awaitTermination() nếu task cần lock đó.
- Shutdown scheduler cũ và tạo scheduler mới sau restore.
- Lưu nextRunAt hoặc trạng thái lịch nghiệp vụ; không dựa vào delay cũ.
- Chọn rõ chính sách skip, run once, catch-up hoặc coalesce cho lần chạy bị lỡ.
- Không để Runnable giữ Connection, client hoặc resource đã đóng qua checkpoint.
- Bảo đảm chỉ có một future cho mỗi job trong một instance.
- Nếu restore nhiều instance, dùng distributed lock, lease hoặc job scheduler tập trung để tránh chạy trùng.
- Bắt CheckpointException để đăng ký lại lịch khi checkpoint bị hủy nếu ứng dụng chủ động gọi Core.checkpointRestore().
- Không dùng afterRestore() làm callback rollback cho checkpoint bị hủy.
- Nếu task không dừng hoặc lịch không thể khởi động lại, giữ ứng dụng ở trạng thái chưa sẵn sàng.

Lịch tác vụ là trạng thái vận hành của ứng dụng, còn scheduler là cơ chế thực thi lịch đó. Khi lưu lịch nghiệp vụ, dừng và drain task trước checkpoint, tạo scheduler mới sau restore và xử lý riêng trường hợp checkpoint bị hủy, ứng dụng có thể tiếp tục tác vụ nền đúng thời điểm mà không tạo lịch trùng hoặc chạy trên dependency đã lỗi thời.
