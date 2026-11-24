# serviceLevelObjectives và lựa chọn ngưỡng đáp ứng yêu cầu dịch vụ

Service Level Objective (SLO) là mục tiêu đo lường chất lượng dịch vụ trong một khoảng thời gian xác định. Với metrics, SLO thường được diễn đạt bằng tỷ lệ request thành công, tỷ lệ request hoàn tất dưới một ngưỡng latency, hoặc tỷ lệ sự kiện đáp ứng một điều kiện vận hành.

Micrometer cho phép khai báo các ngưỡng Service Level Objective trên Timer và DistributionSummary. Những ngưỡng này bổ sung các bucket cho histogram để backend có thể đếm số quan sát nằm trong giới hạn đã chọn. Muốn dùng SLO có ý nghĩa, trước hết phải xác định đúng SLI, đối tượng được tính, ngưỡng chấp nhận được và khoảng thời gian đánh giá.

## 1. Phân biệt SLI, SLO và SLA

Ba thuật ngữ này liên quan nhưng có vai trò khác nhau:

- **Service Level Indicator (SLI):** chỉ số đo chất lượng dịch vụ, ví dụ tỷ lệ request thành công hoặc tỷ lệ request có latency không quá 300 ms.
- **Service Level Objective (SLO):** mục tiêu đặt ra cho SLI trong một cửa sổ thời gian, ví dụ ít nhất 99,9% request đủ điều kiện phải thành công và hoàn tất trong 300 ms trong 30 ngày.
- **Service Level Agreement (SLA):** cam kết dịch vụ giữa các bên, thường gắn với điều khoản, trách nhiệm hoặc bồi hoàn nếu không đạt.

SLO là mục tiêu vận hành mà đội ngũ dùng để điều hành độ tin cậy. SLA có thể dùng SLO làm cơ sở nhưng không nhất thiết có cùng ngưỡng hoặc cùng cách tính.

Ví dụ:

| Loại | Ví dụ |
| --- | --- |
| SLI | Tỷ lệ request thanh toán thành công và hoàn tất trong 800 ms |
| SLO | Ít nhất 99,9% request thanh toán đủ điều kiện đạt SLI trong 30 ngày |
| SLA | Cam kết với khách hàng theo hợp đồng, có quy định xử lý khi không đạt |

Không nên gọi một giá trị p95 hoặc p99 đơn lẻ là SLO nếu chưa xác định mục tiêu, tập request được tính và cửa sổ đánh giá.

## 2. Xây dựng SLI theo good events và total events

Một cách phổ biến để biểu diễn SLI là tỷ lệ sự kiện tốt trên tổng số sự kiện đủ điều kiện:

\[
\text{SLI} =
\frac{\text{good events}}{\text{total eligible events}}
\times 100\%
\]

Với SLI về latency, một request được xem là good event khi nó thỏa điều kiện đã định nghĩa, chẳng hạn:

1. Request thuộc phạm vi cần đo.
2. Request hoàn tất thành công.
3. Thời gian xử lý không vượt quá ngưỡng đã chọn.

Nếu chỉ đo latency mà bỏ qua kết quả, một request lỗi rất nhanh có thể bị tính nhầm là request tốt. Vì vậy, cần xác định rõ cách kết hợp latency và kết quả nghiệp vụ.

Có thể theo dõi availability và latency thành hai SLI riêng:

- Availability SLI: số request thành công chia cho tổng request đủ điều kiện.
- Latency SLI: số request thành công và có latency dưới ngưỡng chia cho tổng request đủ điều kiện.

Cách tách này giúp biết hệ thống đang vi phạm vì lỗi hay vì chậm. Nếu mục tiêu kinh doanh yêu cầu một request chỉ được tính tốt khi vừa thành công vừa đủ nhanh, hãy dùng điều kiện kết hợp cho SLI đó.

## 3. Chọn ngưỡng latency dựa trên trải nghiệm và ngân sách thời gian

Ngưỡng SLO không nên được chọn chỉ vì đó là percentile đang thấy trong dashboard. Hãy bắt đầu từ hành trình người dùng và xác định mức chờ tối đa mà thao tác vẫn có ích.

Một quy trình lựa chọn thực tế:

