# Nhiều tác vụ đồng thời dùng chung một LongTaskTimer

Micrometer LongTaskTimer được thiết kế để quan sát những thao tác có thể chạy lâu và cần biết chúng vẫn đang hoạt động trong lúc hệ thống giám sát lấy mẫu. Khi nhiều tác vụ cùng loại chạy đồng thời, ứng dụng có thể đăng ký một LongTaskTimer dùng chung và gọi start() riêng cho từng lần thực thi.

Mỗi lần start() trả về một Sample độc lập. Sample đó đại diện cho một lần chạy cụ thể và phải được stop() khi chính lần chạy đó kết thúc. Nhờ vậy, một meter có thể theo dõi nhiều tác vụ đồng thời mà không cần tạo meter riêng cho từng task, cũng không cần đưa task ID vào tag.

## 1. LongTaskTimer đo điều gì?

Timer thông thường ghi nhận thời lượng khi thao tác hoàn tất. Nếu một request chạy trong 30 giây nhưng chưa kết thúc, Timer chưa ghi nhận lần thực thi đó cho đến khi nó hoàn tất.

LongTaskTimer cung cấp góc nhìn khác: nó theo dõi các tác vụ đang hoạt động và thời lượng của chúng ngay trong khi tác vụ chưa kết thúc. Các thông tin thường được quan tâm gồm:

- Số tác vụ hiện đang hoạt động.
- Tổng thời gian đã trôi qua của các tác vụ đang hoạt động.
- Thời gian của tác vụ đang hoạt động lâu nhất.

Ví dụ, một service tạo báo cáo có thể chạy nhiều báo cáo cùng lúc. Trong khi chúng đang chạy, dashboard cần biết hiện có bao nhiêu báo cáo hoạt động và báo cáo nào đã chạy quá lâu. LongTaskTimer phù hợp với câu hỏi này.

LongTaskTimer không lưu lịch sử đầy đủ của từng task đã hoàn tất. Khi Sample được stop(), task đó không còn thuộc nhóm active task. Nếu cần thống kê phân phối thời gian của các lần hoàn tất, hãy ghi thêm Timer thông thường.

## 2. Một LongTaskTimer có thể theo dõi nhiều tác vụ

LongTaskTimer là meter được đăng ký vào MeterRegistry. Nó có thể nhận nhiều lần start() cùng lúc. Mỗi lần gọi tạo một Sample riêng, cho phép các tác vụ bắt đầu và kết thúc độc lập.

Có thể hình dung:

~~~text
                    Một LongTaskTimer đã đăng ký
                               |
                +--------------+--------------+
                |              |              |
             start()         start()         start()
                |              |              |
             Sample A       Sample B       Sample C
                |              |              |
             Task A         Task B         Task C
                |              |              |
             stop()         stop()         stop()
                |              |              |
                +--------------+--------------+
                               |
                    active task count giảm
~~~

Ví dụ:

~~~java
LongTaskTimer reportTimer = LongTaskTimer.builder("reports.execution")
    .description("Các tác vụ tạo báo cáo đang chạy")
    .register(registry);

LongTaskTimer.Sample first = reportTimer.start();
LongTaskTimer.Sample second = reportTimer.start();

try {
    // Hai tác vụ có thể tiếp tục chạy đồng thời.
} finally {
    first.stop();
    second.stop();
}
~~~

Hai Sample đại diện cho hai lần thực thi khác nhau. Khi một Sample dừng, Sample còn lại vẫn tiếp tục được theo dõi. Không cần đăng ký meter mới cho mỗi lần chạy.

### Phân biệt meter dùng chung và Sample riêng

| Đối tượng | Vòng đời | Trách nhiệm |
|---|---|---|
| LongTaskTimer | Thường theo vòng đời ứng dụng hoặc bean | Định nghĩa meter và tập tag ổn định |
| Sample | Theo một lần thực thi | Bắt đầu và kết thúc phép đo của task đó |
| MeterRegistry | Theo vòng đời cấu hình metrics | Quản lý meter và xuất số liệu |

Đây là nguyên tắc quan trọng khi thiết kế instrumentation đồng thời: dùng chung meter, giữ Sample riêng cho từng lần thực thi.

