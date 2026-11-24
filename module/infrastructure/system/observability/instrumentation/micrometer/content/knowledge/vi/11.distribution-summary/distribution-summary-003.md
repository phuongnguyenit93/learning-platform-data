# Ghi nhận count, totalAmount, mean và max

## Mục tiêu

Khi cần biết kích thước payload, số phần tử trong một batch hoặc số item trong một đơn hàng, ta thường quan tâm đến cả số mẫu và phân bố giá trị. Micrometer cung cấp DistributionSummary để ghi nhận những đại lượng số không biểu diễn thời gian. Mỗi lần gọi record(amount) tạo một observation; từ các observation đó, meter cung cấp bốn số liệu thường dùng:

- count: số mẫu đã được ghi nhận.
- totalAmount: tổng các giá trị đã ghi nhận.
- mean: giá trị trung bình của các mẫu.
- max: giá trị lớn nhất trong cửa sổ thống kê mà implementation đang duy trì.

Các số liệu này trả lời những câu hỏi khác nhau. Ví dụ, count = 3 và totalAmount = 660 có nghĩa là đã ghi nhận ba mẫu có tổng giá trị 660 đơn vị. mean cho biết trung bình mỗi mẫu là bao nhiêu; max cho biết mẫu lớn nhất gần đây theo cửa sổ thống kê.

Sau bài này, bạn có thể tạo DistributionSummary, ghi mẫu đúng cách, đọc và diễn giải bốn số liệu, hiểu giới hạn của max, chọn đơn vị và kiểm thử kết quả.

## DistributionSummary dùng để đo điều gì?

DistributionSummary theo dõi phân bố của các giá trị số không phải thời lượng. Một số trường hợp phù hợp:

| Đại lượng | Ví dụ metric | Đơn vị |
|---|---|---|
| Kích thước response | http.response.size | bytes |
| Số item mỗi đơn hàng | business.order.items | items |
| Số bản ghi trong batch | worker.batch.records | records |
| Kích thước message | messaging.message.size | bytes |
| Số phần tử trong một trang kết quả | search.page.results | items |

Nếu đại lượng là thời gian, hãy dùng Timer để Micrometer và backend hiểu đúng đơn vị cũng như các phép thống kê latency. Nếu cần quan sát giá trị hiện tại có thể tăng hoặc giảm, chẳng hạn độ dài hàng đợi tại thời điểm lấy mẫu, hãy cân nhắc Gauge.

## Tạo DistributionSummary và ghi dữ liệu

### Ví dụ ghi kích thước response

DistributionSummary có thể được đăng ký trực tiếp từ MeterRegistry:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ResponseMetrics {
    private final DistributionSummary responseSize;

    public ResponseMetrics(MeterRegistry registry) {
        this.responseSize = DistributionSummary
                .builder("http.response.size")
                .description("Kích thước nội dung response")
                .baseUnit("bytes")
                .register(registry);
    }

    public void recordResponse(byte[] body) {
        responseSize.record(body.length);
    }
}
~~~

Mỗi lần recordResponse(...) được gọi, kích thước response được ghi thành một mẫu. Nếu ba response có kích thước 120, 240 và 300 bytes, summary sẽ có:

| Số liệu | Giá trị | Ý nghĩa |
|---|---:|---|
| count() | 3 | Đã ghi nhận ba response |
| totalAmount() | 660 | Tổng kích thước là 660 bytes |
| mean() | 220 | Kích thước trung bình là 220 bytes |
| max() | 300 | Mẫu lớn nhất trong cửa sổ thống kê hiện tại là 300 bytes |

Để ghi nhận, giá trị phải không âm. record() bỏ qua giá trị âm; giá trị 0 vẫn là một observation hợp lệ. Vì vậy, count() phản ánh số mẫu hợp lệ được ghi nhận, không nên dùng nó để suy ra số lần gọi record() nếu đầu vào có thể âm.

### Đăng ký meter một lần, ghi nhiều lần

Nên đăng ký DistributionSummary trong constructor hoặc trong cấu hình instrumentation, rồi giữ lại tham chiếu để ghi dữ liệu. Tránh tạo một meter mới theo từng request. Registry quản lý meter theo tên và tag; tạo tag động theo ID hoặc dữ liệu người dùng có thể làm cardinality tăng không giới hạn.

Ví dụ ghi số item cho từng đơn hàng:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderMetrics {
    private final DistributionSummary itemsPerOrder;

    public OrderMetrics(MeterRegistry registry) {
        this.itemsPerOrder = DistributionSummary
                .builder("business.order.items")
                .description("Số mặt hàng trong mỗi đơn hàng")
                .baseUnit("items")
                .register(registry);
    }

    public void recordOrder(int itemCount) {
        itemsPerOrder.record(itemCount);
    }
}
~~~

