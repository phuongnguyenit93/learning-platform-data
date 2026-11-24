# Tính phân vị từ histogram và kiểm tra tương thích cấu hình thống kê

Prometheus có thể tính p50, p95 hoặc p99 từ histogram do ứng dụng xuất ra. Với Micrometer, histogram thường được bật cho `Timer` hoặc `DistributionSummary`; registry Prometheus xuất các bucket cùng bộ đếm quan sát để Prometheus tổng hợp và ước lượng percentile.

Để kết quả có ý nghĩa khi ứng dụng chạy nhiều instance, các instance phải xuất dữ liệu thống kê tương thích: cùng metric, cùng đơn vị, cùng ý nghĩa, cùng ranh giới bucket và các chiều tag cần thiết. Nếu một instance dùng bucket 100 ms, 300 ms, 1 giây còn instance khác dùng 200 ms, 500 ms, 2 giây, việc cộng các bucket theo nhãn `le` có thể thiếu hoặc sai số quan sát tại một số ranh giới.

Bài này tập trung vào classic histogram của Prometheus, cách dùng `histogram_quantile()`, cách tính tỷ lệ đáp ứng SLO và cách kiểm tra cấu hình thống kê trước khi tổng hợp dữ liệu từ nhiều instance.

## 1. Prometheus histogram xuất những dữ liệu nào?

Một classic histogram của Prometheus thường xuất ba nhóm chuỗi:

- `<metric>_bucket`: số quan sát tích lũy đến từng ranh giới bucket.
- `<metric>_sum`: tổng các giá trị đã quan sát.
- `<metric>_count`: tổng số quan sát.

Ví dụ Timer có thể được export thành các series:

```text
http_server_requests_seconds_bucket{le="0.1", ...}
http_server_requests_seconds_bucket{le="0.3", ...}
http_server_requests_seconds_bucket{le="1.0", ...}
http_server_requests_seconds_bucket{le="+Inf", ...}
http_server_requests_seconds_sum{...}
http_server_requests_seconds_count{...}
```

Tên cụ thể phụ thuộc meter name, naming convention và cấu hình registry. Với Timer, Prometheus thường biểu diễn thời lượng theo giây. Luôn kiểm tra endpoint metrics thực tế trước khi viết truy vấn.

Nhãn `le` có nghĩa là *less than or equal to*. Bucket `le="0.3"` chứa tất cả quan sát có giá trị nhỏ hơn hoặc bằng 0,3 giây. Bucket có `le="+Inf"` chứa toàn bộ quan sát và có số đếm bằng `_count`.

### Bucket là số đếm tích lũy

Giả sử có 100 request với phân bố:

| Khoảng độ trễ riêng | Số request |
|---|---:|
| đến 100 ms | 60 |
| trên 100 đến 300 ms | 25 |
| trên 300 đến 500 ms | 10 |
| trên 500 ms đến 1 giây | 4 |
| trên 1 giây | 1 |

Prometheus xuất bucket tích lũy:

| Ranh giới `le` | Số request tích lũy |
|---|---:|
| `0.1` | 60 |
| `0.3` | 85 |
| `0.5` | 95 |
| `1.0` | 99 |
| `+Inf` | 100 |

Không cộng các bucket tích lũy với nhau. Một request trong bucket 100 ms cũng được tính trong các bucket 300 ms, 500 ms và 1 giây. Khi cần số quan sát riêng giữa hai ranh giới, lấy hiệu của hai bucket tích lũy liên tiếp.

## 2. histogram_quantile() tính percentile như thế nào?

Hàm `histogram_quantile(phi, buckets)` ước lượng phân vị `phi` từ các bucket histogram. Ví dụ:

- `phi = 0.50`: p50, trung vị.
- `phi = 0.95`: p95.
- `phi = 0.99`: p99.