Không lưu Sample đang chạy vào một field dùng chung rồi để mọi task cùng stop field đó. Một task có thể dừng Sample của task khác, khiến active count và duration bị sai. Mỗi lần gọi phải giữ Sample cục bộ trong stack hoặc trong context riêng của chính tác vụ.

## 3. Đăng ký meter một lần, gọi start() cho từng lần chạy

Một lớp metrics có thể giữ một LongTaskTimer làm field và cung cấp phương thức bao quanh công việc:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class ReportMetrics {
    private final LongTaskTimer reportTimer;

    public ReportMetrics(MeterRegistry registry) {
        this.reportTimer = LongTaskTimer.builder("reports.execution")
            .description("Các tác vụ tạo báo cáo đang chạy")
            .tag("operation", "generate")
            .register(registry);
    }

    public <T> T track(Supplier<T> operation) {
        LongTaskTimer.Sample sample = reportTimer.start();
        try {
            return operation.get();
        } finally {
            sample.stop();
        }
    }
}
~~~

Mỗi lần gọi track():

1. Lấy một Sample mới từ cùng LongTaskTimer.
2. Thực thi công việc.
3. Dừng đúng Sample đó trong finally.
4. Trả lại kết quả hoặc truyền tiếp exception của công việc.

Cấu trúc try/finally bảo đảm Sample được dừng dù tác vụ kết thúc bình thường hay ném exception. Nếu không dừng Sample, meter sẽ tiếp tục xem task đó là đang hoạt động và duration vẫn tăng trong những lần scrape tiếp theo.

Với thao tác không trả về kết quả, có thể cung cấp overload nhận Runnable:

~~~java
public void track(Runnable operation) {
    LongTaskTimer.Sample sample = reportTimer.start();
    try {
        operation.run();
    } finally {
        sample.stop();
    }
}
~~~

Hai overload này là các phương thức tiện ích của lớp ứng dụng. Điều quan trọng là Sample được tạo trong từng lời gọi và chỉ được dừng trong chính lời gọi đó.

## 4. Nhiều thread cùng gọi một meter

LongTaskTimer được thiết kế để ghi nhận nhiều tác vụ đang hoạt động. Nhiều thread có thể cùng gọi start() trên cùng meter và nhận các Sample riêng.

Ví dụ có ba worker:

~~~java
public void generateReport(ReportRequest request) {
    LongTaskTimer.Sample sample = reportTimer.start();
    try {
        reportGenerator.generate(request);
    } finally {
        sample.stop();
    }
}
~~~

Nếu ba thread cùng thực thi generateReport():

- LongTaskTimer chỉ được đăng ký một lần.
- Mỗi thread có một Sample riêng.
- activeTasks() phản ánh số Sample đang hoạt động.
- Khi một thread kết thúc, chỉ Sample của thread đó bị dừng.
- Các task còn lại vẫn được tính trong active duration.

Không cần synchronized toàn bộ phần công việc chỉ để cập nhật LongTaskTimer. Registry và implementation của meter quản lý việc ghi nhận đồng thời. Tuy nhiên, trạng thái nghiệp vụ mà task sử dụng vẫn cần cơ chế đồng bộ riêng nếu có chia sẻ dữ liệu mutable.

### Tránh tạo meter theo từng task

Không làm như sau:

~~~java
public void generateReport(String reportId) {
    LongTaskTimer timer = LongTaskTimer.builder("reports.execution")
        .tag("report_id", reportId)
        .register(registry);

    LongTaskTimer.Sample sample = timer.start();
    try {
        reportGenerator.generate(reportId);
    } finally {
        sample.stop();
    }
}
~~~

Cách này đưa report ID vào tag và tạo time series theo từng báo cáo. Khi số báo cáo tăng, cardinality tăng theo. Ngoài ra, meter được đăng ký lặp lại trong đường xử lý nghiệp vụ.

Hãy đăng ký meter với tag có tập giá trị hữu hạn, chẳng hạn loại công việc hoặc nhóm worker:

~~~java
LongTaskTimer.builder("reports.execution")
    .tag("report_type", "monthly")
    .register(registry);
~~~

