# Nguyên nhân Gauge trở thành NaN hoặc biến mất sau thu gom rác

Gauge dùng để quan sát một giá trị tại thời điểm registry đọc meter. Giá trị đó có thể là độ sâu hàng đợi, số kết nối đang mở, số tác vụ đang chờ hoặc dung lượng cache hiện tại. Khác với Counter, Gauge không tích lũy sự kiện; nó lấy mẫu trạng thái của một object hoặc một nguồn dữ liệu.

Một lỗi thường gặp là Gauge hoạt động lúc mới khởi động nhưng sau đó trả về NaN, không còn điểm dữ liệu hoặc biến mất khỏi dashboard. Một nguyên nhân đặc trưng của Micrometer là object được Gauge quan sát không còn tham chiếu mạnh và bị garbage collector thu gom. Bài này giải thích vòng đời tham chiếu của Gauge, cách giữ object sống đúng thời hạn và cách phân biệt lỗi garbage collection với các nguyên nhân tạo ra NaN khác.

## 1. Gauge quan sát trạng thái tại thời điểm đọc

Micrometer Gauge thường được tạo từ một object cùng hàm đọc giá trị:

~~~java
Gauge.builder("queue.depth", queue, Queue::size)
        .description("Number of pending jobs")
        .register(registry);
~~~

Khi registry thu thập metrics, Micrometer gọi hàm Queue::size trên object queue để lấy giá trị hiện tại. Nếu queue có 12 phần tử tại thời điểm scrape, Gauge báo 12. Khi queue giảm còn 4, lần đọc sau báo 4.

Gauge phù hợp với giá trị có thể tăng hoặc giảm:

- Số tác vụ đang chờ trong queue.
- Số kết nối đang được sử dụng.
- Số request đang chạy.
- Số phần tử hiện có trong cache hoặc collection.
- Dung lượng bộ nhớ đang được sử dụng, nếu nguồn đo cung cấp giá trị hiện tại.

Gauge là phép lấy mẫu. Nếu queue tăng từ 0 lên 100 rồi giảm về 0 giữa hai lần scrape, dashboard có thể không nhìn thấy đỉnh 100. Khi cần đếm tổng số sự kiện hoặc đo phân phối của các lần xảy ra, dùng Counter hoặc Timer phù hợp hơn.

## 2. Vì sao object được Gauge quan sát có thể bị garbage collector thu gom?

Để tránh việc registry giữ vô thời hạn mọi object được đo, Gauge của Micrometer mặc định giữ **tham chiếu yếu (weak reference)** đến object được quan sát. Tham chiếu yếu cho phép garbage collector thu gom object khi không còn nơi nào khác giữ tham chiếu mạnh đến nó.

Đây là hành vi có chủ đích: một registry sống lâu không nên vô tình giữ lại mọi object nghiệp vụ đã từng được đăng ký làm Gauge. Nhưng điều đó cũng có nghĩa là mã ứng dụng phải quản lý vòng đời của object được quan sát.

Ví dụ dễ gây lỗi:

~~~java
Gauge.builder(
        "queue.depth",
        new AtomicInteger(0),
        AtomicInteger::get
).register(registry);
~~~

AtomicInteger mới chỉ được truyền vào lúc đăng ký. Sau khi biểu thức kết thúc, nếu không có tham chiếu mạnh nào khác giữ object này, nó có thể bị thu gom. Gauge vẫn có thể còn trong registry nhưng không còn object để đọc giá trị. Micrometer trả về NaN cho phép đo đó.

Vì garbage collection không diễn ra theo thời điểm cố định, lỗi có thể không xuất hiện ngay. Ứng dụng có thể xuất số liệu bình thường lúc khởi động, rồi sau một khoảng thời gian hoặc dưới áp lực bộ nhớ mới bắt đầu thấy NaN. Việc chỉ chạy thử vài giây không đủ để chứng minh Gauge có vòng đời đúng.

## 3. Giữ object được quan sát bằng tham chiếu mạnh

Cách nên dùng là giữ object trạng thái trong một field có vòng đời ít nhất bằng vòng đời Gauge. Với Spring Boot, một component singleton có thể giữ AtomicInteger và đăng ký Gauge một lần trong constructor:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class QueueMetrics {
    private final AtomicInteger pendingJobs = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder("queue.pending", pendingJobs, AtomicInteger::get)
                .description("Number of jobs waiting to be processed")
                .baseUnit("jobs")
                .register(registry);
    }

    public void jobEnqueued() {
        pendingJobs.incrementAndGet();
    }

    public void jobDequeued() {
        pendingJobs.updateAndGet(current -> Math.max(0, current - 1));
    }
}
~~~

