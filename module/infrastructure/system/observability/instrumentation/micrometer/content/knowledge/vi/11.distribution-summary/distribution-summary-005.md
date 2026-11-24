# Giới hạn miền giá trị kỳ vọng để kiểm soát thống kê phân phối

DistributionSummary dùng để ghi nhận phân phối của một đại lượng số, chẳng hạn kích thước response, dung lượng payload, số bản ghi trong batch hoặc tỷ lệ hoàn thành. Khi bật histogram, Micrometer có thể xuất nhiều bucket cho mỗi meter ID để backend tổng hợp và tính percentile. Nếu miền bucket quá rộng so với dữ liệu thực tế, ứng dụng phải duy trì và xuất nhiều bucket không cần thiết.

Các tùy chọn minimumExpectedValue và maximumExpectedValue cho phép khai báo miền giá trị mà summary dự kiến quan sát. Với percentile histogram, chúng đặt giới hạn dưới và trên cho tập bucket được gửi đến hệ thống giám sát hỗ trợ tính percentile có thể tổng hợp. Chọn miền hợp lý giúp giảm cardinality của bucket, dung lượng bộ nhớ và chi phí export.

Điều cần phân biệt ngay từ đầu: **miền giá trị kỳ vọng là cấu hình cho thống kê phân phối, không phải bộ lọc dữ liệu đầu vào**. DistributionSummary vẫn ghi nhận các giá trị hợp lệ được truyền vào record(); cấu hình min/max không tự clamp, chuẩn hóa hoặc từ chối một sample chỉ vì sample nằm ngoài miền kỳ vọng.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích DistributionSummary đo phân phối của các giá trị số không phải thời lượng.
- Đọc count, totalAmount, mean và max.
- Dùng minimumExpectedValue và maximumExpectedValue để giới hạn miền bucket histogram.
- Phân biệt giới hạn bucket với kiểm tra hoặc loại bỏ dữ liệu đầu vào.
- Chọn min/max theo miền dữ liệu nghiệp vụ và kết hợp với SLO boundaries.
- Dùng scale khi dữ liệu có miền nhỏ như tỷ lệ từ 0 đến 1.
- Ước lượng tác động của bucket, tag và cấu hình phân phối lên chi phí.

## DistributionSummary ghi nhận những gì?

DistributionSummary theo dõi phân phối của các giá trị số. Mỗi lần gọi record(amount) cập nhật các thống kê tổng hợp:

| Thống kê | Ý nghĩa |
|---|---|
| count() | Số sample được ghi nhận |
| totalAmount() | Tổng các sample được ghi nhận |
| mean() | Trung bình của các sample |
| max() | Giá trị lớn nhất trong cửa sổ thống kê hiện tại |

Mean được tính từ tổng chia cho số sample. Nếu chưa có sample nào, mean bằng 0. Ví dụ, một summary nhận các payload có kích thước 512, 1024 và 2048 byte:

| Thống kê | Giá trị |
|---|---:|
| Count | 3 |
| Total amount | 3.584 bytes |
| Mean | 1.194,67 bytes |
| Max | 2.048 bytes |

DistributionSummary phù hợp với kích thước response, số item trong batch, dung lượng message hoặc tỷ lệ đã chuyển thành một miền số có ý nghĩa. Với thời lượng thao tác, dùng Timer vì Timer có ngữ nghĩa đơn vị thời gian và export phù hợp hơn.

Theo API Micrometer, record(amount) bỏ qua giá trị âm. Vì vậy DistributionSummary phù hợp với đại lượng không âm. Nếu miền dữ liệu nghiệp vụ có thể âm và dấu âm mang ý nghĩa, hãy chọn mô hình đo khác thay vì kỳ vọng summary giữ lại các giá trị đó.

## Miền giá trị kỳ vọng và histogram bucket

Khi chỉ cần count, totalAmount, mean và max, không nhất thiết phải xuất histogram. Khi cần phân tích phân phối ở backend, có thể bật percentile histogram để registry xuất các bucket. Backend như Prometheus có thể cộng các bucket của nhiều instance rồi tính percentile.

~~~mermaid
flowchart TD
    A[Giá trị nghiệp vụ] --> B[DistributionSummary.record]
    B --> C[Count, totalAmount, mean, max]
    B --> D[Histogram nếu được bật]
    E[minimumExpectedValue] --> F[Giới hạn dưới của bucket]
    G[maximumExpectedValue] --> H[Giới hạn trên của bucket]
    F --> D
    H --> D
    D --> I[Registry export bucket]
    I --> J[Backend tổng hợp và tính percentile]
