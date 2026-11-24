# LongTaskTimer theo dõi thời gian của tác vụ đang thực thi

Trong ứng dụng Java, có những thao tác kéo dài đủ lâu để người vận hành cần quan sát ngay khi chúng vẫn đang chạy: tạo báo cáo lớn, nhập dữ liệu, đồng bộ với hệ thống bên ngoài, xử lý batch hoặc chạy một workflow nhiều bước. Nếu chỉ dùng Timer, số liệu thời gian của thao tác thường chỉ được ghi nhận khi thao tác kết thúc. Một tác vụ đang bị treo hoặc chạy quá lâu có thể chưa xuất hiện trong thống kê thời gian hoàn tất.

Micrometer cung cấp LongTaskTimer để theo dõi các tác vụ đang thực thi. Mỗi lần bắt đầu tạo một sample riêng; sample được dừng khi tác vụ thực sự kết thúc. Trong thời gian sample còn hoạt động, registry có thể đọc số tác vụ đang chạy và thời lượng đã trôi qua. Điều này giúp phát hiện tác vụ bị kéo dài trước khi chúng hoàn tất.

## 1. LongTaskTimer giải quyết câu hỏi nào?

LongTaskTimer phù hợp với câu hỏi về công việc đang diễn ra:

- Hiện có bao nhiêu lần tạo báo cáo đang chạy?
- Tác vụ đồng bộ lâu nhất hiện đã chạy bao nhiêu giây?
- Tổng thời gian đã trôi qua của tất cả tác vụ import còn hoạt động là bao nhiêu?
- Có workflow nào đang chạy vượt quá thời gian dự kiến?
- Một nhóm job có đang bị nghẽn bởi những tác vụ chưa kết thúc không?

Điểm quan trọng là LongTaskTimer quan sát thời lượng của các sample đang hoạt động. Khi một sample được dừng, nó không còn đóng góp vào các giá trị đang chạy.

## 2. Phân biệt LongTaskTimer với Timer

Hai meter đều liên quan đến thời gian nhưng trả lời những câu hỏi khác nhau:

| Tiêu chí | Timer | LongTaskTimer |
| --- | --- | --- |
| Đối tượng quan sát | Những lần thực thi đã được ghi nhận, thường sau khi hoàn tất. | Những lần thực thi hiện vẫn đang hoạt động. |
| Thời điểm có số liệu thời lượng | Sau khi thao tác được ghi nhận hoặc kết thúc. | Trong khi thao tác vẫn đang chạy. |
| Câu hỏi chính | Một thao tác thường mất bao lâu? | Có bao nhiêu thao tác đang chạy và chúng đã chạy bao lâu? |
| Dữ liệu hữu ích | Count, tổng thời lượng, phân bố hoặc percentile tùy registry/cấu hình. | Số sample đang hoạt động, tổng thời lượng hiện tại của các sample đang chạy và thời lượng lớn nhất trong số đó. |
| Khi sample kết thúc | Thời lượng hoàn tất được ghi vào Timer. | Sample được loại khỏi tập tác vụ đang hoạt động. |

Ví dụ, một báo cáo mất 12 phút mới hoàn tất. Trong 12 phút đó, dashboard dựa trên Timer có thể chưa có bản ghi thời lượng của lần chạy này. LongTaskTimer có thể cho thấy báo cáo vẫn đang chạy và thời lượng của nó đang tăng.

Hai meter có thể được dùng cùng nhau. LongTaskTimer giúp phát hiện tác vụ đang chạy quá lâu; Timer giúp phân tích độ trễ của những lần đã hoàn tất. Nếu chỉ quan tâm tác vụ đang chạy, LongTaskTimer có thể đủ. Nếu cần cả cảnh báo tác vụ đang bị treo lẫn phân bố thời gian hoàn tất, hãy ghi nhận cả hai theo cùng một định nghĩa thao tác.

## 3. Mô hình Sample của LongTaskTimer

