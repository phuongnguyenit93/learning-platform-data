# Đăng ký meter tùy chỉnh với Measurement và Statistic

Micrometer cung cấp sẵn Counter, Gauge, Timer, DistributionSummary và một số meter chuyên biệt khác. Các kiểu này đáp ứng phần lớn nhu cầu đo lường ứng dụng. Khi một nguồn dữ liệu có cấu trúc riêng hoặc cần xuất nhiều đại lượng liên quan theo một định danh chung, có thể triển khai Meter tùy chỉnh.

Một Meter tùy chỉnh mô tả danh tính bằng Meter.Id và cung cấp các Measurement thông qua phương thức measure(). Mỗi Measurement gồm một nguồn giá trị dạng DoubleSupplier và một Statistic cho biết ý nghĩa của giá trị đó. Registry gọi các supplier khi thu thập hoặc export metrics.

Custom Meter phù hợp khi cần tích hợp một mô hình trạng thái đặc thù với Micrometer. Hãy ưu tiên meter có sẵn nếu semantics của dữ liệu đã được Counter, Gauge, Timer hoặc DistributionSummary biểu diễn chính xác.

## 1. Cấu trúc của một Meter

Meter là abstraction cơ bản trong Micrometer. Một Meter có hai phần quan trọng:

- **Meter.Id:** định danh meter, gồm tên, tags, base unit, description và type.
- **Measurement:** các đại lượng mà meter cung cấp khi được thu thập.

Hợp đồng chính của Meter gồm getId() và measure(). getId() trả về định danh ổn định; measure() trả về tập Measurement hiện tại.

~~~mermaid
flowchart TD
    A["Nguồn trạng thái của ứng dụng"] --> B["Custom Meter"]
    B --> C["Meter.Id<br/>name + tags + metadata"]
    B --> D["measure()"]
    D --> E["Measurement"]
    E --> F["DoubleSupplier"]
    E --> G["Statistic"]
    C --> H["MeterRegistry"]
    F --> H
    G --> H
    H --> I["Exporter / backend"]
~~~

Meter không bắt buộc phải lưu dữ liệu sự kiện. Nó có thể đọc trạng thái đang được một thành phần khác quản lý. Nếu muốn đo số lần xảy ra, ứng dụng phải duy trì bộ đếm hoặc dùng Counter có sẵn; custom Meter chỉ cung cấp cách trình bày các giá trị đó cho registry.

## 2. Measurement và Statistic

Measurement đại diện cho một giá trị mà meter có thể cung cấp. Về mặt API, nó kết hợp:

- Một DoubleSupplier: hàm trả về giá trị số khi được đọc.
- Một Statistic: ý nghĩa của giá trị, ví dụ COUNT, VALUE hoặc ACTIVE_TASKS.

Statistic giúp registry và exporter hiểu giá trị đang mô tả loại thống kê nào. Một số giá trị thường gặp:

| Statistic | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| COUNT | Số lượng sự kiện hoặc phần tử được đếm | Tổng số job đã hoàn tất |
| TOTAL | Tổng giá trị tích lũy | Tổng số byte đã xử lý |
| TOTAL_TIME | Tổng thời gian tích lũy | Tổng thời gian xử lý |
| MAX | Giá trị lớn nhất theo semantics của meter | Thời gian xử lý lớn nhất trong cửa sổ |
| VALUE | Một giá trị hiện tại hoặc giá trị tổng hợp | Số job đang chờ |
| ACTIVE_TASKS | Số tác vụ đang hoạt động | Số worker đang bận |
| DURATION | Thời lượng được đo | Thời gian tác vụ đang chạy |
| UNKNOWN | Chưa xác định được loại thống kê | Giá trị không có semantics chuyên biệt |

Chỉ dùng Statistic phù hợp với ý nghĩa thực tế. Không gắn COUNT cho một giá trị trạng thái hiện tại, cũng không gắn MAX cho giới hạn cấu hình chỉ vì đó là số lớn nhất mà ứng dụng cho phép.

Ví dụ, số job đang chờ là VALUE; tổng job hoàn tất là COUNT; số worker đang thực thi là ACTIVE_TASKS. Đây là các đại lượng khác nhau dù đều có kiểu số.

### DoubleSupplier được đọc khi nào?

