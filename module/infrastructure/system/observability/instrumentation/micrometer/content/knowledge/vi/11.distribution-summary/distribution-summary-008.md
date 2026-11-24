# Phân biệt DistributionSummary trong Micrometer với kiểu Summary của Prometheus

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `DistributionSummary` là một loại meter của Micrometer dùng để ghi nhận phân phối của các giá trị số không phải thời gian, chẳng hạn kích thước payload, số phần tử trong batch hoặc dung lượng dữ liệu xử lý. Prometheus cũng có một kiểu metric tên là `Summary`. Hai tên gọi gần giống nhau nhưng thuộc hai lớp khái niệm khác nhau.

`DistributionSummary` mô tả API instrumentation mà ứng dụng Java sử dụng. `Summary` của Prometheus mô tả cấu trúc dữ liệu được xuất trong Prometheus exposition format. Khi kết nối hai hệ thống, không nên suy ra kiểu dữ liệu được xuất chỉ từ tên meter. Cần hiểu cách Prometheus Summary và Histogram biểu diễn số liệu, cấu hình registry Micrometer và kiểm tra kết quả thực tế tại endpoint export.

## 1. Hai khái niệm nằm ở hai lớp khác nhau

Micrometer cung cấp API thống nhất để ứng dụng ghi nhận số liệu mà không phải phụ thuộc trực tiếp vào một backend. `DistributionSummary` nhận các giá trị số, duy trì thống kê như số lần ghi nhận và tổng các giá trị, đồng thời có thể cấu hình percentile hoặc histogram tùy registry hỗ trợ.

Prometheus định nghĩa hai kiểu metric thường được dùng để mô tả phân phối:

- **Summary**: xuất tổng số quan sát, tổng giá trị và có thể có các quantile được tính ở phía client.
- **Histogram**: chia quan sát vào các bucket theo ngưỡng; Prometheus lưu số đếm bucket để có thể tổng hợp và tính quantile ở phía server.

| Thuật ngữ | Thuộc lớp nào? | Vai trò |
| --- | --- | --- |
| Micrometer `DistributionSummary` | API instrumentation | Ghi nhận phân phối của giá trị số không phải thời gian |
| Prometheus `Summary` | Kiểu metric trong exposition | Xuất `_count`, `_sum` và có thể có quantile samples |
| Prometheus `Histogram` | Kiểu metric trong exposition | Xuất bucket tích lũy cùng `_count` và `_sum` |

Một `DistributionSummary` không đồng nghĩa với một Prometheus Summary. Registry có thể ánh xạ meter sang dạng exposition phù hợp với cấu hình và khả năng của backend. Vì vậy, hãy phân biệt tên API trong code với tên và kiểu metric mà Prometheus thực sự nhận được.

## 2. DistributionSummary đo đại lượng nào?

`DistributionSummary` phù hợp với một đại lượng số có thể nhận nhiều giá trị qua các lần ghi nhận. Ví dụ, mỗi request có payload khác nhau và ta muốn biết kích thước payload phân phối ra sao.

```java
DistributionSummary payloadSize = registry.summary(
    "orders.payload.size",
    "format", "json");

payloadSize.record(512);
payloadSize.record(2048);
payloadSize.record(1024);
```

Sau ba lần ghi nhận, summary có `count` bằng 3 và `totalAmount` bằng 3584. Đơn vị của các giá trị do ứng dụng quy ước; trong ví dụ này chúng là byte.

Khi cần mô tả, đơn vị và cấu hình thống kê, dùng builder:

```java
DistributionSummary payloadSize =
    DistributionSummary.builder("orders.payload.size")
        .description("Size of order request payloads")
        .baseUnit("bytes")
        .tag("format", "json")
        .register(registry);

payloadSize.record(payload.length);
```

Các trường hợp thường gặp:

- Kích thước request hoặc response theo byte.
- Số bản ghi trong một batch.
- Số item được xử lý trong một lần chạy.
- Dung lượng file được nhập hoặc xuất.
- Giá trị số khác cần quan sát phân phối theo thời gian.

Nếu đại lượng cần đo là thời lượng, hãy dùng `Timer`. `DistributionSummary` không tự diễn giải đơn vị số thành thời gian.

## 3. Prometheus Summary biểu diễn dữ liệu ra sao?

Một Prometheus Summary có thể xuất ba nhóm thông tin:

1. Quantile samples, thường có label `quantile` như `0.5`, `0.9` hoặc `0.99`.
2. `_sum`: tổng giá trị đã quan sát.
3. `_count`: tổng số quan sát.

