# Số tác vụ đang chạy, tổng thời gian và thời gian lớn nhất của tác vụ hiện hành

Một `Timer` thông thường ghi nhận thời lượng sau khi một lần thực thi kết thúc. Trong khi một tác vụ vẫn đang chạy, dashboard có thể chưa thấy lần đo đó. Với các tác vụ kéo dài như đồng bộ dữ liệu, tạo báo cáo, xử lý batch hoặc gọi dịch vụ bên ngoài, người vận hành thường cần biết ngay có bao nhiêu tác vụ đang hoạt động và chúng đã chạy bao lâu.

Micrometer `LongTaskTimer` phục vụ câu hỏi này. Mỗi lần gọi `start()` tạo một mẫu đại diện cho một tác vụ đang chạy. Trong khi mẫu còn hoạt động, meter cung cấp số tác vụ đang chạy, tổng thời gian đã trôi qua của tất cả tác vụ đang chạy và thời gian lớn nhất trong số chúng. Khi gọi `stop()` trên mẫu, tác vụ đó không còn được tính vào các thống kê đang hoạt động.

## LongTaskTimer khác Timer như thế nào?

Hai meter đo thời gian nhưng trả lời các câu hỏi khác nhau:

| Đặc điểm | `Timer` | `LongTaskTimer` |
|---|---|---|
| Khi bắt đầu đo | Khi gọi `record(...)` hoặc `Timer.start(registry)` | Khi gọi `LongTaskTimer.start()` |
| Khi có số đo | Sau khi lần thực thi kết thúc | Ngay khi mẫu đang hoạt động, có thể đọc khi tác vụ chưa xong |
| `count` | Tổng số lần đã ghi nhận hoàn tất | Số tác vụ hiện đang chạy (`activeTasks`) |
| Thời lượng | Thống kê thời lượng của các lần đã hoàn tất | Tổng thời gian đã trôi qua của các tác vụ hiện đang chạy |
| Giá trị lớn nhất | Tùy cấu hình, có thể phản ánh cực đại của các lần đã ghi nhận | Thời lượng lớn nhất trong các tác vụ đang chạy tại thời điểm đọc |
| Sau khi tác vụ kết thúc | Observation vẫn được giữ trong thống kê tích lũy | Mẫu được loại khỏi thống kê đang hoạt động |

`LongTaskTimer` không phải counter tổng số job đã bắt đầu, cũng không phải lịch sử tổng thời gian của tất cả job từng chạy. Khi một tác vụ kết thúc, số tác vụ đang chạy và tổng thời gian hoạt động sẽ giảm tương ứng. Giá trị `max` cũng có thể giảm khi tác vụ đang chạy lâu nhất kết thúc và tác vụ còn lại ngắn hơn.

Nếu cần cả thời gian đang chạy lẫn phân phối thời lượng của các lần hoàn tất, có thể dùng `LongTaskTimer` và `Timer` song song cho cùng một thao tác. LongTaskTimer giúp quan sát tình trạng hiện tại; Timer lưu thống kê sau khi thao tác kết thúc.

## Đăng ký LongTaskTimer

Có thể đăng ký meter bằng builder và gắn các tag có tập giá trị hữu hạn:

```java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;

public class ReportMetrics {
    private final LongTaskTimer reportTimer;

    public ReportMetrics(MeterRegistry registry) {
        this.reportTimer = LongTaskTimer.builder("reports.generation")
                .description("Thời gian các tác vụ tạo báo cáo đang chạy")
                .tag("report_type", "monthly")
                .register(registry);
    }

    public long activeReports() {
        return reportTimer.activeTasks();
    }

    public double activeDurationSeconds() {
        return reportTimer.duration(TimeUnit.SECONDS);
    }

    public double longestActiveSeconds() {
        return reportTimer.max(TimeUnit.SECONDS);
    }
}
```

`activeTasks()` trả về số mẫu chưa dừng. `duration(unit)` trả về tổng thời gian đã trôi qua của tất cả mẫu đang hoạt động, đổi sang đơn vị được yêu cầu. `max(unit)` trả về thời lượng lớn nhất trong các mẫu hiện đang hoạt động. Khi không có tác vụ nào chạy, các giá trị thời lượng đang hoạt động bằng không.