Ở đây, mỗi đơn hàng tạo một observation. Không gắn orderId làm tag vì mỗi đơn hàng có thể có một ID riêng. Nếu cần phân tích theo kênh bán hàng, có thể dùng tag có tập giá trị nhỏ như channel=web hoặc channel=store.

## Đọc count, totalAmount, mean và max

Các phương thức của DistributionSummary trả về bốn đại lượng:

~~~java
long count = summary.count();
double total = summary.totalAmount();
double average = summary.mean();
double maximum = summary.max();
~~~

### count: số mẫu đã ghi nhận

count() trả về số lần ghi nhận hợp lệ kể từ khi meter được tạo. Mỗi lần record(300) làm count tăng một, không tăng 300. Count là số observation, không phải tổng số đơn vị nằm trong các observation.

Ví dụ, nếu ghi ba batch có lần lượt 10, 20 và 30 bản ghi:

- count = 3: có ba batch được quan sát.
- totalAmount = 60: tổng cộng 60 bản ghi nằm trong các batch.

Nếu câu hỏi vận hành là “đã xử lý bao nhiêu batch?”, hãy đọc count. Nếu câu hỏi là “đã xử lý bao nhiêu bản ghi?”, hãy đọc tổng amount hoặc đo riêng số bản ghi theo đúng định nghĩa nghiệp vụ.

### totalAmount: tổng các giá trị

totalAmount() trả về tổng tất cả giá trị đã được ghi nhận. Đây là số liệu hữu ích khi cần biết tổng byte, tổng item hoặc tổng đơn vị công việc trong phạm vi meter.

Với các mẫu 120, 240 và 300 bytes:

\[
\text{totalAmount} = 120 + 240 + 300 = 660
\]

Total amount có thể tăng rất nhanh nếu đơn vị lớn hoặc lưu lượng cao. Hãy chọn kiểu dữ liệu và đơn vị phù hợp, đồng thời tránh diễn giải tổng amount thành số observation.

### mean: giá trị trung bình

mean() trả về giá trị trung bình của các mẫu đã ghi nhận. Có thể hiểu theo công thức:

\[
\text{mean} =
\begin{cases}
0 & \text{khi count = 0}\\
\dfrac{\text{totalAmount}}{\text{count}} & \text{khi count > 0}
\end{cases}
\]

Với các mẫu 120, 240 và 300 bytes:

\[
\text{mean} = \frac{660}{3} = 220 \text{ bytes}
\]

Micrometer cung cấp mean() trực tiếp trên DistributionSummary. Khi tự tính, phải xử lý trường hợp count = 0 để tránh chia cho 0.

Mean hữu ích để theo dõi xu hướng chung, nhưng có thể che khuất một số mẫu rất lớn. Ví dụ, nhiều response nhỏ và một response cực lớn có thể tạo ra mean tăng mạnh dù phần lớn response vẫn nhỏ. Khi cần hiểu phần đuôi của phân bố, hãy xem thêm max, percentile hoặc histogram.

### max: giá trị lớn nhất trong cửa sổ thống kê

max() trả về giá trị lớn nhất được quan sát trong cửa sổ thống kê mà implementation của summary đang duy trì. Với các implementation phổ biến như CumulativeDistributionSummary và StepDistributionSummary, max sử dụng cơ chế TimeWindowMax.

Điều này có một hệ quả quan trọng: max() không nhất thiết là giá trị lớn nhất trong toàn bộ vòng đời ứng dụng. Khi không có mẫu mới và các cửa sổ cũ hết hạn, max có thể trở về 0. Thời gian giữ mẫu cũ phụ thuộc expiry nhân với bufferLength trong DistributionStatisticConfig; bufferLength mặc định thường là 3, còn expiry mặc định phụ thuộc step của registry hoặc cấu hình cụ thể.

Ví dụ:

- Trong một cửa sổ, các giá trị được ghi là 100, 200 và 900; max là 900.
- Sau khi cửa sổ chứa mẫu 900 hết hạn, nếu các mẫu mới chỉ là 100 và 150, max hiện tại có thể là 150.
- Nếu không có mẫu mới và cửa sổ cũ hết hạn hoàn toàn, max có thể trở về 0.

Vì vậy, khi đọc max trên dashboard, hãy xem nó như cực đại gần đây theo cửa sổ thống kê. Không dùng nó như một bản ghi lịch sử vĩnh viễn. Giá trị max bằng 0 cũng không đủ để kết luận chưa từng có mẫu, vì record(0) hợp lệ và max cũ có thể đã hết hạn; hãy đọc count cùng các số liệu liên quan. Nếu cần lưu giá trị lớn nhất từ khi ứng dụng khởi động hoặc qua nhiều lần khởi động, cần thiết kế cơ chế lưu trữ riêng với semantics rõ ràng.