Ví dụ minh họa một Summary theo kích thước payload:

```text
# TYPE request_payload_bytes summary
request_payload_bytes{quantile="0.5"} 1024
request_payload_bytes{quantile="0.9"} 4096
request_payload_bytes{quantile="0.99"} 8192
request_payload_bytes_sum 245760
request_payload_bytes_count 100
```

Đây là dữ liệu minh họa để giải thích cấu trúc, không phải tên metric cố định do Micrometer tạo ra. Quantile là kết quả tính ở phía client theo cấu hình và cửa sổ thời gian của Summary. `_sum` và `_count` cho phép tính trung bình trong một khoảng thời gian, nhưng không đủ để dựng lại toàn bộ phân phối hoặc tính một quantile mới ở server.

Một điểm quan trọng là quantile của Summary thường chỉ có ý nghĩa ở phạm vi instance đã tính nó. Nếu có nhiều instance cùng xuất quantile p95, không thể cộng hoặc lấy trung bình các giá trị p95 đó để có p95 chính xác của toàn service. Quantile không phải đại lượng có tính cộng gộp.

## 4. Prometheus Histogram biểu diễn dữ liệu ra sao?

Histogram chia giá trị quan sát thành các bucket theo ngưỡng. Mỗi bucket `le` biểu thị số quan sát nhỏ hơn hoặc bằng ngưỡng đó. Các bucket là tích lũy: bucket có ngưỡng 4096 bao gồm cả các quan sát đã nằm trong bucket 1024.

Ví dụ:

```text
# TYPE orders_payload_size_bytes histogram
orders_payload_size_bytes_bucket{le="1024"} 40
orders_payload_size_bytes_bucket{le="4096"} 85
orders_payload_size_bytes_bucket{le="8192"} 97
orders_payload_size_bytes_bucket{le="+Inf"} 100
orders_payload_size_bytes_sum 245760
orders_payload_size_bytes_count 100
```

Các bucket cho biết số lượng quan sát đến từng ngưỡng; `_sum` và `_count` vẫn được xuất. Ví dụ `_bucket` và label `le` ở đây mô tả classic histogram. Prometheus cũng hỗ trợ native histogram với cách lưu trữ và truy vấn khác; hãy kiểm tra kiểu dữ liệu mà exporter và cấu hình ingestion đang sử dụng. Với classic histogram, dữ liệu bucket có thể cộng giữa các instance có cùng ranh giới bucket, nhờ đó Prometheus có thể tính quantile tổng hợp bằng `histogram_quantile()`.

Ví dụ truy vấn p95 trên toàn bộ instance:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_payload_size_bytes_bucket[5m])
  )
)
```

`rate()` được áp dụng trên từng time series bucket trước khi tổng hợp theo `le`. Nếu cần phân tách theo service hoặc một tag có cardinality thấp, thêm chiều đó vào `sum by`, ví dụ `sum by (service, le)`. Tên metric và label trong truy vấn phải khớp với endpoint exposition thực tế.

## 5. Cấu hình DistributionSummary để xuất histogram

Với Prometheus, histogram thường là lựa chọn phù hợp khi cần tính quantile tổng hợp trên nhiều instance. Có thể bật percentile histogram và khai báo các ngưỡng SLO cho `DistributionSummary`:

```java
DistributionSummary payloadSize =
    DistributionSummary.builder("orders.payload.size")
        .description("Size of order request payloads")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .minimumExpectedValue(1L)
        .maximumExpectedValue(65536L)
        .serviceLevelObjectives(1024, 4096, 8192)
        .register(registry);
```

Sau đó ghi nhận giá trị theo cùng đơn vị:

```java
payloadSize.record(requestBody.length);
```

`publishPercentileHistogram()` yêu cầu Micrometer tạo các bucket phù hợp với registry hỗ trợ histogram. `serviceLevelObjectives(...)` thêm các ranh giới bucket cụ thể theo ngưỡng mà ứng dụng quan tâm. `minimumExpectedValue(...)` và `maximumExpectedValue(...)` giới hạn miền bucket được xuất, giúp kiểm soát số bucket và bộ nhớ histogram. Với `DistributionSummary`, mặc định không có miền min/max; nếu bật percentile histogram mà không giới hạn miền, Micrometer có thể chọn toàn bộ 276 bucket định trước. Hãy chọn min/max theo miền dữ liệu thực tế; các giá trị trong ví dụ chỉ là giới hạn minh họa cho payload tối đa 64 KiB.

Không phải mọi registry đều xuất cùng một cấu trúc. Cấu hình builder là yêu cầu đối với Micrometer; registry và phiên bản tích hợp quyết định cách yêu cầu đó được chuyển thành metric của backend. Sau khi cấu hình, kiểm tra `/actuator/prometheus` hoặc endpoint export tương ứng để xác nhận các series `_bucket`, `_sum` và `_count` thực sự có mặt.

## 6. Percentile phía client và histogram phía server

Micrometer có thể cấu hình percentile tính ở phía client bằng `publishPercentiles(...)`:

```java
DistributionSummary payloadSize =
    DistributionSummary.builder("orders.payload.size")
        .baseUnit("bytes")
        .publishPercentiles(0.5, 0.9, 0.95, 0.99)
        .register(registry);
