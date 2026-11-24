# Đo tác vụ đang chạy bằng LongTaskTimer và kết quả hoàn tất bằng Timer

Trong bài thực hành này, bạn sẽ instrument một tác vụ xuất báo cáo có thể chạy trong nhiều giây. Trong lúc tác vụ đang chạy, hệ thống cần biết có bao nhiêu tác vụ còn active và chúng đã chạy bao lâu. Khi tác vụ kết thúc, hệ thống cần ghi nhận thời lượng hoàn tất để phân tích latency và phân loại kết quả thành công hoặc lỗi.

Hai meter đảm nhiệm hai câu hỏi khác nhau:

- LongTaskTimer cho biết công việc nào vẫn đang chạy, số tác vụ active và thời lượng của chúng tại thời điểm đọc metrics.
- Timer ghi nhận duration của một lần thực thi sau khi lần đó kết thúc, kèm count và total time.

Bạn sẽ xây dựng service đo một tác vụ xuất báo cáo, viết test giữ tác vụ ở trạng thái active bằng CountDownLatch, kiểm tra metrics trước và sau khi hoàn tất, rồi mở rộng test cho nhánh lỗi và nhiều tác vụ đồng thời.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

1. Đăng ký LongTaskTimer để theo dõi tác vụ còn đang chạy.
2. Dùng Timer.Sample để đo duration của một lần thực thi từ lúc bắt đầu đến lúc kết thúc.
3. Ghi Timer cho cả nhánh thành công và lỗi.
4. Hiểu vì sao Timer chưa tăng count khi tác vụ vẫn đang chạy.
5. Quan sát active task count và duration trước khi tác vụ hoàn tất.
6. Kiểm thử lifecycle mà không dùng Thread.sleep để điều khiển thứ tự.
7. Phân biệt thời gian của tác vụ đang active với tổng duration của các tác vụ đã hoàn tất.

## 2. Bối cảnh bài toán

Một dịch vụ billing xuất báo cáo doanh thu theo tháng. Một lần xuất báo cáo có thể:

- Đọc dữ liệu từ nhiều bảng.
- Tổng hợp số liệu.
- Tạo file CSV.
- Lưu file vào object storage.

Người vận hành cần biết có bao nhiêu lần export đang chạy và tác vụ active lâu nhất đã chạy bao lâu. Sau khi một lần export kết thúc, dashboard cần có duration và outcome để phân tích latency, tỷ lệ lỗi.

Ta chọn hợp đồng metrics sau:

| Meter | Loại | Tags | Ý nghĩa |
|---|---|---|---|
| report.export.active | LongTaskTimer | report_type | Số tác vụ export đang active và thời lượng hiện tại |
| report.export.duration | Timer | report_type, outcome | Duration của mỗi lần export đã kết thúc |

Giá trị tag được giới hạn:

- report_type: monthly.
- outcome: success hoặc error.

Không thêm report ID, user ID, file name hoặc request ID vào metric tags. Các định danh cụ thể nên được ghi trong log hoặc trace.

## 3. Chuẩn bị project

Ví dụ dùng Java 17+, Micrometer Core, JUnit 5 và AssertJ. Nếu ứng dụng đã dùng Spring Boot Actuator, hãy dùng phiên bản Micrometer do Spring Boot dependency management quản lý.

Với Maven, dependency chính:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-core</artifactId>
</dependency>
~~~

Dependency test:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle:

~~~kotlin
implementation("io.micrometer:micrometer-core")
testImplementation("org.junit.jupiter:junit-jupiter")
testImplementation("org.assertj:assertj-core")
~~~

Không cần cài Prometheus để làm các unit test. Ta sẽ dùng SimpleMeterRegistry để đọc meter trong bộ nhớ.

## 4. Tạo service đo tác vụ export

Tạo class ReportExportService. Service nhận MeterRegistry qua constructor và đăng ký ba meter:

- Một LongTaskTimer dùng chung cho các lần export monthly.
- Một Timer cho outcome success.
- Một Timer cho outcome error.

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.Callable;

public final class ReportExportService {

    private final MeterRegistry registry;
    private final LongTaskTimer activeExports;
    private final Timer successfulExports;
    private final Timer failedExports;