Tag `report_type` trong ví dụ có một giá trị cố định. Trong ứng dụng thực tế có thể dùng các nhóm như `daily`, `monthly` hoặc `adhoc`, nhưng không đưa `reportId`, tên khách hàng hay tên file riêng lẻ vào tag. Mỗi tổ hợp tag tạo một meter riêng và có thể làm cardinality tăng nhanh.

## Bắt đầu và kết thúc một tác vụ

`LongTaskTimer.start()` trả về `LongTaskTimer.Sample`. Giữ sample trong phạm vi một lần thực thi và gọi `stop()` khi công việc kết thúc:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final LongTaskTimer reportTimer;
    private final ReportGenerator generator;

    public ReportService(MeterRegistry registry, ReportGenerator generator) {
        this.reportTimer = LongTaskTimer.builder("reports.generation")
                .tag("report_type", "monthly")
                .register(registry);
        this.generator = generator;
    }

    public Report generate(ReportRequest request) {
        LongTaskTimer.Sample sample = reportTimer.start();
        try {
            return generator.generate(request);
        } finally {
            sample.stop();
        }
    }
}
```

Đoạn mã trên đăng ký meter một lần trong constructor và tái sử dụng cho các lần tạo báo cáo. `finally` bảo đảm sample được dừng cả khi generator trả về bình thường lẫn khi ném exception. Nếu quên gọi `stop()`, tác vụ tiếp tục được tính là đang chạy và thời lượng của nó tiếp tục tăng dù công việc thực tế đã kết thúc.

Trong ứng dụng Spring Boot, cách đơn giản là inject `MeterRegistry` vào service và đăng ký meter một lần trong constructor hoặc bean cấu hình. Không tạo một LongTaskTimer mới cho mỗi lần gọi nghiệp vụ; hãy tái sử dụng cùng meter theo tên và tag ổn định.

Ví dụ đầy đủ hơn, kết hợp LongTaskTimer để theo dõi tác vụ hiện hành và Timer để ghi nhận thời lượng sau khi hoàn tất:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    private final MeterRegistry registry;
    private final LongTaskTimer activeExports;
    private final Timer completedExports;
    private final ExportWorker worker;

    public ExportService(MeterRegistry registry, ExportWorker worker) {
        this.registry = registry;
        this.worker = worker;
        this.activeExports = LongTaskTimer.builder("exports.active")
                .tag("format", "csv")
                .register(registry);
        this.completedExports = Timer.builder("exports.duration")
                .tag("format", "csv")
                .register(registry);
    }

    public ExportFile export(ExportRequest request) {
        LongTaskTimer.Sample active = activeExports.start();
        Timer.Sample completed = Timer.start(registry);
        try {
            return worker.export(request);
        } finally {
            active.stop();
            completed.stop(completedExports);
        }
    }
}
```

Trong ví dụ kết hợp này, cần khai báo và lưu `MeterRegistry registry` như một field trong constructor để `Timer.start(registry)` sử dụng được. Khi export đang chạy, `exports.active` phản ánh số tác vụ và thời gian đang hoạt động. Khi export kết thúc, mẫu LongTaskTimer được dừng còn Timer ghi nhận một observation hoàn tất, kể cả khi worker ném exception. Hai meter có thể dùng cùng tag vì chúng phục vụ hai góc nhìn khác nhau.

## Diễn giải ba số đo của tác vụ hiện hành

Giả sử tại thời điểm scrape có ba tác vụ đang chạy:

| Tác vụ | Thời gian đã chạy |
|---|---:|
| A | 12 giây |
| B | 7 giây |
| C | 4 giây |

Các giá trị LongTaskTimer tương ứng là:

\[
activeTasks = 3
\]

\[
duration = 12 + 7 + 4 = 23\text{ giây}
\]

\[
max = 12\text{ giây}
\]