```

Các percentile này được tính trong ứng dụng/registry cho từng meter. Chúng hữu ích khi cần một góc nhìn cục bộ, nhưng không thể cộng gộp chính xác thành percentile của toàn bộ các instance. Registry quyết định cách biểu diễn chúng ở backend. Với Prometheus Java Client 1.x, không thể xuất client-side percentile và histogram dưới cùng một tên metric theo cách kết hợp cũ; hãy kiểm tra phiên bản registry và cấu hình thực tế.

Histogram cung cấp bucket để backend tổng hợp quan sát rồi ước lượng quantile ở server. So sánh:

| Tiêu chí | Percentile phía client | Histogram bucket |
| --- | --- | --- |
| Nơi tính quantile | Trong ứng dụng/registry | Trong hệ giám sát như Prometheus |
| Phạm vi | Từng meter/instance | Có thể tổng hợp nhiều instance |
| Có thể cộng gộp quantile? | Không | Cộng bucket trước khi tính quantile |
| Chi phí dữ liệu | Các percentile được cấu hình | Nhiều bucket cho mỗi tổ hợp tag |
| Truy vấn Prometheus | Không dùng `histogram_quantile()` trên quantile samples | Dùng `histogram_quantile()` trên bucket rate |

Nếu mục tiêu là dashboard p95/p99 ở cấp service chạy nhiều replica, hãy ưu tiên histogram bucket được hỗ trợ bởi registry. Nếu chỉ quan sát một instance hoặc cần percentile cục bộ, client-side percentile có thể phù hợp. Với Prometheus Java Client 1.x, client-side percentiles và histogram không thể được xuất đồng thời dưới cùng tên metric; hãy xác nhận giới hạn của phiên bản đang dùng trước khi kết hợp cấu hình.

## 7. Truy vấn count, sum và trung bình

Dù dùng Summary hay Histogram, `_count` và `_sum` thường cho phép tính thông lượng quan sát và giá trị trung bình trong một cửa sổ thời gian.

Số lần ghi nhận mỗi giây:

```promql
sum(rate(orders_payload_size_bytes_count[5m]))
```

Tổng số byte được ghi nhận mỗi giây:

```promql
sum(rate(orders_payload_size_bytes_sum[5m]))
```

Kích thước payload trung bình trong cửa sổ 5 phút:

```promql
sum(rate(orders_payload_size_bytes_sum[5m]))
/
sum(rate(orders_payload_size_bytes_count[5m]))
```

Các truy vấn trên giả định exporter đặt tên series như ví dụ. Hãy xác nhận tên thực tế trong endpoint export. Nếu không có quan sát trong cửa sổ, mẫu số có thể bằng 0 hoặc truy vấn không có dữ liệu; dashboard nên thể hiện trạng thái không có mẫu thay vì gán một giá trị trung bình giả.

## 8. Vì sao không thể dùng quantile Summary để tổng hợp nhiều instance

Giả sử service có hai instance:

- Instance A xử lý 100 request, p95 kích thước payload là 2 KB.
- Instance B xử lý 10.000 request, p95 kích thước payload là 8 KB.

Lấy trung bình hai giá trị p95 thành 5 KB không tạo ra p95 chính xác của toàn service. Mỗi p95 đã được tính từ phân phối cục bộ và không mang đủ thông tin về toàn bộ các quan sát. Ngay cả khi số mẫu hai instance bằng nhau, trung bình các quantile vẫn không đảm bảo là quantile của dữ liệu gộp.

Histogram giải quyết bài toán tổng hợp bằng cách lưu số lượng quan sát trong các bucket có cùng ranh giới. Ta cộng số đếm bucket giữa các instance rồi tính quantile từ phân phối đã gộp. Kết quả là một ước lượng dựa trên độ phân giải của bucket; độ chính xác phụ thuộc cách chọn bucket.

Vì vậy, đừng viết truy vấn PromQL để lấy `avg()` của các series quantile p95 từ Summary rồi gọi kết quả đó là p95 toàn service. Nếu cần percentile tổng hợp, hãy xuất histogram bucket.

## 9. Kiểm soát cardinality và chi phí bucket

Mỗi bucket của histogram được nhân với từng tổ hợp tag. Nếu meter có nhiều giá trị `region`, `channel`, `result` và các tag không giới hạn như `customerId`, số time series có thể tăng rất nhanh. Bật histogram làm số series tăng thêm theo số bucket.

Nên chọn các tag có tập giá trị hữu hạn, ví dụ:

- `format`: `json`, `xml`, `protobuf`.
- `result`: `success`, `failure`.
- `operation`: một tập thao tác đã định nghĩa.
- `region`: danh sách vùng triển khai cố định.

Không dùng `orderId`, `userId`, URL thô, request ID hoặc nội dung do người dùng nhập làm tag. Cần tránh cấu hình quá nhiều bucket nếu không có câu hỏi vận hành tương ứng. Các ngưỡng SLO nên tập trung quanh vùng giá trị mà hệ thống cần phân loại hoặc cảnh báo.

## 10. Kiểm thử DistributionSummary

`SimpleMeterRegistry` có thể xác minh ứng dụng ghi nhận đúng số quan sát và tổng giá trị mà không cần backend Prometheus:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PayloadSizeMetricsTest {
    @Test
    void recordsCountAndTotalAmount() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        DistributionSummary summary =
            DistributionSummary.builder("orders.payload.size")
                .baseUnit("bytes")
                .register(registry);

        summary.record(512);
        summary.record(2048);
        summary.record(1024);

        assertEquals(3, summary.count());
        assertEquals(3584.0, summary.totalAmount());
    }
}
```

