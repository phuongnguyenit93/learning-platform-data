# Ý nghĩa của histogram, bucket và phân vị p50, p95 hoặc p99

Khi đo thời gian xử lý bằng Micrometer `Timer` hoặc đo một đại lượng số bằng `DistributionSummary`, giá trị trung bình thường chưa đủ để hiểu trải nghiệm thực tế. Một dịch vụ có thể xử lý phần lớn request rất nhanh nhưng vẫn có một nhóm nhỏ request chậm bất thường. Histogram và percentile giúp mô tả phân bố của các lần đo, từ đó trả lời những câu hỏi như: 50% request hoàn tất trong bao lâu, 95% request có độ trễ thấp hơn ngưỡng nào, hay 1% request chậm nhất đang mất bao nhiêu thời gian.

Ba khái niệm cần phân biệt:

- **Histogram** lưu số lượng quan sát rơi vào các khoảng giá trị.
- **Bucket** là một khoảng hoặc ranh giới dùng để gom các quan sát trong histogram.
- **Percentile** là một phân vị của phân bố, chẳng hạn p50, p95 hoặc p99.

Micrometer có thể xuất histogram để backend tính percentile trên dữ liệu đã tổng hợp, hoặc tính percentile ở phía ứng dụng rồi xuất giá trị percentile. Hai cách này có đặc điểm khác nhau, đặc biệt khi cần tổng hợp metrics từ nhiều instance.

## 1. Vì sao cần nhìn vào phân bố?

Giả sử một dịch vụ xử lý 100 request. Có 95 request hoàn tất trong khoảng 100 ms, nhưng 5 request còn lại mất 2 giây. Trung bình của cả nhóm là:

$$
rac{95 	imes 100 + 5 	imes 2000}{100} = 195 	ext{ ms}
$$

Con số trung bình 195 ms không cho biết phần lớn request chỉ mất 100 ms, cũng không cho biết 5 request bị chậm tới 2 giây. Khi chỉ nhìn trung bình, nhóm request chậm có thể bị che khuất.

Percentile giúp diễn giải rõ hơn:

- p50 cho biết giá trị ở vị trí giữa của phân bố.
- p95 cho biết khoảng 95% quan sát có giá trị nhỏ hơn hoặc bằng ngưỡng đó.
- p99 cho biết khoảng 99% quan sát có giá trị nhỏ hơn hoặc bằng ngưỡng đó.

Các phân vị cao như p95 và p99 thường được dùng để theo dõi tail latency, tức độ trễ ở phần đuôi chậm của phân bố.

## 2. Histogram và bucket hoạt động như thế nào?

Histogram chia miền giá trị thành các bucket. Mỗi quan sát được ghi nhận vào bucket tương ứng với ranh giới của nó. Histogram không cần lưu toàn bộ từng giá trị riêng lẻ; nó duy trì số lượng quan sát theo các khoảng đã định.

Ví dụ, histogram đo thời gian request với các ranh giới 100 ms, 300 ms, 500 ms và 1 giây:

| Bucket (ranh giới trên) | Số quan sát trong khoảng riêng | Ý nghĩa |
|---|---:|---|
| đến 100 ms | 60 | 60 request không quá 100 ms |
| trên 100 đến 300 ms | 25 | 25 request nằm trong khoảng này |
| trên 300 đến 500 ms | 10 | 10 request nằm trong khoảng này |
| trên 500 ms đến 1 giây | 4 | 4 request nằm trong khoảng này |
| trên 1 giây | 1 | 1 request vượt 1 giây |

Có 100 quan sát. Nếu cần tính tỷ lệ request không quá 300 ms, cộng hai bucket đầu: 60 + 25 = 85 request, tương đương 85%.

### Bucket tích lũy trong Prometheus

Prometheus dùng histogram bucket có giá trị tích lũy. Nhãn `le` (less than or equal) biểu thị ranh giới trên; bucket `le="0.3"` chứa tất cả quan sát có giá trị nhỏ hơn hoặc bằng 0,3 giây, kể cả những quan sát thuộc bucket nhỏ hơn.

Từ ví dụ trên, số bucket tích lũy được biểu diễn như sau:

| Bucket Prometheus | Số quan sát tích lũy |
|---|---:|
| `le="0.1"` | 60 |
| `le="0.3"` | 85 |
| `le="0.5"` | 95 |
| `le="1.0"` | 99 |
| `le="+Inf"` | 100 |

