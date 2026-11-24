# expiry, bufferLength và thời gian sống của thống kê theo cửa sổ

Micrometer có thể duy trì một số thống kê phân phối theo cửa sổ thời gian thay vì giữ mãi giá trị lớn nhất hoặc phân phối của toàn bộ vòng đời ứng dụng. Hai cấu hình quan trọng điều khiển cửa sổ này là **expiry** và **bufferLength**. Hiểu đúng hai tham số giúp diễn giải max và percentile, chọn khoảng thời gian phù hợp với nhịp đo, đồng thời tránh nhầm lẫn giữa thời gian sống của thống kê trong ứng dụng với thời gian lưu metrics ở backend.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, Timer và DistributionSummary có thể cung cấp count, tổng giá trị, max, histogram và percentile. Một số thống kê như max và percentile phía ứng dụng sử dụng dữ liệu theo cửa sổ. Bài này giải thích cách cửa sổ hoạt động, ảnh hưởng của expiry và bufferLength, cấu hình trong Micrometer/Spring Boot và cách kiểm tra khi số liệu thay đổi hoặc trở về 0.

## 1. Thống kê theo cửa sổ là gì?

Giả sử một dịch vụ ghi nhận kích thước payload theo các giá trị: 100, 200, 500, 900 và 1.500 byte. Ứng dụng có thể cần biết:

- Có bao nhiêu payload đã được ghi nhận?
- Tổng số byte đã xử lý là bao nhiêu?
- Payload lớn nhất trong khoảng thời gian gần đây là bao nhiêu?
- p95 của kích thước payload trong khoảng thời gian gần đây là bao nhiêu?

Count và tổng giá trị có thể được tích lũy theo cách phụ thuộc loại registry và temporality của backend. Max và percentile phía ứng dụng thường cần một vùng dữ liệu hữu hạn để phản ánh tình trạng gần đây. Nếu max giữ giá trị lớn nhất mãi mãi, một payload bất thường từ nhiều giờ trước vẫn có thể chi phối dashboard dù hệ thống đã ổn định.

Thống kê theo cửa sổ (time-window statistics) giữ dữ liệu trong một khoảng thời gian giới hạn. Khi cửa sổ dịch chuyển, phần dữ liệu cũ dần bị loại khỏi thống kê. Nhờ vậy, max và percentile phản ánh hành vi gần đây thay vì toàn bộ lịch sử từ lúc ứng dụng khởi động.

## 2. expiry xác định thời lượng của mỗi phần cửa sổ

**expiry** là thời lượng của một phần trong bộ đệm xoay vòng dùng cho thống kê theo cửa sổ. Khi hết một khoảng expiry, Micrometer chuyển sang phần kế tiếp và phần dữ liệu cũ sẽ dần bị loại khỏi phép tính khi bộ đệm xoay vòng hoàn tất chu kỳ.

Ví dụ, expiry được đặt là 30 giây. Bộ đệm có thể xoay qua từng khoảng 30 giây; thống kê không giữ mãi mọi mẫu đã ghi nhận.

Expiry ảnh hưởng đến tốc độ thống kê thích nghi với dữ liệu mới:

- Expiry ngắn làm dữ liệu cũ rời cửa sổ nhanh hơn, nên max và percentile phản ánh thay đổi gần đây nhanh hơn.
- Expiry dài giữ dữ liệu trong từng phần cửa sổ lâu hơn, làm thống kê ổn định hơn nhưng chậm phản ánh sự thay đổi mới.
- Nếu dữ liệu mới ngừng xuất hiện, thống kê time-window có thể dần hết mẫu và max có thể trở về 0 sau khi toàn bộ cửa sổ đã trôi qua.

Không nên hiểu expiry là thời gian sống của meter hoặc thời hạn lưu toàn bộ time series. Meter vẫn có thể tồn tại và tiếp tục nhận mẫu sau khi cửa sổ thống kê cũ hết hạn.

## 3. bufferLength xác định số phần cửa sổ được giữ

**bufferLength** là số phần (slot) trong bộ đệm xoay vòng. Nó không phải số lượng mẫu tối đa và cũng không phải giới hạn số request được ghi nhận.

Với expiry và bufferLength, tổng độ dài cửa sổ xấp xỉ:

\[
\text{time window} = \text{expiry} \times \text{bufferLength}
\]

Ví dụ:

| expiry | bufferLength | Tổng cửa sổ |
|---|---:|---:|
| 10 giây | 3 | 30 giây |
| 30 giây | 3 | 90 giây |
| 30 giây | 4 | 120 giây |
| 1 phút | 5 | 5 phút |

Nếu expiry là 30 giây và bufferLength là 4, thống kê giữ dữ liệu trong cửa sổ khoảng hai phút. Khi bộ đệm xoay vòng, các phần cũ lần lượt bị thay thế.

Tăng bufferLength kéo dài thời gian dữ liệu được xem xét. Điều này có thể làm max và percentile mượt hơn trước biến động ngắn, nhưng cũng khiến thống kê phản ứng chậm hơn khi workload đã thay đổi. Bộ đệm lớn hơn có thể cần thêm bộ nhớ, đặc biệt khi bật histogram và có nhiều meter hoặc nhiều tổ hợp tag.

## 4. Giá trị mặc định và cách tính cửa sổ

Trong Micrometer, expiry mặc định thường là step size đối với step registry; với registry không theo step, mặc định thường là hai phút. bufferLength mặc định là 3. Vì vậy, tổng cửa sổ mặc định phụ thuộc loại registry và cấu hình step của nó.

Ví dụ:

- Registry không theo step với expiry mặc định hai phút và bufferLength 3 có cửa sổ khoảng sáu phút.
- Step registry có step một phút và bufferLength 3 có cửa sổ khoảng ba phút.

Đây là giá trị mặc định của cấu hình phân phối, không phải cam kết về thời gian lưu dữ liệu trong backend. Hãy kiểm tra loại registry và step đang sử dụng trước khi suy ra tổng cửa sổ thực tế.

Step là nhịp xuất dữ liệu của một số registry. Expiry là độ dài từng phần của bộ đệm thống kê. Hai giá trị có thể liên quan vì expiry mặc định của step registry thường lấy step size, nhưng chúng vẫn là hai khái niệm khác nhau.

## 5. Ảnh hưởng đến max và percentile

### Max là giá trị lớn nhất trong cửa sổ

Max của Timer hoặc DistributionSummary thường là time-window max. Ví dụ, ứng dụng ghi nhận kích thước payload 100, 200 và 2.000 byte. Trong cửa sổ hiện tại, max là 2.000. Sau khi mẫu 2.000 byte hết hạn khỏi cửa sổ và không còn mẫu lớn hơn, max có thể giảm xuống 200 hoặc 0 nếu cửa sổ không còn mẫu.

Vì vậy, max trở về 0 không nhất thiết có nghĩa payload hiện tại có kích thước bằng 0. Nó có thể có nghĩa là cửa sổ thống kê không còn mẫu hợp lệ. Khi diễn giải dashboard, cần phân biệt "giá trị lớn nhất trong cửa sổ" với "giá trị lớn nhất kể từ khi tiến trình khởi động".

### Percentile phía ứng dụng cũng có thời gian sống hữu hạn

Khi bật publishPercentiles, Micrometer tính percentile ở phía ứng dụng. Phân phối dùng để tính percentile được duy trì trong bộ đệm thời gian; expiry và bufferLength ảnh hưởng đến lượng dữ liệu còn tham gia phép tính.

Ví dụ p95 của payload trong cửa sổ gần đây có thể thay đổi khi các mẫu cũ hết hạn và mẫu mới được ghi nhận. Nếu không còn mẫu trong cửa sổ, percentile có thể không có giá trị hữu ích để xuất.

Percentile cục bộ của từng instance không thể cộng hoặc lấy trung bình để tạo percentile chính xác của toàn cụm. Nếu cần tổng hợp phân phối giữa nhiều instance, hãy cân nhắc publishPercentileHistogram để backend tổng hợp bucket rồi tính percentile.

### Histogram xuất cho backend cần được phân biệt với percentile cục bộ

Histogram bucket được xuất đến backend như Prometheus có thể được lưu và truy vấn theo chính sách của backend. Ví dụ, Prometheus lưu các mẫu bucket và truy vấn rate trong cửa sổ năm phút hoặc một giờ. Khoảng truy vấn đó do PromQL lựa chọn; nó không phải expiry của bộ đệm percentile trong Micrometer.

