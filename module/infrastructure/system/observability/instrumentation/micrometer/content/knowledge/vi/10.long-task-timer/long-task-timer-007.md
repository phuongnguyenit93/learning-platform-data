# Phát hiện vượt ngưỡng trong khi tác vụ vẫn chưa kết thúc

Một số thao tác trong ứng dụng Java có thể kéo dài nhiều giây hoặc nhiều phút: tạo báo cáo lớn, nhập dữ liệu, đồng bộ kho, xử lý batch, chạy migration hoặc thực hiện một workflow nền. Nếu chỉ dùng `Timer`, thời lượng của thao tác thường được ghi nhận khi thao tác kết thúc. Trong lúc công việc vẫn đang chạy, metrics của Timer chưa cho biết lần thực thi hiện tại đã kéo dài bao lâu.

Micrometer cung cấp **LongTaskTimer** để quan sát các tác vụ đang hoạt động. Khi một tác vụ bắt đầu, ứng dụng tạo một sample; trong suốt thời gian sample còn mở, registry có thể xuất số tác vụ đang chạy, tổng thời lượng của các tác vụ đang chạy và thời lượng lớn nhất trong số đó. Nhờ vậy, hệ thống giám sát có thể phát hiện một tác vụ đang chạy vượt ngưỡng mà không cần chờ nó hoàn tất.

LongTaskTimer phù hợp để giám sát trạng thái của công việc dài hạn. Nếu cần thống kê thời lượng của cả những lần đã hoàn tất, nên kết hợp thêm Timer với một tên metric riêng.

## 1. Vì sao Timer thông thường chưa đủ?

Timer đo số lần thực hiện và thời lượng của các thao tác đã được ghi nhận. Với cách dùng `timer.record(...)`, thời lượng được cập nhật sau khi khối mã kết thúc.

Ví dụ, một tác vụ tạo báo cáo bắt đầu lúc 10:00 và kết thúc lúc 10:08. Trong phần lớn thời gian đó, Timer chưa có mẫu hoàn chỉnh của lần chạy hiện tại. Nếu mục tiêu là phát hiện ngay khi tác vụ đã chạy quá 5 phút, chỉ nhìn vào Timer thông thường sẽ không đủ thông tin tại thời điểm phút thứ 5.

LongTaskTimer theo dõi thời gian của từng sample đang mở. Khi tác vụ vẫn chạy, giá trị thời lượng đang hoạt động đã có thể được đọc và xuất ra backend.

| Nhu cầu giám sát | Timer | LongTaskTimer |
|---|---|---|
| Đếm số lần hoàn tất | Có | Không phải mục tiêu chính |
| Phân bố thời lượng của các lần hoàn tất | Có, khi cấu hình phù hợp | Không lưu lịch sử các lần đã dừng |
| Số tác vụ hiện đang chạy | Không trực tiếp | Có |
| Tổng thời lượng của các tác vụ đang chạy | Không trực tiếp | Có |
| Thời lượng lớn nhất trong các tác vụ đang chạy | Không trực tiếp | Có |
| Phát hiện tác vụ đang chạy lâu trước khi hoàn tất | Không phù hợp | Phù hợp |

Một ứng dụng có thể dùng cả hai loại meter để trả lời hai câu hỏi khác nhau: LongTaskTimer cho biết công việc đang diễn ra thế nào; Timer cho biết các lần thực hiện đã hoàn tất có thời lượng ra sao.

## 2. Ba số đo chính của LongTaskTimer

LongTaskTimer cung cấp ba thông tin quan trọng:

- `activeTasks()`: số sample đang hoạt động, tức số tác vụ đã bắt đầu nhưng chưa gọi `stop()`.
- `duration(TimeUnit)`: tổng thời lượng đang tích lũy của tất cả sample còn hoạt động, được đổi sang đơn vị yêu cầu.
- `max(TimeUnit)`: thời lượng lớn nhất trong các sample còn hoạt động.

Ví dụ, tại một thời điểm có ba tác vụ đang chạy:

| Tác vụ | Thời gian đã chạy |
|---|---:|
| Import khách hàng | 40 giây |
| Tạo báo cáo | 320 giây |
| Đồng bộ kho | 90 giây |