Một LongTaskTimer được đăng ký trong MeterRegistry. Mỗi lần một tác vụ bắt đầu, gọi start() để nhận một LongTaskTimer.Sample. Sample đại diện cho đúng một lần thực thi.

Các thao tác quan trọng:

- start() bắt đầu theo dõi một lần thực thi và trả về Sample.
- Sample.stop() kết thúc lần theo dõi đó. Sample không còn được tính là tác vụ đang hoạt động.
- activeTasks() trả về số sample hiện đang hoạt động.
- duration(TimeUnit) trả về tổng thời lượng đã trôi qua của các sample hiện đang hoạt động, theo đơn vị được yêu cầu.
- max(TimeUnit) trả về thời lượng lớn nhất trong các sample hiện đang hoạt động, theo đơn vị được yêu cầu.

Các giá trị duration và max mô tả tập tác vụ đang chạy tại thời điểm đọc. Chúng không phải tổng thời lượng lịch sử của mọi tác vụ đã từng hoàn tất. Khi một tác vụ kết thúc, nó bị loại khỏi tập đang hoạt động nên activeTasks, duration và max có thể giảm.

## 4. Đăng ký LongTaskTimer

Ví dụ đăng ký một meter cho các lần tạo báo cáo định kỳ:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ReportMetrics {

    private final LongTaskTimer reportGeneration;

    public ReportMetrics(MeterRegistry registry) {
        this.reportGeneration = LongTaskTimer.builder("reports.generation")
                .description("Execution time of report generation tasks currently running")
                .tag("job_type", "monthly")
                .register(registry);
    }

    public LongTaskTimer reportGeneration() {
        return reportGeneration;
    }
}
~~~

Meter được đăng ký một lần khi Spring tạo bean. Tag job_type=monthly là giá trị cố định, có miền giá trị được kiểm soát. Nếu ứng dụng có nhiều loại job, hãy đăng ký meter theo một danh mục loại job hữu hạn hoặc dùng một meter với tag tương ứng.

Không đăng ký LongTaskTimer mới cho mỗi lần chạy. Meter đại diện cho một loại hoạt động; Sample đại diện cho một lần thực thi cụ thể.

## 5. Bắt đầu và kết thúc Sample đúng vòng đời

Khi thao tác bắt đầu, tạo Sample. Dừng Sample trong khối finally để bảo đảm sample được kết thúc cả khi thao tác thành công lẫn khi phát sinh exception:

~~~java
import io.micrometer.core.instrument.LongTaskTimer;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportMetrics metrics;

    public ReportService(ReportMetrics metrics) {
        this.metrics = metrics;
    }

    public Report generateMonthlyReport() {
        LongTaskTimer.Sample sample = metrics.reportGeneration().start();
        try {
            return generateReportData();
        } finally {
            sample.stop();
        }
    }

    private Report generateReportData() {
        // Perform the long-running report generation.
        return new Report();
    }
}
~~~

Điểm bắt đầu phải tương ứng với thời điểm công việc thực sự bắt đầu. Nếu tạo Sample trước khi một job nằm trong hàng đợi nhiều phút, LongTaskTimer sẽ tính cả thời gian chờ đó. Nếu mục tiêu là đo thời gian thực thi, hãy gọi start() khi worker bắt đầu xử lý. Nếu cần theo dõi thời gian chờ, hãy đo riêng thời gian trong queue bằng một meter hoặc timestamp phù hợp.

Tương tự, chỉ gọi stop() khi công việc thực sự kết thúc. Với tác vụ bất đồng bộ, không dừng sample ngay sau khi submit tác vụ; sample phải được dừng trong phần xử lý hoàn tất của worker.

## 6. Theo dõi nhiều tác vụ đồng thời

Một LongTaskTimer có thể theo dõi nhiều sample đồng thời. Mỗi lần thực thi phải giữ Sample riêng:

~~~java
LongTaskTimer.Sample first = timer.start();
LongTaskTimer.Sample second = timer.start();

