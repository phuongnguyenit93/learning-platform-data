# minimumExpectedValue và maximumExpectedValue trong điều khiển độ chi tiết

Micrometer hỗ trợ thu thập phân phối của thời lượng và các đại lượng số thông qua histogram, percentile và service level objective (SLO). Hai cấu hình minimumExpectedValue và maximumExpectedValue xác định khoảng giá trị kỳ vọng mà histogram phân phối cần bao phủ. Chọn khoảng này phù hợp giúp cân bằng độ chi tiết của dữ liệu, chi phí bộ nhớ và số lượng time series.

Hai cấu hình này không phải ngưỡng kiểm tra dữ liệu đầu vào và cũng không thay thế SLO. Chúng định hướng phạm vi của histogram. Muốn biết request có vượt 300 ms hay không, hãy cấu hình một SLO boundary tương ứng; muốn từ chối payload quá lớn, hãy kiểm tra payload trong logic ứng dụng.

## 1. Histogram, bucket và độ chi tiết

Histogram chia miền giá trị thành các khoảng (bucket). Mỗi bucket cho biết có bao nhiêu quan sát nằm trong hoặc thấp hơn một ranh giới nhất định, tùy quy ước của backend. Từ các bucket, hệ thống giám sát có thể tính gần đúng phân vị như p90, p95 hoặc p99 trên tập dữ liệu được tổng hợp.

Ví dụ histogram thời gian xử lý request có thể có các ranh giới:

~~~text
<= 10 ms
<= 25 ms
<= 50 ms
<= 100 ms
<= 250 ms
<= 500 ms
<= 1 s
+Inf
~~~

Nếu bucket quá thưa trong vùng latency quan trọng, phân vị có thể kém chính xác. Nếu tạo quá nhiều bucket trên một miền quá rộng, chi phí bộ nhớ, scrape, lưu trữ và truy vấn sẽ tăng.

minimumExpectedValue và maximumExpectedValue giúp giới hạn khoảng mà histogram percentile được thiết kế để bao phủ. Với percentile histogram, Micrometer tạo các bucket theo cấu hình và implementation của registry. Khoảng kỳ vọng càng rộng thường cần nhiều bucket hơn để bao phủ miền giá trị đó.

Có thể hình dung:

~~~text
Miền giá trị đo được
0 ------------------------------------------------------------>

Khoảng kỳ vọng hẹp:
        [ min ---------------- max ]
        bucket tập trung quanh vùng quan tâm

Khoảng kỳ vọng rộng:
[ min ----------------------------------------------------- max ]
        cần bao phủ thêm nhiều giá trị ở vùng xa
~~~

Độ chi tiết không chỉ phụ thuộc min/max. Nó còn phụ thuộc thuật toán histogram, backend registry, cấu hình percentile histogram, các SLO boundary và cách backend tổng hợp bucket.

## 2. Ý nghĩa của minimumExpectedValue và maximumExpectedValue

### minimumExpectedValue

minimumExpectedValue là giá trị thấp nhất mà ứng dụng dự kiến quan sát trong phân phối. Với Timer, giá trị được truyền dưới dạng Duration. Với DistributionSummary, giá trị được truyền theo đơn vị số mà summary đang ghi nhận.

Ví dụ, nếu đo thời gian xử lý API và các request hợp lệ thường mất từ khoảng 1 ms trở lên:

~~~java
Timer.builder("api.request.duration")
    .minimumExpectedValue(Duration.ofMillis(1))
    .register(registry);
~~~

Nếu đặt min quá cao so với dữ liệu thực tế, vùng latency rất thấp có thể không được phân chia theo độ chi tiết mong muốn. Hãy chọn min dựa trên độ phân giải cần quan sát và dữ liệu thực tế, không dựa trên một con số tùy ý.

### maximumExpectedValue

maximumExpectedValue là giá trị cao nhất mà ứng dụng dự kiến histogram cần bao phủ chi tiết.

~~~java
Timer.builder("api.request.duration")
    .maximumExpectedValue(Duration.ofSeconds(5))
    .register(registry);
~~~

Nếu request bình thường hoàn tất dưới 5 giây nhưng một số request có thể kéo dài đến vài phút, hãy cân nhắc liệu dashboard có cần phân biệt chi tiết vùng trên 5 giây hay không. Nếu có, cần tăng max hoặc thiết kế một metric chuyên biệt cho tác vụ dài.

