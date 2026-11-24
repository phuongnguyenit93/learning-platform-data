# Đồng hồ đơn điệu và đồng hồ thời gian thực trong việc đo thời lượng

Đo thời lượng là xác định khoảng thời gian trôi qua giữa hai thời điểm. Trong Java, cần phân biệt **đồng hồ đơn điệu (monotonic clock)** với **đồng hồ thời gian thực (wall clock)**. Hai loại đồng hồ trả về giá trị thời gian với mục đích khác nhau: đồng hồ đơn điệu phù hợp để đo elapsed time; đồng hồ thời gian thực phù hợp để ghi timestamp có thể đối chiếu với lịch và các hệ thống khác.

Sự phân biệt này đặc biệt quan trọng khi dùng Micrometer Timer. Nếu đo một thao tác bằng cách lấy timestamp bắt đầu và kết thúc từ wall clock, việc đồng bộ thời gian hệ thống, chỉnh giờ thủ công hoặc các điều chỉnh của máy chủ có thể làm kết quả bị âm hoặc sai lệch. Timer cần đo khoảng thời gian bằng nguồn thời gian đơn điệu để số liệu latency đáng tin cậy.

## 1. Hai loại đồng hồ giải quyết hai bài toán khác nhau

### Đồng hồ đơn điệu: đo khoảng thời gian đã trôi qua

Đồng hồ đơn điệu là nguồn thời gian chỉ tiến về phía trước theo cách phù hợp để đo elapsed time. Trong Java, API tiêu chuẩn là System.nanoTime().

~~~java
long startedAt = System.nanoTime();

// Thực hiện công việc cần đo.
performOperation();

long elapsedNanos = System.nanoTime() - startedAt;
~~~

Giá trị trả về của nanoTime không phải timestamp tính từ epoch. Điểm bắt đầu của nó là tùy ý và có thể khác giữa các lần chạy JVM. Vì vậy:

- Chỉ dùng hiệu giữa hai lần đọc để tính thời lượng.
- Không chuyển trực tiếp giá trị nanoTime thành ngày giờ.
- Không so sánh giá trị nanoTime giữa hai tiến trình hoặc hai máy.
- Không lưu nanoTime như timestamp nghiệp vụ để tra cứu về sau.

Đơn vị trả về là nanosecond. Độ phân giải của nguồn đo phụ thuộc hệ điều hành và phần cứng; việc API trả số nanosecond không có nghĩa phép đo luôn chính xác đến từng nanosecond.

### Đồng hồ thời gian thực: ghi nhận một thời điểm trên lịch

System.currentTimeMillis() trả về số mili giây từ epoch Unix (1970-01-01T00:00:00Z). Java cũng cung cấp Instant.now() để biểu diễn một thời điểm theo UTC:

~~~java
long epochMillis = System.currentTimeMillis();
Instant occurredAt = Instant.now();
~~~

Wall clock phù hợp cho các mục đích như:

- Ghi thời điểm đơn hàng được tạo.
- Gắn timestamp cho log hoặc audit event.
- Đối chiếu thời điểm xảy ra sự cố giữa nhiều dịch vụ.
- Hiển thị ngày giờ cho người dùng theo múi giờ tương ứng.

Wall clock có thể được điều chỉnh bởi NTP, quản trị viên, hypervisor hoặc môi trường chạy. Thời gian có thể nhảy tiến hoặc lùi. Vì vậy, lấy hiệu giữa hai lần đọc currentTimeMillis() không phải cách đáng tin cậy để đo latency.

Múi giờ chỉ ảnh hưởng cách hiển thị và chuyển đổi timestamp sang giờ địa phương; bản thân việc đổi múi giờ không làm thay đổi epoch timestamp. Điều có thể làm phép đo wall clock sai là đồng hồ hệ thống thực sự bị điều chỉnh.

## 2. Vì sao không nên đo duration bằng currentTimeMillis()?

Một cách đo dễ viết nhưng không an toàn:

~~~java
long startedAt = System.currentTimeMillis();

performOperation();

long elapsedMillis = System.currentTimeMillis() - startedAt;
~~~

