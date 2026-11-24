# DistributionSummary đo phân phối đại lượng không phải thời gian

DistributionSummary là meter của Micrometer dùng để ghi nhận phân phối của những giá trị đo không phải thời lượng. Ví dụ thường gặp là kích thước request hoặc response, số byte truyền đi, số bản ghi trong một lô, số item được xử lý mỗi lần hoặc dung lượng dữ liệu của một sự kiện. Mỗi lần ghi nhận, ứng dụng cung cấp một giá trị; DistributionSummary tích lũy số lần ghi và tổng các giá trị, đồng thời có thể cung cấp thống kê phân phối như histogram và percentile tùy cấu hình.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, DistributionSummary bổ sung cho Counter, Gauge và Timer. Counter đếm sự kiện, Gauge quan sát trạng thái hiện tại, Timer đo thời lượng, còn DistributionSummary giúp trả lời câu hỏi: mỗi lần xử lý thường có kích thước bao nhiêu, các giá trị phân bố ra sao và những trường hợp lớn bất thường xuất hiện với tần suất nào?

## 1. DistributionSummary dùng để đo điều gì?

DistributionSummary phù hợp khi mỗi lần thao tác tạo ra một đại lượng số có ý nghĩa và cần phân tích phân phối của đại lượng đó.

Ví dụ:

- Kích thước request hoặc response tính bằng byte.
- Số bản ghi được xử lý trong một batch.
- Số item được trả về trong một truy vấn.
- Kích thước message gửi qua message broker.
- Dung lượng file được xử lý.
- Số phần tử được nạp vào cache trong mỗi lần refresh.

DistributionSummary không có ngữ nghĩa thời gian. Nếu cần đo một thao tác mất bao lâu, dùng Timer. Nếu chỉ cần đếm có bao nhiêu lần thao tác xảy ra, dùng Counter. Nếu muốn theo dõi số item hiện đang nằm trong queue, dùng Gauge.

| Loại meter | Câu hỏi chính | Ví dụ |
|---|---|---|
| Counter | Có bao nhiêu sự kiện đã xảy ra? | Tổng số batch đã xử lý |
| Gauge | Trạng thái hiện tại là bao nhiêu? | Số item đang chờ trong queue |
| Timer | Một thao tác mất bao lâu? | Thời gian xử lý batch |
| DistributionSummary | Mỗi lần thao tác tạo ra giá trị có độ lớn/phân phối ra sao? | Số bản ghi trong từng batch |

Một luồng xử lý batch có thể dùng cả bốn meter: Counter đếm số batch, Gauge đo số batch đang chờ, Timer đo thời gian xử lý và DistributionSummary đo số bản ghi trong mỗi batch. Mỗi meter trả lời một câu hỏi khác nhau.

## 2. Những thống kê cơ bản của DistributionSummary

Khi ứng dụng ghi nhận nhiều giá trị, DistributionSummary cung cấp các thống kê nền tảng:

- **count**: số lần ghi nhận giá trị.
- **totalAmount**: tổng tất cả giá trị đã ghi nhận.
- **mean**: giá trị trung bình có thể tính bằng totalAmount chia cho count khi count lớn hơn 0.
- **max**: giá trị lớn nhất trong cửa sổ thống kê mà registry đang duy trì; đây không nhất thiết là giá trị lớn nhất kể từ khi ứng dụng khởi động.

Ví dụ, ứng dụng ghi nhận kích thước năm response: 100, 200, 300, 400 và 1.000 byte.

- count = 5.
- totalAmount = 2.000 byte.
- mean = 400 byte mỗi response.
- max quan sát được trong cửa sổ thống kê hiện tại là 1.000 byte.

Count và totalAmount hữu ích để tính trung bình và tổng lưu lượng dữ liệu. Tuy nhiên, hai con số này không mô tả đầy đủ phân phối. Hai hệ thống có thể cùng trung bình 400 byte nhưng một hệ thống có các response gần bằng nhau, còn hệ thống kia có nhiều response nhỏ và một số response rất lớn. Histogram hoặc percentile giúp nhìn thấy khác biệt đó.

## 3. Khởi tạo DistributionSummary trong Micrometer

Có thể tạo DistributionSummary từ MeterRegistry bằng builder:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ResponseSizeMetrics {
    private final DistributionSummary responseSize;

    public ResponseSizeMetrics(MeterRegistry registry) {
        this.responseSize = DistributionSummary
                .builder("http.response.size")
                .description("HTTP response body size")
                .baseUnit("bytes")
                .register(registry);
    }

    public void recordResponse(byte[] body) {
        responseSize.record(body.length);
    }
}
~~~

Trong ví dụ:

- Tên meter mô tả đại lượng được ghi nhận.
- Description giải thích giá trị đại diện cho điều gì.
- Base unit là bytes để người đọc hiểu đơn vị.
- Mỗi response được ghi nhận bằng kích thước mảng byte.
- Meter được đăng ký một lần và tái sử dụng cho những lần ghi tiếp theo.

Nếu cần đo số byte của chuỗi, phải xác định encoding trước khi tính kích thước. Số ký tự của String không nhất thiết bằng số byte khi mã hóa UTF-8:

~~~java
int sizeInBytes = responseText.getBytes(StandardCharsets.UTF_8).length;
responseSize.record(sizeInBytes);
~~~

Không trộn byte, kilobyte và số ký tự vào cùng một DistributionSummary. Mọi lần record của một meter phải có cùng ý nghĩa và đơn vị. Nếu muốn hiển thị kilobyte, có thể chuyển đổi nhất quán trước khi ghi và đặt base unit phù hợp, hoặc ghi byte rồi đổi đơn vị ở tầng truy vấn/hiển thị.

## 4. Ghi nhận số lượng cho mỗi lần xử lý

DistributionSummary hữu ích khi muốn biết quy mô của từng lần xử lý, thay vì chỉ biết tổng số sự kiện.

Ví dụ, một batch import có thể chứa số bản ghi khác nhau:

~~~java
import java.util.List;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ImportMetrics {
    private final DistributionSummary batchSize;
    private final ImportService importService;

    public ImportMetrics(MeterRegistry registry, ImportService importService) {
        this.batchSize = DistributionSummary.builder("import.batch.size")
                .description("Number of records in each import batch")
                .baseUnit("records")
                .register(registry);
        this.importService = importService;
    }

    public void processBatch(List<Record> records) {
        batchSize.record(records.size());
        importService.process(records);
    }
}
~~~

Nếu batch có 10, 20 và 50 bản ghi, DistributionSummary có count bằng 3 và totalAmount bằng 80. Giá trị trung bình là khoảng 26,67 bản ghi mỗi batch. Phân phối còn cho biết batch lớn thường xuất hiện ở mức nào.

Cần quyết định thời điểm ghi nhận phù hợp với câu hỏi vận hành. Nếu muốn biết quy mô batch được gửi đến, ghi khi batch được nhận. Nếu muốn biết quy mô batch xử lý thành công, ghi sau khi xử lý thành công. Nếu muốn đo cả batch thất bại, có thể ghi ngay khi bắt đầu và phân loại kết quả bằng một meter khác hoặc tag outcome có tập giá trị hữu hạn.

Đừng nhầm số lần xử lý batch với số bản ghi. Counter có thể đếm tổng batch; DistributionSummary ghi số bản ghi trong từng batch. Nếu một batch có 50 bản ghi, Counter batch tăng một còn DistributionSummary ghi nhận một mẫu có giá trị 50.

## 5. Cấu hình percentile và histogram

DistributionSummary có thể xuất thống kê phân vị và histogram. Hai cơ chế này phục vụ các nhu cầu khác nhau.

### Percentile tính tại phía ứng dụng

Có thể yêu cầu Micrometer tính các percentile cụ thể:

~~~java
DistributionSummary payloadSize = DistributionSummary.builder("message.payload.size")
        .description("Message payload size")
        .baseUnit("bytes")
        .publishPercentiles(0.50, 0.90, 0.95, 0.99)
        .register(registry);
~~~

Các percentile này giúp quan sát p50, p90, p95 hoặc p99 của phân phối tại từng instance/registry. Chúng hữu ích khi muốn theo dõi phân phối cục bộ, nhưng percentile đã tính riêng ở từng instance không thể cộng hoặc lấy trung bình để tạo ra percentile chính xác của toàn bộ cụm.

Ví dụ, p95 của instance A và p95 của instance B không thể cộng lại rồi chia đôi để có p95 của cả hai instance. Percentile không có tính chất tổng hợp như sum hoặc count.

### Histogram bucket để tổng hợp ở backend

Nếu cần tổng hợp phân phối trên nhiều instance, bật percentile histogram:

~~~java
DistributionSummary payloadSize = DistributionSummary.builder("message.payload.size")
        .description("Message payload size")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .register(registry);
~~~

Histogram ghi nhận số mẫu nằm trong các bucket theo ngưỡng. Backend có thể cộng số mẫu ở cùng bucket giữa các instance rồi tính percentile trên phân phối đã tổng hợp.

Với Prometheus, histogram thường được xuất dưới dạng các series bucket có label le, cùng count và sum. Tên metric cuối cùng phụ thuộc quy tắc chuẩn hóa và base unit của Prometheus registry; hãy kiểm tra endpoint export trước khi viết truy vấn.