    public ReportExportService(MeterRegistry registry) {
        this.registry = registry;

        this.activeExports = LongTaskTimer
                .builder("report.export.active")
                .description("Currently running monthly report exports")
                .tag("report_type", "monthly")
                .register(registry);

        this.successfulExports = Timer
                .builder("report.export.duration")
                .description("Completed monthly report export duration")
                .tag("report_type", "monthly")
                .tag("outcome", "success")
                .register(registry);

        this.failedExports = Timer
                .builder("report.export.duration")
                .description("Failed monthly report export duration")
                .tag("report_type", "monthly")
                .tag("outcome", "error")
                .register(registry);
    }

    public <T> T execute(Callable<T> operation) throws Exception {
        LongTaskTimer.Sample activeSample = activeExports.start();
        Timer.Sample completedSample = Timer.start(registry);
        boolean success = false;

        try {
            T result = operation.call();
            success = true;
            return result;
        } finally {
            try {
                activeSample.stop();
            } finally {
                completedSample.stop(
                        success ? successfulExports : failedExports
                );
            }
        }
    }
}
~~~

Điểm quan trọng nằm ở hai sample:

- activeSample bắt đầu khi công việc bắt đầu và dừng trong finally.
- completedSample cũng bắt đầu lúc đó, nhưng chỉ ghi vào Timer đích khi stop.

Biến success mặc định là false. Chỉ khi operation trả về bình thường, biến mới thành true. Vì vậy cả checked exception, RuntimeException và Error đều đi qua finally và được ghi vào Timer outcome error; exception gốc vẫn được ném tiếp cho caller.

Khối finally lồng nhau bảo đảm completedSample vẫn được dừng nếu thao tác dừng LongTaskTimer phát sinh RuntimeException. Trong một registry thông thường, hai thao tác stop đều nhanh và không thực hiện I/O mạng.

## 5. Vì sao phải dùng cả hai meter?

Timer và LongTaskTimer không thay thế nhau:

| Câu hỏi | LongTaskTimer | Timer |
|---|---|---|
| Có bao nhiêu tác vụ đang chạy? | Có, qua activeTasks() | Không |
| Tác vụ active đã chạy bao lâu? | Có, qua duration() và max() | Chưa có số đo cho đến khi stop |
| Đếm số lần đã hoàn tất? | Không phải mục đích chính | Có, qua count() |
| Tổng duration của các lần đã hoàn tất? | Không | Có, qua totalTime() |
| Phân tích latency theo outcome? | Không phù hợp làm meter chính | Có, qua tags và distribution |
| Thấy tác vụ bị treo khi chưa kết thúc? | Có | Không, vì Timer chưa được ghi |

LongTaskTimer cho biết trạng thái đang diễn ra. Timer cung cấp lịch sử các lần hoàn tất. Nếu chỉ dùng Timer, một tác vụ treo có thể chưa xuất hiện trong count hoặc percentile. Nếu chỉ dùng LongTaskTimer, bạn thiếu thống kê duration của các lần đã hoàn tất.

## 6. Viết test kiểm tra tác vụ trong lúc đang chạy

Test cần giữ tác vụ ở giữa quá trình thực thi để đọc LongTaskTimer trước khi hoàn tất. Dùng hai CountDownLatch:

- started báo rằng worker đã đi vào operation.
- release cho phép worker tiếp tục và kết thúc.

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class ReportExportServiceTest {

    @Test
    void observesActiveTaskAndRecordsTimerAfterCompletion() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ReportExportService service = new ReportExportService(registry);

            LongTaskTimer active = registry.get("report.export.active")
                    .tag("report_type", "monthly")
                    .longTaskTimer();

            Timer success = registry.get("report.export.duration")
                    .tags("report_type", "monthly", "outcome", "success")
                    .timer();

            Timer error = registry.get("report.export.duration")
                    .tags("report_type", "monthly", "outcome", "error")
                    .timer();

            Future<String> result = executor.submit(() ->
                    service.execute(() -> {
                        started.countDown();
                        if (!release.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                    "Test did not release the export task"
                            );
                        }
                        return "monthly-report.csv";
                    })
            );

            assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();

            // Tác vụ đã chạy nhưng chưa được cho phép kết thúc.
            assertThat(active.activeTasks()).isEqualTo(1);
            assertThat(active.duration(TimeUnit.MILLISECONDS))
                    .isGreaterThanOrEqualTo(0.0);

            // Timer chỉ ghi duration sau khi operation hoàn tất.
            assertThat(success.count()).isZero();
            assertThat(error.count()).isZero();

            release.countDown();

            assertThat(result.get(5, TimeUnit.SECONDS))
                    .isEqualTo("monthly-report.csv");

            assertThat(active.activeTasks()).isZero();
            assertThat(success.count()).isEqualTo(1);
            assertThat(error.count()).isZero();
            assertThat(success.totalTime(TimeUnit.MILLISECONDS))
                    .isGreaterThanOrEqualTo(0.0);
        } finally {
            release.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
            registry.close();
        }
    }
}
~~~

