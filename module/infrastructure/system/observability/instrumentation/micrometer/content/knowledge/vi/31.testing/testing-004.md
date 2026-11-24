# Kiểm thử LongTaskTimer trước, trong và sau khi tác vụ kết thúc

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `LongTaskTimer` dùng để quan sát công việc có thể chạy lâu và cần biết trạng thái ngay khi nó còn đang thực thi. Khác với `Timer` thông thường, vốn ghi nhận một mẫu khi thao tác hoàn tất, `LongTaskTimer` cung cấp số tác vụ đang hoạt động cùng thời lượng hiện tại của chúng. Vì vậy, có thể kiểm tra một tác vụ trước khi bắt đầu, trong lúc đang chạy và sau khi dừng để xác minh vòng đời instrumentation.

Một bài kiểm thử tốt cần xác nhận ba điều: trước khi start không có tác vụ active; sau khi start, số tác vụ và thời lượng tăng theo clock; sau khi `Sample.stop()`, tác vụ biến mất khỏi thống kê active. Có thể dùng `MockClock` để điều khiển thời gian mà không phụ thuộc `Thread.sleep()`.

## 1. LongTaskTimer quan sát điều gì?

`LongTaskTimer` phù hợp với thao tác kéo dài như tạo báo cáo, import dữ liệu, chạy batch, đồng bộ hệ thống hoặc xử lý một tác vụ nền nhiều phút. Nó trả lời các câu hỏi:

- Hiện có bao nhiêu tác vụ đang chạy?
- Tổng thời gian đã trôi qua của các tác vụ đang chạy là bao nhiêu?
- Tác vụ active lâu nhất đã chạy bao lâu?

Ba phép đo chính:

| API | Ý nghĩa |
| --- | --- |
| `activeTasks()` | Số sample đang hoạt động |
| `duration(TimeUnit)` | Tổng thời lượng hiện tại của tất cả sample đang hoạt động |
| `max(TimeUnit)` | Thời lượng lớn nhất trong các sample đang hoạt động |

Nếu không có sample nào active, các giá trị thời lượng hiện tại trở về 0. `LongTaskTimer` không giữ một lịch sử duration của các tác vụ đã hoàn tất; khi sample được dừng, nó không còn được tính trong các phép đo active.

## 2. Phân biệt LongTaskTimer với Timer

Hai loại meter giải quyết hai câu hỏi khác nhau:

| Khía cạnh | `Timer` | `LongTaskTimer` |
| --- | --- | --- |
| Mục tiêu | Thống kê các lần thực thi đã hoàn tất | Theo dõi các lần thực thi còn đang chạy |
| Khi ghi nhận | Khi gọi `record(...)` kết thúc hoặc sample được stop | Ngay từ lúc `start()` và cập nhật khi sample còn active |
| Dữ liệu chính | Count, total time, max và phân phối nếu cấu hình | Active task count, tổng duration active, max duration active |
| Sau khi task kết thúc | Mẫu vẫn nằm trong thống kê tích lũy của Timer | Sample bị loại khỏi thống kê active |
| Câu hỏi điển hình | Các tác vụ đã hoàn tất mất bao lâu? | Hiện tại có tác vụ nào chạy quá lâu không? |

Trong ứng dụng production, thường dùng cả hai: `LongTaskTimer` để phát hiện tác vụ đang treo hoặc kéo dài bất thường; `Timer` để phân tích latency của các tác vụ sau khi hoàn tất. Không dùng `LongTaskTimer` thay thế toàn bộ thống kê phân phối của `Timer`.

## 3. Tạo LongTaskTimer và bắt đầu sample

Đăng ký meter một lần trong giai đoạn khởi tạo thành phần:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ReportMetrics {
    private final LongTaskTimer activeReports;

    public ReportMetrics(MeterRegistry registry) {
        this.activeReports = LongTaskTimer.builder("reports.active")
            .description("Reports currently being generated")
            .register(registry);
    }

    public LongTaskTimer.Sample startReport() {
        return activeReports.start();
    }
}
```

`start()` trả về `LongTaskTimer.Sample`. Sample đại diện cho một lần thực thi cụ thể. Khi công việc kết thúc, gọi `sample.stop()` đúng một lần để loại sample đó khỏi các phép đo active.

Không tạo `LongTaskTimer` mới cho từng report. Hãy giữ một meter dùng chung và tạo một sample riêng cho mỗi lần thực thi. Meter có thể được cập nhật đồng thời bởi nhiều thread; sample phải thuộc đúng tác vụ mà nó theo dõi.

## 4. Trạng thái trước khi tác vụ bắt đầu

Ngay sau khi tạo meter nhưng chưa gọi `start()`, không có tác vụ nào active:

```java
import java.util.concurrent.TimeUnit;

