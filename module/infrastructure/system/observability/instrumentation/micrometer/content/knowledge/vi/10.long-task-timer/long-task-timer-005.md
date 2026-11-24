# Phân biệt thời gian tác vụ đang chạy với thống kê tác vụ đã hoàn tất

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `Timer` và `LongTaskTimer` đều đo thời gian nhưng trả lời hai câu hỏi vận hành khác nhau. `Timer` ghi nhận thời lượng của một lần thực thi khi lần đó kết thúc. `LongTaskTimer` theo dõi các lần thực thi vẫn đang chạy để hệ giám sát có thể quan sát chúng trước khi hoàn tất.

Sự khác biệt này quan trọng với những công việc kéo dài như tạo báo cáo, nhập dữ liệu, xử lý batch, đồng bộ hệ thống hoặc chạy tác vụ nền. Nếu chỉ dùng `Timer`, một tác vụ bị treo có thể chưa tạo ra mẫu thời lượng hoàn tất nào. `LongTaskTimer` cho biết tác vụ vẫn hoạt động bao lâu và hiện có bao nhiêu tác vụ đang chạy. Khi cần cả hai góc nhìn, hãy ghi nhận đồng thời bằng hai meter.

## 1. Hai câu hỏi khác nhau

`Timer` thường được dùng để trả lời:

- Một thao tác đã hoàn tất mất bao lâu?
- Có bao nhiêu lần thực thi đã kết thúc?
- Phân phối thời lượng hoàn tất ra sao, chẳng hạn p95 hoặc p99?

`LongTaskTimer` thường được dùng để trả lời:

- Hiện có bao nhiêu tác vụ đang chạy?
- Tổng thời gian đã trôi qua của các tác vụ đang chạy là bao nhiêu?
- Tác vụ đang chạy lâu nhất đã kéo dài bao lâu?

| Khía cạnh | `Timer` | `LongTaskTimer` |
| --- | --- | --- |
| Bắt đầu đo | Khi gọi `record(...)` hoặc `Timer.Sample.start` | Khi gọi `LongTaskTimer.start()` |
| Khi nào có số liệu | Khi lần thực thi kết thúc và được ghi nhận | Trong suốt thời gian tác vụ đang chạy |
| Số lần thực thi | Có `count` của các lần đã ghi nhận | Có `activeTasks` của các lần hiện còn chạy |
| Thời lượng | Tổng và phân phối thời lượng đã hoàn tất | Thời lượng đang trôi qua của các tác vụ còn hoạt động |
| Percentile/histogram hoàn tất | Có thể cấu hình tùy registry | Không phải mục tiêu của meter này |
| Khi tác vụ dừng | Ghi nhận mẫu hoàn tất | Loại tác vụ đó khỏi tập đang hoạt động |

Hai meter bổ sung cho nhau. `Timer` mô tả lịch sử hoàn tất; `LongTaskTimer` mô tả trạng thái hiện tại của công việc.

## 2. Vì sao Timer chưa đủ cho tác vụ dài

Với một thao tác đồng bộ thông thường, `Timer.record(...)` chỉ ghi nhận thời lượng sau khi hàm trả về hoặc ném exception:

```java
Timer reportTimer = registry.timer("reports.generate.duration");

reportTimer.record(() -> reportService.generate(reportId));
```

Giả sử `reportService.generate(...)` chạy trong 15 phút. Trong khoảng thời gian đó, timer chưa có mẫu hoàn tất cho lần thực thi đang diễn ra. Nếu tác vụ bị kẹt ở phút thứ 12 và không bao giờ kết thúc, dashboard chỉ dựa vào thời lượng hoàn tất có thể không cho thấy tác vụ đó đang bị treo.

Đây không phải lỗi của `Timer`: nó đo thời lượng hoàn tất theo đúng mục đích. Để theo dõi tiến trình đang chạy, cần một meter có thể xuất số liệu trước khi công việc kết thúc. Đó là vai trò của `LongTaskTimer`.

## 3. LongTaskTimer ghi nhận trạng thái đang hoạt động

Có thể tạo `LongTaskTimer` bằng builder và đăng ký vào `MeterRegistry`:

```java
LongTaskTimer reportTaskTimer = LongTaskTimer.builder("reports.generate.active")
    .description("Currently active report generation tasks")
    .register(registry);
```