Ở đây QueueMetrics là Spring singleton và giữ pendingJobs bằng field final. Gauge giữ tham chiếu yếu đến AtomicInteger, nhưng component vẫn giữ tham chiếu mạnh. Vì thế object tiếp tục tồn tại khi component còn sống và Gauge có thể đọc giá trị mới mỗi lần scrape.

Nếu trạng thái thực tế nằm trong một collection, giữ chính collection đó trong field:

~~~java
private final Queue<Job> pendingJobs = new ConcurrentLinkedQueue<>();

public QueueMetrics(MeterRegistry registry) {
    Gauge.builder("queue.pending", pendingJobs, Queue::size)
            .description("Number of jobs waiting in queue")
            .register(registry);
}
~~~

Khi thêm hoặc lấy job khỏi queue, Gauge đọc trực tiếp kích thước hiện tại. Không cần tạo một object mới cho mỗi lần cập nhật.

Các nguyên tắc cần giữ:

- Object được quan sát phải có một chủ sở hữu rõ ràng trong ứng dụng.
- Thời gian sống của object phải bao phủ thời gian sống mong muốn của Gauge.
- Đăng ký Gauge một lần khi khởi tạo component hoặc khi tạo resource có vòng đời xác định.
- Cập nhật trạng thái bên trong object; không tạo Gauge mới cho từng request.
- Nếu resource kết thúc vòng đời, gỡ meter tương ứng khi cần và quản lý việc đăng ký lại một cách có chủ đích.

## 4. Dùng strongReference(true) khi thật sự cần

Micrometer Gauge.Builder có tùy chọn strongReference(true) để Gauge giữ tham chiếu mạnh đến object được quan sát:

~~~java
Gauge.builder("queue.depth", temporaryState, QueueState::depth)
        .strongReference(true)
        .register(registry);
~~~

Với tùy chọn này, registry giữ object sống thông qua Gauge. Nó có thể hữu ích khi vòng đời object được quản lý bởi registry hoặc khi không thể giữ tham chiếu ở một thành phần khác.

Tuy nhiên, không nên dùng strongReference(true) như cách sửa mặc định cho mọi Gauge. Registry thường sống lâu hơn object nghiệp vụ. Nếu Gauge giữ mạnh object, object và toàn bộ object graph mà nó tham chiếu có thể không được thu gom. Khi đăng ký nhiều Gauge cho các object ngắn hạn, bộ nhớ có thể tăng và tạo rò rỉ bộ nhớ.

Ưu tiên giữ object trong field của component hoặc resource owner. Chỉ bật strongReference(true) khi đã xác định rõ registry cần sở hữu vòng đời object và có kế hoạch gỡ meter khi resource kết thúc.

## 5. NaN có thể đến từ nguồn đo, không chỉ từ garbage collection

NaN (Not a Number) là một giá trị số dấu phẩy động đặc biệt. Khi Gauge báo NaN, cần kiểm tra cả object được quan sát và hàm tính giá trị.

### Object đã bị thu gom

Đây là trường hợp phổ biến với weak reference: object không còn tham chiếu mạnh, bị GC thu gom và Gauge không thể lấy mẫu. Kiểm tra xem object có được giữ trong field, bean singleton, cache hoặc một resource owner còn sống hay không.

### Hàm đo chủ động trả về NaN

Ví dụ, một Gauge tính tỷ lệ phần trăm:

~~~java
Gauge.builder("cache.hit.ratio", cacheStats, stats -> {
    long total = stats.hits() + stats.misses();
    return total == 0
            ? Double.NaN
            : (double) stats.hits() / total;
}).register(registry);
~~~

Ở đây NaN là kết quả do hàm đo chủ động trả về khi chưa có lượt truy cập. Đây không phải bằng chứng object đã bị GC. Nếu yêu cầu nghiệp vụ coi trạng thái chưa có dữ liệu là 0%, có thể trả 0.0; nếu muốn thể hiện chưa xác định, cần thống nhất cách backend và dashboard xử lý NaN.

Không thay mọi NaN bằng 0 một cách máy móc. Giá trị 0 có nghĩa là đã đo được và trạng thái thực sự bằng 0; NaN có nghĩa là không có một kết quả số hợp lệ. Hai trạng thái này có ý nghĩa khác nhau.

