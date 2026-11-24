# Timer khi hoàn tất và LongTaskTimer cho thao tác còn hoạt động

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `Timer` và `LongTaskTimer` đều đo thời gian nhưng trả lời hai câu hỏi vận hành khác nhau. `Timer` ghi nhận duration khi một lần thực thi kết thúc. `LongTaskTimer` theo dõi những lần thực thi đang diễn ra, cho biết hiện có bao nhiêu tác vụ còn hoạt động và chúng đã chạy bao lâu.

Với request ngắn, `Timer` thường đủ để tính throughput, thời lượng trung bình và percentile của các lần hoàn tất. Với báo cáo, batch, export hoặc workflow kéo dài nhiều phút, chỉ dùng `Timer` có thể khiến dashboard chưa thấy gì trong khi công việc đang bị treo. Kết hợp cả hai giúp quan sát được lịch sử hoàn tất và tình trạng đang chạy.

## 1. Hai loại timer trả lời hai câu hỏi khác nhau

`Timer` đo những lần thực thi đã hoàn tất. Mỗi lần record đóng góp vào count, tổng thời gian và các thống kê phân phối được cấu hình. Trong lúc thao tác còn chạy, mẫu duration chưa được ghi nhận.

`LongTaskTimer` đo những thao tác hiện còn hoạt động. Khi gọi `start()`, meter bắt đầu theo dõi một sample. Trong thời gian sample chưa dừng, số tác vụ active và thời gian đã trôi qua được phản ánh trong các lần scrape/đọc meter. Khi gọi `stop()`, sample rời khỏi tập active.

| Đặc điểm | `Timer` | `LongTaskTimer` |
| --- | --- | --- |
| Thời điểm có mẫu | Khi lần thực thi hoàn tất | Ngay khi sample bắt đầu và trong lúc còn active |
| Số liệu chính | Count, total duration, max/histogram/percentile tùy cấu hình | Số task active, tổng duration đang chạy và duration lớn nhất đang active |
| Dùng cho | Throughput, latency của các lần hoàn tất, p95/p99 | Task đang chạy, task bị treo, tác vụ dài chưa kết thúc |
| Percentile histogram | Có thể cấu hình | Không phải mục đích của LongTaskTimer |
| Vòng đời sample | Record một lần khi hoàn tất | `start()` rồi `stop()` đúng một lần |

Không xem `LongTaskTimer` là một `Timer` có thời lượng lớn hơn. Chúng có semantics khác nhau và thường nên được dùng song song cho cùng một loại công việc.

## 2. Vì sao Timer chưa đủ cho tác vụ dài?

Giả sử một báo cáo mất 12 phút để tạo. Nếu chỉ dùng `Timer`, dashboard không có một quan sát duration hoàn tất trong suốt 12 phút đó. Nếu job bị deadlock hoặc chờ một dependency vô thời hạn, hệ thống có thể không bao giờ ghi nhận mẫu duration.

`LongTaskTimer` bắt đầu ghi nhận trạng thái ngay khi công việc thực sự bắt đầu. Trong thời gian job chạy, dashboard có thể cho biết:

- Có bao nhiêu báo cáo đang được tạo.
- Tổng thời gian tích lũy của các báo cáo đang active.
- Báo cáo active lâu nhất đã chạy bao lâu.

Khi job hoàn tất, `LongTaskTimer.Sample.stop()` loại sample khỏi trạng thái active. `Timer` ghi nhận duration hoàn tất để phân tích lịch sử. Nếu job bị treo, LongTaskTimer vẫn thể hiện nó đang hoạt động; đây là tín hiệu để điều tra trước khi có mẫu Timer.

## 3. Đăng ký Timer và LongTaskTimer