`activeTasks` giúp phát hiện công việc đang bị dồn hoặc không giảm về mức bình thường. `duration` là tổng thời gian đang tích lũy của tất cả tác vụ còn chạy; khi có nhiều tác vụ song song, nó có thể tăng nhanh hơn thời gian thực của đồng hồ. `max` cho biết tác vụ hiện hành chạy lâu nhất đã kéo dài bao lâu.

Các giá trị này thay đổi theo thời gian và có thể giảm khi tác vụ hoàn tất. Chúng không phải counter đơn điệu. Đừng áp dụng cách diễn giải `rate()` của counter cho các giá trị active duration này.

## Dùng LongTaskTimer với tác vụ bất đồng bộ

Với công việc chạy trên executor, hãy bắt đầu sample bên trong phần thân tác vụ nếu muốn đo thời gian xử lý thực tế, loại trừ thời gian chờ hàng đợi:

```java
CompletableFuture<Report> future = CompletableFuture.supplyAsync(() -> {
    LongTaskTimer.Sample active = reportTimer.start();
    try {
        return generator.generate(request);
    } finally {
        active.stop();
    }
}, executor);
```

Sample bắt đầu khi worker thực sự chạy lambda và dừng khi `generator.generate(...)` kết thúc. Nếu muốn theo dõi cả thời gian tác vụ nằm chờ trong executor, hãy tạo sample trước khi submit và dừng khi future hoàn tất. Khi đó số đo biểu diễn thời gian từ lúc gửi tác vụ đến lúc hoàn tất, bao gồm queue wait.

Với API trả về future từ một client bên ngoài, sample phải sống đến callback hoàn tất:

```java
LongTaskTimer.Sample active = remoteCallTimer.start();
try {
    return client.callAsync(request)
            .whenComplete((response, error) -> active.stop());
} catch (RuntimeException exception) {
    active.stop();
    throw exception;
}
```

`whenComplete(...)` chạy khi future hoàn tất bình thường, hoàn tất lỗi hoặc bị hủy, vì vậy sample được dừng khi vòng đời bất đồng bộ kết thúc. Khối `catch` xử lý trường hợp phương thức `callAsync(...)` ném exception đồng bộ trước khi trả về future. Nếu callback có nhiều nhánh hoàn tất hoặc có cơ chế hủy riêng, cần bảo đảm sample chỉ được dừng một lần.

Chọn điểm bắt đầu theo câu hỏi vận hành. Bắt đầu trước khi submit để đo tuổi của toàn bộ công việc trong hệ thống; bắt đầu trong worker để đo thời gian xử lý thực tế. Có thể tạo thêm một Timer riêng cho queue wait nếu cần tách hai giai đoạn.

## Quan sát qua endpoint và backend

Khi dùng Spring Boot Actuator, inject registry do Spring Boot cấu hình và expose endpoint metrics theo chính sách của ứng dụng. Endpoint `/actuator/metrics` có thể hiển thị các measurement của meter nếu registry hỗ trợ chúng. Tên measurement và cách biểu diễn LongTaskTimer phụ thuộc registry.

Với backend scrape như Prometheus, LongTaskTimer được xuất thành các số đo phản ánh tác vụ đang hoạt động. Tên metric cụ thể và hậu tố có thể khác theo phiên bản registry; hãy kiểm tra endpoint exposition của ứng dụng trước khi viết truy vấn. Không giả định mọi backend đều dùng cùng tên metric hoặc cùng cấu trúc.

LongTaskTimer đặc biệt hữu ích với scrape-based monitoring vì backend có thể đọc số tác vụ đang chạy trước khi chúng hoàn tất. Tuy nhiên, một tác vụ bắt đầu và kết thúc giữa hai lần scrape có thể không xuất hiện trong mẫu active nào. Nếu cần thống kê mọi lần thực thi, kể cả tác vụ ngắn, hãy ghi thêm `Timer`.

## Kiểm thử vòng đời sample