Các giá trị quan sát tương ứng:

- `activeTasks()` = 3
- `duration(SECONDS)` = 450 giây
- `max(SECONDS)` = 320 giây

Nếu ngưỡng cảnh báo là 300 giây, giá trị `max` cho biết ít nhất một tác vụ đang hoạt động đã vượt ngưỡng. LongTaskTimer không nhất thiết cho biết tác vụ nào trong số ba tác vụ đó đã chạy lâu nhất; nếu cần xác định một lần chạy cụ thể, hãy dùng log hoặc trace có correlation ID.

Khi một sample được dừng, nó không còn nằm trong các số đo active. Vì vậy, `activeTasks()`, `duration(...)` và `max(...)` có thể giảm khi tác vụ kết thúc. Chúng mô tả trạng thái hiện tại của các sample đang mở, không phải lịch sử tích lũy của mọi lần chạy.

## 3. Đăng ký LongTaskTimer trong Spring Boot

Có thể đăng ký LongTaskTimer qua `MeterRegistry` giống các meter khác:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class ReportTaskMetrics {

    private final LongTaskTimer reportGeneration;

    public ReportTaskMetrics(MeterRegistry registry) {
        this.reportGeneration = LongTaskTimer.builder(
                "report.generation.active"
            )
            .description("Currently active report generation tasks")
            .register(registry);
    }

    public LongTaskTimer.Sample start() {
        return reportGeneration.start();
    }

    public long activeTasks() {
        return reportGeneration.activeTasks();
    }

    public double longestActiveTaskSeconds() {
        return reportGeneration.max(TimeUnit.SECONDS);
    }
}
```

Tên metric `report.generation.active` mô tả trạng thái công việc đang chạy. Các tag chung như `service`, `environment` hoặc `region` có thể được cấu hình ở cấp registry để phân biệt môi trường và dịch vụ.

Không nên đưa ID của từng báo cáo, tên file hoặc user ID vào tag của LongTaskTimer. Những giá trị đó có thể thay đổi theo mỗi lần chạy và tạo cardinality rất cao. LongTaskTimer tổng hợp các sample đang hoạt động trong cùng meter; dùng log hoặc trace để liên kết với một tác vụ cụ thể.

## 4. Bắt đầu và kết thúc sample đúng vòng đời

Mỗi lần tác vụ bắt đầu, gọi `start()` để tạo một `LongTaskTimer.Sample`. Khi công việc kết thúc, gọi `stop()`. Phải bảo đảm sample được dừng kể cả khi tác vụ ném exception hoặc bị hủy.

Ví dụ với một service tạo báo cáo:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportTaskMetrics metrics;
    private final ReportGenerator generator;

    public ReportService(
            ReportTaskMetrics metrics,
            ReportGenerator generator
    ) {
        this.metrics = metrics;
        this.generator = generator;
    }

    public Report generate(ReportRequest request) {
        LongTaskTimer.Sample sample = metrics.start();

        try {
            return generator.generate(request);
        } finally {
            sample.stop();
        }
    }
}
```

Sample tồn tại trong toàn bộ thời gian `generator.generate(...)` chạy. Trong khoảng này, backend có thể quan sát thời lượng đang hoạt động. Khối `finally` bảo đảm sample được đóng khi thao tác trả về bình thường hoặc kết thúc bằng exception.

Nếu quên gọi `stop()`, sample có thể tiếp tục được tính là đang hoạt động sau khi logic nghiệp vụ đã kết thúc. Khi đó, số tác vụ đang chạy và thời lượng lớn nhất sẽ bị sai. Hãy gắn vòng đời sample với vòng đời thực tế của công việc.

## 5. Phát hiện vượt ngưỡng khi tác vụ vẫn đang chạy

Giả sử quy định một lần tạo báo cáo không nên chạy quá 5 phút. Đặt ngưỡng:

[
T = 300 	ext{ giây}
]

Khi tác vụ còn hoạt động, LongTaskTimer liên tục cung cấp thời lượng đang chạy cho lần scrape hoặc publish tiếp theo. Nếu giá trị `max(TimeUnit.SECONDS)` lớn hơn 300, ít nhất một tác vụ đang chạy đã vượt ngưỡng.