Test này không phụ thuộc vào một duration chính xác. Nó kiểm tra trạng thái trước và sau khi giải phóng worker:

| Thời điểm | activeTasks | Timer success count | Timer error count |
|---|---:|---:|---:|
| Trước khi submit | 0 | 0 | 0 |
| Worker đang chờ release | 1 | 0 | 0 |
| Worker đã hoàn tất thành công | 0 | 1 | 0 |

Latch làm thứ tự kiểm thử xác định. Không dùng Thread.sleep để hy vọng worker đã bắt đầu hoặc chưa kết thúc.

## 7. Kiểm tra nhánh lỗi

Khi operation ném exception, LongTaskTimer vẫn phải dừng và Timer error phải tăng count:

Thêm method dưới đây vào cùng class ReportExportServiceTest ở phần trước và đặt static import assertThatThrownBy ở đầu file test.

~~~java
@Test
void stopsActiveSampleAndRecordsErrorWhenOperationFails() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        ReportExportService service = new ReportExportService(registry);

        LongTaskTimer active = registry.get("report.export.active")
                .tag("report_type", "monthly")
                .longTaskTimer();

        Timer error = registry.get("report.export.duration")
                .tags("report_type", "monthly", "outcome", "error")
                .timer();

        assertThatThrownBy(() ->
                service.execute(() -> {
                    throw new IllegalStateException("Storage unavailable");
                })
        ).isInstanceOf(IllegalStateException.class)
         .hasMessage("Storage unavailable");

        assertThat(active.activeTasks()).isZero();
        assertThat(error.count()).isEqualTo(1);
    } finally {
        registry.close();
    }
}
~~~

Thêm static import:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

Exception vẫn đến caller. Instrumentation chỉ ghi duration và outcome; nó không biến lỗi thành kết quả thành công.

## 8. Quan sát nhiều tác vụ đồng thời

LongTaskTimer tổng hợp các tác vụ đang active cùng meter identity. Nếu hai lần export cùng report_type chạy đồng thời:

- activeTasks() bằng 2.
- duration() phản ánh tổng thời lượng đang chạy của các sample active.
- max() phản ánh tác vụ active lâu nhất.
- Khi một tác vụ kết thúc, activeTasks() giảm còn 1.
- Timer completed tăng count khi từng tác vụ kết thúc.

Mở rộng test ở phần 6 bằng fixed thread pool có hai worker và hai cặp latch riêng. Chỉ giải phóng worker thứ nhất, xác minh activeTasks() còn 1 và Timer count là 1; sau đó giải phóng worker thứ hai và xác minh activeTasks() về 0, Timer count là 2.

Không cộng active duration với completed Timer total time để suy ra thời gian wall-clock của hệ thống. Với hai tác vụ chạy đồng thời mỗi tác vụ 10 giây, tổng duration của Timer có thể gần 20 giây dù thời gian thực đã trôi qua chỉ khoảng 10 giây.

## 9. Hiển thị metrics khi tác vụ chưa hoàn tất

Nếu dùng Spring Boot Actuator và Prometheus registry, expose endpoint Prometheus trong cấu hình ứng dụng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Khi một tác vụ export đang chờ, gọi endpoint scrape và tìm meter report.export.active. Các series cụ thể phụ thuộc naming convention và phiên bản exporter; thường LongTaskTimer xuất số tác vụ active và duration của các tác vụ đang chạy.

Sau khi worker hoàn tất:

- Số tác vụ active trở về 0.
- Thời lượng active không còn được báo cáo như một tác vụ đang chạy.
- Timer report.export.duration có count và total time của lần hoàn tất.

Đừng giả định tên series backend nếu chưa kiểm tra scrape output. Hãy dùng endpoint thực tế để xác nhận tên metric và tag.