`SimpleMeterRegistry` cho phép kiểm tra số tác vụ đang hoạt động mà không cần backend:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class LongTaskTimerTest {
    @Test
    void tracksOnlyTasksThatHaveNotStopped() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LongTaskTimer timer = LongTaskTimer.builder("test.jobs.active")
                .register(registry);

        LongTaskTimer.Sample first = timer.start();
        LongTaskTimer.Sample second = timer.start();

        assertThat(timer.activeTasks()).isEqualTo(2);
        assertThat(timer.duration(TimeUnit.MILLISECONDS)).isGreaterThanOrEqualTo(0);
        assertThat(timer.max(TimeUnit.MILLISECONDS)).isGreaterThanOrEqualTo(0);

        first.stop();
        assertThat(timer.activeTasks()).isEqualTo(1);

        second.stop();
        assertThat(timer.activeTasks()).isZero();
        assertThat(timer.duration(TimeUnit.MILLISECONDS)).isZero();

        registry.close();
    }
}
```

Test xác nhận hai sample đang chạy được đếm là hai; sau khi dừng một sample, số tác vụ hoạt động giảm còn một; sau khi dừng sample còn lại, số tác vụ và tổng thời gian hoạt động trở về không. Không nên assert thời lượng bằng một số cố định vì kết quả phụ thuộc tốc độ máy và lịch thực thi của test.

Với tác vụ bất đồng bộ, cần kiểm tra sample vẫn hoạt động khi future chưa hoàn tất và được dừng sau callback hoàn tất. Cũng nên kiểm tra nhánh exception và cancellation để tránh sample bị bỏ quên.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `activeTasks()` tăng nhưng không giảm | Một số nhánh kết thúc không gọi `sample.stop()` | Dùng `finally` hoặc callback hoàn tất bao phủ cả success, failure và cancellation |
| Không thấy tác vụ ngắn trên dashboard | Tác vụ hoàn tất giữa hai lần scrape | Dùng thêm `Timer` để ghi nhận mọi lần hoàn tất |
| Tổng `duration` lớn hơn thời gian đồng hồ | Có nhiều tác vụ chạy song song và thời lượng được cộng lại | Diễn giải đây là tổng active duration, không phải wall-clock duration |
| `max()` giảm sau khi một tác vụ kết thúc | Tác vụ đang chạy lâu nhất đã bị loại khỏi tập active | Đây là hành vi đúng; `max` không phải cực đại lịch sử |
| Đo thời gian dài hơn phần xử lý | Sample bắt đầu trước khi submit và bao gồm queue wait | Bắt đầu sample trong worker nếu chỉ muốn đo execution duration |
| Số tác vụ active không khớp | Sample bị dừng sớm, dừng lặp hoặc không dừng khi hủy | Rà soát vòng đời mỗi sample và các nhánh kết thúc |

## Checklist triển khai

- [ ] LongTaskTimer được đăng ký một lần với tên và tag ổn định.
- [ ] Mỗi lần thực thi tạo một sample riêng bằng `start()`.
- [ ] Mọi đường kết thúc đều dừng sample, kể cả exception và cancellation.
- [ ] `activeTasks()` được hiểu là số tác vụ đang chạy, không phải tổng số đã hoàn tất.
- [ ] `duration()` được hiểu là tổng thời gian đã trôi qua của các tác vụ hiện hành.
- [ ] `max()` được hiểu là thời gian lớn nhất trong nhóm tác vụ hiện hành, không phải cực đại lịch sử.
- [ ] Điểm bắt đầu sample được chọn rõ để bao gồm hoặc loại trừ queue wait.
- [ ] Dùng thêm `Timer` nếu cần thống kê thời lượng của tất cả lần hoàn tất.
- [ ] Đã kiểm thử sample khi chạy, hoàn tất, lỗi và hủy.
- [ ] Tag chỉ chứa nhóm giá trị hữu hạn, không chứa ID của từng tác vụ.

`LongTaskTimer` cho biết trạng thái của các tác vụ còn đang chạy: số lượng, tổng tuổi của chúng và tác vụ hiện hành lâu nhất. Mỗi sample phải được dừng đúng lúc để số liệu phản ánh đúng vòng đời công việc. Khi cần lịch sử thời lượng sau hoàn tất, kết hợp thêm `Timer` để có cả góc nhìn hiện tại và thống kê tích lũy.