### Phép tính tạo ra giá trị không hợp lệ

Các phép chia với mẫu số bằng 0, phép tính trên dữ liệu chưa khởi tạo hoặc một sentinel không hợp lệ có thể tạo NaN hoặc vô cực. Hãy kiểm tra logic của hàm ToDoubleFunction và dữ liệu nguồn trước khi trả về giá trị.

### Callback không đọc được trạng thái hợp lệ

Nếu hàm đọc phụ thuộc vào một resource đã đóng, object đã được thay thế hoặc dữ liệu chưa sẵn sàng, kết quả có thể không phản ánh trạng thái thật. Hãy xác định rõ trạng thái hợp lệ, thời điểm khởi tạo và hành vi khi resource ngừng hoạt động.

## 6. Phân biệt NaN, time series biến mất và scrape thất bại

Nhìn thấy panel trống không có nghĩa chắc chắn object đã bị GC. Cần phân biệt các trường hợp:

| Dấu hiệu | Khả năng nguyên nhân | Cách xác minh |
|---|---|---|
| Metric vẫn tồn tại nhưng giá trị là NaN | Object Gauge đã bị GC hoặc hàm đo trả về NaN | Kiểm tra vòng đời object và logic callback |
| Metric biến mất khỏi kết quả truy vấn | Meter không được đăng ký, exporter bỏ qua giá trị, series trở thành stale hoặc truy vấn lọc sai | Kiểm tra endpoint export và truy vấn trực tiếp backend |
| Nhiều metrics cùng biến mất | Scrape/export thất bại, ứng dụng dừng hoặc endpoint không truy cập được | Kiểm tra trạng thái target, log và kết nối |
| Gauge có giá trị 0 ổn định | Object vẫn tồn tại và hàm đọc trả về 0, hoặc trạng thái thật đang bằng 0 | Đối chiếu với trạng thái ứng dụng |
| Gauge thay đổi không đúng thực tế | Đang quan sát object cũ, cập nhật sai nguồn hoặc callback tính sai | Kiểm tra object được capture và vị trí cập nhật |

Trong Micrometer, object bị thu gom có thể làm phép đo Gauge thành NaN. Tùy registry, exporter và backend, giá trị NaN có thể được xuất nguyên dạng, bị xử lý như mẫu không hợp lệ hoặc không xuất hiện thành điểm dữ liệu mà dashboard hiển thị. Vì vậy, hãy kiểm tra endpoint metrics và backend trước khi kết luận.

Với Prometheus, kiểm tra riêng trạng thái scrape bằng:

~~~promql
up{job="checkout-service"}
~~~

Nếu up bằng 0 hoặc target DOWN, cần điều tra scrape, mạng hoặc endpoint. Nếu up bằng 1 nhưng Gauge có giá trị NaN, scrape vẫn thành công và vấn đề có thể nằm ở object hoặc hàm đo. Truy vấn trực tiếp series Gauge giúp phân biệt dữ liệu nguồn với cấu hình panel.

## 7. Không thay object được quan sát một cách tùy tiện

Một lỗi khác xảy ra khi mã ứng dụng thay object trạng thái sau khi Gauge đã đăng ký:

~~~java
private QueueState state = new QueueState();

public void resetState() {
    state = new QueueState();
}
~~~

Nếu Gauge được tạo với object state ban đầu, nó vẫn quan sát object đó. Việc gán field state sang object mới không tự động chuyển Gauge sang object mới. Object cũ có thể bị GC, khiến Gauge thành NaN; object mới không được Gauge cũ theo dõi.

Có hai cách thiết kế tốt hơn:

**Giữ một object ổn định và cập nhật nội dung của nó.** Ví dụ, giữ AtomicInteger hoặc một QueueState có các field mutable và thay đổi giá trị bên trong. Đây thường là lựa chọn đơn giản nhất cho trạng thái của một dịch vụ.

**Quản lý rõ vòng đời của meter khi resource thực sự được thay thế.** Khi resource cũ kết thúc, gỡ meter cũ bằng registry.remove(meter) nếu cần, sau đó đăng ký Gauge mới cho resource mới. Cần đồng bộ thao tác thay thế và tránh tạo hàng loạt series với tag không giới hạn.

Lưu ý rằng registry thường nhận diện meter bằng tên và tập tag. Đăng ký lại một Gauge cùng tên và tag không nên được xem như thao tác thay object đang được quan sát. Hãy giữ object ổn định hoặc thực hiện quy trình remove/register có chủ đích.