Nếu cần phân biệt nhiều nhóm tác vụ, có thể dùng nhiều giá trị tag ổn định như monthly, daily hoặc export. Không dùng ID duy nhất của từng lần chạy làm tag.

## 5. Tích hợp với Executor và tác vụ bất đồng bộ

Khi dùng ExecutorService, cần xác định chính xác thời điểm bắt đầu đo. Nếu muốn đo thời gian task thực sự được thực thi, hãy gọi start() bên trong Runnable hoặc Callable, sau khi worker bắt đầu chạy.

~~~java
public Future<Report> submitReport(ReportRequest request) {
    return executor.submit(() -> {
        LongTaskTimer.Sample sample = reportTimer.start();
        try {
            return reportGenerator.generate(request);
        } finally {
            sample.stop();
        }
    });
}
~~~

Cách này chỉ tính thời gian thực thi trên worker. Khoảng thời gian task nằm trong queue trước khi worker nhận nó không nằm trong LongTaskTimer.

Nếu muốn quan sát cả thời gian chờ trong queue và thời gian thực thi, hãy đo riêng hai giai đoạn:

- Thời gian chờ: ghi nhận từ lúc submit đến lúc worker bắt đầu bằng Timer hoặc một metric phù hợp.
- Thời gian thực thi dài: dùng LongTaskTimer từ lúc worker bắt đầu đến lúc hoàn tất.

Không gộp hai đại lượng khác nhau vào một meter nếu dashboard cần phân biệt queue saturation với thời gian xử lý thực tế.

### Task bị từ chối trước khi chạy

Nếu executor từ chối task trước khi Runnable bắt đầu, Sample chưa được tạo nên không có active task nào cần stop. Nếu ứng dụng tạo Sample ở thời điểm submit, task bị từ chối có thể khiến Sample không bao giờ được dừng.

Đây là một lý do quan trọng để bắt đầu đo tại điểm task thực sự được thực thi khi mục tiêu là theo dõi active work.

### Task bị hủy khi đang chạy

Nếu task đang chạy bị interrupt hoặc hủy, phần xử lý cần thoát qua finally để Sample được stop. Không dựa vào việc Future.cancel() tự động dừng Sample vì Future không biết Sample nào đang được dùng.

~~~java
Future<?> future = executor.submit(() -> {
    LongTaskTimer.Sample sample = reportTimer.start();
    try {
        reportGenerator.generate(request);
    } finally {
        sample.stop();
    }
});

// Nếu hủy task đang chạy, code trong task cần phản ứng với interrupt
// và đi qua finally để đóng Sample.
future.cancel(true);
~~~

Nếu task bỏ qua interrupt và tiếp tục chạy, Sample vẫn còn active cho đến khi phương thức thực sự kết thúc. Điều này phản ánh đúng thực tế: tác vụ vẫn đang tiêu thụ tài nguyên.

## 6. Theo dõi nhiều loại tác vụ bằng tag có kiểm soát

Một LongTaskTimer có thể đo tất cả task cùng loại. Nếu cần phân nhóm theo loại công việc, đăng ký meter riêng theo một tập tag nhỏ:

~~~java
private final LongTaskTimer monthlyReportTimer;
private final LongTaskTimer dailyReportTimer;

public ReportMetrics(MeterRegistry registry) {
    monthlyReportTimer = LongTaskTimer.builder("reports.execution")
        .tag("report_type", "monthly")
        .register(registry);

    dailyReportTimer = LongTaskTimer.builder("reports.execution")
        .tag("report_type", "daily")
        .register(registry);
}
~~~

Mỗi meter có định danh khác nhau do tag value khác nhau. Các lần chạy cùng loại dùng chung meter tương ứng nhưng vẫn có Sample riêng.

Có thể chọn timer theo enum hoặc map có tập key cố định. Tránh tạo meter theo chuỗi đầu vào tùy ý:

~~~java
private LongTaskTimer timerFor(ReportType type) {
    return switch (type) {
        case DAILY -> dailyReportTimer;
        case MONTHLY -> monthlyReportTimer;
    };
}
~~~

Tag có thể dùng cho operation, worker pool hoặc loại tác vụ khi tập giá trị nhỏ và ổn định. Không dùng task ID, user ID, file name hoặc nội dung request.