Có thể đọc trực tiếp giá trị trong code để phục vụ kiểm tra hoặc logic giám sát nội bộ:

```java
double longestRunningSeconds =
    reportTaskMetrics.longestActiveTaskSeconds();

if (longestRunningSeconds > 300) {
    // Ghi nhận trạng thái cần chú ý hoặc phát tín hiệu nội bộ.
}
```

Đoạn code trên chỉ kiểm tra giá trị tại thời điểm nó được gọi. Nó không tự tạo cảnh báo trong Prometheus. Trong hệ thống production, thường nên để metrics backend đánh giá điều kiện theo chu kỳ và gửi alert đến hệ thống cảnh báo.

### Cấu hình cảnh báo ở Prometheus

Tên chuỗi metrics được export phụ thuộc registry và naming convention. Sau khi kiểm tra endpoint metrics của ứng dụng, giả sử LongTaskTimer được export thành series:

```text
report_generation_active_seconds_max
```

Có thể định nghĩa alert rule:

```yaml
groups:
  - name: long-running-tasks
    rules:
      - alert: ReportGenerationRunningTooLong
        expr: report_generation_active_seconds_max > 300
        labels:
          severity: warning
        annotations:
          summary: "A report generation task is running longer than 5 minutes"
          description: "The maximum duration among active report generation tasks has exceeded 300 seconds."
```

Điều kiện được đánh giá dựa trên các mẫu Prometheus đã scrape. Cần xác nhận tên series thực tế tại endpoint `/actuator/prometheus` trước khi đưa rule vào production; không nên giả định mọi registry hoặc phiên bản đều xuất cùng một tên.

Nếu chạy nhiều instance, có thể tổng hợp theo service và môi trường bằng PromQL, tùy bộ tag đang có:

```promql
max by (service, environment) (
  report_generation_active_seconds_max
) > 300
```

Phép tổng hợp này giữ lại giá trị lớn nhất giữa các instance cùng service/environment. Nếu muốn biết số instance hoặc số tác vụ đang chạy, dùng series active count tương ứng và chọn phép tổng hợp phù hợp, chẳng hạn `sum` cho tổng số tác vụ đang hoạt động.

## 6. Hiểu giới hạn của việc phát hiện theo chu kỳ scrape

LongTaskTimer giúp quan sát tác vụ đang chạy trước khi hoàn tất, nhưng việc phát hiện ở backend vẫn phụ thuộc thời điểm thu thập.

Ví dụ, Prometheus scrape mỗi 15 giây. Một tác vụ vượt ngưỡng 5 phút ở 10:05:02 và kết thúc ở 10:05:08. Nếu lần scrape trước là 10:04:59 và lần tiếp theo là 10:05:14, sample đã dừng trước khi Prometheus đọc được giá trị vượt ngưỡng. Alert dựa trên LongTaskTimer có thể bỏ lỡ lần chạy này.

Do đó:

- LongTaskTimer hỗ trợ phát hiện tác vụ đang chạy lâu nếu backend thu thập được sample khi nó còn hoạt động.
- Scrape interval ngắn hơn tăng cơ hội quan sát nhưng không bảo đảm bắt được mọi lần vượt ngưỡng.
- Nếu mọi lần vượt ngưỡng đều phải được lưu lại, ứng dụng cần ghi nhận sự kiện khi ngưỡng bị vượt, ví dụ tăng Counter đúng một lần cho mỗi lần chạy.
- Có thể ghi thêm Timer khi tác vụ kết thúc để giữ phân bố thời lượng của các lần hoàn tất.

Nếu yêu cầu là phát hiện ngay tại thời điểm vượt ngưỡng, không phụ thuộc chu kỳ scrape, ứng dụng có thể kiểm tra thời gian chạy bằng cơ chế điều phối hoặc watchdog phù hợp rồi phát ra một sự kiện. LongTaskTimer vẫn cung cấp số đo quan sát cho dashboard và xác minh trạng thái.

## 7. Kết hợp LongTaskTimer với Timer