Supplier được gọi khi registry hoặc exporter cần lấy số đo. Nó không phải callback được gọi ngay khi ứng dụng thay đổi trạng thái. Vì vậy:

- Supplier phải đọc trạng thái hiện tại một cách nhanh chóng.
- Không thực hiện I/O, truy vấn database hoặc tính toán nặng trong supplier.
- Không thay đổi trạng thái hay tăng counter bên trong supplier.
- Kết quả cần an toàn khi được gọi từ thread thu thập metrics.
- Nếu nguồn dữ liệu không còn hợp lệ, hãy có cách biểu diễn trạng thái phù hợp thay vì ném exception khi scrape.

Không lưu kết quả supplier vào một biến bất biến lúc khởi tạo meter nếu mục tiêu là đọc trạng thái mới. Supplier cần tham chiếu đến nguồn trạng thái đang được cập nhật.

## 3. Xác định Meter.Id

Meter.Id mô tả meter bằng các metadata:

| Trường | Vai trò |
| --- | --- |
| name | Tên metric ổn định, mô tả đại lượng |
| tags | Các chiều phân loại có cardinality được kiểm soát |
| baseUnit | Đơn vị cơ sở của giá trị nếu có |
| description | Mô tả để người dùng hiểu metric |
| type | Loại meter, với custom meter thường dùng OTHER |

Ví dụ một ID cho trạng thái worker pool:

~~~java
Meter.Id id = new Meter.Id(
    "jobs.pool.state",
    Tags.of("pool", "default"),
    null,
    "Trạng thái hiện tại của worker pool",
    Meter.Type.OTHER
);
~~~

Tên và tags cần ổn định giữa các lần khởi động. Không đưa job ID, request ID, user ID hoặc mã giao dịch vào tags vì mỗi giá trị mới có thể tạo thêm một chuỗi thời gian. Base unit và description nên phản ánh đúng dữ liệu mà meter cung cấp.

Một registry thường không cho phép hai meter khác nhau có cùng định danh tên và tags. Nếu đăng ký một custom Meter trùng định danh với meter đã tồn tại, kết quả có thể là meter đã được đăng ký được dùng lại hoặc xung đột theo loại meter/implementation. Vì vậy, hãy dành tên riêng cho custom meter và tránh trùng với meter chuẩn hoặc meter do binder tích hợp tạo ra.

## 4. Ví dụ: custom Meter cho trạng thái worker pool

Giả sử ứng dụng cần xuất ba đại lượng từ một worker pool:

- Số job đang chờ.
- Số worker đang thực thi.
- Tổng số job đã hoàn tất.

Các đại lượng này được lưu trong AtomicLong để hỗ trợ cập nhật từ nhiều thread. Custom Meter chỉ đọc các giá trị đó thông qua Measurement.

~~~java
import io.micrometer.core.instrument.Measurement;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.Tags;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicLong;

public final class WorkerPoolMeter implements Meter {

    private final Id id;
    private final Iterable<Measurement> measurements;

    public WorkerPoolMeter(
        String poolName,
        AtomicLong pendingJobs,
        AtomicLong activeWorkers,
        AtomicLong completedJobs
    ) {
        this.id = new Id(
            "jobs.pool.state",
            Tags.of("pool", poolName),
            null,
            "Trạng thái của worker pool",
            Type.OTHER
        );

        this.measurements = Arrays.asList(
            new Measurement(
                () -> pendingJobs.get(),
                Statistic.VALUE
            ),
            new Measurement(
                () -> activeWorkers.get(),
                Statistic.ACTIVE_TASKS
            ),
            new Measurement(
                () -> completedJobs.get(),
                Statistic.COUNT
            )
        );
    }

    @Override
    public Id getId() {
        return id;
    }

    @Override
    public Iterable<Measurement> measure() {
        return measurements;
    }
}
~~~

Trong ví dụ:

- Meter.Id có tên jobs.pool.state và tag pool.
- Measurement thứ nhất đọc số job đang chờ với Statistic.VALUE.
- Measurement thứ hai đọc số worker đang hoạt động với Statistic.ACTIVE_TASKS.
- Measurement thứ ba đọc tổng job hoàn tất với Statistic.COUNT.
- Các supplier đọc AtomicLong tại thời điểm thu thập, vì vậy không đóng băng giá trị ở thời điểm đăng ký.