1. **Xác định thao tác:** ví dụ mở trang đơn hàng, tìm kiếm, tạo đơn hoặc xác nhận thanh toán.
2. **Xác định điều kiện hoàn tất:** response được trả về, giao dịch được xác nhận hay tác vụ nền được chấp nhận.
3. **Xác định ngưỡng có ý nghĩa với người dùng:** ví dụ thao tác tương tác cần phản hồi trong 300 ms, trong khi báo cáo lớn có thể có ngưỡng vài giây.
4. **Chia ngân sách thời gian:** phân bổ thời gian cho gateway, ứng dụng, database và dịch vụ phụ thuộc.
5. **Đo baseline:** quan sát p50, p90, p95, p99 và histogram trong điều kiện tải đại diện.
6. **Đặt mục tiêu có thể vận hành:** chọn ngưỡng và tỷ lệ good events mà đội ngũ có thể cam kết duy trì.
7. **Đánh giá lại sau thay đổi lớn:** thay đổi UX, traffic, kiến trúc hoặc dependency có thể làm ngưỡng cũ không còn phù hợp.

Ví dụ, người dùng bấm xác nhận thanh toán. Nếu trải nghiệm yêu cầu phản hồi trong 800 ms, ngân sách có thể được chia như sau:

| Thành phần | Ngân sách ví dụ |
| --- | ---: |
| Gateway và mạng nội bộ | 80 ms |
| Xử lý trong ứng dụng | 180 ms |
| Database | 220 ms |
| Dịch vụ thanh toán phụ thuộc | 220 ms |
| Dự phòng và phần phát sinh | 100 ms |
| **Tổng** | **800 ms** |

Đây là cách phân bổ để thảo luận và kiểm chứng, không phải công thức cố định. Nếu dependency chiếm phần lớn thời gian, cần đo riêng thời gian gọi dependency để biết nơi cần cải thiện.

### Chọn ngưỡng theo loại thao tác

Không nên áp cùng một ngưỡng cho mọi endpoint:

| Nhóm thao tác | Ngưỡng minh họa | Lý do |
| --- | ---: | --- |
| Đọc dữ liệu đơn giản | 200–300 ms | Người dùng cần phản hồi nhanh |
| Tìm kiếm có nhiều điều kiện | 500–800 ms | Có thể tốn thêm chi phí truy vấn |
| Xác nhận giao dịch | 800 ms–1 s | Có thể gọi dịch vụ phụ thuộc |
| Tạo báo cáo lớn | Vài giây hoặc theo deadline riêng | Công việc nặng, có thể chạy nền |

Các giá trị chỉ là ví dụ để bắt đầu thảo luận. Ngưỡng thực tế phải dựa trên yêu cầu sản phẩm, tải, dữ liệu đo và mức độ quan trọng của thao tác.

## 4. SLO, percentile và histogram trả lời các câu hỏi khác nhau

Percentile mô tả vị trí trong phân phối quan sát. Ví dụ p95 = 300 ms có nghĩa khoảng 95% quan sát nằm ở hoặc dưới mức 300 ms theo cách ước lượng của hệ thống thống kê.

SLO mô tả tỷ lệ sự kiện cần đạt một điều kiện trong một cửa sổ thời gian. Ví dụ 99,9% request thành công phải hoàn tất trong 300 ms trong 30 ngày.

| Khái niệm | Câu hỏi được trả lời |
| --- | --- |
| p50, p95, p99 | Phân phối latency đang có hình dạng ra sao? |
| Histogram | Có bao nhiêu quan sát nằm trong từng khoảng giá trị? |
| SLO threshold | Có bao nhiêu sự kiện đạt ngưỡng đã cam kết? |
| SLO target | Tỷ lệ sự kiện đạt ngưỡng cần duy trì là bao nhiêu? |

Không thể thay thế SLO bằng percentile được xuất từ từng instance. Client-side percentile thường không thể cộng gộp chính xác giữa nhiều instance. Histogram bucket có thể được cộng gộp ở backend để tính tỷ lệ hoặc ước lượng percentile trên toàn dịch vụ.

Khi mục tiêu là kiểm tra một ngưỡng cụ thể như 300 ms, hãy khai báo SLO bucket đúng tại 300 ms. Khi mục tiêu là phân tích phân phối tổng thể, có thể bật histogram và dùng percentile phù hợp. Hai cấu hình phục vụ các mục đích liên quan nhưng khác nhau.

## 5. Khai báo SLO bucket với Timer

Timer.Builder có thể nhận một hoặc nhiều ngưỡng bằng serviceLevelObjectives(Duration...). Các ngưỡng này được dùng làm bucket bổ sung trong thống kê phân phối:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
public class CheckoutMetrics {

    private final Timer paymentDuration;

    public CheckoutMetrics(MeterRegistry registry) {
        this.paymentDuration = Timer.builder("checkout.payment.duration")
            .description("Thời gian xử lý thanh toán")
            .tag("operation", "authorize")
            .serviceLevelObjectives(
                Duration.ofMillis(300),
                Duration.ofMillis(800),
                Duration.ofSeconds(1)
            )
            .register(registry);
    }