Cả hai loại meter có thể được đăng ký một lần trong bean instrumentation:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class ReportMetrics {
    private final Timer completed;
    private final LongTaskTimer active;

    public ReportMetrics(MeterRegistry registry) {
        this.completed = Timer.builder("reports.generation")
            .description("Duration of completed report generation tasks")
            .register(registry);

        this.active = LongTaskTimer.builder("reports.generation.active")
            .description("Report generation tasks currently running")
            .register(registry);
    }

    public Timer completedTimer() {
        return completed;
    }

    public LongTaskTimer activeTimer() {
        return active;
    }
}
```

`Timer` và `LongTaskTimer` nên có tên rõ ràng để dashboard phân biệt dữ liệu hoàn tất với dữ liệu active. Có thể dùng chung một tiền tố nghiệp vụ nhưng cần tránh định danh meter xung đột. Chỉ đăng ký meter một lần và tái sử dụng chúng trong suốt vòng đời ứng dụng.

## 4. Dùng cả hai cho cùng một thao tác đồng bộ

Một cách đơn giản là bắt đầu cả `Timer.Sample` và `LongTaskTimer.Sample` khi công việc bắt đầu. Trong `finally`, dừng LongTaskTimer và ghi duration hoàn tất vào Timer:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final Timer completedTimer;
    private final LongTaskTimer activeTimer;
    private final MeterRegistry registry;

    public ReportService(ReportMetrics metrics, MeterRegistry registry) {
        this.completedTimer = metrics.completedTimer();
        this.activeTimer = metrics.activeTimer();
        this.registry = registry;
    }

    public Report generate(String reportType) {
        Timer.Sample completedSample = Timer.start(registry);
        LongTaskTimer.Sample activeSample = activeTimer.start();

        try {
            return generateReport(reportType);
        }
        finally {
            activeSample.stop();
            completedSample.stop(completedTimer);
        }
    }

    private Report generateReport(String reportType) {
        // Đọc dữ liệu, tổng hợp và tạo báo cáo.
        return new Report(reportType);
    }
}
```

`LongTaskTimer` bắt đầu theo dõi ngay khi worker đi vào `generate()`. `Timer.Sample` ghi nhận duration khi method kết thúc. `finally` bảo đảm cả hai sample được dừng kể cả khi `generateReport()` ném exception.

`Timer.start(registry)` dùng clock của registry được truyền vào. Dùng cùng registry với meter đích giúp phép đo nhất quán với cấu hình clock của ứng dụng.

## 5. Vòng đời sample phải được quản lý đúng

`LongTaskTimer.Sample` đại diện cho một lần thực thi đang active. Mỗi sample cần được dừng đúng một lần khi công việc kết thúc. Nếu quên `stop()`, LongTaskTimer tiếp tục báo task đang chạy dù công việc đã kết thúc.

Mẫu an toàn:

Đoạn dưới giả định `registry`, `activeTimer` và `completedTimer` đã được inject vào bean:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

LongTaskTimer.Sample activeSample = activeTimer.start();
Timer.Sample completedSample = Timer.start(registry);

try {
    performWork();
}
catch (RuntimeException exception) {
    // Có thể tăng counter lỗi hoặc báo lỗi vào Observation.
    throw exception;
}
finally {
    activeSample.stop();
    completedSample.stop(completedTimer);
}
```

Không đặt `stop()` chỉ trong nhánh thành công. Exception, timeout và cancellation đều phải đi qua cleanup. Nếu tác vụ bị hủy trước khi bắt đầu, không có LongTaskTimer sample nào được tạo; nếu bị hủy trong khi đang chạy, đường thực thi worker phải đi qua `finally` để dừng sample.

## 6. Đo từ lúc worker bắt đầu, không tính queue wait vào active duration

Với executor, thời điểm submit và thời điểm worker bắt đầu có thể cách nhau đáng kể. Nếu mục tiêu là số tác vụ đang thực sự tiêu thụ worker, hãy gọi `LongTaskTimer.start()` bên trong task sau khi worker bắt đầu.

Đây là method trong một bean đã inject `registry`, `activeTimer` và `completedTimer`:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public CompletableFuture<Report> submitReport(
        String reportType,
        Executor executor) {
    return CompletableFuture.supplyAsync(() -> {
        LongTaskTimer.Sample activeSample = activeTimer.start();
        Timer.Sample completedSample = Timer.start(registry);
        try {
            return generateReport(reportType);
        }
        finally {
            activeSample.stop();
            completedSample.stop(completedTimer);
        }
    }, executor);
}
```