Các Measurement được tạo một lần trong constructor và tái sử dụng trong measure(). Mỗi supplier vẫn đọc giá trị mới từ AtomicLong. Cách này tránh tạo lại danh sách measurement ở mỗi lần scrape.

## 5. Đăng ký custom Meter vào MeterRegistry

Sau khi triển khai Meter, đăng ký nó vào registry đang được ứng dụng sử dụng:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicLong;

@Component
public class WorkerPoolMetrics {

    private final AtomicLong pendingJobs = new AtomicLong();
    private final AtomicLong activeWorkers = new AtomicLong();
    private final AtomicLong completedJobs = new AtomicLong();

    public WorkerPoolMetrics(MeterRegistry registry) {
        WorkerPoolMeter meter = new WorkerPoolMeter(
            "default",
            pendingJobs,
            activeWorkers,
            completedJobs
        );

        registry.register(meter);
    }

    public void jobQueued() {
        pendingJobs.incrementAndGet();
    }

    public void jobStarted() {
        pendingJobs.decrementAndGet();
        activeWorkers.incrementAndGet();
    }

    public void jobCompleted() {
        activeWorkers.decrementAndGet();
        completedJobs.incrementAndGet();
    }
}
~~~

Ví dụ minh họa nơi cập nhật trạng thái; trong hệ thống thực tế, các phương thức này cần được gọi tại đúng điểm chuyển trạng thái của worker pool. Chỉ giảm pendingJobs khi job thực sự rời queue, và chỉ giảm activeWorkers một lần khi job kết thúc hoặc bị hủy sau khi đã bắt đầu.

Nếu việc submit bị từ chối trước khi job được xếp hàng, không tăng pendingJobs. Nếu job bị hủy khi còn nằm trong queue, cần có nhánh giảm pendingJobs tương ứng. Hãy giữ logic cập nhật trạng thái tại thành phần sở hữu queue/worker để tránh các service khác nhau cập nhật cùng bộ đếm theo quy tắc không thống nhất.

## 6. Custom Meter và các meter chuẩn

Custom Meter không phải lựa chọn mặc định. Trước khi triển khai, hãy kiểm tra liệu các đại lượng có thể được biểu diễn rõ ràng bằng meter chuẩn:

| Nhu cầu | Meter chuẩn phù hợp |
| --- | --- |
| Đếm số job hoàn tất | Counter |
| Đọc số job đang chờ | Gauge |
| Đo thời gian xử lý job | Timer |
| Theo dõi job đang chạy lâu | LongTaskTimer |
| Đo kích thước payload | DistributionSummary |
| Đọc số liệu tích lũy từ một object khác | FunctionCounter hoặc FunctionTimer |

Một custom Meter có thể gom nhiều Measurement dưới cùng Meter.Id. Điều đó hữu ích khi một thành phần có một hợp đồng trạng thái riêng. Tuy nhiên, nếu mỗi đại lượng cần truy vấn, cảnh báo, histogram hoặc percentile theo cách khác nhau, meter chuẩn riêng biệt thường dễ hiểu và tương thích exporter hơn.

Không tạo custom Meter chỉ để giảm số dòng code hoặc gom mọi metric của ứng dụng vào một đối tượng. Tên metric, tags và statistic vẫn cần đủ rõ để người vận hành hiểu và truy vấn độc lập.

## 7. Statistic và cách backend biểu diễn dữ liệu

Measurement cung cấp Statistic để registry/exporter diễn giải giá trị. Cách chuyển statistic thành tên series, suffix hoặc loại metric phụ thuộc implementation của registry và quy ước backend.

Ví dụ, backend có thể biểu diễn COUNT hoặc TOTAL_TIME theo dạng series riêng, hoặc áp dụng naming convention của chính nó. Không nên giả định mọi registry sẽ xuất custom Meter giống hệt Prometheus, Atlas, Datadog hay một hệ thống khác.

Khi chọn Statistic:

1. Xác định chính xác đại lượng mà supplier trả về.
2. Chọn statistic có semantics tương ứng.
3. Kiểm tra registry đích có hỗ trợ cách biểu diễn đó không.
4. Kiểm tra exposition hoặc dữ liệu sau export để xác nhận tên và đơn vị.
5. Viết truy vấn dựa trên dữ liệu thực tế mà backend nhận được.