Mỗi lần bắt đầu một tác vụ, gọi `start()` để lấy một `LongTaskTimer.Sample`:

```java
LongTaskTimer.Sample sample = reportTaskTimer.start();
try {
    reportService.generate(reportId);
} finally {
    sample.stop();
}
```

Từ lúc `start()` được gọi đến lúc `stop()` được gọi, sample được tính là một tác vụ đang hoạt động. Trong thời gian đó, registry có thể đọc các phép đo như:

```java
import java.util.concurrent.TimeUnit;

long activeCount = reportTaskTimer.activeTasks();
double activeDurationSeconds = reportTaskTimer.duration(TimeUnit.SECONDS);
double longestActiveSeconds = reportTaskTimer.max(TimeUnit.SECONDS);
```

- `activeTasks()` cho biết số sample chưa được dừng.
- `duration(unit)` cho biết tổng thời lượng đã trôi qua của các sample đang hoạt động.
- `max(unit)` cho biết thời lượng lớn nhất trong các sample đang hoạt động.

Các giá trị này chỉ mô tả tác vụ còn chạy tại thời điểm đọc. Khi một sample được dừng, tác vụ đó không còn đóng góp vào số lượng và thời lượng active. Nếu không còn tác vụ nào hoạt động, các giá trị thời lượng active trở về trạng thái không có công việc; cách biểu diễn cụ thể phụ thuộc registry.

## 4. Luôn dừng sample trong finally

Một sample của `LongTaskTimer` phải được dừng khi công việc kết thúc, bất kể kết thúc bình thường hay bằng exception. Nếu bỏ quên `stop()`, meter tiếp tục xem tác vụ là đang chạy và số liệu active sẽ tăng sai.

```java
LongTaskTimer.Sample sample = reportTaskTimer.start();
try {
    return reportService.generate(reportId);
} finally {
    sample.stop();
}
```

`finally` được thực thi cả khi `return` hoặc exception đi ra khỏi khối `try`. Đặt `sample.stop()` ở đây giúp bảo đảm vòng đời đo kết thúc cùng vòng đời thực thi mà sample đại diện.

Nếu tác vụ được chia thành nhiều giai đoạn, hãy xác định rõ ranh giới nào được xem là toàn bộ tác vụ. Ví dụ, nếu thời gian tạo báo cáo bao gồm truy vấn dữ liệu, render file và ghi file, hãy bắt đầu sample trước giai đoạn đầu tiên và dừng sau giai đoạn cuối cùng. Không dừng sample ngay sau khi tạo job nếu phần xử lý thực tế còn chạy trong worker nền.

## 5. Ghi đồng thời LongTaskTimer và Timer

Khi cần biết cả tình trạng đang chạy và phân phối thời lượng hoàn tất, hãy đăng ký hai meter riêng. `LongTaskTimer` theo dõi sample active; `Timer` ghi nhận một mẫu khi sample hoàn tất.