    public void record(Runnable paymentOperation) {
        paymentDuration.record(paymentOperation);
    }
}
~~~

Ví dụ tạo các ngưỡng 300 ms, 800 ms và 1 giây. Backend có thể dùng bucket tương ứng để tính số lượng quan sát nằm trong hoặc dưới từng ngưỡng. Thứ tự và cách biểu diễn bucket cụ thể phụ thuộc registry.

Lớp CheckoutMetrics ở ví dụ này minh họa Timer khi không cần phân loại outcome bằng tag. Nếu SLI phải loại request thất bại khỏi good events, dùng cách chọn Timer theo result ở ví dụ tiếp theo. Hai cách là hai lựa chọn thiết kế; không đăng ký cùng một metric name với tập key tags không nhất quán trong cùng ứng dụng.

Với DistributionSummary, ngưỡng được khai báo bằng giá trị số theo đơn vị cơ sở mà ứng dụng ghi nhận, thông qua serviceLevelObjectives(double...). Ví dụ, nếu summary ghi kích thước payload theo byte:

~~~java
DistributionSummary payloadSize = DistributionSummary
    .builder("uploads.payload.size")
    .baseUnit("bytes")
    .serviceLevelObjectives(
        64 * 1024,
        256 * 1024,
        1024 * 1024
    )
    .register(registry);
~~~

Các ngưỡng trên tương ứng 64 KiB, 256 KiB và 1 MiB. Hãy thống nhất đơn vị khi gọi record(value), đặt baseUnit để mô tả đại lượng và không trộn byte với kilobyte trong cùng một meter.

Nếu cần phân loại theo outcome, hãy đăng ký Timer riêng theo tag result hoặc dùng Timer.Sample để chọn Timer sau khi kết quả đã rõ. Không ghi mọi request vào Timer gắn result=success nếu một phần request có thể thất bại.

Ví dụ ghi nhận kết quả với outcome:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    paymentGateway.authorize(command);
    sample.stop(paymentTimer("success"));
} catch (PaymentGatewayException ex) {
    sample.stop(paymentTimer("failure"));
    throw ex;
}
~~~

Hàm paymentTimer tạo hoặc tra cứu Timer theo outcome và áp dụng cùng SLO buckets cho mọi outcome:

~~~java
private Timer paymentTimer(String result) {
    return Timer.builder("checkout.payment.duration")
        .tag("operation", "authorize")
        .tag("result", result)
        .serviceLevelObjectives(
            Duration.ofMillis(300),
            Duration.ofMillis(800),
            Duration.ofSeconds(1)
        )
        .register(registry);
}
~~~

Trong ứng dụng thực tế, cần cấu hình cùng SLO buckets cho các meter có cùng mục tiêu và cùng cách diễn giải. Hãy giữ tags có cardinality thấp.

## 6. Cấu hình SLO trong Spring Boot

Với Spring Boot Actuator, có thể cấu hình SLO thresholds theo tên meter trong application.properties:

~~~properties
management.metrics.distribution.slo.checkout.payment.duration=300ms,800ms,1s
management.metrics.distribution.percentiles-histogram.checkout.payment.duration=true
management.metrics.distribution.percentiles.checkout.payment.duration=0.5,0.95,0.99
~~~

Ba cấu hình có mục đích khác nhau:

- distribution.slo khai báo các ranh giới SLO cần có trong histogram.
- distribution.percentiles-histogram bật histogram phù hợp với việc tổng hợp ở backend.
- distribution.percentiles yêu cầu Micrometer xuất các percentile tính phía ứng dụng nếu registry hỗ trợ.

Không nhất thiết phải bật tất cả. Nếu chỉ cần tỷ lệ đạt các ngưỡng đã định nghĩa và backend hỗ trợ SLO buckets, cấu hình SLO buckets có thể là đủ. Bật thêm histogram hoặc percentile sẽ tăng lượng dữ liệu và chi phí, nên chọn theo nhu cầu truy vấn.

Tên property cần khớp với tên meter được đăng ký trong ứng dụng. Khi dùng naming convention của registry, tên hiển thị ở backend có thể khác tên trong code.

## 7. Tính tỷ lệ đạt ngưỡng từ histogram

Với Prometheus classic histogram, mỗi bucket có label le (less than or equal). Bucket tại le=0.3 đếm số quan sát có giá trị không quá 0,3 giây. Các bucket là cumulative: bucket ở ngưỡng lớn hơn bao gồm cả quan sát ở các ngưỡng nhỏ hơn.