Nếu exporter không hiểu statistic hoặc loại meter tùy chỉnh, số đo có thể bị bỏ qua, được ánh xạ khác dự kiến hoặc khó truy vấn. Với hệ thống cần khả năng chuyển đổi backend, ưu tiên meter chuẩn và chỉ dùng custom Meter khi có nhu cầu cụ thể.

## 8. Thread safety và tính nhất quán của Measurement

Registry có thể thu thập metrics trong lúc ứng dụng đang xử lý request hoặc job. Do đó, nguồn trạng thái phải hỗ trợ truy cập đồng thời.

- Dùng AtomicLong hoặc LongAdder cho các bộ đếm được cập nhật đồng thời.
- Dùng API đọc trạng thái chính thức của queue hoặc pool thay vì sao chép trạng thái bằng biến không đồng bộ.
- Không trả về collection có thể bị sửa đồng thời trong lúc registry đang duyệt.
- Giữ các supplier đơn giản, nhanh và không có side effect.
- Không giữ lock lâu trong measure() vì việc scrape có thể chặn các luồng thu thập khác.

Trong ví dụ worker pool, từng AtomicLong được đọc độc lập. Nếu ba giá trị phải tạo thành một snapshot nhất quán tuyệt đối, cần lấy snapshot đồng bộ từ thành phần sở hữu trạng thái, ví dụ tạo immutable snapshot dưới một lock ngắn rồi cho supplier đọc snapshot đó. Nếu chỉ cần số đo gần thời điểm hiện tại, sai khác nhỏ do các lần đọc diễn ra ở những thời điểm khác nhau thường có thể chấp nhận.

Measurement dùng DoubleSupplier nên giá trị được biểu diễn dưới dạng double. Số nguyên lớn hơn 2^53 không còn được biểu diễn chính xác từng đơn vị bằng double. Với bộ đếm có thể vượt ngưỡng này và yêu cầu độ chính xác tuyệt đối, hãy xem xét giới hạn của pipeline metrics hoặc dùng hệ thống lưu trữ giao dịch phù hợp cho số liệu chính xác.

## 9. Tags và cardinality của custom Meter

Custom Meter vẫn chịu quy tắc cardinality như meter chuẩn. Mỗi tổ hợp tên và tags có thể tạo một chuỗi thời gian riêng. Vì vậy:

- Chỉ dùng tags có tập giá trị hữu hạn như pool=default, pool=priority.
- Không dùng jobId, userId, requestId hoặc sessionId làm tags.
- Không tạo Meter mới cho mỗi job hoặc mỗi request.
- Giữ tên và tập key tags ổn định giữa các phiên bản ứng dụng.
- Nếu cần phân loại theo outcome, dùng một tập giá trị nhỏ như success, failure, timeout.

Nếu ứng dụng có nhiều worker pool động, hãy giới hạn số pool được instrument hoặc gom theo nhóm có ý nghĩa vận hành. Không tạo một meter riêng cho mỗi khách hàng nếu số lượng khách hàng không được kiểm soát.

## 10. Kiểm thử custom Meter

Có thể dùng SimpleMeterRegistry để xác nhận custom Meter được đăng ký và các Measurement trả về giá trị mới:

~~~java
import io.micrometer.core.instrument.Measurement;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Statistic;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerPoolMeterTest {

    @Test
    void measurementsReadCurrentState() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicLong pending = new AtomicLong(4);
        AtomicLong active = new AtomicLong(2);
        AtomicLong completed = new AtomicLong(10);

        registry.register(
            new WorkerPoolMeter("default", pending, active, completed)
        );

        Meter meter = registry.getMeters().stream()
            .filter(candidate ->
                candidate.getId().getName().equals("jobs.pool.state")
            )
            .findFirst()
            .orElseThrow();

        Map<Statistic, Double> values = StreamSupport
            .stream(meter.measure().spliterator(), false)
            .collect(Collectors.toMap(
                Measurement::getStatistic,
                Measurement::getValue
            ));

        assertThat(values.get(Statistic.VALUE)).isEqualTo(4.0);
        assertThat(values.get(Statistic.ACTIVE_TASKS)).isEqualTo(2.0);
        assertThat(values.get(Statistic.COUNT)).isEqualTo(10.0);

        pending.set(1);
        completed.incrementAndGet();

        Map<Statistic, Double> updatedValues = StreamSupport
            .stream(meter.measure().spliterator(), false)
            .collect(Collectors.toMap(
                Measurement::getStatistic,
                Measurement::getValue
            ));

        assertThat(updatedValues.get(Statistic.VALUE)).isEqualTo(1.0);
        assertThat(updatedValues.get(Statistic.COUNT)).isEqualTo(11.0);

        registry.close();
    }
}
~~~

