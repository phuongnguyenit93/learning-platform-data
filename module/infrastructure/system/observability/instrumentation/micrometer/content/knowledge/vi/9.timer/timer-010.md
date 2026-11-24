# Giá trị âm, tác vụ quá dài và giới hạn tích lũy thời gian

Timer đo thời gian thực hiện và số lần một thao tác được ghi nhận. Khi thiết kế instrumentation, cần xử lý đúng các trường hợp duration âm, duration bằng 0, tác vụ kéo dài và tổng thời gian tích lũy rất lớn. Những trường hợp này ảnh hưởng đến count, total time, max, histogram và cách backend diễn giải latency.

Micrometer Timer phù hợp với các thao tác có điểm bắt đầu và kết thúc rõ ràng. Giá trị thời gian được ghi nhận phải không âm. Với tác vụ kéo dài và vẫn đang chạy, Timer chỉ có thể ghi nhận khi tác vụ kết thúc; LongTaskTimer phù hợp hơn để quan sát số tác vụ đang hoạt động và thời gian chúng đã chạy.

## 1. Timer ghi nhận những gì?

Một Timer thường cung cấp ít nhất:

- **count:** số lần ghi nhận.
- **total time:** tổng thời gian của các lần ghi nhận.
- **max:** thời gian lớn nhất trong cửa sổ thống kê mà implementation đang duy trì.
- **Histogram hoặc percentile:** phân phối thời gian, nếu được cấu hình và registry hỗ trợ.

Ví dụ, nếu ba request có thời gian lần lượt là 20 ms, 40 ms và 100 ms:

\[
\text{count}=3,\qquad
\text{total time}=160\text{ ms}
\]

Giá trị trung bình có thể tính từ total time chia cho count, nhưng khi đánh giá latency vận hành, cần xem thêm percentile hoặc histogram để nhận ra đuôi phân phối. Một request rất chậm có thể bị che khuất nếu chỉ xem trung bình.

Timer là meter cho sự kiện đã được đo. Khi một thao tác bắt đầu nhưng chưa kết thúc, lần ghi nhận đó chưa làm count và total time của Timer tăng. Vì vậy, Timer không tự cho biết có bao nhiêu tác vụ đang nằm giữa hai mốc thời gian.

## 2. Giá trị âm không phải duration hợp lệ

Duration âm thường xuất hiện do:

- Trừ hai mốc thời gian lấy từ đồng hồ lịch (wall clock) trong khi đồng hồ hệ thống bị chỉnh lùi.
- Dữ liệu đầu vào sai, ví dụ client truyền thời gian xử lý âm.
- Tính sai thứ tự hai mốc bắt đầu và kết thúc.
- Dùng giá trị mặc định hoặc sentinel âm để biểu diễn trạng thái chưa có dữ liệu.

Micrometer Timer chỉ nhận duration không âm. Các lần ghi nhận có amount âm bị bỏ qua; chúng không được tính như một mẫu duration bình thường. Không nên dựa vào hành vi bỏ qua này để che lỗi ở tầng nghiệp vụ. Hãy xác thực dữ liệu trước khi gọi Timer và ghi nhận riêng trường hợp duration không hợp lệ nếu cần theo dõi.

Ví dụ kiểm tra một Duration đến từ dữ liệu bên ngoài:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public class LatencyRecorder {

    private final Timer latency;
    private final Counter invalidDuration;

    public LatencyRecorder(Timer latency, Counter invalidDuration) {
        this.latency = latency;
        this.invalidDuration = invalidDuration;
    }

    public void record(Duration duration) {
        if (duration == null || duration.isNegative()) {
            invalidDuration.increment();
            return;
        }

        latency.record(duration);
    }
}
~~~

Ở đây, duration âm được phân loại là dữ liệu không hợp lệ và không đi vào phân phối latency. Counter invalidDuration nên có tags giới hạn và không chứa giá trị đầu vào gây lỗi.

### Duration bằng 0