~~~

Micrometer có một tập bucket histogram được chọn sẵn. Nếu không giới hạn miền kỳ vọng, một summary bật percentile histogram có thể xuất nhiều bucket hơn mức dữ liệu ứng dụng cần. minimumExpectedValue đặt cận dưới và maximumExpectedValue đặt cận trên cho miền bucket được xuất. Nhờ đó có thể giảm số bucket không hữu ích ở ngoài miền quan sát dự kiến.

Ví dụ, một ứng dụng ghi nhận kích thước response thường nằm từ 1 byte đến 1 MiB. Việc cấu hình miền 1–1.048.576 giúp histogram tập trung vào khoảng giá trị này thay vì sử dụng một miền bucket rất rộng:

~~~java
DistributionSummary responseSize = DistributionSummary
    .builder("http.response.size")
    .baseUnit("bytes")
    .minimumExpectedValue(1.0)
    .maximumExpectedValue(1_048_576.0)
    .publishPercentileHistogram()
    .register(registry);
~~~

Các giá trị 1 và 1.048.576 chỉ là ví dụ. Hãy dùng đơn vị và giới hạn phù hợp với hệ thống thực tế. Nếu response lớn hơn 1 MiB vẫn hợp lệ, đừng đặt maximumExpectedValue thấp chỉ để làm histogram nhỏ; hãy chọn ngưỡng phản ánh đúng miền nghiệp vụ hoặc chấp nhận rằng histogram chi tiết tập trung trong một miền hẹp hơn.

## Min/max không lọc sample được ghi nhận

Đây là khác biệt quan trọng nhất khi thiết kế cấu hình:

| Cấu hình hoặc API | Tác động |
|---|---|
| minimumExpectedValue / maximumExpectedValue | Giới hạn miền bucket histogram được xuất |
| record(value) | Ghi nhận sample hợp lệ vào summary |
| Kiểm tra đầu vào trong code | Có thể từ chối, clamp hoặc phân loại dữ liệu trước khi record |

Giả sử summary được cấu hình maximumExpectedValue là 1.048.576 bytes nhưng ứng dụng ghi nhận response 2.000.000 bytes. Cấu hình expected value không có nghĩa Micrometer tự bỏ response đó hoặc đổi nó thành 1.048.576. Các thống kê tổng hợp như count và totalAmount vẫn phản ánh sample được ghi nhận. Tuy nhiên, histogram bucket chi tiết được xuất bị giới hạn theo miền đã cấu hình; backend có thể chỉ thể hiện các sample vượt miền trong bucket overflow như +Inf nếu định dạng histogram hỗ trợ bucket đó.

Do đó, hãy dùng hai lớp riêng nếu có yêu cầu kiểm soát dữ liệu:

1. Kiểm tra hoặc chuẩn hóa giá trị tại ranh giới nghiệp vụ nếu dữ liệu ngoài giới hạn là không hợp lệ.
2. Cấu hình min/max của DistributionSummary để kiểm soát miền bucket và chi phí thống kê.

Không dùng maximumExpectedValue như một cơ chế validation. Nếu dữ liệu ngoài giới hạn cần được cảnh báo, hãy ghi nhận bằng một counter có tag hữu hạn, ví dụ reason=above_expected_range, thay vì đưa chính giá trị bất thường vào tag.

## Chọn min và max từ miền nghiệp vụ

Không nên chọn min/max theo phỏng đoán hoặc chỉ dựa vào một vài sample đầu tiên. Hãy bắt đầu từ hợp đồng dữ liệu và cách sử dụng metric:

1. Xác định đại lượng và đơn vị: byte, item, bản ghi, phần trăm hay một số đo khác.
2. Xác định miền hợp lệ theo nghiệp vụ: giá trị nhỏ nhất và lớn nhất mà hệ thống cho phép.
3. Quan sát dữ liệu thực tế: phân vị, giá trị cực đại thường gặp và tần suất outlier.
4. Chọn miền kỳ vọng đủ rộng để bao phủ phần lớn dữ liệu có ý nghĩa, đồng thời tránh khoảng trống bucket quá rộng.
5. Chọn các SLO boundary nếu dashboard cần trả lời câu hỏi theo ngưỡng cụ thể.
6. Kiểm tra bucket export và số chuỗi sau khi triển khai.