Giả sử thao tác bắt đầu lúc wall clock chỉ 10:00:05.000. Trong lúc chạy, đồng hồ hệ thống được điều chỉnh lùi 2 giây. Khi thao tác kết thúc, wall clock chỉ 10:00:04.500. Phép trừ cho kết quả -500 ms dù thao tác thực tế đã mất 1,5 giây.

Nếu đồng hồ nhảy tiến, duration có thể lớn hơn thực tế. Nếu đồng hồ được đồng bộ bằng cách điều chỉnh từ từ (slew), tốc độ trôi của wall clock trong khoảng đo cũng có thể khác tốc độ thời gian thực. Những sai lệch này ảnh hưởng trực tiếp đến latency, timeout, percentile và cảnh báo.

Dùng System.nanoTime() cho elapsed duration:

~~~java
long startedAt = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - startedAt;
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Phép trừ hai giá trị nanoTime là cách sử dụng được Java khuyến nghị. Không cần đổi từng timestamp sang mili giây trước khi trừ; giữ hiệu ở nanosecond rồi đổi đơn vị ở bước cuối để tránh mất độ chính xác do làm tròn sớm.

## 3. Micrometer Timer đo thời lượng bằng clock đơn điệu

Timer là meter dành cho các thao tác có thời lượng. Ngoài tổng thời gian và số lần ghi nhận, tùy registry và cấu hình, Timer còn có thể cung cấp histogram, percentile hoặc giá trị max. Đây là cơ sở để phân tích latency và phân phối thời gian xử lý.

Micrometer cung cấp Clock abstraction với cả wall time và monotonic time. Khi đo thời lượng, Timer và Timer.Sample sử dụng monotonic time của clock thuộc registry để tính khoảng thời gian. Người dùng không cần tự lấy timestamp wall clock rồi trừ chúng.

Ví dụ dùng Timer.record:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final Timer lookupTimer;

    public InventoryService(MeterRegistry registry) {
        this.lookupTimer = Timer.builder("inventory.lookup")
                .description("Time spent looking up inventory")
                .register(registry);
    }

    public Inventory find(String sku) {
        return lookupTimer.record(() -> inventoryRepository.find(sku));
    }
}
~~~

Timer.record(Supplier) đo thời gian thực thi của hàm và trả về kết quả. Nếu hàm ném exception, thời lượng thực thi vẫn được ghi nhận trước khi exception được truyền tiếp. Điều này hữu ích khi muốn latency phản ánh cả những lần xử lý thất bại; nếu cần phân tích kết quả, có thể thêm tag outcome có tập giá trị hữu hạn.

### Dùng Timer.Sample khi chỉ biết tag sau khi thao tác kết thúc

Có trường hợp chỉ xác định được outcome sau khi gọi dịch vụ bên ngoài. Timer.Sample cho phép bắt đầu đo trước, rồi chọn Timer đích khi dừng:

~~~java
Timer.Sample sample = Timer.start(registry);

String outcome = "success";
try {
    paymentGateway.charge(request);
} catch (PaymentException ex) {
    outcome = "failure";
    throw ex;
} finally {
    sample.stop(registry.timer(
            "payment.processing",
            "outcome", outcome
    ));
}
~~~

Timer.Sample ghi lại thời điểm bắt đầu bằng monotonic clock của registry. Khi gọi stop(), Micrometer tính thời gian đã trôi qua và ghi vào Timer được chọn. Ví dụ trên phân loại latency theo outcome. Trong ứng dụng thật, hãy bảo đảm các giá trị tag như success và failure là hữu hạn; không đưa exception message hoặc request ID vào tag.

Với tác vụ bất đồng bộ, có thể tạo Sample trước khi gửi công việc và gọi stop ở callback hoàn tất. Sample phải được giữ cho đến khi thao tác kết thúc; không đo bằng cách lấy wall-clock timestamp ở thread gửi rồi trừ timestamp ở thread nhận.

## 4. Clock của Micrometer và vai trò của registry

Micrometer định nghĩa Clock để tách việc đọc thời gian khỏi logic meter. Clock cung cấp hai khái niệm:

| Khái niệm | Mục đích | Ví dụ Java tương ứng |
|---|---|---|
| wallTime | Timestamp theo epoch để xác định thời điểm | System.currentTimeMillis() |
| monotonicTime | Đo thời gian đã trôi qua | System.nanoTime() |

Timer cần monotonicTime để tính duration. Các thành phần cần timestamp hoặc ranh giới thời gian theo lịch có thể dùng wallTime. Nhờ abstraction này, registry và môi trường kiểm thử có thể cung cấp clock phù hợp.

Không nên tự thay Clock của registry trong production chỉ để khắc phục một phép đo sai. Trước hết, kiểm tra code có đang dùng Timer hoặc Timer.Sample đúng cách không. Nếu ứng dụng tự đo thủ công, dùng System.nanoTime() cho elapsed time hoặc chuyển sang Timer API để Micrometer quản lý phép đo.

## 5. Dùng timestamp và duration đúng mục đích

Một thao tác có thể cần cả timestamp và duration. Ví dụ, khi xử lý yêu cầu thanh toán:

~~~java
Instant receivedAt = Instant.now();
Timer.Sample sample = Timer.start(registry);

try {
    PaymentResult result = paymentService.process(request);
    return result;
} finally {
    sample.stop(paymentTimer);
    auditLogger.recordReceivedAt(receivedAt);
}
~~~

Trong ví dụ này:

- receivedAt là timestamp wall clock, hữu ích cho log hoặc audit.
- Timer.Sample đo duration bằng monotonic clock.
- Hai giá trị phục vụ hai câu hỏi khác nhau: sự kiện xảy ra lúc nào và thao tác mất bao lâu.

Nếu cần ghi thời điểm bắt đầu và kết thúc cho audit, hãy dùng Instant. Nếu cần đo latency cho metrics, hãy dùng Timer. Không suy ra timestamp lịch từ nanoTime vì nguồn gốc của nanoTime không gắn với epoch.

Cũng không nên tính timeout bằng currentTimeMillis() nếu yêu cầu là đo thời gian chờ đã trôi qua. Với timeout, deadline nội bộ nên dựa trên monotonic time hoặc cơ chế timeout của thư viện. Timestamp wall clock có thể dùng để hiển thị deadline cho con người, nhưng không nên là cơ sở duy nhất để quyết định một khoảng chờ đã hết hay chưa.

## 6. Đơn vị thời lượng và cách đọc số liệu

Timer của Micrometer chuẩn hóa thời lượng khi ghi nhận và cho phép truy vấn theo đơn vị cần thiết. Ví dụ:

~~~java
Timer timer = registry.timer("checkout.processing");

timer.record(250, TimeUnit.MILLISECONDS);

double seconds = timer.totalTime(TimeUnit.SECONDS);
long count = timer.count();
~~~

Ở đây, record nhận giá trị 250 với đơn vị milliseconds. Khi truy vấn totalTime, có thể yêu cầu seconds, milliseconds hoặc nanoseconds. Luôn truyền TimeUnit chính xác để tránh nhầm lẫn giữa con số và đơn vị.

Với Prometheus registry, Timer thường được biểu diễn bằng các series liên quan đến count và sum; nếu histogram được bật, còn có các bucket. Tên metric cụ thể phụ thuộc quy tắc chuẩn hóa của registry. Một truy vấn thường dùng để tính tốc độ request:

~~~promql
sum(rate(checkout_processing_seconds_count[5m]))
~~~

Nếu có histogram bucket, có thể ước lượng p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(checkout_processing_seconds_bucket[5m])
  )
)
~~~

Các truy vấn này phân tích dữ liệu Timer đã được thu thập. Chúng không sửa được sai lệch nếu ứng dụng tự ghi duration từ wall clock. Nguồn đo thời lượng phải đúng ngay từ lúc instrumentation.

## 7. Kiểm thử phép đo thời lượng

Unit test nên xác minh Timer được ghi nhận và số lần ghi đúng. Không nên khẳng định một thời lượng thực cụ thể trong test chạy với đồng hồ hệ thống vì scheduling của JVM và máy chạy có thể làm thời gian dao động.