Duration bằng 0 là một giá trị không âm và có thể được ghi nhận. Lần ghi nhận này vẫn làm count tăng, còn total time tăng thêm 0. Điều này có thể xảy ra khi thao tác quá ngắn so với độ phân giải của nguồn đo hoặc khi ứng dụng nhận một duration bằng 0 từ dữ liệu đầu vào.

Không nên tự động đổi duration âm thành 0 để tránh mất dữ liệu. Làm vậy sẽ biến dữ liệu lỗi thành một mẫu latency cực nhanh, khiến count và phân phối bị sai lệch. Chỉ ghi duration bằng 0 khi đó thực sự là giá trị đo hợp lệ.

## 3. Dùng đồng hồ monotonic để đo thời gian trôi qua

Đo thời gian thực hiện cần đồng hồ monotonic, tức nguồn thời gian tăng theo thời gian trôi qua và không bị thay đổi bởi việc chỉnh ngày giờ hệ thống. Không nên tự lấy hiệu hai giá trị System.currentTimeMillis() để đo latency vì wall clock có thể bị đồng bộ NTP, người quản trị chỉnh giờ hoặc thay đổi theo môi trường ảo hóa.

Micrometer Timer.Sample dùng clock của registry để lấy mốc monotonic khi bắt đầu và khi dừng. Cách này giúp tránh việc phép đo bị âm chỉ vì đồng hồ lịch bị điều chỉnh.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final MeterRegistry registry;
    private final ReportRepository repository;

    public ReportService(
        MeterRegistry registry,
        ReportRepository repository
    ) {
        this.registry = registry;
        this.repository = repository;
    }

    public Report generate(ReportRequest request) {
        Timer.Sample sample = Timer.start(registry);
        try {
            return repository.generate(request);
        } finally {
            sample.stop(
                registry.timer(
                    "reports.generate.duration",
                    "result", "completed"
                )
            );
        }
    }
}
~~~

Ví dụ trên đo thời gian đến lúc hàm repository trả về hoặc ném lỗi. Nếu cần phân biệt success và failure, hãy chọn result trong từng nhánh hoàn tất rồi dừng sample với Timer tương ứng. Không gắn một outcome cố định nếu thao tác có thể kết thúc theo nhiều cách.

Với một duration được tính từ hai mốc thời gian bên ngoài, hãy xác định nguồn clock và thứ tự mốc rõ ràng. Nếu có thể, giữ lại Timer.Sample thay vì tự tính duration từ wall clock.

## 4. Ghi nhận duration bằng các API của Timer

Micrometer cung cấp nhiều cách ghi nhận:

~~~java
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.TimeUnit;

Timer timer = registry.timer("orders.process.duration");

// Ghi một giá trị với đơn vị tường minh.
timer.record(25, TimeUnit.MILLISECONDS);

// Ghi một khoảng thời gian.
timer.record(java.time.Duration.ofMillis(40));

// Đo thời gian thực thi đồng bộ, kể cả khi operation ném exception.
timer.record(() -> orderService.process(order));
~~~

Khi dùng record(long, TimeUnit), luôn truyền đúng đơn vị của amount. Nhầm MILLISECONDS thành SECONDS có thể làm latency sai lệch hàng nghìn lần mà code vẫn chạy bình thường.

Với record(Runnable) hoặc overload tương ứng, Timer đo thời gian thực thi của phần code được bọc. Nếu cần đo toàn bộ thao tác gồm cả việc chờ kết quả bất đồng bộ, không chỉ bọc lời gọi trả về CompletableFuture vì lời gọi đó có thể kết thúc ngay sau khi submit. Hãy dừng Timer.Sample trong callback hoàn tất hoặc dùng cơ chế đo long-running phù hợp.

## 5. Tác vụ quá dài: khi nào nên dùng LongTaskTimer?

Timer phù hợp với latency của thao tác đã hoàn tất. Với tác vụ có thể chạy nhiều phút hoặc nhiều giờ, chỉ dùng Timer sẽ không hiển thị duration trong lúc tác vụ còn chạy. Backend chỉ nhận được lần đo khi thao tác kết thúc.