LongTaskTimer timer = LongTaskTimer.builder("reports.active")
    .register(registry);

assertThat(timer.activeTasks()).isZero();
assertThat(timer.duration(TimeUnit.SECONDS)).isZero();
assertThat(timer.max(TimeUnit.SECONDS)).isZero();
```

Đây là baseline của bài kiểm thử. Nếu active count khác 0, cần kiểm tra xem test có dùng registry dùng chung với test khác hay sample cũ chưa được dừng. Dùng registry mới cho mỗi test giúp cô lập trạng thái.

Ở ứng dụng thực tế, tác vụ đang nằm trong executor queue chưa phải là tác vụ đang chạy. Chỉ gọi `start()` khi worker thực sự bắt đầu xử lý nếu mục tiêu là đo active execution. Nếu start tại thời điểm submit, queue wait cũng bị tính vào thời lượng active và active count sẽ bao gồm cả task chưa chiếm worker.

## 5. Trạng thái trong khi tác vụ đang chạy

Sau khi gọi `start()`, `activeTasks()` tăng lên. `duration(unit)` bắt đầu phản ánh thời gian đã trôi qua của sample; `max(unit)` phản ánh sample active lâu nhất.

```java
LongTaskTimer.Sample sample = timer.start();

assertThat(timer.activeTasks()).isEqualTo(1);
assertThat(timer.duration(TimeUnit.SECONDS)).isGreaterThanOrEqualTo(0.0);
assertThat(timer.max(TimeUnit.SECONDS)).isGreaterThanOrEqualTo(0.0);
```

Trong test dùng clock giả, có thể tiến clock một khoảng xác định rồi so sánh duration với giá trị mong đợi. Trong production, các giá trị này được cập nhật theo clock khi registry đọc meter hoặc exporter thu thập dữ liệu.

`duration()` là tổng duration của tất cả sample đang active. Nếu có ba tác vụ cùng chạy trong 10 giây, tổng duration có thể gần 30 giây, dù thời gian thực chỉ trôi qua 10 giây. `max()` là duration của sample active dài nhất, không phải tổng duration.

## 6. Trạng thái sau khi tác vụ kết thúc

Khi công việc hoàn tất, dừng sample:

```java
sample.stop();

assertThat(timer.activeTasks()).isZero();
assertThat(timer.duration(TimeUnit.SECONDS)).isZero();
assertThat(timer.max(TimeUnit.SECONDS)).isZero();
```

Sau khi dừng, sample không còn được tính trong thống kê active. Đây là hành vi cần xác minh trong mọi nhánh kết thúc, gồm thành công, exception và cancellation khi task đang chạy.

`LongTaskTimer` không lưu duration vừa hoàn tất như một `Timer`. Nếu dashboard cần biết tác vụ vừa kết thúc mất bao lâu, ghi thêm một `Timer` thông thường. Có thể dùng `Timer.Sample` hoặc `Timer.record(...)` trong cùng khối xử lý để thu thập duration hoàn tất.

## 7. Luôn dừng sample bằng finally

Nếu task ném exception mà code bỏ qua `sample.stop()`, active count sẽ giữ lại một tác vụ không còn chạy. Đây là lỗi instrumentation phổ biến và làm dashboard báo có công việc bị treo dù worker đã thoát.

```java
LongTaskTimer.Sample sample = activeReports.start();
try {
    return reportService.generate(reportId);
}
finally {
    sample.stop();
}
```

Đặt `stop()` trong `finally` để sample được đóng khi method trả về bình thường hoặc ném exception. Không gọi `stop()` ở cả `catch` lẫn `finally`, vì một sample chỉ cần dừng một lần. Nếu code có nhiều nhánh return, `finally` giúp tránh bỏ sót nhánh.

## 8. Kết hợp LongTaskTimer với Timer để xem active và completed

Ví dụ dưới đây theo dõi tác vụ báo cáo đang chạy và duration của các lần đã hoàn tất:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class ReportExecutionMetrics {
    private final LongTaskTimer active;
    private final Timer completed;

    public ReportExecutionMetrics(MeterRegistry registry) {
        this.active = LongTaskTimer.builder("reports.active")
            .description("Reports currently being generated")
            .register(registry);
        this.completed = Timer.builder("reports.execution")
            .description("Duration of completed report generations")
            .register(registry);
    }

    public Report generate(Supplier<Report> operation) {
        LongTaskTimer.Sample activeSample = active.start();
        try {
            return completed.record(operation);
        }
        finally {
            activeSample.stop();
        }
    }
}
```