## 7. Đọc active count và active duration

LongTaskTimer cung cấp các giá trị để quan sát tác vụ đang chạy:

~~~java
long active = reportTimer.activeTasks();
double totalActiveSeconds =
    reportTimer.duration(TimeUnit.SECONDS);
double longestActiveSeconds =
    reportTimer.max(TimeUnit.SECONDS);
~~~

Các giá trị này có ý nghĩa khác nhau:

- activeTasks(): số tác vụ đang hoạt động tại thời điểm đọc.
- duration(unit): tổng thời lượng đã trôi qua của các tác vụ hiện đang hoạt động.
- max(unit): thời lượng của tác vụ đang hoạt động lâu nhất.

Giả sử có ba tác vụ đang hoạt động lần lượt 10, 20 và 30 giây:

| Số đo | Giá trị |
|---|---:|
| Active tasks | 3 |
| Tổng active duration | 60 giây |
| Longest active duration | 30 giây |

Khi tác vụ 30 giây kết thúc, active count còn 2, tổng active duration chỉ còn tổng thời gian hiện tại của hai task còn lại, và max phản ánh task đang hoạt động lâu nhất trong nhóm còn lại.

Các giá trị này không phải tổng thời lượng của mọi task kể từ khi ứng dụng khởi động. Sample đã stop không còn nằm trong active duration. Nếu cần thống kê lịch sử thời lượng hoàn tất, hãy kết hợp Timer thông thường.

## 8. Kết hợp LongTaskTimer và Timer

LongTaskTimer trả lời câu hỏi “hiện tại có tác vụ nào còn chạy và đã chạy bao lâu?”. Timer trả lời câu hỏi “các lần thực thi đã hoàn tất mất bao lâu?”.

Có thể ghi cả hai trên cùng một thao tác:

~~~java
private final MeterRegistry registry;
private final LongTaskTimer activeReportTimer;
private final Timer completedReportTimer;

public ReportMetrics(MeterRegistry registry) {
    this.registry = registry;
    activeReportTimer = LongTaskTimer.builder("reports.execution.active")
        .description("Các lần tạo báo cáo đang chạy")
        .register(registry);

    completedReportTimer = Timer.builder("reports.execution.duration")
        .description("Thời gian hoàn tất tạo báo cáo")
        .register(registry);
}

public Report generate(ReportRequest request) {
    LongTaskTimer.Sample activeSample = activeReportTimer.start();
    Timer.Sample completedSample = Timer.start(this.registry);

    try {
        return reportGenerator.generate(request);
    } finally {
        activeSample.stop();
        completedSample.stop(completedReportTimer);
    }
}
~~~

Trong ví dụ này, registry cần được giữ trong field để tạo Timer.Sample. Có thể thay cách tạo Timer.Sample bằng Timer.record(...) nếu không cần dùng cùng một ranh giới đo cho nhiều nhãn động.

Khi dùng cả hai, hãy xác định rõ:

- LongTaskTimer dùng để cảnh báo task đang chạy quá lâu hoặc có quá nhiều task cùng hoạt động.
- Timer dùng để phân tích thời gian hoàn tất, throughput và histogram/percentile nếu được cấu hình.
- Hai metric có tên riêng và mô tả riêng để tránh dashboard diễn giải nhầm.

Nếu chỉ quan tâm tác vụ ngắn và phân phối latency sau khi hoàn tất, Timer thường đủ. LongTaskTimer đặc biệt hữu ích cho công việc dài, streaming, batch, migration, export hoặc thao tác có thể kéo dài nhiều phút.

## 9. Kiểm thử nhiều Sample đồng thời