LongTaskTimer được thiết kế để quan sát tác vụ đang hoạt động. Nó cung cấp số tác vụ hiện đang chạy và tổng thời gian mà các tác vụ đang chạy đã tiêu thụ tại thời điểm thu thập.

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    private final LongTaskTimer exportInProgress;

    public ExportService(MeterRegistry registry) {
        this.exportInProgress = LongTaskTimer.builder("exports.in.progress")
            .description("Các tác vụ export hiện đang chạy")
            .tag("format", "csv")
            .register(registry);
    }

    public void export() {
        LongTaskTimer.Sample sample = exportInProgress.start();
        try {
            performLargeExport();
        } finally {
            sample.stop();
        }
    }
}
~~~

Khi gọi start(), LongTaskTimer bắt đầu theo dõi một tác vụ đang hoạt động. Trong lúc tác vụ chưa dừng, registry có thể thu thập trạng thái số tác vụ và thời gian hoạt động. Khi sample.stop() được gọi, tác vụ đó không còn nằm trong tập đang chạy.

LongTaskTimer không thay thế hoàn toàn Timer:

| Câu hỏi | Meter phù hợp |
| --- | --- |
| Có bao nhiêu tác vụ đang chạy ngay lúc này? | LongTaskTimer hoặc Gauge trạng thái |
| Những tác vụ đang chạy đã hoạt động bao lâu? | LongTaskTimer |
| Một tác vụ hoàn tất mất tổng cộng bao lâu? | Timer |
| Có bao nhiêu tác vụ đã hoàn tất? | Counter hoặc count của Timer |

Nếu cần cả trạng thái đang chạy lẫn latency cuối cùng, có thể dùng LongTaskTimer cho thời gian đang hoạt động và Timer cho thời gian hoàn tất. Bảo đảm mỗi sample được dừng đúng một lần và các tags dùng chung một quy ước.

## 6. Đo tác vụ bất đồng bộ và bảo đảm dừng sample

Với tác vụ bất đồng bộ, sample phải sống đến khi công việc thực sự hoàn tất. Không dừng sample ngay sau khi submit:

~~~java
Timer.Sample sample = Timer.start(registry);

return reportClient.generateAsync(request)
    .whenComplete((report, error) -> {
        String result = error == null ? "success" : "failure";

        sample.stop(
            registry.timer(
                "reports.generate.duration",
                "result", result
            )
        );
    });
~~~

Nếu tác vụ có timeout hoặc cancellation, hãy xác định callback nào chịu trách nhiệm kết thúc phép đo. Một tác vụ chỉ được ghi nhận một lần; tránh gọi stop ở cả nhánh timeout lẫn callback hoàn tất nếu cả hai có thể chạy. Với tác vụ rất dài, có thể theo dõi trạng thái in-flight bằng LongTaskTimer.Sample và ghi Timer khi kết quả cuối cùng có mặt.

## 7. Giới hạn khi chuyển Duration sang nanosecond

Micrometer Timer chuẩn hóa các duration theo đơn vị thời gian phù hợp với registry, và API cho phép truy vấn tổng thời gian theo TimeUnit. Khi dùng Timer.record(Duration), Java cần chuyển Duration sang nanosecond. Duration.toNanos() có thể ném ArithmeticException nếu giá trị vượt phạm vi của kiểu long nanosecond.

Giới hạn biểu diễn của signed 64-bit nanosecond vào khoảng 292 năm cho một duration đơn lẻ. Các thao tác thực tế thường ngắn hơn rất nhiều, nhưng hệ thống có thể gặp vấn đề nếu chuyển đổi duration cực lớn hoặc dữ liệu đầu vào không hợp lệ.

~~~java
import java.time.Duration;

Duration duration = Duration.ofDays(2);