LongTaskTimer và Timer bổ sung cho nhau. Một LongTaskTimer cho biết các tác vụ đang hoạt động, còn Timer ghi nhận thời lượng khi một lần thực thi hoàn tất.

Nên dùng hai tên metric khác nhau vì chúng là hai loại meter có ngữ nghĩa khác nhau:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.TimeUnit;

public class ImportMetrics {

    private final LongTaskTimer activeImports;
    private final Timer completedImports;

    public ImportMetrics(MeterRegistry registry) {
        this.activeImports = LongTaskTimer.builder(
                "customer.import.active"
            )
            .description("Currently active customer imports")
            .register(registry);

        this.completedImports = Timer.builder(
                "customer.import.duration"
            )
            .description("Duration of completed customer imports")
            .publishPercentileHistogram()
            .register(registry);
    }

    public void run(Runnable importOperation) {
        LongTaskTimer.Sample activeSample = activeImports.start();

        try {
            completedImports.record(importOperation);
        } finally {
            activeSample.stop();
        }
    }

    public long activeCount() {
        return activeImports.activeTasks();
    }

    public double longestActiveSeconds() {
        return activeImports.max(TimeUnit.SECONDS);
    }
}
```

Trong ví dụ, LongTaskTimer được mở trước khi import bắt đầu và đóng sau khi thao tác kết thúc. Timer ghi nhận thời lượng của lần import đã hoàn tất. Khi import vẫn đang chạy, LongTaskTimer cung cấp thời lượng active; khi import kết thúc, Timer có thêm một mẫu duration.

Hai metric có tên riêng vì đăng ký cùng tên và tag bằng hai loại meter khác nhau trong cùng registry sẽ tạo xung đột danh tính. Cấu hình histogram trên Timer giúp backend phân tích phân bố thời lượng hoàn tất, ví dụ p95 hoặc p99 nếu registry và backend hỗ trợ cấu hình đó.

## 8. Nhiều tác vụ đồng thời và cách diễn giải max

Một LongTaskTimer có thể theo dõi nhiều sample cùng lúc. Mỗi lần gọi `start()` tạo một sample độc lập. Các giá trị quan sát tổng hợp những sample còn hoạt động trong meter đó.

Ví dụ:

| Sample | Trạng thái | Thời lượng hiện tại |
|---|---|---:|
| A | Đang chạy | 45 giây |
| B | Đang chạy | 410 giây |
| C | Đã dừng | Không còn được tính |
| D | Đang chạy | 120 giây |

Khi đó:

- `activeTasks()` = 3
- `duration(SECONDS)` = 575 giây
- `max(SECONDS)` = 410 giây

Giá trị `max` cho biết sample đang hoạt động lâu nhất đã chạy 410 giây. Nó không cho biết ID của sample B. Nếu cần điều tra tác vụ cụ thể, ghi correlation ID trong log/trace và đặt tag metric ở mức loại tác vụ có tập giá trị giới hạn, ví dụ `operation=monthly-report`.

Nếu có nhiều loại công việc với ngưỡng khác nhau, nên tạo LongTaskTimer riêng theo loại thao tác hoặc dùng tag có tập giá trị hữu hạn. Không gộp các công việc có SLA rất khác nhau vào một meter nếu một ngưỡng chung không có ý nghĩa.

## 9. Kiểm thử vòng đời và điều kiện vượt ngưỡng

Có thể dùng `SimpleMeterRegistry` để kiểm tra sample được tính khi bắt đầu và được loại khỏi số tác vụ active khi dừng:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LongTaskTimerTest {

    @Test
    void tracksActiveTaskUntilSampleStops() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        LongTaskTimer timer = LongTaskTimer.builder("report.generation.active")
            .register(registry);

        LongTaskTimer.Sample sample = timer.start();

        assertThat(timer.activeTasks()).isEqualTo(1);

        sample.stop();

        assertThat(timer.activeTasks()).isZero();
    }
}
```

Test này kiểm tra vòng đời active. Nếu muốn kiểm thử logic vượt ngưỡng mà không phải chờ thời gian thực, có thể dùng clock giả được hỗ trợ bởi phiên bản Micrometer trong dự án, bắt đầu sample, tiến đồng hồ qua ngưỡng rồi kiểm tra `max(TimeUnit.SECONDS)`. Việc kiểm thử alert rule và tên series export cần integration test với registry/backend tương ứng.