Bucket `+Inf` chứa toàn bộ quan sát và bằng tổng số mẫu. Với Prometheus, các chuỗi thường có hậu tố `_bucket`, ví dụ `http_server_requests_seconds_bucket`.

Không cộng các bucket tích lũy với nhau để tính tổng vì một quan sát trong bucket nhỏ cũng đã được tính vào mọi bucket có ranh giới lớn hơn. Muốn lấy số quan sát nằm riêng giữa hai ranh giới, lấy hiệu của hai bucket tích lũy liên tiếp.

## 3. p50, p95 và p99 có ý nghĩa gì?

Percentile là giá trị mà một tỷ lệ phần trăm quan sát không vượt quá. Với độ trễ request:

- **p50 (median):** khoảng một nửa request có độ trễ không vượt quá p50; một nửa còn lại có thể chậm hơn.
- **p95:** khoảng 95% request có độ trễ không vượt quá p95; 5% còn lại nằm ở phần đuôi chậm hơn.
- **p99:** khoảng 99% request có độ trễ không vượt quá p99; 1% còn lại chậm hơn.

Ví dụ dashboard hiển thị:

| Phân vị | Độ trễ |
|---|---:|
| p50 | 80 ms |
| p95 | 240 ms |
| p99 | 900 ms |

Có thể diễn giải: request điển hình có độ trễ khoảng 80 ms; 95% request hoàn tất trong khoảng 240 ms; 1% request chậm nhất có độ trễ từ khoảng 900 ms trở lên.

p99 cao hơn nhiều so với p95 cho thấy phần đuôi phân bố có thể có một nhóm request chậm đáng kể. Đây là dấu hiệu nên điều tra thêm bằng trace, log và các metrics thành phần như database, pool kết nối hoặc dịch vụ phụ thuộc.

Percentile là giá trị ước lượng từ tập quan sát và cách tính cụ thể. Khi dùng histogram, độ chính xác phụ thuộc vào vị trí bucket và thuật toán nội suy giữa các ranh giới. Không nên diễn giải p95 là thời gian tối đa hoặc bảo đảm mọi request đều hoàn tất trong thời gian đó.

## 4. Histogram giúp ước lượng percentile ra sao?

Histogram cung cấp số lượng quan sát theo các bucket. Backend dùng phân bố bucket để ước lượng vị trí percentile.

Giả sử có 100 request và p95 cần tìm. p95 nằm quanh quan sát thứ 95 khi sắp xếp độ trễ tăng dần. Từ bảng bucket tích lũy:

- Đến 300 ms có 85 request.
- Đến 500 ms có 95 request.
- Đến 1 giây có 99 request.

Vì quan sát thứ 95 nằm trong hoặc tại ranh giới bucket 500 ms, p95 được ước lượng gần 500 ms. Nếu bucket rộng, kết quả có thể kém chính xác hơn. Nếu bucket được đặt dày hơn quanh vùng quan tâm, khả năng phân giải percentile trong vùng đó tốt hơn, nhưng số bucket và lượng dữ liệu export cũng tăng.

Histogram không giữ lại chính xác từng thời lượng đã đo. Nó giữ thông tin tổng hợp theo bucket, vì vậy percentile từ histogram thường là giá trị xấp xỉ.

## 5. Hai cách xuất percentile trong Micrometer

Micrometer hỗ trợ hai hướng chính để xuất thông tin percentile:

| Cách | API cấu hình | Nơi tính percentile | Có thể tổng hợp giữa instance? |
|---|---|---|---|
| Percentile phía ứng dụng | `publishPercentiles(0.5, 0.95, 0.99)` | Trong tiến trình ứng dụng | Không thể tổng hợp chính xác các giá trị percentile riêng lẻ |
| Histogram phía ứng dụng, tính ở backend | `publishPercentileHistogram()` | Backend truy vấn histogram | Có, nếu các bucket tương thích |

### Percentile phía ứng dụng

Khi dùng `publishPercentiles(...)`, Micrometer tính các phân vị trong từng instance và xuất các giá trị percentile tương ứng. Cách này thuận tiện khi chỉ quan sát một instance hoặc cần percentile cục bộ.

Tuy nhiên, percentile của các instance không thể cộng hoặc lấy trung bình để tạo percentile toàn hệ thống. Ví dụ:

- Instance A có p95 = 100 ms.
- Instance B có p95 = 900 ms.

Trung bình hai giá trị là 500 ms, nhưng 500 ms không phải p95 của toàn bộ request từ A và B. Muốn tính percentile toàn hệ thống, cần dữ liệu phân bố có thể tổng hợp, chẳng hạn histogram bucket.