Với classic histogram, dữ liệu đầu vào phải giữ nhãn `le` để Prometheus biết ranh giới bucket. Thông thường cần tính tốc độ tăng của các counter bucket trong một cửa sổ thời gian, sau đó cộng các instance theo ranh giới bucket rồi mới tính percentile.

Truy vấn p95 cơ bản:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Cách đọc:

1. `rate(...[5m])` tính tốc độ tăng của số quan sát trong từng bucket trên cửa sổ 5 phút.
2. `sum by (le)(...)` cộng dữ liệu từ các instance, giữ lại ranh giới bucket.
3. `histogram_quantile(0.95, ...)` ước lượng p95 từ histogram tổng hợp.

Dùng `rate` trước `sum` để Prometheus xử lý counter reset của từng instance trước khi gộp. Nếu cộng counter của các instance trước rồi mới tính rate, lần restart ở một instance có thể làm sai phép tính.

### Giữ các chiều cần phân tích

Nếu cần p95 theo service, hãy giữ nhãn service trong phép tổng hợp:

```promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Nếu cần phân tách theo service và HTTP method:

```promql
histogram_quantile(
  0.99,
  sum by (service, method, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Không giữ `instance` nếu mục tiêu là percentile toàn service. Nếu giữ `instance`, Prometheus sẽ tính phân vị riêng cho từng instance. Chọn nhãn trong `by(...)` theo đúng câu hỏi dashboard cần trả lời.

## 3. Vì sao phải cộng histogram trước khi tính percentile?

Percentile của từng instance không thể cộng hoặc lấy trung bình để tạo percentile toàn hệ thống.

Ví dụ:

| Instance | p95 cục bộ |
|---|---:|
| A | 100 ms |
| B | 900 ms |

Trung bình hai giá trị là 500 ms, nhưng 500 ms không phải p95 của tất cả request từ A và B. Mỗi instance có thể nhận số lượng request rất khác nhau và có phân bố riêng.

Với histogram, Prometheus cộng số quan sát ở cùng ranh giới bucket của các instance. Sau khi đã có phân bố tổng hợp, `histogram_quantile()` mới ước lượng percentile toàn service.

Đây là lý do histogram bucket phù hợp khi cần percentile có thể tổng hợp. Nếu chỉ xuất percentile được tính ở phía ứng dụng, các giá trị p95 cục bộ không chứa đủ thông tin để khôi phục phân bố tổng thể.

## 4. Kết quả percentile là giá trị ước lượng

Classic histogram không lưu lại mọi thời lượng gốc. Nó lưu số đếm theo bucket. Prometheus ước lượng vị trí percentile bên trong bucket chứa phân vị, thường bằng nội suy tuyến tính giữa các ranh giới.

Do đó, độ chính xác phụ thuộc cách chọn bucket:

- Bucket rộng làm kết quả percentile kém chính xác hơn trong vùng đó.
- Bucket dày hơn quanh vùng quan tâm cải thiện độ phân giải.
- Bucket quá nhiều làm tăng số chuỗi thời gian, lưu trữ và chi phí truy vấn.
- Nếu percentile rơi vào bucket `+Inf`, Prometheus dùng ranh giới trên của bucket hữu hạn ngay trước đó làm giá trị ước lượng. Histogram không cho biết các quan sát trong bucket vô hạn lớn hơn ranh giới này bao xa, vì vậy cần có bucket hữu hạn phù hợp với vùng tail đang quan tâm.

Ví dụ, nếu p95 nằm trong bucket từ 300 ms đến 500 ms, Prometheus ước lượng vị trí trong khoảng này dựa trên số đếm tích lũy. Kết quả không phải thời lượng chính xác của request thứ 95.

Không diễn giải p95 là thời gian tối đa. p95 cho biết khoảng 95% quan sát không vượt quá giá trị ước lượng; phần đuôi còn lại có thể chậm hơn.

## 5. Bật histogram trong Micrometer

Có thể cấu hình histogram ngay khi xây dựng Timer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public class RequestMetrics {

    private final Timer requestTimer;

    public RequestMetrics(MeterRegistry registry) {
        this.requestTimer = Timer.builder("http.server.requests")
            .description("HTTP request processing duration")
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofMillis(500),
                Duration.ofSeconds(1)
            )
            .minimumExpectedValue(Duration.ofMillis(1))
            .maximumExpectedValue(Duration.ofSeconds(10))
            .register(registry);
    }

    public void record(Runnable handler) {
        requestTimer.record(handler);
    }
}
```

Các cấu hình quan trọng:

- `publishPercentileHistogram()` bật histogram bucket để backend có thể tính percentile.
- `serviceLevelObjectives(...)` bổ sung bucket tại các ngưỡng có ý nghĩa với SLO.
- `minimumExpectedValue(...)` và `maximumExpectedValue(...)` giới hạn miền thống kê phù hợp với đại lượng đo.

SLO bucket và bucket được tạo cho histogram có thể cùng xuất hiện trong dữ liệu. Chọn các ranh giới dựa trên độ trễ thực tế và yêu cầu vận hành, không bật histogram rộng cho mọi meter một cách mặc định.

### Cấu hình qua Spring Boot

Với Spring Boot Actuator và Micrometer, có thể cấu hình phân phối theo tên meter trong `application.yml`:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 1s
      minimum-expected-value:
        http.server.requests: 1ms
      maximum-expected-value:
        http.server.requests: 10s
```

Các thuộc tính này áp dụng cho meter có tên khớp cấu hình. Hãy xác nhận tên meter trước khi cấu hình; tên nội bộ của Micrometer có thể khác tên series sau khi registry chuyển đổi để export.

Nếu dùng `publishPercentiles(0.5, 0.95, 0.99)`, Micrometer tính percentile tại từng instance và xuất các giá trị đó. Đây là cấu hình khác với histogram. Percentile phía ứng dụng phù hợp cho quan sát cục bộ; histogram bucket phù hợp hơn khi cần tổng hợp percentile từ nhiều instance.

## 6. Tính tỷ lệ đáp ứng một ngưỡng SLO

Histogram còn cho phép tính tỷ lệ request không vượt quá một ngưỡng cụ thể. Giả sử SLO yêu cầu request hoàn tất trong 300 ms. Với bucket `le="0.3"`, tỷ lệ đáp ứng ngưỡng trong cửa sổ 5 phút là:

```promql
sum(
  rate(http_server_requests_seconds_bucket{le="0.3"}[5m])
)
/
sum(
  rate(http_server_requests_seconds_count[5m])
)
```

Kết quả nằm trong khoảng 0 đến 1. Nhân với 100 để hiển thị phần trăm.

Nếu cần phân tách theo service, giữ cùng nhãn ở cả tử số và mẫu số:

```promql
sum by (service) (
  rate(http_server_requests_seconds_bucket{le="0.3"}[5m])
)
/
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
)
```

Tử số là tốc độ request có thời lượng không quá 300 ms; mẫu số là tốc độ tổng request. Đây là tỷ lệ đạt ngưỡng trong cửa sổ đang xét, không phải percentile.

SLO bucket cần được cấu hình tại đúng ngưỡng cần đánh giá. Nếu không có bucket tương ứng, truy vấn có thể không trả kết quả mong muốn. Có thể dùng một bucket lớn hơn làm ranh giới để ước lượng một tỷ lệ khác, nhưng không thay thế được ranh giới chính xác của SLO.

## 7. Kiểm tra tương thích cấu hình giữa các instance

Để tổng hợp histogram chính xác, các instance của cùng một service cần thống nhất cấu hình thống kê. Những điểm cần kiểm tra gồm:

| Thành phần | Điều cần tương thích | Hậu quả nếu không đồng nhất |
|---|---|---|
| Metric name | Cùng tên và cùng ngữ nghĩa | Có thể trộn các phép đo khác nhau hoặc tách cùng một phép đo thành nhiều metric |
| Meter type | Cùng loại, ví dụ đều là Timer | Cấu trúc series và ý nghĩa dữ liệu không giống nhau |
| Unit | Cùng đơn vị và scale | Giá trị tổng hợp không thể so sánh trực tiếp |
| Bucket boundaries | Cùng các ranh giới `le` | Bucket thiếu hoặc không tương ứng làm sai phân bố tổng hợp |
| SLO boundaries | Cùng các ngưỡng nghiệp vụ | Tỷ lệ SLO có thể chỉ tính được trên một phần instance |
| Tag keys và ý nghĩa | Cùng schema cho các chiều cần tổng hợp | Dữ liệu bị tách hoặc gộp sai khi truy vấn |
| Histogram enabled | Các instance cần tổng hợp đều export bucket | Instance không có bucket bị thiếu khỏi phân bố |
| Naming convention | Cùng quy tắc chuyển tên và đơn vị | Truy vấn có thể đọc nhầm hoặc bỏ sót series |

Ví dụ, instance A export bucket `0.1`, `0.3`, `0.5`, `+Inf`; instance B export `0.2`, `0.5`, `1.0`, `+Inf`. Khi cộng theo `le`, bucket `0.1` không có dữ liệu từ B và bucket `0.2` không có dữ liệu từ A. Các số đếm tại những ranh giới này không đại diện cho cùng một tập instance, dẫn đến percentile tổng hợp sai.

Vì vậy, cần triển khai cùng cấu hình histogram cho mọi replica thuộc cùng một nhóm tổng hợp. Khi rollout phiên bản mới có thay đổi bucket, cần cân nhắc giai đoạn chuyển tiếp và không trộn dữ liệu có cấu trúc bucket khác nhau trong cùng truy vấn percentile.

## 8. Kiểm tra bucket thực tế trên Prometheus

Trước khi dùng `histogram_quantile()`, hãy xem các bucket mà từng instance đang xuất.

Truy vấn liệt kê các cặp instance và ranh giới bucket:

```promql
group by (instance, le) (
  http_server_requests_seconds_bucket{
    service="checkout",
    method="GET"
  }
)
```

Có thể kiểm tra số instance đang cung cấp từng ranh giới:

```promql
count by (le) (
  group by (instance, le) (
    http_server_requests_seconds_bucket{
      service="checkout",
      method="GET"
    }
  )
)
```

Nếu kết quả có số instance khác nhau giữa các giá trị `le`, có thể một số instance không export cùng bộ bucket hoặc một số target đang thiếu dữ liệu. Hãy kiểm tra riêng từng instance và cấu hình triển khai.

Có thể kiểm tra tổng số quan sát theo instance:

```promql
sum by (instance) (
  rate(http_server_requests_seconds_count{
    service="checkout",
    method="GET"
  }[5m])
)
```

Đối chiếu số quan sát giúp phát hiện instance có traffic nhưng không xuất histogram như mong đợi. Cần phân biệt trường hợp instance không nhận request với trường hợp registry không bật histogram.

## 9. Kiểm tra thống kê sau khi cấu hình Micrometer

Một quy trình xác minh hữu ích:

1. **Kiểm tra cấu hình build và runtime.** Xác nhận ứng dụng có Prometheus registry phù hợp và các phiên bản Micrometer tương thích.
2. **Kiểm tra tên meter nội bộ.** Đảm bảo cấu hình Spring Boot hoặc builder áp dụng đúng meter cần đo.
3. **Kiểm tra endpoint export.** Mở `/actuator/prometheus` và tìm các series `_bucket`, `_sum`, `_count`.
4. **Kiểm tra nhãn `le`.** Xác nhận có các ranh giới hữu hạn dự kiến và bucket `+Inf`.
5. **Kiểm tra từng instance.** So sánh bộ bucket và tag schema giữa các replica.
6. **Chạy truy vấn percentile.** Kiểm tra `histogram_quantile()` có dữ liệu và đơn vị đúng.
7. **Đối chiếu với SLO.** So sánh tỷ lệ dưới ngưỡng bằng bucket với yêu cầu dịch vụ.
8. **Theo dõi cardinality.** Đánh giá số chuỗi thời gian sau khi bật histogram.

Ví dụ endpoint có các series sau là dấu hiệu histogram classic đã được export:

```text
http_server_requests_seconds_bucket{le="0.1", ...}
http_server_requests_seconds_bucket{le="0.3", ...}
http_server_requests_seconds_bucket{le="0.5", ...}
http_server_requests_seconds_bucket{le="+Inf", ...}
http_server_requests_seconds_sum{...}
http_server_requests_seconds_count{...}
```

Nếu chỉ thấy `_sum` và `_count` mà không thấy `_bucket`, cần kiểm tra histogram có được bật cho meter đó không, registry có hỗ trợ cấu hình đang dùng không và meter có khớp tên cấu hình không.

## 10. Chọn cửa sổ rate phù hợp

Truy vấn thường dùng `rate(...[5m])`, nhưng cửa sổ cần phù hợp với tần suất scrape và lưu lượng.

- Cửa sổ quá ngắn có thể thiếu mẫu hoặc tạo percentile dao động mạnh.
- Cửa sổ dài làm mượt dữ liệu nhưng phản ứng chậm với sự cố mới.
- Với lưu lượng thấp, số quan sát ít khiến p95/p99 thiếu ổn định.
- Khi so sánh các service hoặc phiên bản, nên dùng cửa sổ và cách tổng hợp nhất quán.

Percentile từ histogram phản ánh phân bố trong cửa sổ truy vấn. p95 trong 5 phút có thể khác đáng kể p95 trong 1 giờ vì hai cửa sổ chứa các tập request khác nhau.

Với alert SLO, cần xem cả độ trễ và số lượng request. Một p99 dao động trên vài request không nhất thiết có ý nghĩa giống p99 trên hàng nghìn request. Có thể bổ sung điều kiện về traffic hoặc dùng cửa sổ dài hơn để giảm nhiễu.

## 11. Histogram và percentile phía ứng dụng không thay thế nhau

| Đặc điểm | Percentile phía ứng dụng | Histogram bucket |
|---|---|---|
| Cấu hình Micrometer | `publishPercentiles(...)` | `publishPercentileHistogram()` hoặc SLO buckets |
| Nơi tính | Trong từng instance | Backend |
| Dữ liệu export | Giá trị quantile cục bộ | Số đếm theo bucket |
| Tổng hợp nhiều instance | Không thể gộp chính xác quantile | Có thể cộng bucket tương thích |
| Phân tích SLO theo ngưỡng bucket | Không trực tiếp | Có |
| Chi phí | Một số series cho từng percentile | Nhiều series theo bucket và tag |

Không cần bật cả hai cách nếu không có nhu cầu rõ ràng. Với dashboard service-wide và SLO, histogram thường cung cấp dữ liệu phù hợp hơn. Percentile phía ứng dụng có thể hữu ích khi muốn xem phân vị cục bộ của từng instance.

## 12. Cardinality và chi phí histogram

Mỗi bucket được export cho từng tổ hợp tag. Nếu một meter có nhiều tag combinations và nhiều bucket, số chuỗi thời gian có thể tăng nhanh.

Ví dụ, một Timer có 20 bucket, 4 HTTP methods, 5 status groups và 10 route templates có thể tạo ra hàng nghìn chuỗi thời gian khi nhân các chiều tag và bucket. Số lượng thực tế còn phụ thuộc registry và các thống kê bổ sung.

Để kiểm soát chi phí:

- Chỉ bật histogram cho meter thực sự cần percentile hoặc SLO.
- Dùng route template thay URL động.
- Không dùng request ID, user ID hoặc exception message làm tag.
- Chọn bucket theo vùng độ trễ có ý nghĩa.
- Dùng cùng bộ bucket giữa các instance.
- Theo dõi số chuỗi thời gian sau rollout.
- Xem xét bỏ các percentile phía ứng dụng nếu histogram đã đáp ứng nhu cầu.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Lấy trung bình p95 của từng instance | Percentile không có tính cộng gộp | Cộng histogram bucket rồi tính percentile |
| Quên giữ nhãn `le` trong PromQL | Hàm quantile không còn ranh giới bucket | Dùng `sum by (le, ...)` |
| Cộng counter trước khi gọi rate | Counter reset của instance có thể làm sai kết quả | Gọi `rate` trên từng series rồi mới `sum` |
| Bucket giữa instance khác nhau | Các ranh giới không đại diện cùng phạm vi quan sát | Đồng bộ histogram/SLO configuration |
| Chỉ bật histogram ở một số replica | Phân bố tổng hợp thiếu dữ liệu của replica còn lại | Triển khai cùng cấu hình trên toàn nhóm |
| Nhầm p95 với giá trị tối đa | Phần đuôi 5% vẫn có thể chậm hơn | Xem p99, max và trace khi cần |
| Dùng cửa sổ quá ngắn với traffic thấp | Percentile dao động và thiếu mẫu | Chọn cửa sổ phù hợp, xem số quan sát |
| Dùng bucket không đúng đơn vị | Ranh giới SLO không khớp giá trị đo | Xác nhận Timer xuất giây và bucket theo cùng đơn vị |
| Dùng histogram để lưu từng request | Histogram chỉ lưu phân bố theo bucket | Dùng log/trace cho từng request |

## 14. Checklist trước khi triển khai percentile toàn service

- [ ] Xác nhận metric là classic histogram với series `_bucket`, `_sum`, `_count`.
- [ ] Xác nhận bucket có nhãn `le` và bucket `+Inf`.
- [ ] Bật histogram hoặc SLO bucket cho đúng meter trong Micrometer.
- [ ] Đồng bộ metric name, loại meter, đơn vị và bucket boundaries giữa các instance.
- [ ] Đồng bộ tag keys và ý nghĩa của từng tag.
- [ ] Xác nhận mọi instance cần tổng hợp đều export bucket.
- [ ] Dùng `rate(bucket[window])` trước khi tổng hợp.
- [ ] Giữ `le` trong `sum by (...)` trước `histogram_quantile()`.
- [ ] Không lấy trung bình percentile cục bộ để suy ra percentile toàn hệ thống.
- [ ] Dùng bucket đúng ngưỡng nếu cần tính tỷ lệ SLO.
- [ ] Chọn cửa sổ truy vấn phù hợp với scrape interval và traffic.
- [ ] Kiểm tra cardinality và chi phí lưu trữ sau khi bật histogram.

Prometheus tính percentile từ histogram bằng cách tổng hợp số đếm tại các bucket tương ứng rồi ước lượng phân vị trên phân bố chung. Với Micrometer, điều quan trọng là mọi instance cần xuất cùng metric, đơn vị, tag schema và ranh giới bucket. Hãy kiểm tra dữ liệu `_bucket` thực tế trước khi triển khai dashboard hoặc alert; một truy vấn đúng cú pháp vẫn có thể cho kết quả sai nếu cấu hình thống kê giữa các instance không tương thích.

## Tài liệu tham khảo

- [Prometheus Histograms and Summaries](https://prometheus.io/docs/practices/histograms/) — bucket, `histogram_quantile()` và khả năng tổng hợp histogram.
- [Prometheus histogram_quantile()](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile) — cú pháp và cách ước lượng quantile.
- [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html) — cấu hình histogram, percentile và SLO bucket.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — histogram và phân bố thời lượng của Timer.