## Phân biệt bốn số liệu qua một ví dụ

Giả sử một API ghi kích thước năm response theo bytes:

| Response | Kích thước |
|---|---:|
| A | 100 |
| B | 150 |
| C | 200 |
| D | 250 |
| E | 800 |

Kết quả tổng hợp:

| Số liệu | Kết quả | Câu hỏi được trả lời |
|---|---:|---|
| Count | 5 | Có bao nhiêu response được ghi nhận? |
| Total amount | 1.500 bytes | Tổng kích thước response là bao nhiêu? |
| Mean | 300 bytes | Kích thước trung bình là bao nhiêu? |
| Max | 800 bytes | Response lớn nhất trong cửa sổ thống kê là bao nhiêu? |

Mean bằng 300 bytes nhưng bốn trong năm response có kích thước không quá 250 bytes. Max giúp nhận ra mẫu lớn bất thường mà mean không mô tả đầy đủ. Nếu cần biết bao nhiêu response vượt 500 bytes, có thể dùng histogram/SLO bucket hoặc một Counter riêng cho sự kiện “response vượt ngưỡng”; không thể suy ra chính xác số lượng đó chỉ từ count, totalAmount, mean và max.

## Chọn đơn vị và scale

### Đặt base unit

Khi tạo summary, nên đặt baseUnit nếu đại lượng có đơn vị tự nhiên:

~~~java
DistributionSummary.builder("http.response.size")
        .baseUnit("bytes")
        .register(registry);
~~~

Đơn vị giúp người đọc dashboard hiểu giá trị đang biểu diễn điều gì. Hãy thống nhất một đơn vị trong toàn bộ metric. Ví dụ, không ghi một số mẫu theo bytes và mẫu khác theo kilobytes vào cùng một summary.

### Dùng scale khi miền giá trị cần chuyển đổi

Builder có scale(...) để nhân mỗi giá trị được ghi với một hệ số. Ví dụ, tỷ lệ từ 0 đến 1 có thể được scale lên miền 0 đến 100:

~~~java
DistributionSummary ratio = DistributionSummary
        .builder("business.checkout.completion.ratio")
        .description("Tỷ lệ hoàn tất checkout theo phần trăm")
        .baseUnit("percent")
        .scale(100)
        .register(registry);

ratio.record(0.85); // ghi nhận giá trị 85
~~~

Khi dùng scale, các số liệu tổng hợp cũng phản ánh giá trị sau scale. Hãy ghi rõ điều này trong mô tả metric để người truy vấn không nhầm giữa tỷ lệ 0.85 và 85 phần trăm.

## Đọc số liệu ở hệ thống giám sát

Với registry dạng time series như Prometheus, DistributionSummary thường được export thành count và sum; khi bật histogram, có thêm các bucket. Tên metric và hậu tố phụ thuộc quy tắc chuẩn hóa tên, base unit và phiên bản registry.

Ví dụ minh họa:

~~~text
http_response_size_bytes_count 5
http_response_size_bytes_sum 1500
~~~

Count là số mẫu; sum là tổng amount. Mean thường được tính từ sum chia count thay vì được export như một chuỗi riêng. Max có thể được export dưới dạng metric riêng tùy registry và phiên bản; hãy kiểm tra endpoint /actuator/prometheus hoặc dữ liệu scrape thực tế trước khi viết truy vấn.

Với Prometheus, có thể tính mean của các mẫu mới trong cửa sổ năm phút bằng tỷ lệ giữa tốc độ tăng của sum và count:

~~~promql
sum by (uri) (
  rate(http_response_size_bytes_sum[5m])
)
/
sum by (uri) (
  rate(http_response_size_bytes_count[5m])
)
~~~

Đây là trung bình có trọng số trên các observation trong cửa sổ, phù hợp hơn với việc lấy trung bình các mean riêng lẻ của từng instance. Để đếm số mẫu tăng thêm trong một giờ:

~~~promql
sum by (uri) (
  increase(http_response_size_bytes_count[1h])
)
~~~

Thay tên metric và label bằng tên thực tế được registry export. Với cumulative registry, count và totalAmount thường tích lũy kể từ khi meter được tạo; với step registry, các giá trị export có thể phản ánh step hiện tại. Max của implementation phổ biến lại được tính theo cửa sổ thống kê riêng. Hãy hiểu semantics của backend trước khi so sánh trực tiếp count, mean và max.

## Kiểm thử DistributionSummary