Một kiểm thử quan trọng là chứng minh hai task có thể cùng hoạt động trên một LongTaskTimer và dừng độc lập. Có thể dùng CountDownLatch để điều khiển thứ tự, tránh phụ thuộc vào sleep.

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConcurrentLongTaskTimerTest {

    @Test
    void tracksTwoConcurrentTasksIndependently() throws Exception {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            LongTaskTimer timer = LongTaskTimer.builder("reports.execution")
                .register(registry);

            ExecutorService executor = Executors.newFixedThreadPool(2);
            CountDownLatch started = new CountDownLatch(2);
            CountDownLatch release = new CountDownLatch(1);

            try {
                Runnable task = () -> {
                    LongTaskTimer.Sample sample = timer.start();
                    try {
                        started.countDown();
                        if (!release.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("test timed out");
                        }
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(exception);
                    } finally {
                        sample.stop();
                    }
                };

                Future<?> first = executor.submit(task);
                Future<?> second = executor.submit(task);

                assertTrue(started.await(5, TimeUnit.SECONDS));
                assertEquals(2, timer.activeTasks());

                release.countDown();
                first.get(5, TimeUnit.SECONDS);
                second.get(5, TimeUnit.SECONDS);

                assertEquals(0, timer.activeTasks());
            } finally {
                release.countDown();
                executor.shutdownNow();
            }
        }
    }
}
~~~

Kiểm thử này xác minh:

1. Hai task gọi start() trên cùng một meter.
2. Khi cả hai đã bắt đầu, activeTasks() bằng 2.
3. Khi mở latch, mỗi task stop Sample riêng của nó.
4. Sau khi cả hai hoàn tất, activeTasks() trở về 0.

Trong test thật, nên kiểm thử thêm nhánh exception, interruption và cancellation. Mỗi đường kết thúc phải đi qua finally để không để lại Sample đang hoạt động.

## 10. Các lỗi thường gặp

- **Tạo LongTaskTimer mới cho từng task:** làm tăng số meter và có thể gây cardinality cao. Đăng ký một meter cho mỗi loại tác vụ có tag ổn định.
- **Dùng chung một Sample giữa nhiều task:** một task có thể stop nhầm phép đo của task khác. Mỗi lần start() cần giữ Sample riêng.
- **Không gọi stop():** active task bị treo trong metrics và duration tiếp tục tăng.
- **Gọi stop() nhiều lần hoặc từ nhiều callback:** làm vòng đời đo khó kiểm soát; chỉ một nơi chịu trách nhiệm kết thúc Sample.
- **Start khi submit thay vì lúc thực thi:** số liệu bao gồm cả thời gian chờ queue dù mục tiêu chỉ là thời gian thực thi.
- **Cho rằng cancel() tự stop Sample:** task phải thoát qua finally hoặc callback kết thúc có kiểm soát.
- **Dùng LongTaskTimer để thay Timer:** LongTaskTimer không cung cấp lịch sử đầy đủ của các task đã hoàn tất.
- **Gắn task ID vào tag:** tạo time series theo từng task và làm cardinality tăng.
- **Dùng chung meter cho các loại công việc không cùng ngữ nghĩa:** dashboard khó giải thích; dùng tag có tập giá trị hữu hạn hoặc meter riêng.
- **Chỉ kiểm thử một task:** bỏ sót lỗi chia sẻ Sample hoặc xử lý concurrency.

## 11. Checklist triển khai

- [ ] LongTaskTimer được đăng ký một lần trong registry.
- [ ] Mọi lần thực thi gọi start() để tạo Sample độc lập.
- [ ] Sample được giữ riêng theo từng task hoặc invocation.
- [ ] Sample được stop() trong finally trên mọi đường kết thúc.
- [ ] Tác vụ bất đồng bộ bắt đầu đo tại đúng thời điểm thực thi.
- [ ] Cancellation và interruption không làm rò rỉ Sample.
- [ ] Tag chỉ dùng các chiều có cardinality thấp và ổn định.
- [ ] Không tạo meter theo task ID hoặc dữ liệu request.
- [ ] Dùng Timer riêng nếu cần lịch sử và phân phối thời gian hoàn tất.
- [ ] Kiểm thử nhiều task cùng chạy và kết thúc độc lập.
- [ ] Dashboard phân biệt active count, active duration và completed duration.

Khi nhiều tác vụ cùng loại chạy đồng thời, hãy dùng một LongTaskTimer đã đăng ký chung và tạo Sample riêng cho từng lần thực thi. Mỗi Sample phải được dừng đúng lúc, kể cả khi task lỗi hoặc bị hủy. Cách tổ chức này giữ số meter ổn định mà vẫn cho phép quan sát số lượng và thời gian của các tác vụ đang hoạt động.