Khi operation chạy, `LongTaskTimer` phản ánh tác vụ active. Khi operation hoàn tất, `Timer` ghi nhận count và duration; `finally` dừng sample active. Nếu operation ném exception, `Timer.record(...)` vẫn ghi nhận thời gian thực thi trước khi exception truyền ra, còn `finally` bảo đảm active sample được đóng.

Trong một hệ thống async, hãy đặt `active.start()` bên trong worker, tại điểm công việc thật sự bắt đầu. Nếu gọi từ caller trước khi enqueue, metric sẽ đo cả queue wait.

## 9. Kiểm thử trước, trong và sau bằng MockClock

Không cần `Thread.sleep()` để kiểm tra thời lượng. `MockClock` cho phép tiến thời gian chủ động; `SimpleMeterRegistry` nhận clock này khi khởi tạo.

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LongTaskTimerLifecycleTest {
    @Test
    void reportsTaskBeforeDuringAndAfterExecution() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        LongTaskTimer timer = LongTaskTimer.builder("reports.active")
            .register(registry);

        // Before: chưa có sample nào hoạt động.
        assertEquals(0, timer.activeTasks());
        assertEquals(0.0, timer.duration(TimeUnit.SECONDS), 0.001);

        LongTaskTimer.Sample sample = timer.start();

        // During: một sample đang hoạt động.
        assertEquals(1, timer.activeTasks());
        clock.add(Duration.ofSeconds(4));
        assertEquals(4.0, timer.duration(TimeUnit.SECONDS), 0.001);
        assertEquals(4.0, timer.max(TimeUnit.SECONDS), 0.001);

        sample.stop();

        // After: sample đã rời khỏi tập active.
        assertEquals(0, timer.activeTasks());
        assertEquals(0.0, timer.duration(TimeUnit.SECONDS), 0.001);
        assertEquals(0.0, timer.max(TimeUnit.SECONDS), 0.001);

        registry.close();
    }
}
```

Test tiến clock đúng 4 giây và xác minh duration trong lúc sample active. Sau khi dừng sample, active count, tổng duration và max active duration trở về 0. Dùng sai số nhỏ khi so sánh số thực để tránh phụ thuộc biểu diễn floating point.

## 10. Kiểm thử nhiều tác vụ chạy đồng thời

Một `LongTaskTimer` có thể theo dõi nhiều sample cùng lúc. `activeTasks()` đếm số sample, `duration()` cộng thời gian của tất cả sample đang chạy, còn `max()` lấy sample dài nhất.

```java
LongTaskTimer.Sample first = timer.start();
clock.add(Duration.ofSeconds(2));
LongTaskTimer.Sample second = timer.start();
clock.add(Duration.ofSeconds(3));

assertEquals(2, timer.activeTasks());
assertEquals(8.0, timer.duration(TimeUnit.SECONDS), 0.001);
assertEquals(5.0, timer.max(TimeUnit.SECONDS), 0.001);

first.stop();
assertEquals(1, timer.activeTasks());
assertEquals(3.0, timer.duration(TimeUnit.SECONDS), 0.001);
assertEquals(3.0, timer.max(TimeUnit.SECONDS), 0.001);