Kiểm thử này xác nhận supplier đọc trạng thái mới sau khi AtomicLong thay đổi. Nó không chứng minh exporter bên ngoài sẽ biểu diễn các Statistic theo cùng cách.

Các kiểm tra bổ sung nên bao gồm:

- Meter.Id có tên và tags ổn định.
- Mỗi Measurement dùng Statistic đúng nghĩa.
- Không có hai Measurement cùng statistic trong một Meter nếu exporter không thể phân biệt chúng.
- Supplier không ném exception, không thực hiện I/O và không thay đổi trạng thái.
- Giá trị được cập nhật an toàn khi nhiều thread cùng thao tác.
- Registry chỉ đăng ký một meter cho một identity dự kiến.
- Endpoint export có các series và đơn vị như mong đợi.

## 11. Lỗi thường gặp khi triển khai Meter tùy chỉnh

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Supplier trả về giá trị đã chụp tại constructor | Metrics không thay đổi theo trạng thái thực | Đọc nguồn trạng thái trong supplier |
| Dùng Statistic không đúng semantics | Dashboard hoặc exporter diễn giải sai | Chọn Statistic theo ý nghĩa đại lượng |
| Supplier truy vấn database mỗi lần scrape | Tăng tải và làm chậm endpoint metrics | Duy trì trạng thái trong bộ nhớ hoặc dùng binder |
| Dùng biến thường trong môi trường nhiều thread | Số đo có thể mất cập nhật | Dùng atomic hoặc snapshot đồng bộ |
| Trùng tên và tags với meter khác | Xung đột hoặc dùng nhầm meter đã tồn tại | Đặt identity riêng và kiểm tra registry |
| Đưa ID động vào tags | Cardinality tăng không giới hạn | Chuẩn hóa tags về tập hữu hạn |
| Giả định exporter nào cũng xử lý statistic giống nhau | Dữ liệu xuất khác kỳ vọng | Kiểm tra exposition của registry đích |
| Dùng custom Meter thay cho Timer/Counter/Gauge có sẵn | Mất semantics và tính năng chuẩn | Ưu tiên meter chuẩn khi phù hợp |

## 12. Quy trình thiết kế custom Meter

Khi cần tích hợp một nguồn dữ liệu riêng:

1. Xác định đại lượng cần xuất và câu hỏi vận hành mà nó trả lời.
2. Kiểm tra Counter, Gauge, Timer, DistributionSummary, LongTaskTimer hoặc binder có sẵn đã đáp ứng chưa.
3. Chọn tên, tags, base unit, description và Meter.Type.
4. Chọn Statistic chính xác cho từng Measurement.
5. Tạo DoubleSupplier đọc trạng thái hiện tại một cách an toàn và nhanh.
6. Triển khai Meter với getId() ổn định và measure() trả về các Measurement.
7. Đăng ký custom Meter vào MeterRegistry dùng chung.
8. Kiểm thử giá trị, tags, concurrency và identity trong SimpleMeterRegistry.
9. Kiểm tra cách exporter/backend biểu diễn từng Statistic.
10. Xem lại cardinality và chi phí thu thập trước khi triển khai rộng.

Measurement và Statistic là hợp đồng để custom Meter trình bày các đại lượng của ứng dụng với Micrometer. Khi Meter.Id ổn định, supplier an toàn và Statistic phản ánh đúng ý nghĩa, registry có thể thu thập các giá trị theo cùng pipeline metrics. Chỉ nên dùng cơ chế này khi meter chuẩn không biểu diễn được mô hình dữ liệu cần quan sát; với các phép đo phổ biến, meter chuẩn vẫn mang lại semantics rõ ràng và khả năng tương thích tốt hơn.