Không nên dùng `Thread.sleep(...)` dài trong unit test chỉ để đợi một tác vụ vượt ngưỡng. Clock có thể điều khiển được giúp test nhanh và ổn định hơn.

## 10. Những lỗi thường gặp

- **Dùng Timer để cảnh báo khi tác vụ chưa kết thúc:** Timer thông thường ghi nhận duration sau khi thao tác hoàn tất; LongTaskTimer phù hợp hơn cho trạng thái active.
- **Quên gọi `sample.stop()`:** tác vụ đã xong nhưng vẫn được tính là active, làm sai active count và duration.
- **Dừng sample quá sớm:** nếu chỉ đo lúc submit công việc vào executor, thời gian xử lý thực tế của worker không nằm trong sample.
- **Dừng sample quá muộn:** nếu callback không chạy khi tác vụ bị hủy hoặc lỗi, sample có thể tồn tại lâu hơn vòng đời thực tế.
- **Cho rằng LongTaskTimer lưu lịch sử tác vụ đã hoàn tất:** sample bị loại khỏi số đo active khi dừng; dùng Timer hoặc sự kiện để lưu thông tin hoàn tất.
- **Đặt ngưỡng mà không xét scrape interval:** tác vụ có thể vượt ngưỡng rồi kết thúc giữa hai lần thu thập.
- **Dùng task ID làm tag:** mỗi lần chạy tạo một chuỗi thời gian mới; dùng log/trace để theo dõi ID cụ thể.
- **Dùng cùng tên cho Timer và LongTaskTimer:** hai loại meter khác nhau cần tên riêng trong cùng registry.
- **Coi `max` là thời lượng lớn nhất của tất cả tác vụ từ trước đến nay:** `max` của LongTaskTimer chỉ phản ánh các sample còn active.

## 11. Checklist triển khai cảnh báo tác vụ dài

- [ ] Xác định chính xác thời điểm một tác vụ bắt đầu và kết thúc.
- [ ] Tạo một LongTaskTimer cho từng nhóm công việc có cùng ý nghĩa và ngưỡng.
- [ ] Gọi `start()` khi công việc thực sự bắt đầu chạy.
- [ ] Gọi `sample.stop()` trong `finally` hoặc callback hoàn tất tương ứng.
- [ ] Theo dõi `activeTasks()`, `duration(...)` và `max(...)` theo nhu cầu.
- [ ] Xác nhận tên series thực tế mà registry export.
- [ ] Thiết lập alert dựa trên max duration của các tác vụ đang active.
- [ ] Chọn scrape interval phù hợp với yêu cầu phát hiện và chi phí thu thập.
- [ ] Dùng Counter nếu cần lưu lại mọi lần vượt ngưỡng, kể cả khi tác vụ kết thúc giữa hai lần scrape.
- [ ] Kết hợp Timer nếu cần phân bố duration của các lần đã hoàn tất.
- [ ] Dùng log/trace để xác định tác vụ cụ thể; không dùng task ID làm metric tag.
- [ ] Kiểm thử cả đường thành công, exception, cancellation và timeout để sample luôn được đóng.

LongTaskTimer giúp quan sát thời lượng của các tác vụ vẫn đang chạy. Bằng cách theo dõi `max(TimeUnit)`, backend có thể cảnh báo khi tác vụ active vượt ngưỡng trước khi nó kết thúc, miễn là có mẫu được thu thập trong khoảng thời gian đó. Kết hợp LongTaskTimer với Timer và Counter sẽ cung cấp cả trạng thái hiện tại, thống kê thời lượng hoàn tất và dấu vết về những lần vượt ngưỡng đã xảy ra.

## Tài liệu tham khảo

- [Micrometer Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html) — khái niệm, cách đăng ký và các phép đo active task.
- [Micrometer LongTaskTimer API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/LongTaskTimer.html) — `start()`, `activeTasks()`, `duration(...)` và `max(...)`.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — ghi nhận thời lượng và phân bố của các lần thực thi đã hoàn tất.