Ví dụ cho kích thước payload:

| Yếu tố | Giá trị minh họa |
|---|---:|
| Đơn vị | bytes |
| Payload nhỏ nhất có ý nghĩa | 1 byte |
| Payload thông thường | 1 KB đến 64 KB |
| Payload lớn hợp lệ | 1 MB |
| Miền histogram dự kiến | 1 đến 1.048.576 bytes |
| Ngưỡng SLO cần theo dõi | 16 KB, 64 KB, 256 KB |

Các ngưỡng SLO có thể được khai báo cùng histogram:

~~~java
DistributionSummary responseSize = DistributionSummary
    .builder("http.response.size")
    .baseUnit("bytes")
    .minimumExpectedValue(1.0)
    .maximumExpectedValue(1_048_576.0)
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        16_384.0,
        65_536.0,
        262_144.0
    )
    .register(registry);
~~~

Các SLO boundary bổ sung những ranh giới bucket mà ứng dụng muốn truy vấn. Chúng không thay thế việc chọn min/max; hãy đảm bảo các ngưỡng phản ánh câu hỏi vận hành và nằm trong miền có ý nghĩa. SLO boundary có thể làm tăng số bucket được xuất.

## Giới hạn bucket và cardinality

Histogram có nhiều bucket hơn sẽ tạo nhiều chuỗi dữ liệu hơn ở backend. Số chuỗi tăng thêm phụ thuộc vào số bucket, số meter ID và số instance được thu thập. Với một summary được gắn tag, mỗi tổ hợp tag tạo một meter ID riêng; mỗi meter ID lại có tập bucket của nó.

Một ước lượng khái niệm cho số chuỗi histogram là:

~~~text
số chuỗi xấp xỉ = số meter ID × (số bucket + các chuỗi count/sum phụ trợ)
~~~

Ví dụ, nếu summary có 20 tổ hợp tag và mỗi meter ID xuất 60 bucket, backend có thể phải lưu hàng nghìn chuỗi cho metric family này khi tính cả count, sum và bucket. Nếu tag chứa request ID hoặc user ID, số meter ID tăng mạnh và chi phí histogram bị nhân lên tương ứng.

Giới hạn min/max giúp giảm bucket cardinality trong từng meter ID. Nó không làm giảm số meter ID do tag tạo ra. Hai bài toán phải được xử lý cùng nhau:

- **Bucket cardinality:** chọn miền expected value và SLO boundary phù hợp.
- **Tag cardinality:** dùng tag có tập giá trị hữu hạn, ổn định như operation, route template, provider hoặc outcome.

Đừng bật percentile histogram cho mọi DistributionSummary theo mặc định. Chỉ bật ở metric cần truy vấn phân phối; với metric chỉ cần count và total, giữ cấu hình đơn giản sẽ tiết kiệm tài nguyên hơn.

## Ví dụ: đo kích thước payload

Ví dụ sau tạo summary để đo kích thước message theo byte, giới hạn histogram vào miền dự kiến và ghi nhận một số payload:

~~~java
package example;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class PayloadMetricsDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        try {
            DistributionSummary payloadSize = DistributionSummary
                .builder("message.payload.size")
                .description("Kích thước payload message")
                .baseUnit("bytes")
                .minimumExpectedValue(1.0)
                .maximumExpectedValue(1_048_576.0)
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                    1_024.0,
                    16_384.0,
                    65_536.0,
                    262_144.0
                )
                .register(registry);

            payloadSize.record(512);
            payloadSize.record(8_192);
            payloadSize.record(65_536);

            System.out.println("Count: " + payloadSize.count());
            System.out.println("Total bytes: " + payloadSize.totalAmount());
            System.out.println("Mean bytes: " + payloadSize.mean());
            System.out.println("Max bytes: " + payloadSize.max());
        } finally {
            registry.close();
        }
    }
}
~~~

Với ba sample trên, count bằng 3 và totalAmount bằng 74.240 bytes. Mean bằng khoảng 24.746,67 bytes; max bằng 65.536 bytes trong cửa sổ thống kê hiện tại.