Unit test này xác minh logic ghi nhận ở tầng Micrometer. Nó không chứng minh Prometheus nhận được Summary hay Histogram. Để kiểm tra ánh xạ backend, cần dùng Prometheus registry tương ứng trong test tích hợp hoặc khởi động ứng dụng rồi kiểm tra endpoint exposition, bao gồm kiểu metric, label và các series bucket/quantile.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Nghĩ `DistributionSummary` luôn xuất Prometheus Summary | Nhầm abstraction Micrometer với kiểu metric trong exposition; kiểm tra cấu hình và registry thực tế |
| Không tính được p95 toàn service | Chỉ xuất client-side quantile hoặc đang dùng Summary quantile thay vì histogram bucket |
| `histogram_quantile()` không trả kết quả | Không có series `_bucket`, sai tên metric hoặc sai label `le` |
| Trung bình không đúng đơn vị | Ghi giá trị theo nhiều đơn vị trong cùng meter hoặc đặt `baseUnit` không khớp |
| Số series tăng mạnh sau khi bật histogram | Quá nhiều bucket hoặc tổ hợp tag có cardinality cao |
| Trung bình có dữ liệu nhưng quantile không có | Có `_sum`/`_count` nhưng chưa xuất histogram bucket hoặc quantile samples |
| Unit test qua nhưng dashboard không thấy metric | `SimpleMeterRegistry` không kiểm tra định dạng export của Prometheus registry |

Khi số liệu không như mong đợi, hãy kiểm tra theo thứ tự: giá trị và đơn vị được ghi vào `DistributionSummary`, cấu hình histogram/percentile, registry đang dùng, dữ liệu exposition, rồi mới đến PromQL. Việc nhìn tên meter trong code không đủ để xác định kiểu metric Prometheus đã nhận.

## 12. Nguyên tắc áp dụng

`DistributionSummary` là meter Micrometer để ghi nhận phân phối giá trị số; Prometheus Summary là một kiểu metric có quantile phía client cùng `_sum` và `_count`; Prometheus Histogram lưu bucket để có thể tổng hợp và tính quantile phía server. Ba khái niệm liên quan nhưng không đồng nhất.

Nếu cần p95/p99 ở cấp toàn service, hãy cấu hình histogram bucket cho `DistributionSummary`, giữ ranh giới bucket nhất quán giữa các instance và truy vấn bằng `histogram_quantile()` sau khi tổng hợp bucket. Dùng client-side percentile khi cần quan sát cục bộ và hiểu rõ giới hạn tổng hợp. Cuối cùng, kiểm tra endpoint export để xác nhận registry thực sự phát ra dữ liệu mà dashboard đang truy vấn.

## Tài liệu tham khảo

- [Micrometer: Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Prometheus: Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
- [Prometheus: Metric Types](https://prometheus.io/docs/concepts/metric_types/)