## 10. Diễn giải hai meter trên dashboard

Tạo hai khu vực riêng:

**Tác vụ đang chạy**

- Số tác vụ export active.
- Tổng duration của các tác vụ active.
- Duration lớn nhất trong số tác vụ active.

**Tác vụ đã hoàn tất**

- Số lần export hoàn tất theo outcome.
- Average duration theo outcome.
- p95/p99 nếu đã bật histogram hoặc percentile phù hợp.
- Tỷ lệ lỗi trong một cửa sổ thời gian.

Ví dụ truy vấn PromQL cho Timer nếu exporter đặt tên theo quy ước Prometheus:

~~~promql
sum by (outcome) (
  rate(report_export_duration_seconds_count[5m])
)
~~~

Average duration:

~~~promql
sum by (outcome) (
  rate(report_export_duration_seconds_sum[5m])
)
/
sum by (outcome) (
  rate(report_export_duration_seconds_count[5m])
)
~~~

Tên metric có thể khác tùy exporter và naming convention. Hãy thay bằng tên quan sát được trong scrape output.

## 11. Phân biệt thời gian active và duration hoàn tất

Hai giá trị có thể khác nhau vì ranh giới đo có thể khác nhau:

- LongTaskTimer bắt đầu khi worker bắt đầu xử lý.
- Timer.Sample trong ví dụ bắt đầu ngay trước khi gọi operation.

Trong ví dụ này hai sample bắt đầu gần như cùng thời điểm. Trong ứng dụng thực tế, hãy quyết định rõ muốn đo từ lúc nhận yêu cầu, lúc đưa vào queue hay lúc worker thực sự bắt đầu.

Nếu mục tiêu là đo thời gian chờ queue cộng với thời gian xử lý, bắt đầu cả hai sample trước khi submit. Nếu mục tiêu là đo worker execution, bắt đầu LongTaskTimer bên trong worker. Không so sánh hai meter nếu chúng dùng hai ranh giới khác nhau mà không ghi rõ trong tên hoặc description.

## 12. Tránh dừng LongTaskTimer quá sớm trong code bất đồng bộ

Một lỗi phổ biến là bắt đầu LongTaskTimer trước khi submit future rồi dừng ngay khi phương thức trả về:

~~~java
LongTaskTimer.Sample sample = activeTimer.start();
CompletableFuture<Result> future = client.callAsync();
sample.stop(); // Sai nếu muốn đo thời gian công việc async thực sự chạy
return future;
~~~

Đoạn code trên chỉ đo thời gian submit request. Nếu muốn theo dõi toàn bộ công việc async, dừng sample khi future hoàn tất:

~~~java
LongTaskTimer.Sample active = activeTimer.start();
Timer.Sample completed = Timer.start(registry);

CompletableFuture<Result> future;
try {
    future = client.callAsync();
} catch (RuntimeException | Error error) {
    active.stop();
    completed.stop(errorTimer);
    throw error;
}

return future.whenComplete((result, error) -> {
    try {
        active.stop();
    } finally {
        completed.stop(error == null ? successTimer : errorTimer);
    }
});
~~~

Trong ứng dụng thật, cần phân loại CancellationException riêng nếu cancellation có ý nghĩa vận hành. Cũng cần xác định future nào đại diện cho công việc cần đo, vì hủy một dependent future không tự động bảo đảm future upstream hoặc worker đã dừng.

Nếu callback hoàn tất chạy trên event-loop, chỉ thực hiện thao tác stop metrics nhanh; không chạy xử lý blocking trong callback.

## 13. Kiểm soát cardinality

Tag outcome phải là tập giá trị hữu hạn. Không tạo Timer riêng cho từng report ID:

~~~java
// Không nên: mỗi reportId có thể tạo một meter mới.
registry.timer(
        "report.export.duration",
        "report_id", reportId
);
~~~

Dùng tag phân loại ổn định:

~~~java
registry.timer(
        "report.export.duration",
        "report_type", "monthly",
        "outcome", "success"
);
~~~

Nếu cần điều tra một lần export cụ thể, ghi report ID trong log có cấu trúc hoặc trace attribute. Metrics nên dùng để tổng hợp.

## 14. Các lỗi thường gặp