Ví dụ dùng SimpleMeterRegistry để minh họa việc ghi nhận và đọc thống kê cơ bản. SimpleMeterRegistry không phải registry export histogram cho Prometheus; để xác nhận các bucket thực tế, hãy dùng registry backend tương ứng và kiểm tra endpoint export.

## Ví dụ: tỷ lệ từ 0 đến 1

Một số đại lượng có miền rất hẹp. Ví dụ, tỷ lệ cache hit có miền [0,1]. Histogram bucket được chọn sẵn của DistributionSummary hướng đến miền số rộng; vì thế có thể scale tỷ lệ thành phần trăm trước khi ghi nhận:

~~~java
DistributionSummary cacheHitRatio = DistributionSummary
    .builder("cache.hit.ratio")
    .baseUnit("percent")
    .scale(100)
    .minimumExpectedValue(0.0)
    .maximumExpectedValue(100.0)
    .publishPercentileHistogram()
    .serviceLevelObjectives(70.0, 80.0, 90.0)
    .register(registry);

cacheHitRatio.record(0.82); // Được scale thành 82
~~~

Sau khi scale, giá trị summary ghi nhận là 82 phần trăm. Vì thế count, totalAmount, mean, max và các SLO boundary đều được hiểu trên miền 0–100. Các hệ thống đọc metric phải hiểu đơn vị và scale này; không được diễn giải giá trị 82 như tỷ lệ 0,82 nếu không chuyển đổi.

Scale thay đổi giá trị mà summary ghi nhận, khác với minimumExpectedValue và maximumExpectedValue chỉ giới hạn miền bucket. Chọn scale nhất quán với base unit và dashboard.

## Percentile histogram và percentile phía client

Micrometer hỗ trợ hai cách phổ biến để xem percentile:

| Cấu hình | Cách hoạt động | Có thể tổng hợp nhiều instance? |
|---|---|---|
| publishPercentiles(0.5, 0.95, 0.99) | Tính percentile phía client trong từng process | Không thể gộp trực tiếp thành percentile chính xác toàn cụm |
| publishPercentileHistogram() | Xuất bucket histogram để backend truy vấn | Có, nếu backend hỗ trợ histogram có thể tổng hợp |

Giới hạn expected value chủ yếu kiểm soát miền bucket histogram được xuất. Nếu dùng percentile phía client, dung lượng histogram nội bộ còn phụ thuộc cấu hình precision và buffer; min/max không phải là công cụ thay thế cho các tùy chọn đó.

Với Prometheus, histogram bucket có thể được tổng hợp trước khi tính percentile bằng histogram_quantile. Ví dụ:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(message_payload_size_bytes_bucket[5m])
  )
)
~~~

Tên metric ở trên chỉ là ví dụ. Tên thực tế phụ thuộc quy tắc đặt tên và đơn vị của registry. Hãy kiểm tra endpoint export để xác nhận tên metric, label và bucket.

## Khi nào dùng MeterFilter hoặc cấu hình tập trung?

Khi nhiều summary cần chung một miền expected value, có thể tập trung cấu hình distribution statistic thay vì lặp lại ở từng builder. Micrometer cung cấp MeterFilter để điều chỉnh DistributionStatisticConfig trong lúc meter được đăng ký. Cách này phù hợp khi một nhóm meter có quy ước miền thống kê giống nhau.

Ví dụ cấu hình builder trực tiếp thường dễ đọc hơn khi mỗi metric có miền riêng. Nếu dùng filter tập trung, hãy giới hạn theo tên meter hoặc quy tắc rõ ràng để không vô tình áp dụng miền của payload bytes cho metric tỷ lệ hoặc số item trong batch.

Với Spring Boot, có thể dùng các thuộc tính phân phối theo tên meter để cấu hình percentile histogram và expected value trong application configuration. Cần đối chiếu cú pháp với phiên bản Spring Boot đang dùng; khi cần cấu hình khác nhau theo loại meter, customizer hoặc MeterFilter cho phép diễn đạt quy tắc rõ ràng hơn.

## Kiểm thử miền kỳ vọng

Kiểm thử cần xác minh hai điều riêng biệt: summary vẫn ghi nhận sample hợp lệ và cấu hình histogram có miền bucket như dự kiến. Với SimpleMeterRegistry, có thể kiểm tra count, total và mean:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

DistributionSummary summary = DistributionSummary.builder("payload.size")
    .minimumExpectedValue(1.0)
    .maximumExpectedValue(1_048_576.0)
    .register(registry);