second.stop();
assertEquals(0, timer.activeTasks());
```

Ở thời điểm cuối, sample thứ nhất đã chạy 5 giây và sample thứ hai chạy 3 giây. Tổng duration là 8 giây và max là 5 giây. Khi dừng sample thứ nhất, chỉ còn sample thứ hai với duration 3 giây.

Đây là lý do không thể diễn giải `duration()` như thời gian wall-clock của toàn bộ hệ thống. Khi có nhiều task chồng lấn, tổng thời gian active lớn hơn thời gian thực đã trôi qua.

## 11. Kiểm thử nhánh exception

Một bài test cần xác nhận sample được dừng dù logic nghiệp vụ thất bại:

```java
LongTaskTimer.Sample sample = timer.start();
try {
    throw new IllegalStateException("report failed");
}
finally {
    sample.stop();
}
```

Trong test thực tế, gọi method service được instrument bằng `LongTaskTimer`, bắt exception ở test, sau đó xác minh `activeTasks()` bằng 0. Không chỉ kiểm tra exception được ném; cần kiểm tra trạng thái meter sau khi method thoát.

Nếu sample vẫn active sau exception, có thể handler hoặc code cleanup chưa được gọi. Đặt `stop()` trong `finally` của chính ranh giới sở hữu sample giúp vòng đời dễ kiểm tra và tránh phụ thuộc caller có bắt lỗi hay không.

## 12. Cancellation và tác vụ trong queue

Phân biệt hai trường hợp:

- **Task bị hủy trước khi worker bắt đầu:** chưa gọi `LongTaskTimer.start()`, vì vậy không có sample active cần dừng. Có thể ghi Counter riêng cho số task bị cancel/reject nếu cần thống kê.
- **Task bị hủy khi đang chạy:** sample đã active. Worker cần đi qua `finally` để dừng sample khi nhận interrupt hoặc thoát khỏi logic xử lý.

Không dừng sample chỉ vì caller hủy `Future` nếu công việc nền vẫn tiếp tục chạy. Việc cancel Future không đảm bảo code worker đã dừng ngay lập tức; sample phải theo dõi vòng đời thực của task. Nếu tác vụ bỏ qua interrupt, nó vẫn là tác vụ active và LongTaskTimer tiếp tục phản ánh điều đó.

## 13. Kiểm tra meter qua Actuator và exporter

Với Spring Boot Actuator, endpoint `/actuator/metrics` có thể được dùng để kiểm tra meter LongTaskTimer theo tên đã đăng ký, ví dụ:

```text
GET /actuator/metrics/reports.active
```

Các measurement thường phản ánh active task count, duration và max duration; tên measurement cụ thể phụ thuộc phiên bản Micrometer/Spring Boot. Nếu dùng Prometheus registry, kiểm tra `/actuator/prometheus` để xem cách registry ánh xạ LongTaskTimer sang exposition.

Không giả định tên series của mọi backend giống nhau. Hãy kiểm tra output thực tế, xác nhận đơn vị thời gian, tag và giá trị thay đổi khi bắt đầu/dừng sample. LongTaskTimer thường được export bằng các phép đo trạng thái hiện tại; không áp dụng cách truy vấn counter cumulative như `rate()` cho active count hoặc active duration nếu backend không định nghĩa chúng là counter.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| `activeTasks()` không trở về 0 | Thiếu `sample.stop()` ở nhánh exception/cancel hoặc sample bị giữ lại |
| Duration bằng 0 ngay sau start | Clock chưa tiến hoặc sample chưa được start |
| Duration lớn hơn thời gian wall-clock | Nhiều sample active cùng lúc; duration là tổng thời gian của chúng |
| `max()` nhỏ hơn `duration()` | Bình thường khi có nhiều task active; max chỉ lấy sample dài nhất |
| Không thấy duration của task đã hoàn tất | LongTaskTimer chỉ đo sample active; dùng Timer để lưu lịch sử completed |
| Test chập chờn | Dùng `Thread.sleep()` thay vì `MockClock` |
| Active count tăng khi task chỉ đang chờ queue | Gọi `start()` ở thời điểm submit thay vì worker start |
| Future đã cancel nhưng active vẫn tăng | Worker chưa thực sự dừng hoặc không xử lý interrupt |
| Exporter không có series như mong đợi | Tên/định dạng LongTaskTimer phụ thuộc registry và phiên bản exporter |

Khi điều tra, kiểm tra vị trí gọi `start()`, mọi đường gọi `stop()`, trạng thái task thực tế và semantics của exporter. Nếu cần lịch sử duration đã hoàn tất, kiểm tra Timer riêng thay vì tìm dữ liệu đó trong LongTaskTimer.

## 15. Nguyên tắc áp dụng

Tạo một `LongTaskTimer` dùng chung cho loại công việc và tạo một `Sample` cho mỗi lần thực thi. Gọi `start()` khi tác vụ thực sự bắt đầu chạy, đọc `activeTasks()`, `duration()` và `max()` trong lúc task active, rồi gọi `stop()` trong `finally` để kết thúc vòng đời.

Kiểm thử đủ ba trạng thái trước/trong/sau, thêm trường hợp nhiều sample đồng thời và exception/cancellation. Dùng `MockClock` cùng `SimpleMeterRegistry` để xác minh thời gian có thể lặp lại mà không sleep. Kết hợp `LongTaskTimer` với `Timer` khi cần cả trạng thái đang chạy lẫn thống kê latency của tác vụ đã hoàn tất; xác minh tên và đơn vị export tại endpoint Actuator hoặc backend thực tế.