Đặt max quá thấp có thể làm histogram không có đủ bucket chi tiết cho vùng latency cao. Các quan sát vượt phạm vi kỳ vọng không nên bị hiểu là đã bị validation từ chối hoặc bị xóa khỏi nghiệp vụ; min/max là cấu hình phân phối, không phải cơ chế giới hạn request. Với histogram Prometheus, bucket +Inf vẫn bao gồm các quan sát lớn hơn những bucket hữu hạn; tuy nhiên, histogram không có các ranh giới hữu hạn bổ sung để phân biệt chi tiết vùng trên max. Hành vi cụ thể của các thống kê khác phụ thuộc implementation và backend, nên cần xác minh output thực tế của registry đang dùng.

### Min/max không phải hai ngưỡng SLO

Hai cấu hình này trả lời câu hỏi: “Histogram cần bao phủ khoảng giá trị nào?”

SLO trả lời câu hỏi: “Có bao nhiêu lần quan sát nằm trong giới hạn nghiệp vụ cụ thể?”

Ví dụ:

- Min/max kỳ vọng: 1 ms đến 5 s để thiết lập miền histogram.
- SLO: 100 ms, 300 ms và 1 s để theo dõi các ngưỡng latency quan trọng.
- Validation: từ chối request nếu payload vượt kích thước cho phép; đây là quy tắc nghiệp vụ riêng.

Không dùng maximumExpectedValue thay cho timeout hoặc validation. Một request mất 20 giây không tự động bị dừng chỉ vì histogram được cấu hình max 5 giây.

## 3. Cấu hình cho Timer

Timer ghi nhận thời lượng và số lần hoàn tất. Các giá trị min/max của Timer được cấu hình bằng Duration để tránh nhầm lẫn đơn vị.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

Timer requestTimer = Timer.builder("api.request.duration")
    .description("Thời gian xử lý request API")
    .publishPercentileHistogram()
    .minimumExpectedValue(Duration.ofMillis(1))
    .maximumExpectedValue(Duration.ofSeconds(5))
    .register(registry);
~~~

Ở đây:

- publishPercentileHistogram() yêu cầu registry xuất histogram bucket có thể được backend tổng hợp.
- minimumExpectedValue(...) thiết lập cận dưới kỳ vọng.
- maximumExpectedValue(...) thiết lập cận trên kỳ vọng.
- register(registry) đăng ký meter với registry.

Nếu dùng Timer cho thời gian xử lý API, hãy dùng cùng một đơn vị trong tư duy vận hành, chẳng hạn milliseconds khi đọc dashboard, dù API Java nhận Duration. Micrometer và registry sẽ xử lý quy ước đơn vị khi xuất dữ liệu.

Có thể bổ sung SLO boundary:

~~~java
Timer requestTimer = Timer.builder("api.request.duration")
    .publishPercentileHistogram()
    .minimumExpectedValue(Duration.ofMillis(1))
    .maximumExpectedValue(Duration.ofSeconds(5))
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

SLO boundaries là các ranh giới bổ sung có chủ đích. Chúng không thay thế miền histogram và cũng không có nghĩa chỉ những giá trị này mới được ghi nhận.

## 4. Cấu hình cho DistributionSummary

DistributionSummary đo phân phối của đại lượng số không phải thời lượng, ví dụ kích thước payload, số bản ghi trong batch hoặc dung lượng dữ liệu. Giá trị min/max được truyền theo cùng đơn vị mà ứng dụng ghi vào summary.

~~~java
import io.micrometer.core.instrument.DistributionSummary;

DistributionSummary payloadSize = DistributionSummary
    .builder("api.request.payload.size")
    .description("Kích thước payload request")
    .baseUnit("bytes")
    .publishPercentileHistogram()
    .minimumExpectedValue(128)
    .maximumExpectedValue(1_048_576)
    .register(registry);
~~~

Trong ví dụ, min là 128 bytes và max là 1 MiB (1.048.576 bytes). Giá trị ghi nhận phải dùng cùng đơn vị:

~~~java
payloadSize.record(requestBody.length);
~~~

Nếu baseUnit là bytes nhưng code ghi số kilobytes, histogram sẽ bị diễn giải sai về quy mô. Base unit là metadata mô tả, không tự chuyển đổi số đã ghi. Hãy thống nhất đơn vị trong code, min/max, SLO và dashboard.