summary.record(512);
summary.record(2_000_000);

assertEquals(2, summary.count());
assertEquals(2_000_512.0, summary.totalAmount());

registry.close();
~~~

Đoạn kiểm thử minh họa rằng maximumExpectedValue không tự loại bỏ sample lớn hơn miền kỳ vọng khỏi count và totalAmount. Đây là điểm cần giữ rõ khi giải thích ý nghĩa của cấu hình.

Để xác minh bucket thực tế, hãy viết kiểm thử tích hợp với registry hỗ trợ histogram và kiểm tra dữ liệu export. Kiểm thử chỉ dùng SimpleMeterRegistry không chứng minh backend đã nhận đúng bucket.

Checklist kiểm thử:

- Sample hợp lệ được ghi nhận đúng vào count và totalAmount.
- Sample âm bị xử lý theo semantics của DistributionSummary.
- Min/max phản ánh đúng đơn vị và miền nghiệp vụ.
- SLO boundary nằm ở các ngưỡng có ý nghĩa.
- Histogram được bật chỉ ở những meter cần percentile tổng hợp.
- Số bucket và số series export được kiểm tra trên registry đích.
- Tag của summary có miền giá trị hữu hạn.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Nghĩ maximumExpectedValue là ngưỡng từ chối dữ liệu | Sample ngoài miền bị hiểu nhầm là bị loại bỏ | Validate dữ liệu riêng; min/max chỉ giới hạn bucket histogram |
| Không đặt min/max khi bật percentile histogram | Xuất nhiều bucket hơn nhu cầu và tăng chi phí | Chọn miền expected value dựa trên dữ liệu nghiệp vụ |
| Đặt max quá thấp | Histogram thiếu độ phân giải chi tiết ở vùng giá trị lớn | Bao phủ miền dữ liệu hợp lệ và theo dõi outlier |
| Dùng đơn vị không nhất quán | Dashboard diễn giải sai giá trị và ngưỡng | Khai báo baseUnit và chuẩn hóa scale |
| Thêm quá nhiều SLO boundary | Bucket và time series tăng thêm | Chỉ giữ ngưỡng phục vụ truy vấn hoặc alert |
| Dùng tag có cardinality cao | Mỗi meter ID có thêm một tập histogram riêng | Dùng tag hữu hạn và ổn định |
| Dùng DistributionSummary cho số âm | Sample âm bị bỏ qua | Chọn mô hình đo phù hợp với miền dữ liệu |

## Ghi nhớ

- DistributionSummary ghi nhận phân phối của các giá trị số không phải thời lượng.
- count(), totalAmount(), mean() và max() mô tả số lượng, tổng, trung bình và cực đại trong cửa sổ thống kê.
- minimumExpectedValue và maximumExpectedValue giới hạn miền bucket histogram được xuất; chúng không lọc hoặc clamp sample trong record().
- Chọn min/max theo đơn vị, hợp đồng dữ liệu và phân phối quan sát được.
- serviceLevelObjectives bổ sung các ranh giới bucket phục vụ câu hỏi vận hành cụ thể.
- scale giúp chuyển miền dữ liệu hẹp như [0,1] thành miền số phù hợp cho histogram, nhưng cũng thay đổi đơn vị giá trị summary ghi nhận.
- Bucket cardinality và tag cardinality là hai yếu tố riêng; cần kiểm soát cả hai.
- Dùng percentile histogram khi backend cần tổng hợp phân phối giữa nhiều instance; percentile phía client không thể gộp trực tiếp.
- Kiểm tra bucket trên registry export thực tế; SimpleMeterRegistry chỉ phù hợp để kiểm thử các số đo cơ bản.

Khi chọn đúng miền giá trị kỳ vọng, DistributionSummary vẫn giữ ý nghĩa của dữ liệu nghiệp vụ trong các thống kê tổng hợp, đồng thời tránh xuất một tập bucket quá rộng so với câu hỏi vận hành cần trả lời.

## Tài liệu tham khảo

- [Micrometer: Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html) — miền bucket, scaling, percentile histogram và ước lượng bộ nhớ.
- [Micrometer Core: DistributionSummary.Builder](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/DistributionSummary.Builder.html) — API minimumExpectedValue, maximumExpectedValue, scale, SLO và cấu hình phân phối.