// Both samples are active at the same time.
// Stop each sample when its own task finishes.
first.stop();
second.stop();
~~~

Khi cả hai sample đang hoạt động, activeTasks() trả về 2. duration(TimeUnit.SECONDS) là tổng thời gian đã trôi qua của cả hai sample tại thời điểm đọc; max(TimeUnit.SECONDS) là thời lượng của sample đang chạy lâu nhất.

Không lưu một Sample duy nhất trong field dùng chung cho nhiều request hoặc nhiều job. Nếu các lần chạy ghi đè Sample của nhau, một tác vụ có thể không được dừng đúng cách và số liệu sẽ sai. Hãy giữ Sample trong biến cục bộ của lần thực thi hoặc trong context riêng gắn với tác vụ.

## 7. Xử lý tác vụ bất đồng bộ và hủy tác vụ

Với tác vụ chạy trên executor, Sample cần theo sát vòng đời thực thi bên trong worker. Ví dụ:

~~~java
public CompletableFuture<Report> generateAsync() {
    LongTaskTimer.Sample sample = metrics.reportGeneration().start();
    try {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return generateReportData();
            } finally {
                sample.stop();
            }
        }, executor);
    } catch (RuntimeException submissionFailure) {
        sample.stop();
        throw submissionFailure;
    }
}
~~~

Trong ví dụ, Sample được dừng sau khi phần việc trong executor hoàn tất. Nếu việc submit thất bại đồng bộ, khối catch cũng dừng Sample để tránh để lại tác vụ hoạt động giả.

Nếu hệ thống hỗ trợ hủy tác vụ, cần xác định chính xác thời điểm công việc thực sự dừng và gọi stop() một lần trong đường hoàn tất/hủy. Hủy một CompletableFuture không phải lúc nào cũng có nghĩa công việc nền đã dừng ngay; nếu worker vẫn tiếp tục chạy, không nên dừng Sample quá sớm. Có thể dùng một cơ chế hoàn tất tập trung để bảo đảm mọi đường success, failure, cancellation và submission rejection đều kết thúc Sample đúng một lần.

## 8. Diễn giải ba số đo đang hoạt động

Giả sử có ba báo cáo đang chạy với thời lượng lần lượt là 20, 35 và 50 giây:

| Số đo | Giá trị | Cách hiểu |
| --- | ---: | --- |
| activeTasks() | 3 | Có ba báo cáo đang chạy. |
| duration(SECONDS) | 105 | Tổng thời gian đã trôi qua của ba báo cáo đang hoạt động. |
| max(SECONDS) | 50 | Báo cáo chạy lâu nhất trong tập hiện tại đã chạy 50 giây. |

Nếu báo cáo 50 giây hoàn tất và Sample được dừng, số đo sẽ phản ánh hai báo cáo còn lại: activeTasks() còn 2, tổng thời lượng đang hoạt động còn khoảng 55 giây và max(SECONDS) còn khoảng 35 giây tại thời điểm đọc tiếp theo.

Đây là khác biệt quan trọng với số liệu lịch sử. LongTaskTimer không giữ lại 50 giây vừa hoàn tất trong duration hay max đang hoạt động. Muốn thống kê thời gian hoàn tất, hãy dùng Timer riêng.

## 9. Đặt tên và tag cho LongTaskTimer

Tên nên mô tả loại công việc đang được theo dõi, ví dụ:

| Tên meter | Ý nghĩa |
| --- | --- |
| reports.generation | Các lần tạo báo cáo đang chạy. |
| imports.execution | Các lần nhập dữ liệu đang thực thi. |
| sync.execution | Các lần đồng bộ đang hoạt động. |
| batch.processing | Các lần xử lý batch đang chạy. |
| workflow.execution | Các workflow hiện chưa hoàn tất. |

Tag nên là chiều phân nhóm ổn định, có tập giá trị nhỏ:

- job_type: monthly, daily, reconciliation.
- operation: full_sync, incremental_sync.
- queue: tên queue được cấu hình cố định.
- region: mã khu vực triển khai được quản lý.