DistributionSummary cũng có thể khai báo SLO bằng các ngưỡng số:

~~~java
DistributionSummary payloadSize = DistributionSummary
    .builder("api.request.payload.size")
    .baseUnit("bytes")
    .publishPercentileHistogram()
    .minimumExpectedValue(128)
    .maximumExpectedValue(1_048_576)
    .serviceLevelObjectives(16_384, 65_536, 262_144)
    .register(registry);
~~~

Các ngưỡng lần lượt là 16 KiB, 64 KiB và 256 KiB nếu ứng dụng ghi bytes. Chọn ngưỡng dựa trên câu hỏi vận hành, chẳng hạn tỷ lệ payload nằm trong giới hạn khuyến nghị.

## 5. Chọn khoảng kỳ vọng từ dữ liệu thực tế

Không nên chọn min/max chỉ dựa trên giá trị lớn nhất từng thấy. Một outlier bất thường có thể làm miền histogram rộng hơn nhiều và tăng chi phí bucket cho mọi quan sát.

Một quy trình thực tế:

1. Thu thập dữ liệu ban đầu với cấu hình phù hợp hoặc xem dữ liệu đo đã có.
2. Xác định vùng thường gặp, vùng cần phân biệt và vùng tail quan trọng.
3. Chọn min đủ thấp để quan sát các giá trị nhỏ có ý nghĩa.
4. Chọn max đủ cao để bao phủ vùng tail cần chẩn đoán.
5. Bổ sung SLO boundaries tại các ngưỡng nghiệp vụ cần theo dõi.
6. Kiểm tra số bucket, số time series, bộ nhớ và thời gian scrape sau khi triển khai.
7. Điều chỉnh từ dữ liệu vận hành, không mở rộng miền một cách mặc định.

Ví dụ với API đọc dữ liệu, phân phối quan sát được như sau:

| Vùng latency | Tỷ lệ quan sát |
|---|---:|
| 1–50 ms | 35% |
| 50–100 ms | 40% |
| 100–300 ms | 20% |
| 300 ms–1 s | 4% |
| 1–5 s | 0,9% |
| Trên 5 s | 0,1% |

Nếu mục tiêu là theo dõi p95 và p99 của API, khoảng 1 ms đến 5 s có thể là điểm bắt đầu hợp lý. Tuy nhiên, 0,1% request trên 5 s vẫn có thể rất quan trọng nếu đó là lỗi nghẽn. Cần kiểm tra liệu các request tail có cần thêm một metric riêng, cảnh báo theo timeout hoặc LongTaskTimer hay không.

Với payload, hãy xem kích thước tối thiểu, median, p95, p99 và giới hạn nghiệp vụ. Một miền 128 bytes đến 1 MiB có thể phù hợp với API upload nhỏ; với endpoint nhận file lớn, cần khoảng khác. Không sao chép cùng một min/max cho tất cả meter.

## 6. Min/max ảnh hưởng đến chi phí như thế nào?

Histogram tạo nhiều bucket để mô tả phân phối. Với backend dạng time series như Prometheus, mỗi bucket thường tạo thêm series cho từng tổ hợp tên metric và tag. Khi có nhiều tag, số series tăng theo tích số giá trị của các chiều.

Ví dụ một histogram có:

- 20 bucket.
- 4 giá trị method.
- 5 giá trị status.
- 3 giá trị region.

Số series bucket xấp xỉ 20 × 4 × 5 × 3 = 1.200, chưa tính các series count, sum và các thống kê khác. Đây là ví dụ minh họa cách cardinality nhân lên; số bucket thực tế phụ thuộc registry, cấu hình và các SLO boundaries.

Mở rộng khoảng min/max có thể làm tăng số bucket được sinh ra để bao phủ miền rộng hơn. Cùng lúc, thêm tag có cardinality cao có thể nhân số series lên nhiều lần. Vì vậy, hãy điều chỉnh range và tag như hai phần của cùng một ngân sách cardinality.

Các cách giảm chi phí:

- Chỉ bật percentile histogram cho meter cần phân tích phân vị.
- Chọn min/max phù hợp với miền giá trị có ý nghĩa.
- Giữ số tag value hữu hạn và ổn định.
- Chỉ thêm SLO boundary phục vụ quyết định vận hành.
- Không thêm ID, URL đầy đủ hoặc nội dung request vào tag.
- Theo dõi số series và chi phí lưu trữ sau khi triển khai.