## 8. Kiểm thử Gauge và vòng đời object

Có thể dùng SimpleMeterRegistry để xác nhận Gauge đọc trạng thái mới từ object được giữ tham chiếu mạnh:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueGaugeTest {

    @Test
    void readsTheCurrentValueFromTheObservedObject() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicInteger pendingJobs = new AtomicInteger(2);

        Gauge gauge = Gauge.builder(
                "queue.pending",
                pendingJobs,
                AtomicInteger::get
        ).register(registry);

        assertThat(gauge.value()).isEqualTo(2.0);

        pendingJobs.set(5);
        assertThat(gauge.value()).isEqualTo(5.0);

        registry.close();
    }
}
~~~

Test giữ pendingJobs trong biến cục bộ suốt thời gian kiểm thử, nên object vẫn có tham chiếu mạnh. Test cũng chứng minh Gauge đọc giá trị hiện tại thay vì lưu một bản sao tại lúc đăng ký.

Không nên viết unit test dựa vào việc gọi System.gc() rồi mong object chắc chắn bị thu gom. GC là hoạt động không xác định thời điểm; System.gc() chỉ là gợi ý cho JVM. Test như vậy dễ chập chờn giữa các môi trường. Thay vào đó:

- Kiểm thử callback trả về giá trị đúng khi trạng thái thay đổi.
- Kiểm thử riêng logic trả NaN khi trạng thái chưa xác định, nếu đó là quy ước mong muốn.
- Giữ object sống trong test để kiểm tra hành vi Gauge bình thường.
- Dùng quan sát heap hoặc kiểm thử tích hợp có kiểm soát khi cần điều tra vòng đời object thật.
- Kiểm tra endpoint export sau khi ứng dụng chạy đủ lâu và có hoạt động GC.

## 9. Quy trình chẩn đoán khi Gauge thành NaN hoặc biến mất

Khi gặp lỗi, đi theo thứ tự sau để khoanh vùng:

1. **Kiểm tra scrape/export.** Với Prometheus, xem target có UP hay không. Với OTLP, xem log exporter và Collector. Nếu cả nhóm metrics cùng biến mất, bắt đầu từ kết nối và tiến trình.
2. **Kiểm tra endpoint metrics.** Tìm đúng tên Gauge, tag và giá trị được xuất. Xác định meter không tồn tại, có giá trị NaN hay vẫn có số hợp lệ.
3. **Kiểm tra object được quan sát.** Xác định object nào được truyền vào Gauge.builder; tìm tham chiếu mạnh trong bean, field hoặc resource owner.
4. **Kiểm tra vòng đời.** Tìm chỗ tạo object tạm, gán lại field, xóa collection, đóng resource hoặc kết thúc scope khiến object cũ không còn được giữ.
5. **Kiểm tra callback.** Đọc hàm ToDoubleFunction, kiểm tra mẫu số bằng 0, giá trị chưa khởi tạo và các trạng thái đặc biệt.
6. **Kiểm tra đăng ký trùng.** Xác nhận cùng tên và tag không được đăng ký lại với object khác rồi kỳ vọng registry tự thay tham chiếu.
7. **Đối chiếu backend và dashboard.** Nếu endpoint có số hợp lệ nhưng panel trống, kiểm tra truy vấn, bộ lọc tag, time range và cách backend xử lý NaN.

## 10. Checklist để Gauge có vòng đời ổn định

Trước khi đưa Gauge vào production, hãy xác nhận:

- Object được quan sát có chủ sở hữu rõ ràng và được giữ sống trong suốt thời gian cần đo.
- Không truyền object tạm thời mà không giữ tham chiếu mạnh.
- Gauge được đăng ký một lần và trạng thái được cập nhật trên cùng object.
- Chỉ dùng strongReference(true) khi chủ động chấp nhận việc registry giữ object sống.
- Hàm đo không tạo NaN hoặc vô cực ngoài chủ đích.
- Giá trị 0 và trạng thái chưa xác định được phân biệt rõ.
- Có kiểm thử xác nhận Gauge đọc được trạng thái mới.
- Endpoint export, backend và dashboard được kiểm tra độc lập.

Gauge chỉ hữu ích khi object mà nó quan sát còn tồn tại và hàm đo trả về giá trị có ý nghĩa. Giữ vòng đời object ổn định, đăng ký meter đúng một lần và kiểm tra cả callback lẫn đường xuất metrics sẽ giúp tránh lỗi NaN hoặc khoảng trống dữ liệu sau garbage collection.