### Service level objectives (SLO) boundaries

Nếu hệ thống có các ngưỡng vận hành cụ thể, có thể cấu hình các ranh giới bucket phù hợp:

~~~java
DistributionSummary batchSize = DistributionSummary.builder("import.batch.size")
        .description("Number of records in each import batch")
        .baseUnit("records")
        .serviceLevelObjectives(100, 500, 1000, 5000)
        .register(registry);
~~~

Các ngưỡng phải cùng đơn vị với giá trị được ghi nhận. Ví dụ trên có các mốc 100, 500, 1.000 và 5.000 bản ghi. Chúng có thể giúp trả lời câu hỏi như bao nhiêu phần trăm batch có không quá 500 bản ghi.

Histogram có chi phí: mỗi bucket bổ sung series cho mỗi tổ hợp tag. Vì vậy, chỉ bật histogram và thêm ngưỡng thật sự cần thiết. Hãy cân nhắc số meter, số tag, số instance và số bucket trước khi triển khai trên quy mô lớn.

## 6. Chọn ngưỡng phân phối theo miền giá trị

Để histogram hữu ích, cần hiểu miền giá trị thường gặp và giới hạn có ý nghĩa. Ví dụ, nếu payload thường từ vài byte đến 2 MB, ngưỡng histogram nên phản ánh miền đó. Nếu đặt ngưỡng quá rộng hoặc quá nhiều, dữ liệu có thể tốn tài nguyên mà không giúp trả lời câu hỏi vận hành.

Một số nguyên tắc:

- Chọn đơn vị và miền giá trị trước khi cấu hình histogram.
- Dùng SLO boundary theo ngưỡng nghiệp vụ hoặc hạ tầng cần theo dõi.
- Không tạo hàng trăm ngưỡng gần nhau nếu không có quyết định vận hành tương ứng.
- Dùng minimum/maximum expected value khi cần giới hạn miền bucket được tạo bởi registry; chọn giá trị phù hợp với dữ liệu thực tế và phiên bản Micrometer đang dùng.
- Theo dõi số lượng time series sau khi bật histogram.

Giá trị nằm ngoài các ngưỡng SLO tùy cấu hình vẫn có thể được ghi nhận trong tổng count/sum; SLO boundary là ranh giới thống kê, không phải bộ lọc loại bỏ dữ liệu. Hãy kiểm tra hành vi bucket và exporter cụ thể của registry đang sử dụng.

## 7. Truy vấn DistributionSummary trên Prometheus

Khi Prometheus registry xuất DistributionSummary, các series thường bao gồm count và sum; histogram có thêm bucket. Tên metric phụ thuộc quy tắc chuyển đổi tên và base unit, vì vậy ví dụ dưới đây giả định endpoint thực tế xuất các series:

- http_response_size_bytes_count
- http_response_size_bytes_sum
- http_response_size_bytes_bucket

Để tính số response trung bình mỗi giây trong năm phút:

~~~promql
sum(rate(http_response_size_bytes_count[5m]))
~~~

Để tính kích thước response trung bình trong năm phút:

~~~promql
sum(rate(http_response_size_bytes_sum[5m]))
/
sum(rate(http_response_size_bytes_count[5m]))
~~~

Tử số là tốc độ tăng tổng byte mỗi giây; mẫu số là tốc độ tăng số response mỗi giây. Tỷ lệ hai giá trị là số byte trung bình mỗi response trong cửa sổ.

Nếu histogram bucket đã được bật, có thể ước lượng p95 kích thước response:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_response_size_bytes_bucket[5m])
  )
)
~~~

Cần giữ label le khi cộng bucket để hàm histogram_quantile có thể tính phân vị. Các tag khác có thể được thêm vào nhóm nếu muốn xem p95 theo service, environment hoặc region:

~~~promql
histogram_quantile(
  0.95,
  sum by (service, environment, region, le) (
    rate(http_response_size_bytes_bucket[5m])
  )
)
~~~

Để tính tổng byte đã ghi nhận trong một giờ, có thể dùng:

~~~promql
sum(increase(http_response_size_bytes_sum[1h]))
~~~

Các truy vấn phải dùng đúng tên series và label xuất hiện trong Prometheus. Không suy đoán tên metric chỉ từ tên builder; hãy xem endpoint hoặc dùng autocomplete trong Prometheus UI.

## 8. Phân biệt percentile, mean và max

Ba thống kê này trả lời những câu hỏi khác nhau:

| Thống kê | Ý nghĩa | Dùng để |
|---|---|---|
| Mean | Tổng giá trị chia cho số lần ghi | Theo dõi mức trung bình |
| Percentile p95 | 95% mẫu nằm ở hoặc dưới ngưỡng phân vị 95 | Quan sát phần lớn hoạt động và đuôi phân phối |
| Max | Giá trị lớn nhất trong cửa sổ thống kê hiện tại | Phát hiện mẫu lớn bất thường gần đây |

Mean có thể bị kéo lên bởi một số mẫu rất lớn. P95 giúp quan sát phần đuôi mà không bị một mẫu đơn lẻ chi phối như max. Max có thể thay đổi hoặc giảm sau khi cửa sổ thống kê trôi qua; không xem nó như giá trị cực đại tích lũy vĩnh viễn.

Nếu mục tiêu là kiểm soát payload không vượt quá giới hạn, cần kết hợp metric với validation hoặc cơ chế giới hạn ở ứng dụng. DistributionSummary chỉ quan sát và báo cáo; nó không tự chặn request quá lớn.

## 9. Kiểm soát tag và cardinality

Mỗi tổ hợp tên metric và tag tạo ra một time series. Khi histogram được bật, số bucket làm số series tăng thêm cho mỗi tổ hợp đó. Vì vậy, tag cần có tập giá trị nhỏ và ổn định.

Các tag phù hợp có thể gồm:

- service: checkout-service, catalog-service.
- environment: development, staging, production.
- region: các vùng triển khai đã định nghĩa.
- payload_type: json, protobuf, image nếu tập giá trị được kiểm soát.
- outcome: success, failure.

Không dùng requestId, userId, orderId, email hoặc URL chứa ID làm tag. Những giá trị này có thể tạo ra một series cho gần như mỗi request hoặc người dùng. Nếu cần truy tìm payload cụ thể, dùng log hoặc trace với cơ chế kiểm soát dữ liệu phù hợp.

Không đăng ký một DistributionSummary mới cho mỗi request với tag mang ID duy nhất. Hãy đăng ký meter theo tên và các chiều phân loại có cardinality thấp, rồi ghi nhiều mẫu vào meter đó.

## 10. Kiểm thử DistributionSummary

Có thể dùng SimpleMeterRegistry để kiểm tra count và totalAmount trong unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class DistributionSummaryTest {

    @Test
    void recordsCountAndTotalAmount() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        DistributionSummary summary = DistributionSummary.builder("payload.size")
                .baseUnit("bytes")
                .register(registry);

        summary.record(100);
        summary.record(200);
        summary.record(300);

        assertThat(summary.count()).isEqualTo(3);
        assertThat(summary.totalAmount()).isEqualTo(600.0);
        assertThat(summary.totalAmount() / summary.count())
                .isEqualTo(200.0);

        registry.close();
    }
}
~~~

Kiểm thử này xác nhận ba mẫu được ghi nhận và tổng giá trị bằng 600. Có thể bổ sung các test cho batch rỗng, giá trị biên, đơn vị và tag để bảo đảm metric không ghi sai ý nghĩa.

Nếu cấu hình percentile hoặc histogram, cần kiểm tra endpoint export của registry hoặc dữ liệu ở backend để xác nhận bucket/percentile được tạo như mong đợi. SimpleMeterRegistry phù hợp cho logic ghi nhận cơ bản nhưng không chứng minh cấu hình exporter Prometheus hay OTLP đang hoạt động.

## 11. Chọn meter phù hợp cho một đại lượng

Trước khi dùng DistributionSummary, hãy xác định:

1. **Đại lượng nào được ghi?** Kích thước payload, số item, số byte hay giá trị khác?
2. **Đơn vị có nhất quán không?** Không trộn byte với ký tự hoặc bản ghi với batch.
3. **Mỗi lần record đại diện cho điều gì?** Một response, một batch hay một file?
4. **Cần thống kê nào?** Count/sum/mean, percentile cục bộ hay histogram tổng hợp trên toàn cụm?
5. **Ngưỡng histogram có ý nghĩa không?** Chọn bucket/SLO theo miền giá trị và nhu cầu vận hành.
6. **Tag có cardinality kiểm soát không?** Chỉ dùng những chiều phân loại có tập giá trị hữu hạn.

DistributionSummary giúp hiểu quy mô và hình dạng phân phối của các đại lượng không phải thời gian. Khi ghi đúng đơn vị, chọn thời điểm record phù hợp, cấu hình histogram theo nhu cầu và giới hạn tag, metrics có thể cho biết kích thước payload điển hình, độ lệch của các batch và tần suất xuất hiện những giá trị lớn mà số đếm hoặc trung bình đơn thuần không thể hiện được.