Ví dụ kiểm thử cơ bản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class TimerRecordingTest {

    @Test
    void recordsAnOperation() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Timer timer = registry.timer("operation.duration");

        timer.record(() -> {
            // Thực hiện thao tác đồng bộ cần đo.
        });

        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(java.util.concurrent.TimeUnit.NANOSECONDS))
                .isGreaterThanOrEqualTo(0.0);

        registry.close();
    }
}
~~~

Để kiểm thử duration chính xác và có tính lặp lại, có thể dùng clock giả (mock clock) được hỗ trợ bởi phiên bản Micrometer đang sử dụng, rồi chủ động tiến monotonic time trong test. Cách này giúp kiểm thử logic mà không phải chờ thời gian thực. API cụ thể của mock clock và constructor registry có thể khác giữa các phiên bản; hãy dùng đúng API của dependency trong dự án.

Các tình huống nên kiểm thử:

- Timer ghi nhận đúng một lần khi thao tác hoàn tất.
- Thời lượng vẫn được ghi khi thao tác ném exception, nếu đó là ngữ nghĩa mong muốn.
- Timer.Sample được dừng đúng một lần trên mọi nhánh kết quả.
- Tag outcome nhận giá trị đúng và không phát sinh tag có cardinality cao.
- Các code path đo duration không dùng currentTimeMillis() để tính hiệu.

## 8. Những lỗi thường gặp khi chọn clock

| Cách làm | Vấn đề | Cách phù hợp |
|---|---|---|
| Lấy hiệu hai lần System.currentTimeMillis() | Wall clock có thể nhảy tiến hoặc lùi | Dùng System.nanoTime() hoặc Micrometer Timer |
| Dùng Instant.now() để tính latency | Instant là timestamp wall clock | Dùng Timer.Sample hoặc monotonic clock |
| Ghi System.nanoTime() vào log như epoch | Giá trị không có mốc epoch và không so sánh được giữa tiến trình | Ghi Instant hoặc epoch timestamp |
| So sánh nanoTime giữa hai máy | Mốc gốc của mỗi JVM không tương ứng | Gửi timestamp wall clock nếu cần đối chiếu; dùng trace context để liên kết hoạt động |
| Đổi nanoTime sang milliseconds trước khi trừ | Có thể mất phần lẻ do làm tròn sớm | Trừ ở nanosecond rồi mới đổi đơn vị |
| Tự ghi Timer bằng duration lấy từ wall clock | Metrics latency có thể âm hoặc sai lệch | Để Timer.record hoặc Timer.Sample đo duration |
| Nhầm đổi múi giờ với đồng hồ bị chỉnh | Múi giờ chỉ đổi cách hiển thị timestamp | Phân biệt timezone formatting với thay đổi giá trị clock hệ thống |

## 9. Quy tắc chọn clock khi instrument ứng dụng

Khi thiết kế metrics hoặc log cho một thao tác, hãy trả lời ba câu hỏi:

1. **Cần biết sự kiện xảy ra lúc nào?** Dùng Instant hoặc timestamp epoch từ wall clock.
2. **Cần biết thao tác mất bao lâu?** Dùng Micrometer Timer/Timer.Sample hoặc System.nanoTime() nếu thật sự cần đo thủ công.
3. **Cần quyết định timeout đã hết chưa?** Dựa trên monotonic elapsed time hoặc cơ chế timeout chuyên dụng, không dựa vào phép trừ wall-clock timestamp.

Đối với Micrometer, ưu tiên Timer.record hoặc Timer.Sample thay vì tự đo rồi truyền một duration không rõ nguồn gốc. Nếu cần truyền duration vào Timer.record(long, TimeUnit), hãy bảo đảm giá trị đó được tính từ monotonic clock và đơn vị được khai báo chính xác.

Đồng hồ đơn điệu và đồng hồ thời gian thực không cạnh tranh nhau; chúng bổ sung cho hai nhu cầu khác nhau. Dùng wall clock để biết sự kiện xảy ra khi nào, dùng monotonic clock để biết đã mất bao lâu. Khi Timer sử dụng đúng nguồn thời gian, latency, histogram và percentile mới phản ánh đáng tin cậy hiệu năng của ứng dụng Java.