SimpleMeterRegistry phù hợp cho unit test vì giữ dữ liệu trong bộ nhớ và không cần kết nối backend:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DistributionSummaryTest {
    @Test
    void recordsCountTotalMeanAndMax() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            DistributionSummary summary = DistributionSummary
                    .builder("test.response.size")
                    .baseUnit("bytes")
                    .register(registry);

            summary.record(120);
            summary.record(240);
            summary.record(300);

            assertThat(summary.count()).isEqualTo(3);
            assertThat(summary.totalAmount()).isEqualTo(660.0);
            assertThat(summary.mean()).isEqualTo(220.0);
            assertThat(summary.max()).isEqualTo(300.0);
        } finally {
            registry.close();
        }
    }

    @Test
    void ignoresNegativeValues() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            DistributionSummary summary = registry.summary("test.payload.size");

            summary.record(100);
            summary.record(-50);

            assertThat(summary.count()).isEqualTo(1);
            assertThat(summary.totalAmount()).isEqualTo(100.0);
        } finally {
            registry.close();
        }
    }
}
~~~

Test đầu xác minh bốn số liệu từ ba mẫu đã biết. Test thứ hai xác minh giá trị âm bị bỏ qua và không làm count hoặc total amount tăng. Không nên dùng test với thời gian chờ để kiểm tra max hết hạn; nếu cần kiểm thử vòng đời cửa sổ, hãy cấu hình clock có thể điều khiển và expiry phù hợp với test.

Ngoài unit test, kiểm thử tích hợp nên xác minh metric xuất hiện ở endpoint của ứng dụng, tên và đơn vị được chuẩn hóa như dự kiến, tag có cardinality hữu hạn và histogram chỉ được bật khi cần thiết.

## Những lỗi thường gặp

**Nhầm count với tổng số đơn vị.** Một lần record(500) tăng count một và total amount 500. Hãy xác định đang đếm mẫu hay đếm đơn vị bên trong mẫu.

**Coi mean là trung bình của các mean instance.** Khi tổng hợp nhiều instance, dùng tổng sum chia tổng count để có trung bình có trọng số.

**Coi max là giá trị lớn nhất vĩnh viễn.** Max của implementation phổ biến là max theo cửa sổ thời gian và có thể trở về 0 sau khi mẫu cũ hết hạn.

**Ghi giá trị âm.** DistributionSummary.record() bỏ qua giá trị âm. Nếu đại lượng cần đo có miền âm/dương, hãy chọn cách biểu diễn khác hoặc tách thành các đại lượng không âm theo yêu cầu phân tích.

**Trộn đơn vị.** Không ghi bytes và kilobytes vào cùng một summary. Dùng baseUnit và quy đổi dữ liệu trước khi ghi.

**Dùng tag có giá trị không giới hạn.** Không gắn user ID, order ID hoặc full URL làm tag. Dùng các chiều hữu hạn như channel hoặc route template.

**Bật histogram mà không giới hạn miền giá trị.** Histogram có thể tạo thêm nhiều chuỗi dữ liệu. Khi bật percentile histogram, hãy đặt giới hạn giá trị kỳ vọng phù hợp và cân nhắc chi phí bộ nhớ, cardinality.

## Checklist đưa DistributionSummary vào ứng dụng

1. Đại lượng cần đo là số học, không phải thời gian.
2. Mỗi lần record() tương ứng với một observation có định nghĩa rõ.
3. Chỉ ghi giá trị không âm; kiểm tra dữ liệu đầu vào trước khi ghi.
4. Chọn đơn vị thống nhất và khai báo baseUnit.
5. Dùng count() để đếm mẫu, totalAmount() để tính tổng, mean() để xem trung bình.
6. Diễn giải max() theo cửa sổ thống kê của registry.
7. Khi tổng hợp nhiều instance, tính mean từ tổng amount chia tổng count.
8. Giữ tag có tập giá trị hữu hạn.
9. Chỉ bật histogram/percentile khi dashboard hoặc cảnh báo cần phân bố chi tiết.
10. Kiểm thử count, totalAmount, mean, max và hành vi với dữ liệu âm.

## Kết luận

DistributionSummary cung cấp một cách thống nhất để ghi nhận phân bố các đại lượng số. count() cho biết số mẫu, totalAmount() cho biết tổng giá trị, mean() cho biết trung bình và max() cho biết cực đại trong cửa sổ thống kê mà implementation duy trì. Hiểu rõ sự khác nhau giữa bốn số liệu, chọn đơn vị nhất quán và kiểm thử dữ liệu đầu vào sẽ giúp metrics phản ánh đúng hành vi ứng dụng.

## Tài liệu tham khảo

- [Micrometer - Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): cách tạo summary, scale, max theo cửa sổ thời gian, histogram và chi phí lưu trữ.
- [Micrometer - DistributionSummary API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/DistributionSummary.html): hợp đồng của record, count, totalAmount, mean và max.
- [Micrometer - Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): cấu hình histogram và percentile.