Trong ví dụ, `Timer.Sample` phải được tạo từ cùng `MeterRegistry` đã dùng để đăng ký `completedReports`. Bean dưới đây giữ registry trong field và minh họa đầy đủ cách đo cả hai góc nhìn:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class ReportMetrics {
    private final MeterRegistry registry;
    private final LongTaskTimer activeReports;
    private final Timer completedReports;
    private final ReportService reportService;

    public ReportMetrics(MeterRegistry registry, ReportService reportService) {
        this.registry = registry;
        this.reportService = reportService;
        this.activeReports = LongTaskTimer.builder("reports.generate.active")
            .description("Currently active report generation tasks")
            .register(registry);
        this.completedReports = Timer.builder("reports.generate.duration")
            .description("Duration of completed report generation tasks")
            .publishPercentileHistogram()
            .register(registry);
    }

    public byte[] recordGeneration(String reportId) {
        LongTaskTimer.Sample activeSample = activeReports.start();
        Timer.Sample completedSample = Timer.start(registry);
        try {
            byte[] result = reportService.generate(reportId);
            completedSample.stop(completedReports);
            return result;
        } catch (RuntimeException | Error exception) {
            completedSample.stop(completedReports);
            throw exception;
        } finally {
            activeSample.stop();
        }
    }
}
```

Ở đây:

1. `activeSample` bắt đầu đo tác vụ đang chạy.
2. `completedSample` bắt đầu đo thời lượng cho timer hoàn tất.
3. Khi service trả về hoặc ném exception, timer ghi nhận thời lượng đã hoàn tất.
4. `finally` dừng sample của `LongTaskTimer`, loại tác vụ khỏi nhóm đang hoạt động.

Nếu cần phân biệt thành công và thất bại, hãy tạo hai timer có cùng tên nhưng tag `result` khác nhau rồi gọi `completedSample.stop(successTimer)` hoặc `completedSample.stop(failureTimer)` ở nhánh tương ứng. Không thêm ID của từng báo cáo vào tag; ID nên nằm trong log hoặc trace.

## 6. Ví dụ cho tác vụ chạy nền bất đồng bộ

Với tác vụ chạy nền, method gửi job vào executor có thể kết thúc rất nhanh trong khi công việc thật vẫn tiếp tục. Nếu dừng `LongTaskTimer.Sample` ngay khi submit hoàn tất, meter chỉ đo thời gian submit, không đo thời gian xử lý job.

Hãy bắt đầu và dừng sample ở nơi thực thi công việc:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ReportWorker {
    private final LongTaskTimer activeReports;
    private final ReportService reportService;

    public ReportWorker(MeterRegistry registry, ReportService reportService) {
        this.activeReports = LongTaskTimer.builder("reports.worker.active")
            .description("Report jobs currently processed by workers")
            .register(registry);
        this.reportService = reportService;
    }

    public void process(String reportId) {
        LongTaskTimer.Sample sample = activeReports.start();
        try {
            reportService.generate(reportId);
        } finally {
            sample.stop();
        }
    }
}
```

Executor có thể gọi `process(reportId)` trên worker thread. Sample sống trong toàn bộ thời gian `generate` thực sự chạy và được dừng khi worker hoàn tất hoặc thất bại. Nếu tác vụ được chia qua nhiều callback hoặc nhiều thread, hãy truyền rõ đối tượng quản lý vòng đời sample và bảo đảm chỉ dừng nó một lần khi công việc thực sự kết thúc.

## 7. Diễn giải số liệu khi có nhiều tác vụ đồng thời

Giả sử có ba tác vụ đang chạy:

- Tác vụ A đã chạy 10 giây.
- Tác vụ B đã chạy 6 giây.
- Tác vụ C đã chạy 2 giây.

Tại thời điểm scrape, `activeTasks()` là 3, tổng `duration(...)` xấp xỉ 18 giây và `max(...)` xấp xỉ 10 giây. Sau khi tác vụ A kết thúc, số tác vụ active còn 2; tổng thời lượng active còn xấp xỉ 8 giây và thời lượng active lớn nhất còn xấp xỉ 6 giây.

Điều này không có nghĩa hệ thống chỉ mất 8 giây để xử lý B và C. Đó là tổng thời gian đã trôi qua của những tác vụ hiện còn chạy tại thời điểm quan sát. Khi tác vụ kết thúc, nó rời khỏi phép đo active.

Vì vậy, không dùng `LongTaskTimer.duration(...)` như tổng thời gian lịch sử đã tiêu tốn cho mọi job. Nếu cần lịch sử thời lượng, hãy dùng `Timer`. Không dùng `activeTasks()` như tổng số job đã nhận; đó là số job đang hoạt động ngay lúc đọc.

## 8. Xuất metrics và quan sát trong hệ giám sát

Registry/exporter quyết định cách trình bày `LongTaskTimer`. Với backend hỗ trợ, các phép đo thường phản ánh số tác vụ active, tổng thời lượng active và thời lượng active lớn nhất. Tên metric, đơn vị và cách đặt hậu tố phụ thuộc registry, vì vậy hãy kiểm tra endpoint export thực tế thay vì giả định tên giống nhau giữa mọi backend.

Với Spring Boot Actuator, có thể kiểm tra meter trong ứng dụng qua endpoint metrics nếu endpoint được expose:

```text
/actuator/metrics/reports.generate.active
```

Endpoint này giúp kiểm tra meter đã đăng ký và các phép đo do registry cung cấp. Endpoint Prometheus hoặc endpoint của backend tương ứng cho biết cách meter được xuất ra ngoài. Khi thiết lập dashboard, hãy quan sát ít nhất:

- Số tác vụ đang hoạt động.
- Thời lượng của tác vụ active lâu nhất.
- Tổng thời lượng active, đặc biệt khi có nhiều tác vụ chạy song song.
- Thời lượng hoàn tất p95/p99 từ `Timer` tương ứng.
- Tỷ lệ lỗi hoặc số lần hoàn tất nếu ứng dụng có instrumentation bổ sung.

Nếu active task count liên tục tăng và không giảm, có thể worker đang bị nghẽn, sample không được dừng hoặc tác vụ bị treo. Nếu max active duration vượt ngưỡng vận hành, hãy kiểm tra log/trace để tìm tác vụ cụ thể; không đưa ID của tác vụ vào metric tag để truy vết.

## 9. Kiểm thử LongTaskTimer

`SimpleMeterRegistry` có thể dùng để kiểm tra số sample đang hoạt động và hành vi sau khi dừng. Test nên giữ sample trong phạm vi kiểm soát và xác minh số tác vụ active giảm về 0 sau `stop()`:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LongTaskTimerTest {
    @Test
    void tracksTaskWhileItIsRunning() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LongTaskTimer timer = LongTaskTimer.builder("reports.active")
            .register(registry);

        LongTaskTimer.Sample sample = timer.start();

        assertEquals(1, timer.activeTasks());
        assertEquals(1, registry.get("reports.active").longTaskTimer().activeTasks());

        sample.stop();

        assertEquals(0, timer.activeTasks());
    }
}
```

Để kiểm thử tích hợp, có thể khởi động ứng dụng, bắt đầu một tác vụ có thời gian chờ điều khiển được, đọc endpoint metrics khi tác vụ còn chạy, sau đó kết thúc tác vụ và đọc lại. Bài test cần kiểm tra cả trạng thái trước và sau khi kết thúc để phát hiện trường hợp sample bị bỏ quên.

Không nên dùng `Thread.sleep()` dài và thời gian cố định nếu có thể đồng bộ bằng latch hoặc cơ chế báo hiệu trong test. Mục tiêu là tạo một khoảng mà tác vụ chắc chắn còn active để đọc meter.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Active task count tăng nhưng không giảm | Không gọi `sample.stop()`, nhánh exception bỏ qua cleanup hoặc sample không gắn với toàn bộ vòng đời công việc |
| LongTaskTimer chỉ đo thời gian submit job | Sample được dừng khi submit kết thúc thay vì khi worker hoàn tất |
| Timer không hiển thị tác vụ đang bị treo | Timer chỉ ghi mẫu sau khi thao tác hoàn tất; cần thêm LongTaskTimer |
| LongTaskTimer không có lịch sử p95 | Meter mô tả trạng thái active, không phải phân phối thời lượng đã hoàn tất; dùng Timer song song |
| Tổng active duration giảm khi một job kết thúc | Đúng với semantics: job đã rời khỏi tập đang hoạt động |
| Active count bằng 0 dù job vẫn chạy | Sample được dừng quá sớm hoặc ranh giới đo không bao trùm worker thực tế |
| Dashboard không thấy meter | Registry không hỗ trợ xuất loại meter đó, endpoint chưa expose hoặc meter đăng ký vào registry khác |

Khi điều tra, hãy xác định vị trí gọi `start()` và `stop()`, kiểm tra mọi đường kết thúc gồm return, exception, cancel và timeout, rồi so sánh với ranh giới thực thi của worker. Nếu cần biết một tác vụ cụ thể đang mắc ở bước nào, hãy kết hợp trace và log có task ID.

## 11. Nguyên tắc áp dụng

Dùng `LongTaskTimer` khi cần quan sát tác vụ còn đang chạy, đặc biệt với công việc kéo dài hoặc có nguy cơ bị treo. Dùng `Timer` để ghi nhận thời lượng của các lần đã hoàn tất và phân tích histogram/percentile. Hai meter có thể cùng đo một thao tác nhưng phải có tên riêng và ý nghĩa rõ ràng.

Đăng ký meter một lần trong bean quản lý instrumentation, bắt đầu sample tại ranh giới thực thi thật và dừng sample trong `finally` khi tác vụ kết thúc. Với job bất đồng bộ, sample phải theo vòng đời của worker chứ không phải thời gian gửi job. Khi dashboard cho thấy active task kéo dài bất thường, dùng log và tracing để xác định công việc cụ thể; metrics cung cấp tín hiệu tổng hợp về tình trạng đang chạy.