Trong ví dụ này, `LongTaskTimer` phản ánh phần processing trên worker. Thời gian task nằm trong queue không được tính vào active duration. Nếu cần quan sát queue wait hoặc end-to-end duration, hãy tạo Timer riêng ở ranh giới submit và worker start/completion.

Đối với `@Async`, đặt sample trong method async sau khi executor đã giao task cho worker. Đo quanh lời gọi `@Async` từ caller thường chỉ đo thời gian gửi task và lấy Future, không đo toàn bộ công việc nền.

## 7. Dùng LongTaskTimer với Observation

Observation cung cấp vòng đời start, scope, error và stop. Với meter observation handler mặc định, một Observation thường tạo Timer khi Observation kết thúc. Điều này phù hợp để đo duration của các lần hoàn tất, nhưng không tự động có nghĩa mọi Observation đều được theo dõi bằng LongTaskTimer.

Nếu cần số liệu active cho một loại Observation cụ thể, có thể thêm `ObservationHandler` riêng. Handler bắt đầu LongTaskTimer trong `onStart`, lưu sample vào context và dừng sample trong `onStop`:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class LongTaskObservationHandler
        implements ObservationHandler<Observation.Context> {

    private static final String OBSERVATION_NAME = "reports.generate";
    private final LongTaskTimer activeTimer;

    public LongTaskObservationHandler(LongTaskTimer activeTimer) {
        this.activeTimer = activeTimer;
    }

    @Override
    public void onStart(Observation.Context context) {
        if (OBSERVATION_NAME.equals(context.getName())) {
            context.put(LongTaskTimer.Sample.class, activeTimer.start());
        }
    }

    @Override
    public void onStop(Observation.Context context) {
        LongTaskTimer.Sample sample = context.get(LongTaskTimer.Sample.class);
        if (sample != null) {
            sample.stop();
        }
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }
}
```

Đăng ký handler một lần trong lúc cấu hình `ObservationRegistry`:

```java
observationRegistry.observationConfig()
    .observationHandler(new LongTaskObservationHandler(activeTimer));
```

Handler lọc theo tên Observation để chỉ theo dõi loại thao tác cần thiết. Nó dùng cùng context của Observation để lưu sample, nhờ vậy mỗi Observation có sample riêng. Khi Observation kết thúc do thành công hoặc exception, `onStop` dừng LongTaskTimer sample.

Nếu đã có handler mặc định ghi Timer, việc thêm handler này giúp cùng một Observation tạo cả duration hoàn tất và trạng thái active trong lúc chạy. Kiểm tra tên Observation và thứ tự handler thực tế trong ứng dụng; không đăng ký handler nhiều lần hoặc bắt đầu sample cho mọi Observation không cần thiết.

## 8. LongTaskTimer không cung cấp percentile của task đang chạy

LongTaskTimer được thiết kế để theo dõi trạng thái active. Nó không thay thế histogram của Timer và không cung cấp phân phối percentile của các lần thực thi đã hoàn tất.

Nếu cần trả lời câu hỏi “p95 thời gian tạo báo cáo là bao nhiêu?”, hãy dùng Timer và bật histogram hoặc client-side percentile phù hợp. Nếu cần trả lời “hiện có bao nhiêu báo cáo đang chạy và báo cáo active lâu nhất đã chạy bao lâu?”, dùng LongTaskTimer.

Hai loại meter bổ sung cho nhau:

- Timer cho lịch sử các lần hoàn tất.
- LongTaskTimer cho trạng thái hiện tại của các lần đang chạy.

Không suy ra p95 từ `LongTaskTimer.duration()` hoặc `max()`. Những giá trị này mô tả tập sample active tại thời điểm đọc, không phải phân phối của tất cả lần thực thi trong một cửa sổ lịch sử.

## 9. Đọc số liệu LongTaskTimer

Các API thường dùng gồm:

| API | Ý nghĩa |
| --- | --- |
| `activeTasks()` | Số sample đang active |
| `duration(TimeUnit)` | Tổng thời gian đã trôi qua của các sample active |
| `max(TimeUnit)` | Thời lượng lớn nhất trong các sample active |
| `start()` | Bắt đầu một sample mới |
| `Sample.stop()` | Kết thúc sample và trả về duration của sample đó |

Ví dụ đọc trực tiếp trong code:

```java
import java.util.concurrent.TimeUnit;