Giả sử metric Timer được xuất thành checkout_payment_duration_seconds và tag result phân biệt success/failure. Tỷ lệ request thành công trong 300 ms có thể được tính bằng:

~~~promql
sum(rate(checkout_payment_duration_seconds_bucket{le="0.3", result="success"}[30m]))
/
sum(rate(checkout_payment_duration_seconds_count[30m]))
~~~

Tử số là tốc độ request thành công có duration không quá 300 ms; mẫu số là tốc độ tất cả request đủ điều kiện trong cùng cửa sổ. Nhân kết quả với 100 nếu muốn hiển thị phần trăm.

Truy vấn cần được điều chỉnh theo tên series, label và cách export thực tế. Nếu metric dùng tags operation hoặc service, hãy lọc cùng phạm vi ở cả tử số và mẫu số. Không lọc mẫu số theo result=success nếu mục tiêu là coi request thất bại là bad event.

Nếu đang dùng histogram khác hoặc native histogram, cú pháp truy vấn có thể khác. Hãy kiểm tra exposition và loại histogram backend nhận trước khi đưa truy vấn vào dashboard hoặc alert.

### Ví dụ tính error budget

Giả sử SLO yêu cầu 99,9% request đủ điều kiện đạt ngưỡng. Tỷ lệ không đạt cho phép là:

\[
100\%-99.9\%=0.1\%
\]

Nếu có 1.000.000 request đủ điều kiện trong cửa sổ đánh giá, ngân sách lỗi tương ứng là:

\[
1{,}000{,}000 \times 0.1\%=1{,}000
\]

Đội ngũ có thể có tối đa 1.000 bad events trong ví dụ này trước khi vi phạm mục tiêu. Khi error budget bị tiêu thụ nhanh, cần ưu tiên ổn định dịch vụ và giảm rủi ro phát hành.

## 8. Chọn cửa sổ đánh giá và theo dõi error budget

SLO luôn cần một cửa sổ đánh giá. Hai kiểu phổ biến:

- **Rolling window:** ví dụ 30 ngày gần nhất, cập nhật liên tục. Cách này phản ánh tình trạng hiện tại và phù hợp với nhiều dashboard vận hành.
- **Calendar window:** ví dụ tháng dương lịch hoặc quý. Cách này phù hợp khi báo cáo theo kỳ hoặc hợp đồng yêu cầu mốc thời gian cố định.

Hãy chọn cửa sổ theo cách đội ngũ ra quyết định. Cửa sổ quá ngắn dễ dao động khi traffic thấp; cửa sổ quá dài có thể làm một đợt suy giảm mới bị che khuất bởi lịch sử tốt trước đó.

Error budget là phần sự kiện không đạt được phép trong cửa sổ SLO. Nếu SLO là 99,9%, error budget là 0,1%. Có thể theo dõi:

- Budget còn lại.
- Tốc độ tiêu thụ budget (burn rate).
- Dự báo thời điểm budget sẽ cạn nếu tốc độ hiện tại tiếp tục.
- Số lượng bad events và nguyên nhân chính.

Không chỉ cảnh báo khi SLO đã vi phạm. Burn-rate alert giúp phát hiện khi hệ thống đang tiêu thụ budget nhanh bất thường, để đội ngũ can thiệp trước khi hết ngân sách.

## 9. Chọn SLO buckets và quản lý cardinality

Mỗi SLO threshold bổ sung một bucket cho metric. Nếu khai báo quá nhiều ngưỡng cho hàng nghìn tổ hợp tags, số chuỗi thời gian và chi phí lưu trữ sẽ tăng đáng kể.

Nên:

- Chỉ chọn các ngưỡng gắn với quyết định vận hành hoặc cam kết sản phẩm.
- Dùng một vài ngưỡng có ý nghĩa thay vì tạo bucket cho mọi giá trị có thể.
- Dùng route template, operation và result có tập giá trị hữu hạn.
- Không thêm user ID, request ID, order ID hoặc URL thô vào tags.
- Tránh tạo SLO riêng cho từng khách hàng nếu không có yêu cầu rõ ràng và giới hạn cardinality.

Ví dụ, một service có thể theo dõi các ngưỡng 300 ms và 800 ms cho thao tác tương tác. Không cần khai báo thêm các ngưỡng 310, 320, 330 ms nếu chúng không tương ứng với quyết định sản phẩm hoặc cảnh báo.

Với nhiều loại thao tác có đặc tính khác nhau, có thể tạo meter riêng hoặc dùng tag operation có tập giá trị nhỏ. Mỗi SLO cần xác định rõ tập request thuộc phạm vi và cách xử lý outcome.

## 10. Kiểm thử SLO configuration