**Chỉ dùng Timer cho tác vụ dài.** Timer chỉ ghi duration khi sample dừng; tác vụ đang treo chưa có count hoặc duration hoàn tất. Dùng thêm LongTaskTimer.

**Chỉ dùng LongTaskTimer.** Khi tác vụ kết thúc, thông tin active biến mất. Dùng Timer để lưu thống kê các lần hoàn tất.

**Dừng LongTaskTimer sau khi submit async.** Khi đó chỉ đo thời gian submit, không đo thời gian công việc. Dừng trong callback hoàn tất.

**Không dừng sample trong finally.** Exception có thể khiến active task tồn tại mãi và Timer không được ghi. Dừng cả hai sample trong finally.

**Dùng một sample chung cho nhiều task.** Mỗi lần thực thi phải có LongTaskTimer.Sample và Timer.Sample riêng.

**Gắn report ID vào tag.** Tag động tạo cardinality cao. Chỉ dùng report_type và outcome có tập giá trị hữu hạn.

**Cộng active duration với completed duration.** Đây là hai tập thời gian khác nhau; khi có concurrency, tổng duration có thể lớn hơn wall-clock time.

**Dùng Thread.sleep trong test.** Dùng CountDownLatch để điều khiển thời điểm bắt đầu và kết thúc.

**Đóng registry khi worker còn chạy.** Giải phóng worker và chờ Future hoàn tất trước khi đóng registry.

## 15. Bài tập mở rộng

Sau khi test cơ bản chạy thành công, thực hiện thêm:

1. Thêm tag task_type với hai giá trị monthly và daily.
2. Thêm outcome cancelled nếu service hỗ trợ hủy.
3. Chạy hai tác vụ song song và kiểm tra activeTasks() lần lượt là 2, 1, 0.
4. Thêm timeout cho tác vụ và phân biệt timeout với lỗi thông thường.
5. Bật histogram cho completed Timer và kiểm tra cấu hình bucket ở scrape output.
6. Expose metrics qua Actuator và xác minh series của LongTaskTimer khi tác vụ còn active.
7. Tạo dashboard có một panel active task và một panel completed duration.
8. Thử mô phỏng một tác vụ không bao giờ kết thúc; xác định cơ chế timeout hoặc cancellation để tránh active task bị giữ vô hạn.

## 16. Tiêu chí hoàn thành

Bài thực hành được xem là hoàn thành khi:

- [ ] LongTaskTimer được đăng ký với tên và tag ổn định.
- [ ] Timer được đăng ký cho outcome success và error.
- [ ] Mỗi lần chạy tạo một LongTaskTimer.Sample riêng.
- [ ] Mỗi lần chạy tạo một Timer.Sample riêng.
- [ ] Khi tác vụ bị giữ ở trạng thái active, activeTasks() bằng 1.
- [ ] Khi tác vụ còn chạy, Timer count vẫn bằng 0.
- [ ] Khi tác vụ thành công, activeTasks() trở về 0 và Timer success count tăng 1.
- [ ] Khi tác vụ lỗi, activeTasks() trở về 0 và Timer error count tăng 1.
- [ ] Exception nghiệp vụ vẫn được truyền đến caller.
- [ ] Test dùng latch hoặc cơ chế đồng bộ xác định, không dựa vào sleep.
- [ ] Tags không chứa ID hoặc giá trị không giới hạn.
- [ ] Đã xác minh raw metrics hoặc endpoint scrape nếu có exporter.

## 17. Kết luận

LongTaskTimer và Timer bổ sung cho nhau khi đo tác vụ dài. LongTaskTimer cung cấp góc nhìn tức thời về các công việc còn active; Timer ghi nhận duration sau khi từng lần thực thi hoàn tất. Bắt đầu cả hai sample tại đúng ranh giới cần đo và dừng trong finally giúp bao phủ cả thành công lẫn lỗi.

Trong bài lab, CountDownLatch giữ worker ở trạng thái active để test quan sát LongTaskTimer trước khi hoàn tất. Sau khi giải phóng worker, active task count trở về 0 và Timer count tăng đúng một lần. Khi chuyển sang bất đồng bộ, hãy dừng sample trong callback hoàn tất thay vì ngay sau khi submit. Giữ tag có cardinality thấp để metrics phản ánh được trạng thái vận hành mà không tạo quá nhiều time series.

## Tài liệu tham khảo

- [Micrometer – Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer – Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Java – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