Expiry và bufferLength điều khiển các thống kê time-window do Micrometer duy trì. Chúng không tự xóa dữ liệu lịch sử đã được Prometheus, Mimir, Thanos hoặc backend khác lưu trữ. Retention của backend là cấu hình độc lập.

## 6. Count và totalAmount khác với time-window max

Không nên cho rằng mọi thống kê của Timer hoặc DistributionSummary đều hết hạn theo cùng cách.

- Count và totalAmount là các thống kê tích lũy của meter theo semantics của registry.
- Với cumulative registry, count và sum thường tăng theo thời gian trong vòng đời tiến trình.
- Với step registry, số liệu được xuất theo từng step và có thể được reset/roll sang step tiếp theo theo semantics của registry.
- Max và percentile phía ứng dụng có thể được duy trì theo cửa sổ expiry nhân bufferLength.

Điều này giải thích vì sao một dashboard có thể vẫn thấy count và sum tăng trong khi max đã trở về 0 sau khi cửa sổ max không còn mẫu. Đây không nhất thiết là lỗi dữ liệu; các trường đang mô tả những khoảng thời gian và semantics khác nhau.

Khi phân tích, hãy đọc loại registry, loại statistic và cách backend biểu diễn metric. Không so sánh trực tiếp một max theo cửa sổ với tổng count tích lũy như thể chúng cùng một vòng đời.

## 7. Cấu hình expiry và bufferLength bằng Micrometer

Có thể đặt cấu hình trực tiếp trên builder của Timer hoặc DistributionSummary:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public class PayloadMetrics {
    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary
                .builder("message.payload.size")
                .description("Message payload size")
                .baseUnit("bytes")
                .distributionStatisticExpiry(Duration.ofSeconds(30))
                .distributionStatisticBufferLength(4)
                .publishPercentiles(0.50, 0.95, 0.99)
                .register(registry);
    }

    public void record(byte[] payload) {
        payloadSize.record(payload.length);
    }
}
~~~

Cấu hình này dùng expiry 30 giây và bufferLength 4, tạo cửa sổ thống kê khoảng hai phút cho các thống kê time-window tương ứng. Meter được đăng ký một lần và được tái sử dụng khi ghi nhận payload.

Với Timer, có thể áp dụng cùng cấu hình:

~~~java
Timer requestTimer = Timer.builder("api.request.duration")
        .description("API request processing duration")
        .distributionStatisticExpiry(Duration.ofSeconds(20))
        .distributionStatisticBufferLength(3)
        .publishPercentiles(0.50, 0.95, 0.99)
        .register(registry);
~~~

Ở ví dụ này, cửa sổ thống kê tương ứng khoảng một phút. Hãy chọn khoảng thời gian theo tần suất traffic và mục tiêu quan sát; một cửa sổ quá ngắn với traffic thấp có thể thường xuyên không có đủ mẫu để tạo percentile ổn định.

## 8. Cấu hình chung trong Spring Boot

Spring Boot Actuator hỗ trợ cấu hình thống kê phân phối qua application.yml. Ví dụ:

~~~yaml
management:
  metrics:
    distribution:
      expiry: 30s
      buffer-length: 4
      percentiles:
        message.payload.size: 0.5, 0.95, 0.99
      percentiles-histogram:
        api.request.duration: true
~~~

Trong cấu hình này:

- expiry là thời lượng của mỗi phần cửa sổ.
- buffer-length là số phần trong bộ đệm xoay vòng.
- percentiles yêu cầu các percentile tính phía ứng dụng cho meter được chọn.
- percentiles-histogram bật histogram để backend có thể tổng hợp phân phối.

Cấu hình phân phối chung có thể áp dụng cho nhiều meter. Nếu chỉ một meter cần cửa sổ hoặc percentile riêng, có thể dùng builder hoặc MeterFilter để giới hạn cấu hình. Tránh bật histogram cho tất cả metrics khi chưa đánh giá số bucket và cardinality.

Tên thuộc tính và cách cấu hình theo meter có thể phụ thuộc phiên bản Spring Boot/Micrometer. Hãy đối chiếu với phiên bản dependency đang dùng khi áp dụng trong dự án.