long activeCount = activeTimer.activeTasks();
double activeDurationSeconds = activeTimer.duration(TimeUnit.SECONDS);
double longestActiveSeconds = activeTimer.max(TimeUnit.SECONDS);
```

Các giá trị active duration thay đổi theo thời gian ngay cả khi không có task mới hoàn tất. Khi sample dừng, nó rời khỏi tập active; do đó `activeTasks()` và tổng duration active có thể giảm. Đây là hành vi đúng của gauge trạng thái, không phải counter bị reset.

## 10. Export sang Prometheus và truy vấn active task

Prometheus registry ánh xạ LongTaskTimer thành các series mô tả task active. Tên cụ thể phụ thuộc quy tắc chuẩn hóa của registry và phiên bản Micrometer; thường có series cho active count, tổng duration active và max duration active. Hãy kiểm tra `/actuator/prometheus` để lấy tên metric thực tế.

Ví dụ các biểu thức sau dùng tên minh họa sau chuẩn hóa:

```promql
reports_generation_active_count
```

Tổng số giây của các report đang chạy:

```promql
reports_generation_duration_sum
```

Thời gian của report active lâu nhất:

```promql
reports_generation_max
```

Đây là các giá trị trạng thái hiện tại, không phải counter tích lũy; không áp dụng `rate()` lên chúng. Nếu có nhiều instance, có thể `sum` active count để biết tổng số task đang chạy toàn service, còn max duration thường dùng `max` để tìm task lâu nhất trên mọi instance:

```promql
sum(reports_generation_active_count)
```

```promql
max(reports_generation_max)
```

Đối với Timer hoàn tất, truy vấn trung bình trong 5 phút có dạng:

```promql
sum(rate(reports_generation_seconds_sum[5m]))
/
sum(rate(reports_generation_seconds_count[5m]))
```

Nếu cần p95, bật histogram cho Timer và dùng `histogram_quantile()` trên `_bucket`. LongTaskTimer không thay thế histogram của Timer.

## 11. Thiết kế tag và cardinality

LongTaskTimer thường cần tag để phân biệt nhóm công việc, chẳng hạn `job_type=report|invoice` hoặc `queue=critical|default`. Tập giá trị nên nhỏ và ổn định.

Không gắn `jobId`, `userId`, file path tùy ý hoặc request ID vào tag. Mỗi giá trị mới có thể tạo một series active riêng. Nếu cần tìm một tác vụ cụ thể đang chạy, dùng log, trace hoặc một công cụ job tracking có định danh; metrics nên mô tả nhóm tác vụ.

Nếu muốn một LongTaskTimer cho từng loại job, có thể dùng `MeterProvider` để tạo meter theo tag có kiểm soát hoặc đăng ký trước các meter đã biết. Không tạo meter mới với tag động không giới hạn trong mỗi lần submit.

## 12. Xử lý exception, cancellation và timeout

Sample phải dừng trong mọi đường kết thúc:

- **Thành công:** dừng LongTaskTimer và ghi duration vào Timer.
- **Exception:** dừng sample trong `finally`; Timer vẫn ghi nhận duration của lần thực thi thất bại. Có thể thêm counter kết quả lỗi riêng.
- **Timeout:** nếu timeout làm worker thoát qua exception hoặc interrupt, `finally` dừng sample. Nếu chỉ caller ngừng chờ nhưng worker vẫn chạy, LongTaskTimer phải tiếp tục phản ánh task active.
- **Cancellation trước khi worker bắt đầu:** chưa có LongTaskTimer sample, vì vậy không có task active để dừng.
- **Cancellation khi worker đang chạy:** worker cần kết thúc qua `finally`. Nếu code bỏ qua interrupt và tiếp tục chạy, LongTaskTimer đúng khi vẫn báo active.

Không dừng sample từ callback caller chỉ vì `Future.cancel()` trả về true nếu công việc nền vẫn có thể tiếp tục chạy. Điểm dừng phải tương ứng với thời điểm worker thực sự kết thúc.

## 13. Kiểm thử Timer và LongTaskTimer

Có thể kiểm tra hai loại meter bằng `SimpleMeterRegistry` và latch để giữ một task active trong lúc assertion:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LongTaskTimerTest {
    @Test
    void exposesTaskWhileRunningAndTimerAfterCompletion() throws Exception {
        MeterRegistry registry = new SimpleMeterRegistry();
        Timer completed = registry.timer("reports.generation");
        LongTaskTimer active = registry.more().longTaskTimer("reports.generation.active");
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> future = executor.submit(() -> {
                Timer.Sample timerSample = Timer.start(registry);
                LongTaskTimer.Sample activeSample = active.start();
                started.countDown();
                try {
                    release.await();
                }
                catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(exception);
                }
                finally {
                    activeSample.stop();
                    timerSample.stop(completed);
                }
            });

            started.await();
            assertEquals(1, active.activeTasks());
            assertEquals(0, completed.count());

            release.countDown();
            future.get(5, TimeUnit.SECONDS);

            assertEquals(0, active.activeTasks());
            assertEquals(1, completed.count());
        }
        finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

Test giữ task ở trạng thái active để xác nhận LongTaskTimer tăng trước khi Timer có mẫu hoàn tất. Sau khi release latch, LongTaskTimer giảm active count về 0 và Timer count tăng lên 1. Không dùng `Thread.sleep()` để đo một con số duration cố định; thời gian thực thi phụ thuộc scheduler và máy chạy test.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Timer không có mẫu trong lúc job đang chạy | Timer chỉ ghi nhận khi sample hoàn tất |
| LongTaskTimer active count không giảm | Có nhánh không gọi `Sample.stop()` hoặc Observation không được stop |
| LongTaskTimer không thấy task đang chờ queue | Sample được start trước khi worker bắt đầu hoặc metric chỉ được start trong worker |
| Timer duration ngắn hơn thời gian người gọi chờ | Timer đo processing, không bao gồm queue wait hoặc callback phía caller |
| LongTaskTimer max giảm về 0 sau khi job xong | Max chỉ mô tả sample còn active; đây là hành vi bình thường |
| Không có p95 từ LongTaskTimer | LongTaskTimer không phải histogram của các lần hoàn tất |
| Task bị cancel nhưng vẫn active | Worker chưa thực sự dừng hoặc bỏ qua interrupt; cần kiểm tra vòng đời thực tế |
| Active count tăng gấp đôi | Sample bắt đầu ở nhiều lớp cho cùng thao tác hoặc handler đăng ký trùng |
| PromQL dùng `rate()` cho active count | Active count và active duration là gauge trạng thái, không phải counter |

Khi chẩn đoán, xem active count, active max, Timer count/rate, queue wait và trạng thái executor cùng nhau. Kiểm tra nơi sample bắt đầu và nơi dừng; với Observation, xác minh handler được đăng ký một lần và `onStop` luôn được gọi.

## 15. Nguyên tắc áp dụng

Dùng `Timer` để đo duration của các lần thực thi đã hoàn tất và phân tích throughput, mean, p95/p99. Dùng `LongTaskTimer` để theo dõi số lượng và thời gian của các lần thực thi vẫn còn hoạt động. Với tác vụ dài, kết hợp hai meter: bắt đầu LongTaskTimer khi worker thực sự chạy, dừng nó trong `finally`, đồng thời ghi duration hoàn tất vào Timer.

Nếu dùng Micrometer Observation, handler mặc định thường tạo Timer khi Observation kết thúc; muốn theo dõi trạng thái active cần LongTaskTimer instrumentation riêng hoặc `ObservationHandler` tùy chỉnh. Chọn ranh giới start/stop rõ ràng, xử lý exception/cancellation, dùng tag có cardinality thấp và kiểm tra metric export thực tế. Hai loại timer bổ sung cho nhau: một loại mô tả công việc đã xong, loại còn lại cho biết công việc nào vẫn đang diễn ra.

## Tài liệu tham khảo

- [Micrometer: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer: Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
- [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