Không dùng job_id, request_id, user_id, tên file, URL động hoặc thông tin khách hàng làm tag. Một tác vụ có thể tạo một Sample nhưng không nên tạo một tag-value mới cho từng lần chạy. Nếu cần điều tra một job cụ thể, hãy dùng log hoặc trace có định danh phù hợp.

## 10. Đọc LongTaskTimer trong hệ thống giám sát

LongTaskTimer có thể xuất ra những đại lượng về tác vụ đang hoạt động, thường gồm số sample đang chạy, tổng thời lượng hiện tại và thời lượng lớn nhất hiện tại. Tên metric, đơn vị và cách biểu diễn cụ thể phụ thuộc registry và phiên bản Micrometer.

Với Prometheus registry, hãy mở endpoint metrics của ứng dụng và kiểm tra tên thực tế trước khi viết truy vấn. Một số quy ước có thể biểu diễn các đại lượng này bằng hậu tố tương tự active_count, duration_sum và max; không nên giả định mọi phiên bản đều có cùng tên hoặc đơn vị.

Khi đã xác nhận tên metric, các câu hỏi truy vấn thường là:

- Bao nhiêu tác vụ đang hoạt động theo loại job?
- Tác vụ đang chạy lâu nhất hiện đã kéo dài bao lâu?
- Tổng thời lượng hiện tại của các tác vụ đang chạy theo service hoặc queue là bao nhiêu?
- Có tác vụ nào vượt ngưỡng thời gian vận hành cho phép không?

Nếu metric active count đã được xuất dưới tên reports_generation_active_count, có thể nhóm theo loại job:

~~~promql
sum by (job_type) (reports_generation_active_count)
~~~

Nếu metric max duration đã được xuất theo giây dưới tên reports_generation_max, có thể tìm giá trị lớn nhất theo loại job:

~~~promql
max by (job_type) (reports_generation_max)
~~~

Hai tên trên là ví dụ minh họa cho cách viết truy vấn; hãy thay bằng tên và đơn vị đọc được từ endpoint exposition của registry đang dùng.

Đối với cảnh báo, đặt ngưỡng dựa trên SLA hoặc thời gian vận hành kỳ vọng của loại tác vụ. Ví dụ, báo cáo thường hoàn tất trong 10 phút thì một tác vụ chạy hơn 30 phút có thể cần được điều tra. Ngưỡng phải dựa trên đặc tính công việc thực tế, không chọn tùy ý chỉ vì một số đo lớn.

## 11. Tần suất scrape và tác vụ ngắn

LongTaskTimer cung cấp số liệu trong khi tác vụ đang chạy, nhưng backend vẫn chỉ quan sát theo lịch scrape hoặc lịch thu thập. Nếu một tác vụ bắt đầu và kết thúc hoàn toàn giữa hai lần scrape, backend có thể không nhìn thấy sample đó.

Ví dụ, Prometheus scrape mỗi 15 giây trong khi một tác vụ chỉ chạy 3 giây. Tác vụ có thể bắt đầu sau lần scrape thứ nhất và kết thúc trước lần scrape kế tiếp. LongTaskTimer vẫn có ích cho tác vụ dài, nhưng không thay thế Timer để thống kê mọi lần thực thi ngắn.

Hãy chọn scrape interval phù hợp với thời gian tối thiểu cần phát hiện và năng lực của hệ thống giám sát. Nếu cần đếm tất cả lần chạy ngắn, dùng Counter; nếu cần thời lượng hoàn tất và phân bố độ trễ, dùng Timer.

## 12. Kiểm thử LongTaskTimer