## 9. Chọn expiry và bufferLength theo mục tiêu vận hành

Không có một cấu hình phù hợp cho mọi loại metric. Cần chọn cửa sổ dựa trên nhịp hoạt động và câu hỏi mà dashboard cần trả lời.

| Nhu cầu | Hướng chọn | Lý do |
|---|---|---|
| Phát hiện payload lớn đột biến trong thời gian ngắn | expiry ngắn, bufferLength vừa phải | Max và percentile phản ánh thay đổi gần đây nhanh |
| Theo dõi batch size với traffic thưa | Cửa sổ dài hơn | Tăng khả năng có đủ mẫu cho percentile |
| Theo dõi latency của API có traffic cao | Cửa sổ theo step hoặc vài phút | Cân bằng độ nhạy và độ ổn định |
| Dashboard cần percentile tổng hợp nhiều instance | Bật histogram và chọn bucket hợp lý | Backend có thể tổng hợp bucket |
| Giảm bộ nhớ cho số lượng meter lớn | Giới hạn histogram, bucket và bufferLength | Tránh nhân chi phí trên nhiều meter/tag |

Một quy trình chọn cấu hình thực tế:

1. Xác định metric đang đo đại lượng nào và đơn vị gì.
2. Xác định traffic trung bình và khoảng thời gian thường có mẫu mới.
3. Xác định dashboard cần phản ứng nhanh hay cần đường biểu diễn ổn định.
4. Chọn expiry và bufferLength để tạo cửa sổ phù hợp.
5. Đo chi phí bộ nhớ và số series sau khi bật histogram.
6. Kiểm tra max/percentile trong cả giai đoạn có traffic và giai đoạn ít hoặc không có traffic.

Nếu traffic rất thưa, percentile của cửa sổ ngắn có thể không ổn định hoặc không có mẫu. Tăng cửa sổ có thể giúp giữ đủ dữ liệu, nhưng sẽ làm phản ứng chậm hơn trước thay đổi. Hãy chọn theo mục tiêu quan sát thay vì chỉ tăng mọi tham số để tránh khoảng trống.

## 10. Kiểm thử thời gian sống của thống kê

Không nên chỉ kiểm thử một giá trị max ngay sau khi record rồi kết luận cấu hình cửa sổ hoạt động đúng. Cần kiểm tra hành vi sau khi thời gian trôi qua và khi có mẫu mới.

Có thể dùng clock giả trong kiểm thử để điều khiển thời gian mà không phải chờ thật. Ví dụ minh họa với MockClock và SimpleMeterRegistry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class DistributionWindowTest {

    @Test
    void maxExpiresAfterTheConfiguredWindow() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);

        DistributionSummary summary = DistributionSummary.builder("payload.size")
                .distributionStatisticExpiry(Duration.ofSeconds(10))
                .distributionStatisticBufferLength(2)
                .register(registry);

        summary.record(900);
        assertThat(summary.max()).isEqualTo(900.0);

        clock.add(Duration.ofSeconds(21));
        assertThat(summary.max()).isZero();

        registry.close();
    }
}
~~~

Ví dụ minh họa kiểm tra max sau khi toàn bộ cửa sổ khoảng 20 giây đã trôi qua. API MockClock và constructor registry có thể khác theo phiên bản Micrometer; hãy xác minh chữ ký API của dependency đang dùng. Không dựa vào System.gc() để kiểm thử expiry vì garbage collection và thời gian của bộ đệm là hai cơ chế khác nhau.

Các tình huống nên kiểm thử:

- Max phản ánh mẫu lớn nhất trong cửa sổ còn hiệu lực.
- Max hết hạn khi toàn bộ cửa sổ đã trôi qua mà không có mẫu mới.
- Mẫu mới sau khi cửa sổ cũ hết hạn được ghi nhận bình thường.
- Percentile có hành vi phù hợp khi cửa sổ còn mẫu và khi cửa sổ không còn mẫu.
- Count và totalAmount có semantics phù hợp với registry đang dùng.
- Cấu hình chung và cấu hình riêng theo meter không vô tình ghi đè ngoài dự kiến.

## 11. Phân biệt expiry với các mốc thời gian khác

Các khoảng thời gian trong pipeline metrics có thể cùng tồn tại nhưng không thay thế nhau:

| Khái niệm | Thành phần quản lý | Ý nghĩa |
|---|---|---|
| expiry | Micrometer | Thời lượng mỗi phần của cửa sổ thống kê |
| bufferLength | Micrometer | Số phần cửa sổ được giữ |
| expiry × bufferLength | Micrometer | Độ dài cửa sổ time-window |
| step | Step registry | Chu kỳ xuất/luân chuyển số liệu của registry |
| scrape interval | Prometheus | Tần suất Prometheus đọc endpoint |
| query range | PromQL | Khoảng dữ liệu được dùng trong một truy vấn như rate(...[5m]) |
| retention | Metrics backend | Thời gian backend giữ dữ liệu lịch sử |

Ví dụ, Micrometer có cửa sổ max hai phút, Prometheus scrape mỗi 15 giây và backend giữ dữ liệu 30 ngày. Ba mốc này phục vụ ba việc khác nhau: tính thống kê gần đây trong ứng dụng, thu thập dữ liệu và lưu lịch sử để truy vấn.

Nếu max trở về 0 sau khi cửa sổ hết hạn, backend vẫn có thể lưu các mẫu max trước đó trong lịch sử. Có thể truy vấn lịch sử để xem max đã từng đạt bao nhiêu, miễn là series được xuất và backend còn giữ dữ liệu.

## 12. Chẩn đoán khi max hoặc percentile thay đổi bất thường

Khi dashboard cho thấy max đột ngột về 0 hoặc percentile biến mất, kiểm tra theo thứ tự:

1. Xác định meter có tiếp tục được ghi nhận hay không bằng count hoặc log instrumentation.
2. Kiểm tra expiry và bufferLength thực tế của meter; xem cấu hình chung có bị cấu hình riêng ghi đè không.
3. Tính lại độ dài cửa sổ bằng expiry nhân bufferLength.
4. Xác định khoảng thời gian từ lần record cuối cùng đến thời điểm quan sát.
5. Kiểm tra loại registry và step size, đặc biệt nếu expiry đang dùng giá trị mặc định.
6. Kiểm tra endpoint export và backend để phân biệt statistic không còn mẫu với scrape thất bại.
7. Kiểm tra query range và time range của dashboard; không nhầm cửa sổ Micrometer với cửa sổ PromQL.
8. Nếu percentile phía ứng dụng không có giá trị nhưng histogram bucket vẫn có dữ liệu, xác định hai cơ chế đang được cấu hình và truy vấn riêng.

Một max bằng 0 có thể là kết quả hợp lệ của cửa sổ không còn mẫu. Một percentile trống có thể do không có đủ mẫu trong cửa sổ hoặc do meter không xuất percentile. Nếu toàn bộ metrics mất cùng lúc, hãy kiểm tra ứng dụng, endpoint và collector trước khi kết luận expiry là nguyên nhân.

## 13. Checklist cấu hình cửa sổ phân phối

Trước khi đưa expiry và bufferLength vào production, xác nhận:

- Đã xác định statistic nào là time-window và statistic nào có semantics tích lũy/step.
- Đã hiểu expiry là độ dài mỗi slot, không phải TTL của meter.
- Đã hiểu bufferLength là số slot, không phải số mẫu tối đa.
- Đã tính tổng cửa sổ bằng expiry nhân bufferLength.
- Đã xem xét step size của registry và traffic của meter.
- Đã chọn percentile cục bộ hay histogram tổng hợp theo nhu cầu.
- Đã đánh giá bộ nhớ và cardinality khi tăng buffer hoặc bật histogram.
- Đã kiểm thử max/percentile sau khi thời gian cửa sổ trôi qua.
- Đã tách expiry khỏi scrape interval, query range và retention của backend.

expiry và bufferLength giúp kiểm soát khoảng thời gian mà thống kê phân phối trong Micrometer phản ánh. Khi hiểu rõ mỗi slot, số slot và loại statistic bị ảnh hưởng, có thể chọn cửa sổ đủ nhạy để phát hiện thay đổi nhưng vẫn ổn định với nhịp traffic. Đồng thời, việc phân biệt cửa sổ trong ứng dụng với chu kỳ scrape và retention ở backend giúp tránh chẩn đoán nhầm khi max hoặc percentile hết hạn.