SimpleMeterRegistry có thể kiểm tra Timer ghi nhận count và thời gian, nhưng không đại diện đầy đủ cho định dạng histogram của backend. Kiểm thử nên chia thành hai lớp:

**Unit test:** kiểm tra instrumentation ghi nhận đúng meter, tags và kết quả.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

class CheckoutMetricsTest {

    @Test
    void recordsSuccessfulPaymentDuration() {
        MeterRegistry registry = new SimpleMeterRegistry();
        Timer timer = Timer.builder("checkout.payment.duration")
            .tag("result", "success")
            .serviceLevelObjectives(
                Duration.ofMillis(300),
                Duration.ofMillis(800)
            )
            .register(registry);

        timer.record(Duration.ofMillis(250));

        assertThat(timer.count()).isEqualTo(1L);
        assertThat(timer.totalTime(java.util.concurrent.TimeUnit.MILLISECONDS))
            .isEqualTo(250.0);

        registry.close();
    }
}
~~~

**Integration test:** dùng registry/exporter thực tế để xác minh endpoint có các bucket tại đúng ngưỡng, tên metric và tags được chuyển đổi như mong muốn. Với Prometheus, kiểm tra exposition có bucket le tương ứng, sau đó chạy truy vấn SLI trên dữ liệu thử nghiệm.

Các trường hợp nên kiểm tra:

- Quan sát nhỏ hơn ngưỡng được tính vào bucket tương ứng.
- Quan sát bằng đúng ngưỡng được tính vào bucket le đó.
- Quan sát lớn hơn ngưỡng không được tính vào bucket thấp hơn.
- Request thất bại không được tính là good event nếu SLI yêu cầu thành công.
- Tử số và mẫu số dùng cùng tập request đủ điều kiện.
- Meter được xuất với tags có cardinality hữu hạn.

## 11. Những sai lầm thường gặp khi đặt SLO

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chọn ngưỡng chỉ vì p95 hiện tại đang ở mức đó | Mục tiêu chỉ phản ánh baseline, không phản ánh trải nghiệm cần đạt | Bắt đầu từ yêu cầu người dùng và ngân sách latency |
| Dùng percentile client-side để cộng gộp nhiều instance | Kết quả tổng thể không chính xác | Dùng histogram buckets có thể tổng hợp |
| Không khai báo bucket tại ngưỡng SLO | Không thể tính chính xác tỷ lệ quan sát dưới ngưỡng từ bucket đó | Thêm serviceLevelObjectives đúng ngưỡng |
| Tính request lỗi nhanh là good event | SLI bị lạc quan giả tạo | Đưa điều kiện success vào định nghĩa good event |
| Dùng mẫu số khác phạm vi tử số | Tỷ lệ SLI sai | Định nghĩa cùng tập request đủ điều kiện |
| Tạo quá nhiều SLO buckets và tags | Cardinality và chi phí tăng | Chỉ giữ ngưỡng, chiều phân tích có ý nghĩa |
| Chỉ kiểm tra dashboard sau khi triển khai | Có thể phát hiện muộn khi bucket hoặc tag sai | Kiểm tra exposition và truy vấn trong integration test |

## 12. Quy trình lựa chọn và triển khai SLO

Khi thêm SLO cho một metric:

1. Chọn hành trình hoặc thao tác mà người dùng quan tâm.
2. Định nghĩa SLI bằng good events và total eligible events.
3. Chọn latency threshold theo trải nghiệm, ngân sách thời gian và dữ liệu baseline.
4. Chọn target và cửa sổ đánh giá, ví dụ 99,9% trong 30 ngày.
5. Khai báo ngưỡng bằng serviceLevelObjectives trên Timer hoặc cấu hình distribution.slo của Spring Boot.
6. Bật histogram nếu backend cần tổng hợp buckets hoặc tính percentile.
7. Viết truy vấn tính tỷ lệ đạt ngưỡng và error budget.
8. Tạo dashboard và burn-rate alert phù hợp.
9. Kiểm tra cardinality, exposition và hành vi với request thành công/thất bại.
10. Định kỳ xem lại SLO khi trải nghiệm, tải hoặc kiến trúc dịch vụ thay đổi.

Một SLO hữu ích phải gắn với trải nghiệm người dùng và cách đội ngũ phản ứng khi mục tiêu bị đe dọa. Micrometer cung cấp các bucket và số đo để tính SLI; việc chọn good event, threshold, target và cửa sổ thời gian vẫn là quyết định sản phẩm và vận hành. Khi các định nghĩa này rõ ràng, dashboard và alert sẽ giúp đội ngũ bảo vệ độ tin cậy thay vì chỉ hiển thị những con số latency.