Có thể dùng SimpleMeterRegistry để kiểm tra vòng đời Sample:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class LongTaskTimerTest {

    @Test
    void tracksOnlySamplesThatAreStillActive() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        LongTaskTimer timer = LongTaskTimer.builder("reports.generation")
                .register(registry);

        LongTaskTimer.Sample first = timer.start();
        LongTaskTimer.Sample second = timer.start();

        assertThat(timer.activeTasks()).isEqualTo(2);
        assertThat(timer.duration(TimeUnit.NANOSECONDS)).isGreaterThanOrEqualTo(0.0);

        first.stop();
        assertThat(timer.activeTasks()).isEqualTo(1);

        second.stop();
        assertThat(timer.activeTasks()).isZero();
    }
}
~~~

Bài kiểm thử xác minh hai Sample hoạt động độc lập và số tác vụ đang chạy giảm khi từng Sample được dừng. Kiểm thử tích hợp có thể xác minh registry xuất đúng các số đo và đơn vị mà hệ thống giám sát sẽ thu thập.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không gọi stop() khi tác vụ kết thúc | Sample vẫn được xem là đang hoạt động trong vòng đời tiến trình. | Dùng finally hoặc một cơ chế hoàn tất tập trung. |
| Dừng Sample ngay sau khi submit tác vụ nền | Thời gian thực thi thực tế không được theo dõi. | Dừng Sample bên trong worker khi công việc kết thúc. |
| Dùng một Sample chung cho nhiều lần chạy | Các lần chạy ghi đè hoặc dừng nhầm sample của nhau. | Mỗi lần thực thi giữ một Sample riêng. |
| Dùng LongTaskTimer cho mọi request ngắn | Tăng chi phí instrumentation mà không mang lại góc nhìn hữu ích về tác vụ đang chạy. | Dùng Timer cho độ trễ hoàn tất của thao tác ngắn. |
| Nghĩ duration là tổng thời gian lịch sử | Diễn giải sai số liệu khi tác vụ kết thúc. | Hiểu đây là tổng thời lượng của các sample đang hoạt động tại thời điểm đọc. |
| Dùng tag chứa job ID | Cardinality tăng theo số lần chạy. | Dùng tag loại job hữu hạn; tra cứu ID bằng log/trace. |
| Bỏ qua đường lỗi hoặc hủy | Sample có thể tồn tại sau khi công việc đã dừng. | Bao phủ success, exception, cancellation và submission failure. |
| Kỳ vọng nhìn thấy tác vụ ngắn hơn scrape interval | Backend có thể bỏ lỡ tác vụ giữa hai lần scrape. | Dùng Timer/Counter bổ sung hoặc điều chỉnh chu kỳ thu thập. |

## 14. Checklist trước khi phát hành

- [ ] Tác vụ đủ dài hoặc cần được quan sát khi vẫn đang chạy.
- [ ] Đã phân biệt rõ câu hỏi của LongTaskTimer với Timer.
- [ ] Meter được đăng ký một lần cho từng loại tác vụ.
- [ ] Mỗi lần thực thi có Sample riêng.
- [ ] Sample bắt đầu đúng thời điểm công việc thực sự bắt đầu.
- [ ] Sample được dừng trong mọi đường hoàn tất, lỗi và hủy.
- [ ] Với tác vụ bất đồng bộ, Sample theo sát vòng đời worker chứ không phải thời gian submit.
- [ ] Tag có miền giá trị hữu hạn và không chứa ID của từng lần chạy.
- [ ] Tên metric, đơn vị và ngưỡng cảnh báo có ngữ nghĩa rõ ràng.
- [ ] Đã kiểm tra tên metric thực tế trên endpoint của registry.
- [ ] Scrape interval phù hợp với loại tác vụ cần phát hiện.
- [ ] Kiểm thử xác nhận Sample được thêm và loại khỏi tập đang hoạt động đúng lúc.

LongTaskTimer hữu ích khi nhóm vận hành cần thấy công việc đang chạy và thời lượng của chúng trước khi hoàn tất. Mỗi Sample phải gắn với đúng một lần thực thi và được dừng đúng vòng đời; kết hợp LongTaskTimer với Timer khi cần vừa theo dõi tác vụ đang hoạt động vừa phân tích thời gian hoàn tất.