## 7. Cấu hình theo từng meter với Spring Boot

Spring Boot Actuator cho phép cấu hình phân phối theo tên meter qua các thuộc tính metrics. Ví dụ với HTTP server requests:

~~~properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.minimum-expected-value.http.server.requests=1ms
management.metrics.distribution.maximum-expected-value.http.server.requests=5s
management.metrics.distribution.slo.http.server.requests=100ms,300ms,1s
~~~

Các thuộc tính trên:

- Bật percentile histogram cho meter http.server.requests.
- Đặt khoảng kỳ vọng từ 1 ms đến 5 s.
- Thêm các SLO boundary 100 ms, 300 ms và 1 s.

Cú pháp và tên property cần được đối chiếu với phiên bản Spring Boot đang dùng. Nếu cấu hình không có tác dụng, hãy kiểm tra property binding, tên meter thực tế và endpoint metrics thay vì giả định auto-configuration đã áp dụng thành công.

Với meter tùy chỉnh, có thể cấu hình trực tiếp trong builder hoặc dùng MeterFilter/DistributionStatisticConfig khi cần áp dụng chính sách tập trung. Tránh vừa cấu hình cùng một meter bằng nhiều cơ chế nếu không hiểu thứ tự và cách merge các cấu hình.

## 8. Cấu hình tập trung bằng MeterFilter

Khi cần áp dụng range cho một nhóm meter, có thể dùng filter để bổ sung distribution config khi đăng ký. Ví dụ dưới đây minh họa ý tưởng cấu hình histogram cho một DistributionSummary cụ thể:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;

registry.config().meterFilter(
    new MeterFilter() {
        @Override
        public DistributionStatisticConfig configure(
                Meter.Id id,
                DistributionStatisticConfig config) {
            if (!id.getName().equals("api.request.payload.size")) {
                return config;
            }

            return DistributionStatisticConfig.builder()
                .minimumExpectedValue(128.0)
                .maximumExpectedValue(1_048_576.0)
                .percentilesHistogram(true)
                .build()
                .merge(config);
        }
    }
);
~~~

Ví dụ này minh họa cách gắn cấu hình phân phối trong giai đoạn đăng ký meter. Giá trị min/max là số theo đơn vị mà DistributionSummary ghi nhận, ở ví dụ này là bytes.

Filter phải được đăng ký trước khi meter được tạo. Một meter đã tồn tại không được cấu hình lại chỉ vì filter mới được thêm vào registry. Với ứng dụng Spring Boot, cấu hình qua thuộc tính hoặc customizer được khởi tạo sớm thường dễ quản lý hơn.

Nếu dùng filter cho nhiều meter, hãy kiểm tra điều kiện theo tên và loại meter để không áp dụng cùng một khoảng số cho các đại lượng có đơn vị khác nhau. Ví dụ 5.000 có thể là milliseconds trong một metric duration, nhưng là bytes trong một DistributionSummary.

## 9. Phân biệt histogram, percentile và SLO

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Cơ chế | Ý nghĩa | Phù hợp khi |
|---|---|---|
| Percentile histogram | Xuất bucket để backend tính phân vị trên dữ liệu tổng hợp | Cần p95/p99 có thể tổng hợp giữa nhiều instance |
| Client-side percentile | Tính phân vị tại từng process/registry | Cần phân vị cục bộ, chấp nhận không gộp chính xác giữa instance |
| SLO boundary | Thêm ranh giới cụ thể để đếm số quan sát đáp ứng ngưỡng | Cần đo tỷ lệ request dưới 100 ms hoặc payload dưới 64 KiB |

minimumExpectedValue và maximumExpectedValue chủ yếu định hình miền bucket của histogram phân phối. Chúng không tự tạo ra một SLO và cũng không đảm bảo p99 nằm trong miền kỳ vọng.

Khi dùng Prometheus, histogram bucket có thể được tổng hợp qua các instance rồi tính quantile bằng histogram_quantile(...). Khi dùng client-side percentile, mỗi instance tính phân vị cục bộ; không lấy trung bình các p99 cục bộ để suy ra p99 toàn hệ thống.

Nếu cần SLO chính xác theo ngưỡng, hãy khai báo boundary cụ thể và xác minh backend có xuất các bucket tương ứng. Đừng suy ra tỷ lệ đáp ứng SLO từ một p95 duy nhất.