### Histogram phía ứng dụng

Khi dùng `publishPercentileHistogram()`, Micrometer xuất các bucket phù hợp với registry/backend. Backend có thể tổng hợp số đếm bucket từ nhiều instance rồi tính percentile trên phân bố chung.

Cách này phù hợp khi cần dashboard p95/p99 ở cấp service, cluster hoặc region. Cần bảo đảm các instance sử dụng cùng quy ước bucket để phép tổng hợp có ý nghĩa.

## 6. Cấu hình Timer để xuất histogram và percentile

Ví dụ dùng Timer cho độ trễ xử lý request:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public class HttpRequestMetrics {

    private final Timer requestTimer;

    public HttpRequestMetrics(MeterRegistry registry) {
        this.requestTimer = Timer.builder("http.server.request.duration")
            .description("Time spent processing HTTP requests")
            .publishPercentileHistogram()
            .publishPercentiles(0.5, 0.95, 0.99)
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

    public void record(Runnable requestHandler) {
        requestTimer.record(requestHandler);
    }
}
```

Các cấu hình có ý nghĩa:

- `publishPercentileHistogram()`: bật histogram bucket để backend tính percentile.
- `publishPercentiles(...)`: yêu cầu Micrometer tính và xuất các percentile ở phía ứng dụng.
- `serviceLevelObjectives(...)`: thêm các ranh giới bucket cụ thể gắn với ngưỡng dịch vụ cần theo dõi.
- `minimumExpectedValue(...)` và `maximumExpectedValue(...)`: giới hạn miền giá trị histogram phù hợp với đặc tính thao tác và chi phí lưu trữ.

Không nhất thiết phải bật đồng thời histogram và percentile phía ứng dụng. Nếu cần percentile tổng hợp giữa nhiều instance, histogram thường là lựa chọn phù hợp. Nếu chỉ cần percentile cục bộ, có thể cân nhắc `publishPercentiles(...)`. SLO bucket có ích khi muốn đo tỷ lệ request đạt một ngưỡng cụ thể.

### Cấu hình qua Spring Boot

Với Spring Boot Actuator và Micrometer, có thể cấu hình phân phối theo tên meter trong `application.yml`:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      percentiles:
        http.server.requests: 0.5, 0.95, 0.99
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 1s
```

Tên meter cần khớp với meter được ứng dụng hoặc instrumentation tự động đăng ký. Với HTTP server metrics mặc định, `http.server.requests` thường là tên meter trong Micrometer trước khi registry chuyển đổi sang quy ước tên của backend.

Cấu hình histogram và percentile có thể làm tăng số chuỗi thời gian. Chỉ bật cho các meter thực sự cần phân tích phân bố.

## 7. Cấu hình DistributionSummary

Histogram và percentile cũng hữu ích với các đại lượng không phải thời gian, chẳng hạn kích thước payload hoặc số bản ghi trong một batch.

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

public class PayloadMetrics {

    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary
            .builder("message.payload.size")
            .baseUnit("bytes")
            .description("Message payload size in bytes")
            .publishPercentileHistogram()
            .publishPercentiles(0.5, 0.95, 0.99)
            .serviceLevelObjectives(
                1024,
                10_240,
                102_400,
                1_048_576
            )
            .register(registry);
    }

    public void recordPayload(byte[] payload) {
        payloadSize.record(payload.length);
    }
}
```

Ở đây, p95 của `message.payload.size` biểu thị kích thước mà 95% payload được ghi nhận không vượt quá. Với Timer, đơn vị là thời gian; với DistributionSummary, đơn vị phụ thuộc đại lượng ứng dụng ghi nhận.

Nên chọn đơn vị nhất quán, đặt `baseUnit` phù hợp và ghi rõ ý nghĩa của mẫu. Không trộn byte với kilobyte hoặc số phần tử với dung lượng trong cùng một metric.

## 8. Tính p95/p99 từ histogram bằng PromQL

Với Prometheus classic histogram, mỗi bucket được xuất thành series có hậu tố `_bucket` và nhãn `le`. Hàm `histogram_quantile` ước lượng percentile từ các bucket.

Ví dụ tính p95 độ trễ trên toàn bộ instance của một service:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Ý nghĩa:

1. `rate(...[5m])` tính tốc độ tăng số quan sát trong từng bucket trên cửa sổ 5 phút.
2. `sum by (le)(...)` cộng bucket tương ứng từ các instance, giữ lại nhãn ranh giới `le`.
3. `histogram_quantile(0.95, ...)` ước lượng p95 từ histogram đã tổng hợp.

Nếu muốn giữ phân tách theo service, nhóm theo cả `service` và `le`:

```promql
histogram_quantile(
  0.99,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Để tính p50 hoặc p99, thay tham số percentile lần lượt bằng `0.50` hoặc `0.99`.

Không nên tính p95 toàn hệ thống bằng cách lấy trung bình p95 của từng instance. Hãy cộng các bucket trước rồi mới gọi `histogram_quantile`. Cách làm này giữ được phân bố tổng hợp của các quan sát.

Tên metric cụ thể phụ thuộc naming convention của Prometheus registry và meter đang dùng. Hãy kiểm tra endpoint metrics để xác nhận đúng tên series, tag và đơn vị trước khi lưu truy vấn vào dashboard.

## 9. Đo tỷ lệ đáp ứng SLO bằng bucket

Histogram có thể được cấu hình thêm bucket tại các ngưỡng SLO. Ví dụ, yêu cầu 95% request hoàn tất trong 300 ms. Với bucket `le="0.3"`, Prometheus có thể tính tỷ lệ request không quá 300 ms:

```promql
sum(
  rate(http_server_requests_seconds_bucket{le="0.3"}[5m])
)
/
sum(
  rate(http_server_requests_seconds_count[5m])
)
```

Kết quả là tỷ lệ quan sát trong 5 phút có thời lượng nhỏ hơn hoặc bằng 300 ms. Nhân với 100 để biểu diễn phần trăm.

Nếu cần phân tách theo service, thêm `by (service)` ở cả tử số và mẫu số:

```promql
sum by (service) (
  rate(http_server_requests_seconds_bucket{le="0.3"}[5m])
)
/
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
)
```

SLO bucket cho phép đo trực tiếp tỷ lệ đáp ứng một ranh giới đã định. Nó thường dễ diễn giải hơn việc chỉ nhìn p95: một SLO có thể quy định rõ tỷ lệ request phải nằm dưới một ngưỡng độ trễ trong một cửa sổ thời gian.

## 10. Chọn bucket và đánh đổi độ chính xác với chi phí

Số lượng và vị trí bucket ảnh hưởng đến độ chính xác của percentile cũng như chi phí metrics.

- **Bucket quá rộng:** percentile được ước lượng kém chính xác trong vùng có nhiều quan sát.
- **Bucket quá dày:** tăng số chuỗi thời gian, bộ nhớ, lưu lượng scrape và chi phí truy vấn.
- **Bucket không bao phủ vùng quan tâm:** khó ước lượng các percentile ở phần đuôi hoặc phân tích ngưỡng SLO.
- **Bucket không thống nhất giữa instance:** khó tổng hợp histogram nếu các instance không xuất cùng ranh giới.
- **Giới hạn min/max không phù hợp:** các giá trị ngoài miền cấu hình có thể không được phân giải như mong muốn trong histogram.

Hãy đặt bucket tập trung quanh vùng độ trễ hoặc giá trị có ý nghĩa vận hành. Với API cần p95 ở 300 ms, cần có bucket tại hoặc gần 300 ms. Với thao tác batch có thể kéo dài hàng phút, cần bucket ở miền thời gian dài hơn thay vì chỉ dùng các bucket nhỏ dành cho HTTP request.

Micrometer có thể tạo các bucket histogram theo miền giá trị và cấu hình của meter. Việc thêm SLO bucket giúp cố định các ranh giới có ý nghĩa nghiệp vụ. Nên xem số lượng chuỗi thời gian sau khi bật histogram, nhất là khi meter có nhiều tag.

## 11. Cửa sổ thời gian và ý nghĩa của percentile

Percentile không nhất thiết đại diện cho toàn bộ lịch sử từ khi ứng dụng khởi động. Với percentile tính ở phía ứng dụng, Micrometer sử dụng cấu trúc thống kê theo cửa sổ thời gian; kết quả phụ thuộc cấu hình expiry và buffer length của distribution statistics.

Với histogram lưu tại backend, cửa sổ được xác định bởi truy vấn. Ví dụ:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Truy vấn này phản ánh phân bố request trong khoảng thời gian 5 phút được tính từ rate. Nếu đổi thành `[1h]`, p95 mô tả xu hướng trên cửa sổ dài hơn và có thể ít nhạy với đột biến ngắn.

Khi so sánh p95 giữa các dashboard hoặc báo cáo, cần dùng cùng cửa sổ thời gian và cùng cách tổng hợp. Nếu không, hai giá trị percentile có thể khác nhau do phạm vi quan sát chứ không phải do hệ thống thay đổi hiệu năng.

## 12. Cardinality và tác động của histogram

Mỗi bucket được export cho từng tổ hợp tên metric và tag. Nếu một Timer có 10 tag combinations và histogram xuất 20 bucket, số chuỗi thời gian tăng đáng kể so với chỉ xuất count và total time. Thêm percentile phía ứng dụng cũng tạo thêm series cho mỗi percentile được bật.

Để kiểm soát cardinality:

- Dùng tag có tập giá trị giới hạn như method, status group, service hoặc region.
- Tránh request ID, user ID, URL đầy đủ có ID động và exception message.
- Chỉ bật histogram cho các meter cần phân tích phân bố.
- Chọn số bucket và SLO boundary theo câu hỏi vận hành.
- Theo dõi số chuỗi thời gian trước và sau khi bật histogram.
- Giữ quy ước tên, tag và bucket nhất quán giữa các instance.

Histogram là dữ liệu hữu ích nhưng không miễn phí. Thiết kế bucket và tag cần được cân nhắc cùng chi phí lưu trữ và truy vấn của backend.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| p95 nghĩa là 95% request có đúng độ trễ p95 | Khoảng 95% quan sát không vượt quá giá trị p95 |
| p99 là độ trễ tối đa | 1% quan sát có thể chậm hơn p99 |
| Trung bình p95 của các instance là p95 toàn hệ thống | Cần tổng hợp histogram bucket rồi tính percentile |
| Bucket `le="0.3"` chỉ chứa quan sát từ bucket trước đến 300 ms | Prometheus bucket là tích lũy, chứa mọi quan sát không quá 300 ms |
| Histogram lưu lại mọi giá trị gốc | Histogram lưu số lượng theo bucket, không phải nhật ký từng quan sát |
| Càng nhiều bucket càng tốt | Bucket nhiều làm tăng độ chính xác ở một số vùng nhưng cũng tăng cardinality và chi phí |
| Percentile phía ứng dụng có thể cộng giữa instance | Percentile cục bộ không thể tổng hợp chính xác thành percentile toàn cục |
| p95 không đổi nghĩa khi đổi cửa sổ thời gian | Cửa sổ 5 phút và 1 giờ có thể phản ánh hai phân bố rất khác nhau |

## 14. Checklist triển khai histogram và percentile

- [ ] Xác định đại lượng cần phân tích là thời gian hay giá trị số.
- [ ] Chọn Timer cho thời lượng và DistributionSummary cho đại lượng số khác.
- [ ] Xác định p50, p95 hoặc p99 phục vụ câu hỏi vận hành nào.
- [ ] Chọn percentile phía ứng dụng hay histogram tính ở backend.
- [ ] Nếu cần tổng hợp nhiều instance, ưu tiên histogram bucket có thể cộng gộp.
- [ ] Đặt SLO bucket tại các ngưỡng nghiệp vụ quan trọng.
- [ ] Chọn min/max và bucket phù hợp với miền giá trị thực tế.
- [ ] Xác nhận tên series và đơn vị sau khi registry export.
- [ ] Dùng `histogram_quantile` trên bucket đã tổng hợp, không lấy trung bình percentile của instance.
- [ ] Chọn cửa sổ thời gian nhất quán khi so sánh percentile.
- [ ] Kiểm soát tag và số lượng bucket để hạn chế cardinality.
- [ ] Kiểm tra dashboard và alert với dữ liệu đại diện trước khi dùng trong vận hành.

Histogram, bucket và percentile giúp chuyển hàng loạt phép đo riêng lẻ thành thông tin phân bố có thể phân tích. p50 mô tả vùng giữa, p95 và p99 giúp nhìn phần đuôi chậm; bucket cung cấp dữ liệu để backend ước lượng các phân vị và tính tỷ lệ đáp ứng SLO. Khi cần tổng hợp nhiều instance, hãy xuất histogram và tính percentile sau khi cộng bucket. Chọn ranh giới bucket và tag có kiểm soát để cân bằng độ chính xác với chi phí vận hành.

## Tài liệu tham khảo

- [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html) — cách cấu hình percentile, histogram và SLO bucket.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — phân phối thời lượng, histogram và percentile cho Timer.
- [Micrometer Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html) — phân phối các giá trị số không phải thời lượng.
- [Prometheus Histograms and Summaries](https://prometheus.io/docs/practices/histograms/) — cách đọc bucket, tính quantile và tổng hợp histogram giữa các instance.