try {
    long nanos = duration.toNanos();
    timer.record(nanos, java.util.concurrent.TimeUnit.NANOSECONDS);
} catch (ArithmeticException ex) {
    invalidDurationCounter.increment();
    // Ghi log hoặc xử lý dữ liệu vượt phạm vi theo quy tắc ứng dụng.
}
~~~

Không cần tự chuyển mọi duration sang nanosecond nếu không có lý do. Có thể dùng trực tiếp timer.record(duration) cho duration nằm trong phạm vi biểu diễn. Nếu dữ liệu có thể rất lớn, kiểm tra trước khi chuyển đổi và chọn đơn vị phù hợp khi dùng API amount/unit.

## 8. Giới hạn tích lũy total time và count

Total time là tổng thời gian của nhiều lần ghi nhận, không phải thời gian đồng hồ kể từ khi ứng dụng khởi động. Nếu một Timer ghi 10.000 lần, mỗi lần 2 giây, total time tăng thêm 20.000 giây.

Một số implementation lưu thời gian tích lũy nội bộ bằng số nguyên nanosecond có dấu. Với biểu diễn signed long, phạm vi nanosecond tối đa xấp xỉ 292 năm thời gian cộng dồn. Đây là tổng duration của mọi lần ghi nhận, không phải thời gian sống của tiến trình; nhiều thao tác đồng thời có thể làm tổng tăng nhanh hơn thời gian thực.

Chi tiết accumulator phụ thuộc implementation và phiên bản registry. Không nên giả định mọi backend, exporter hoặc storage đều có độ chính xác và phạm vi số giống nhau. API totalTime(TimeUnit) trả về số thực theo đơn vị được yêu cầu; việc chuyển đổi và lưu trữ ở backend có thể có giới hạn riêng.

Count cũng có giới hạn biểu diễn nếu implementation dùng số nguyên hữu hạn. Với số lượng sự kiện cực lớn, cần hiểu kiểu dữ liệu và quy tắc reset của registry/backend. Trong vận hành thông thường, quan trọng hơn là hiểu metric đang là cumulative hay step-based:

- **Cumulative registry:** count và total time thường biểu diễn tổng kể từ khi tiến trình hoặc meter bắt đầu.
- **Step registry:** count và total time có thể biểu diễn lượng phát sinh trong một publishing step và được xoay vòng theo chu kỳ export.

Đừng cộng các giá trị step như thể chúng là counter tích lũy, và đừng giả định mọi registry đều trả về cùng semantics cho cùng một thời điểm truy vấn. Hãy kiểm tra kiểu registry đang dùng và cách backend nhận metric.

## 9. Max không nhất thiết là giá trị lớn nhất từ trước đến nay

Timer có thể cung cấp max, nhưng max của nhiều implementation Micrometer là thống kê theo cửa sổ thời gian. Nếu không có mẫu mới trong khoảng thời gian cấu hình, giá trị max có thể trở về 0 sau khi cửa sổ hết hạn.

Vì vậy:

- Không diễn giải max như thời gian chậm nhất trong toàn bộ vòng đời ứng dụng.
- Dùng histogram hoặc percentile khi cần phân tích phân phối latency.
- Chọn expiry, buffer length và cấu hình thống kê theo khả năng của registry.
- Nếu cần lưu sự kiện latency cực lớn lâu dài, hãy thiết kế một metric hoặc log/trace riêng có semantics rõ ràng.

Histogram cũng có giới hạn. Nếu các bucket được cấu hình cho latency thông thường nhưng một tác vụ kéo dài nhiều giờ, giá trị có thể rơi vào bucket cao nhất hoặc overflow bucket. Hãy chọn phạm vi bucket và SLA phù hợp với thời gian hợp lệ của thao tác; không tăng giới hạn vô hạn nếu điều đó tạo thêm chi phí không cần thiết.

## 10. Không dùng Timer để đo thời gian chờ vô hạn

Nếu một tác vụ có thể chờ vô hạn hoặc kéo dài qua nhiều chu kỳ scrape, Timer chỉ cung cấp số đo sau khi kết thúc. Trong lúc chờ, dashboard có thể không thấy latency của tác vụ đó. Hãy cân nhắc:

- LongTaskTimer để theo dõi tác vụ đang chạy và thời gian đã chạy.
- Gauge để theo dõi số tác vụ đang chờ hoặc đang hoạt động nếu nguồn trạng thái đáng tin cậy.
- Counter để đếm số tác vụ hoàn tất, thất bại hoặc bị timeout.
- Timer để đo thời gian hoàn tất của từng tác vụ.

Kết hợp các meter giúp trả lời cả câu hỏi về trạng thái hiện tại lẫn kết quả sau cùng. Ví dụ, queue depth tăng, số tác vụ đang chạy chạm giới hạn, LongTaskTimer cho thấy thời gian hoạt động kéo dài và Timer khi hoàn tất cho biết latency cuối cùng.

## 11. Kiểm thử duration âm, zero và giới hạn chuyển đổi

SimpleMeterRegistry có thể xác minh hành vi cơ bản của Timer mà không cần backend:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class TimerDurationTest {

    @Test
    void recordsZeroAndPositiveDurationButIgnoresNegativeDuration() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Timer timer = registry.timer("jobs.duration");

        timer.record(0, TimeUnit.MILLISECONDS);
        timer.record(25, TimeUnit.MILLISECONDS);

        long countAfterValidSamples = timer.count();

        timer.record(-10, TimeUnit.MILLISECONDS);

        assertThat(countAfterValidSamples).isEqualTo(2L);
        assertThat(timer.count()).isEqualTo(2L);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(25.0);

        registry.close();
    }
}
~~~

Kiểm thử chuyển đổi Duration lớn:

~~~java
import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(
    () -> Duration.ofSeconds(Long.MAX_VALUE).toNanos()
).isInstanceOf(ArithmeticException.class);
~~~

Các kiểm thử bổ sung nên bao gồm:

- Duration âm từ dữ liệu đầu vào được phát hiện và không làm tăng Timer count.
- Duration bằng 0 chỉ được ghi khi có ý nghĩa hợp lệ.
- Timer.Sample dừng đúng một lần trong cả nhánh thành công và exception.
- Tác vụ bất đồng bộ chỉ được đo đến khi future hoàn tất.
- LongTaskTimer giảm active task sau khi sample dừng.
- Tác vụ kéo dài vẫn xuất hiện trong số tác vụ đang chạy khi scrape.
- Cấu hình histogram có bucket phù hợp với latency hợp lệ của hệ thống.

SimpleMeterRegistry xác minh hành vi trong bộ nhớ. Muốn xác nhận step semantics, histogram, max window hoặc export thực tế, cần integration test với registry và backend tương ứng.

## 12. Quy trình chọn meter và bảo vệ phép đo

Khi thiết kế phép đo thời gian:

1. Xác định thao tác có điểm kết thúc rõ ràng hay có thể chạy lâu trong nền.
2. Dùng Timer cho latency của thao tác hoàn tất; dùng LongTaskTimer cho tác vụ cần quan sát khi vẫn đang chạy.
3. Dùng Timer.Sample hoặc API record thay vì tự trừ wall-clock timestamps.
4. Xác thực duration âm, null và dữ liệu vượt phạm vi trước khi ghi nhận.
5. Dùng đúng TimeUnit khi ghi amount và tránh chuyển đổi nanosecond không cần thiết.
6. Hiểu count, total time, max và histogram theo semantics của registry.
7. Kiểm tra accumulator, step interval, retention và giới hạn số của backend.
8. Kiểm thử duration âm, zero, exception, timeout và tác vụ kéo dài.

Timer cung cấp số đo latency có ích khi duration hợp lệ và semantics được hiểu đúng. LongTaskTimer bổ sung góc nhìn cho công việc đang hoạt động. Kiểm soát duration âm, phạm vi chuyển đổi và tổng thời gian tích lũy giúp metrics không bị sai lệch khi ứng dụng chạy lâu hoặc xử lý tải lớn.