## 10. Kiểm thử cấu hình range

Có thể kiểm thử meter bằng SimpleMeterRegistry để xác nhận builder đăng ký được meter và các lần ghi nhận hoạt động. Tuy nhiên, SimpleMeterRegistry không mô phỏng đầy đủ cách backend histogram thực tế tạo và xuất bucket. Muốn xác minh số bucket hoặc tên series, hãy dùng registry tương ứng với backend trong integration test.

Ví dụ kiểm thử Timer ghi nhận thời lượng:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DistributionRangeTest {

    @Test
    void timerRecordsDurationsWithConfiguredExpectedRange() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Timer timer = Timer.builder("api.request.duration")
                .minimumExpectedValue(Duration.ofMillis(1))
                .maximumExpectedValue(Duration.ofSeconds(5))
                .register(registry);

            timer.record(Duration.ofMillis(120));

            assertEquals(1, timer.count());
            assertEquals(
                120.0,
                timer.totalTime(TimeUnit.MILLISECONDS)
            );
        }
    }
}
~~~

Kiểm thử này xác minh việc ghi nhận thời lượng và count. Nó không chứng minh percentile histogram có số bucket hoặc độ phân giải mong muốn.

Integration test với registry Prometheus nên xác minh:

- Histogram bucket được xuất cho meter cần đo.
- Các SLO boundary xuất hiện đúng.
- Các giá trị gần min, trong miền và vượt max được phản ánh theo hành vi registry dự kiến.
- Số series không vượt ngân sách.
- Truy vấn p95/p99 hoạt động khi tổng hợp nhiều instance.

## 11. Các lỗi thường gặp

- **Coi min/max là validation:** chúng cấu hình miền thống kê; không tự từ chối request hoặc payload.
- **Đặt max quá thấp:** tail latency có thể không có đủ độ chi tiết để chẩn đoán.
- **Đặt min quá cao:** mất độ phân giải ở vùng giá trị thấp có ý nghĩa.
- **Dùng cùng range cho mọi meter:** thời lượng, byte và số phần tử có đơn vị cùng miền khác nhau.
- **Nhầm range với SLO:** min/max không thay thế các boundary nghiệp vụ.
- **Bật histogram cho tất cả meter:** số bucket và time series có thể tăng đáng kể.
- **Quên bật percentile histogram:** cấu hình min/max không tự bảo đảm backend có bucket để tính quantile.
- **Không thống nhất đơn vị:** baseUnit mô tả số đo, không tự chuyển đổi dữ liệu đã ghi.
- **Chỉ kiểm thử bằng SimpleMeterRegistry:** không xác minh được đầy đủ định dạng bucket của backend thực tế.
- **Sửa range sau khi meter đã đăng ký:** builder hoặc filter mới không cấu hình lại meter đang tồn tại; cần cấu hình trước đăng ký hoặc triển khai thay đổi có kiểm soát.

## 12. Checklist lựa chọn và triển khai

- [ ] Xác định đại lượng và đơn vị của meter.
- [ ] Bật histogram khi thực sự cần phân tích phân vị trên backend.
- [ ] Chọn minimumExpectedValue đủ thấp cho vùng quan sát quan trọng.
- [ ] Chọn maximumExpectedValue đủ cao cho tail cần chẩn đoán.
- [ ] Bổ sung SLO boundary riêng cho ngưỡng nghiệp vụ.
- [ ] Ước lượng số bucket và time series theo cardinality tag.
- [ ] Cấu hình range trước khi meter được đăng ký.
- [ ] Kiểm tra hành vi của giá trị nằm ngoài khoảng kỳ vọng trên registry thực tế.
- [ ] Dùng Duration cho Timer và cùng đơn vị số cho DistributionSummary.
- [ ] Xác minh bucket, SLO và truy vấn p95/p99 trong integration test.
- [ ] Theo dõi chi phí scrape, bộ nhớ và lưu trữ sau triển khai.

Chọn minimumExpectedValue và maximumExpectedValue dựa trên phân phối quan sát và vùng cần chẩn đoán. Khoảng hợp lý giúp histogram tập trung tài nguyên vào các giá trị có ý nghĩa, trong khi SLO boundary diễn đạt các ngưỡng vận hành cụ thể. Kết hợp range, tag và kiểm thử backend sẽ giúp metrics vừa đủ chi tiết vừa kiểm soát được chi phí.

