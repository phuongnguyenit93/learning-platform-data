# Giới hạn tổng hợp phân vị đã tính sẵn giữa các tag hoặc instance

Percentile là cách hữu ích để mô tả độ trễ, chẳng hạn p95 cho biết ngưỡng thời gian mà khoảng 95% thao tác hoàn tất. Tuy nhiên, một giá trị p95 đã tính sẵn ở từng instance hoặc từng nhóm tag không thể được cộng, lấy trung bình hay gộp trực tiếp để suy ra p95 của toàn hệ thống.

Trong Micrometer cần phân biệt hai cách xuất phân phối:

- **Client-side percentile**: mỗi meter tính percentile từ các mẫu mà chính nó nhận được rồi xuất giá trị percentile đó. Giá trị này mô tả riêng meter/tag set đó và không giữ đủ thông tin để tái tạo phân phối gốc.
- **Percentile histogram**: meter xuất số lượng mẫu theo các bucket. Backend có thể cộng các bucket tương ứng giữa nhiều tag hoặc instance rồi tính percentile từ phân phối đã gộp.

Nếu dashboard cần p95 toàn service hoặc p95 qua nhiều instance, histogram thường là lựa chọn phù hợp. Nếu chỉ cần percentile cục bộ cho một meter riêng lẻ, client-side percentile có thể đáp ứng, tùy backend và yêu cầu vận hành.

## 1. Percentile biểu diễn điều gì?

Giả sử đo thời gian xử lý của nhiều request. Sau khi sắp xếp các thời lượng từ nhỏ đến lớn, percentile p95 là giá trị ở vị trí tương ứng với 95% mẫu có thời lượng nhỏ hơn hoặc bằng giá trị đó.

Ví dụ, p95 bằng 300 ms có nghĩa khoảng 95% request trong tập mẫu được xét hoàn tất trong tối đa 300 ms; khoảng 5% còn lại chậm hơn. p50 là trung vị, p99 mô tả phần đuôi chậm hơn của phân phối.

Percentile khác với trung bình và max:

| Thống kê | Ý nghĩa | Giới hạn khi đọc riêng |
| --- | --- | --- |
| Mean | Tổng thời lượng chia số mẫu | Có thể bị kéo lên bởi một số request rất chậm. |
| p50 | Trung vị | Không mô tả tốt phần đuôi chậm. |
| p95/p99 | Các ngưỡng ở phần đuôi phân phối | Cần biết tập mẫu và cách tổng hợp. |
| Max | Mẫu lớn nhất trong phạm vi thống kê | Nhạy với một ngoại lệ và có thể thay đổi theo cửa sổ thời gian. |

Điểm quan trọng: percentile là một thống kê đã rút gọn từ tập mẫu. Chỉ giữ lại p95 không có nghĩa là vẫn giữ toàn bộ thông tin của 100% thời lượng đã đo.

## 2. Vì sao percentile tính sẵn không thể gộp trực tiếp?

Một percentile riêng lẻ không chứa thông tin về số lượng mẫu ở từng vùng của phân phối. Khi có nhiều nhóm, p95 của mỗi nhóm không đủ để tính p95 của tập hợp các nhóm.

Ví dụ có hai instance, mỗi instance xử lý 100 request:

- Instance A: 95 request mất 100 ms, 5 request mất 1.000 ms. p95 xấp xỉ 100 ms.
- Instance B: 95 request mất 400 ms, 5 request mất 2.000 ms. p95 xấp xỉ 400 ms.

Lấy trung bình hai p95 sẽ được 250 ms. Nhưng khi gộp 200 request, 95 request đầu tiên mất 100 ms và 95 request tiếp theo mất 400 ms; do đó p95 toàn bộ tập mẫu là khoảng 400 ms theo cách xếp hạng mẫu gần nhất. Kết quả 250 ms không mô tả p95 của tập request đã gộp.

Ngay cả khi biết p95 của từng instance, bạn vẫn thiếu thông tin về:

- Số mẫu mà mỗi instance đã ghi nhận trong khoảng thời gian đó.
- Phân bố của các mẫu thấp hơn và cao hơn p95.
- Hình dạng phần đuôi phân phối và mức độ tập trung của các mẫu quanh percentile.
- Tương quan giữa lượng traffic và độ trễ ở từng nhóm.

Vì vậy, các phép tính sau không tạo ra percentile tổng hợp chính xác:

- Trung bình p95 của các instance.
- Lấy max hoặc min của p95 từng instance.
- Cộng các giá trị p95 của từng route hoặc từng tag.
- Lấy trung bình percentile theo số instance mà không có phân phối gốc.

Đây không phải hạn chế riêng của Micrometer. Đó là tính chất toán học của percentile: các quantile đã tính riêng không thể được ghép lại thành quantile của hợp các tập dữ liệu chỉ bằng cách thao tác trên những con số quantile đó.

## 3. Hai cách xuất percentile trong Micrometer

Micrometer cung cấp API để yêu cầu percentile hoặc histogram trên các meter hỗ trợ thống kê phân phối. Cấu hình thường được đặt ngay trên builder của `Timer` hoặc `DistributionSummary`.

### 3.1. Client-side percentile với publishPercentiles

`publishPercentiles(...)` yêu cầu Micrometer tính các percentile đã chọn trên phía ứng dụng cho từng meter identity:

```java
import io.micrometer.core.instrument.Timer;

Timer requestTimer = Timer.builder("shop.http.request.duration")
        .description("HTTP request duration")
        .publishPercentiles(0.50, 0.95, 0.99)
        .register(registry);
```

Trong ví dụ, ứng dụng yêu cầu p50, p95 và p99 cho meter này. Nếu meter được đăng ký với tag `route=/orders`, percentile phản ánh các mẫu thuộc tag set đó. Meter với `route=/payments` có tập mẫu và percentile riêng.

Các giá trị này hữu ích khi muốn quan sát percentile tại từng meter/tag set. Nhưng khi mỗi instance chạy một registry riêng, percentile mà instance A tính và percentile mà instance B tính vẫn là hai thống kê riêng. Backend không thể cộng hoặc lấy trung bình chúng để khôi phục percentile toàn cụm.

### 3.2. Percentile histogram với publishPercentileHistogram

`publishPercentileHistogram()` yêu cầu meter xuất histogram bucket phù hợp với registry/backend:

```java
Timer requestTimer = Timer.builder("shop.http.request.duration")
        .description("HTTP request duration")
        .publishPercentileHistogram()
        .register(registry);
```

Histogram giữ số lượng mẫu trong các bucket thời lượng. Với classic histogram của Prometheus, các bucket có nhãn `le` biểu diễn giới hạn trên tích lũy. Backend có thể cộng số lượng bucket tương ứng giữa các instance hoặc tag set rồi tính percentile trên phân phối tổng hợp.

Histogram vì thế giữ nhiều thông tin hơn một vài percentile riêng lẻ. Đổi lại, nó tạo thêm chuỗi thời gian và làm tăng chi phí bộ nhớ, scrape, lưu trữ và truy vấn. Cần lựa chọn phạm vi histogram dựa trên yêu cầu phân tích và ngân sách cardinality.

Nguyên tắc tương tự áp dụng cho `DistributionSummary`. Ví dụ, nếu đo kích thước payload, `publishPercentiles(...)` cho percentile kích thước tại từng meter/tag set; `publishPercentileHistogram()` xuất bucket kích thước để backend tổng hợp qua các instance. Cần thống nhất đơn vị và ranh giới bucket giữa các instance, chẳng hạn tất cả cùng ghi byte.

### 3.3. Kết hợp percentile và histogram khi cần

Có thể cấu hình cả client-side percentile và histogram nếu cần cả hai cách quan sát:

```java
Timer requestTimer = Timer.builder("shop.http.request.duration")
        .description("HTTP request duration")
        .publishPercentiles(0.50, 0.95, 0.99)
        .publishPercentileHistogram()
        .register(registry);
```

Client-side percentile cung cấp thống kê cục bộ cho từng meter. Histogram cung cấp bucket để backend tổng hợp. Bật cả hai làm tăng lượng dữ liệu; chỉ nên dùng khi dashboard hoặc quy trình vận hành thực sự cần cả percentile cục bộ và percentile tổng hợp.

## 4. Tổng hợp histogram đúng cách

Để gộp percentile qua nhiều instance, cần cộng số lượng ở cùng một bucket trước, sau đó mới tính percentile. Với histogram cổ điển, mỗi chuỗi bucket có nhãn `le` xác định giới hạn bucket.

Giả sử hai instance cùng xuất bucket `le="0.1"`, `le="0.3"`, `le="1.0"` và `le="+Inf"`. Backend có thể cộng số lượng tương ứng của từng bucket từ cả hai instance. Kết quả là histogram đại diện cho tập mẫu của cả hai instance.

Thứ tự xử lý đúng:

1. Lấy tốc độ tăng hoặc số lượng bucket trong cùng khoảng thời gian.
2. Cộng bucket tương ứng qua những chiều cần gộp, đồng thời giữ lại nhãn `le`.
3. Dùng hàm percentile của backend trên histogram đã gộp.

Không tính p95 riêng trên từng instance rồi mới gộp p95. Phải gộp histogram trước rồi mới tính p95.

### 4.1. Tổng hợp qua tất cả instance và tag

Với Prometheus classic histogram, truy vấn minh họa cho p95 của toàn bộ request trong service:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(shop_http_request_duration_seconds_bucket{job="order-service"}[5m])
  )
)
```

`sum by (le)` gộp các bucket từ nhiều instance và các tag khác, chỉ giữ lại nhãn bucket `le`. `histogram_quantile(0.95, ...)` tính p95 trên histogram đã tổng hợp.

Tên metric trong ví dụ là tên minh họa sau khi Prometheus registry chuẩn hóa tên và đơn vị. Hãy xác nhận tên thực tế cùng các nhãn có trong `/actuator/prometheus` trước khi dùng truy vấn.

### 4.2. Tổng hợp theo một tag, ví dụ route

Nếu cần p95 riêng cho từng route nhưng vẫn gộp qua các instance, giữ lại cả `le` và tag route trong phép cộng:

```promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(shop_http_request_duration_seconds_bucket{job="order-service"}[5m])
  )
)
```

Kết quả có một p95 cho mỗi route, được tính từ histogram của tất cả instance thuộc service. Tên tag route có thể khác tùy instrumentation, chẳng hạn `uri`, `path` hoặc một tag tùy chỉnh. Hãy dùng đúng tên nhãn được xuất.

### 4.3. Giữ nhiều chiều phân tích

Bạn có thể giữ lại nhiều nhãn khi muốn xem p95 theo route và method:

```promql
histogram_quantile(
  0.95,
  sum by (le, route, method) (
    rate(shop_http_request_duration_seconds_bucket{job="order-service"}[5m])
  )
)
```

Mỗi tổ hợp `route` và `method` tạo một phân phối riêng sau khi bucket được gộp giữa các instance. Số nhóm kết quả tăng theo cardinality của các nhãn được giữ lại; không nên giữ các tag có quá nhiều giá trị chỉ để tạo dashboard chi tiết.

## 5. Điều kiện để histogram có thể gộp có ý nghĩa

Histogram chỉ có thể tổng hợp đúng khi các chuỗi được gộp mô tả cùng một đại lượng và có bucket tương thích.

Hãy bảo đảm:

- Cùng metric name mang cùng ý nghĩa và đơn vị đo.
- Các instance dùng cùng cấu hình bucket hoặc cùng các ranh giới bucket cần thiết.
- Tag được chuẩn hóa nhất quán, đặc biệt là route, status và outcome.
- Cùng một cửa sổ truy vấn và cách lấy rate/count được áp dụng cho mọi chuỗi.
- Các nhóm được gộp thuộc cùng một loại thao tác hoặc có ý nghĩa so sánh được.

Nếu một instance xuất bucket 100 ms, 300 ms, 1 giây còn instance khác chỉ xuất 200 ms, 500 ms, 2 giây, việc cộng các bucket theo nhãn `le` không tạo ra phân phối đầy đủ theo cùng một lưới bucket. Hãy thống nhất cấu hình phân phối giữa các instance của cùng service và cùng metric.

### 5.1. Bucket và độ chính xác

Percentile tính từ histogram là ước lượng dựa trên bucket, không phải phép tính lại trên toàn bộ mẫu thô. Độ chính xác phụ thuộc vào ranh giới bucket và cách backend nội suy trong bucket chứa percentile.

Bucket càng dày quanh vùng độ trễ quan trọng thì ước lượng ở vùng đó càng chi tiết, nhưng số chuỗi thời gian tăng. Hãy xác định ngưỡng độ trễ quan trọng của ứng dụng rồi chọn bucket phù hợp thay vì tăng bucket không giới hạn.

### 5.2. Service Level Objectives

Có thể thêm các ranh giới bucket theo SLO để dễ đánh giá tỷ lệ thao tác hoàn thành dưới một ngưỡng:

```java
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

Timer requestTimer = Timer.builder("shop.http.request.duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1)
        )
        .register(registry);
```

Các ranh giới 100 ms, 300 ms và 1 giây giúp theo dõi các ngưỡng có ý nghĩa vận hành. Khi cấu hình SLO bucket trên các instance, cần giữ cấu hình giống nhau để kết quả tổng hợp nhất quán.

## 6. Tổng hợp giữa tag values và tổng hợp giữa instances

Hai nhu cầu thường gặp có cùng nguyên tắc nhưng khác chiều cần giữ:

| Nhu cầu | Client-side percentile | Histogram |
| --- | --- | --- |
| Xem p95 riêng cho từng route | Có thể xem percentile của từng meter/tag set | Có thể tính riêng bằng cách giữ tag route khi gộp bucket |
| Gộp p95 của tất cả route thành p95 toàn service | Không thể gộp các p95 đã tính sẵn | Gộp bucket và bỏ tag route khỏi `group by` |
| Gộp p95 qua nhiều instance | Không thể gộp các p95 đã tính sẵn | Gộp bucket giữa instance rồi tính percentile |
| Gộp theo route qua nhiều instance | Không thể gộp percentile riêng của từng route/instance | Giữ route và `le` khi gộp bucket |
| Giữ chi phí chuỗi thời gian thấp | Thường ít chuỗi hơn histogram, tùy registry | Tạo nhiều chuỗi bucket hơn |

Khi cần p95 toàn service, không nên lấy trung bình p95 của từng route. Route có lưu lượng khác nhau và phân phối độ trễ khác nhau; phải gộp dữ liệu phân phối trước.

Tương tự, nếu muốn p95 của một tag value qua nhiều instance, cần gộp histogram của tag value đó trên tất cả instance rồi mới tính quantile. Giữ tag trong `group by` nếu muốn kết quả riêng cho từng value; bỏ tag khỏi `group by` nếu muốn gộp các value thành một phân phối.

## 7. Ví dụ đầy đủ với Spring Boot và Prometheus

Một component instrumentation có thể đăng ký timer với histogram và SLO bucket:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class HttpOperationMetrics {
    private final Timer requestTimer;

    public HttpOperationMetrics(MeterRegistry registry) {
        this.requestTimer = Timer.builder("shop.http.request.duration")
                .description("Duration of HTTP operations")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(300),
                        Duration.ofSeconds(1)
                )
                .register(registry);
    }

    public void record(long duration, TimeUnit unit) {
        requestTimer.record(duration, unit);
    }
}
```

Trong ứng dụng thực tế, nếu muốn phân tích theo route hoặc method, hãy gắn các tag có tập giá trị hữu hạn và chuẩn hóa trước khi đăng ký meter. Các instance của cùng service phải dùng cùng quy ước tên, tag và cấu hình phân phối.

Prometheus scrape endpoint metrics của từng instance. Truy vấn p95 toàn service có thể dùng:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(shop_http_request_duration_seconds_bucket[5m])
  )
)
```

Truy vấn p95 theo route:

```promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(shop_http_request_duration_seconds_bucket[5m])
  )
)
```

Các truy vấn này minh họa classic histogram. Với native histogram hoặc backend khác, cú pháp và cách tổng hợp có thể khác; hãy sử dụng kiểu dữ liệu mà registry thực tế xuất ra.

## 8. Cách lựa chọn cấu hình

Hãy bắt đầu từ câu hỏi vận hành thay vì bật mọi thống kê:

| Câu hỏi | Cấu hình gợi ý | Lý do |
| --- | --- | --- |
| Cần p95 riêng cho một meter cục bộ | `publishPercentiles(0.95)` | Tính percentile ở phía ứng dụng cho meter đó. |
| Cần p95 toàn service qua nhiều instance | `publishPercentileHistogram()` | Backend có bucket để tổng hợp trước khi tính percentile. |
| Cần p95 theo route, gộp qua các instance | Histogram và truy vấn giữ `le, route` | Cộng bucket theo route rồi tính p95. |
| Cần đánh giá ngưỡng SLO cụ thể | Histogram cùng `serviceLevelObjectives(...)` | Có bucket tại các ranh giới quan trọng. |
| Cần cả p95 cục bộ lẫn p95 toàn cụm | Có thể bật cả percentile và histogram | Chấp nhận chi phí bổ sung để đáp ứng hai nhu cầu khác nhau. |

Hãy xem xét số metric, số tag, số route, số instance, số bucket và tần suất scrape. Histogram trên một metric có cardinality cao có thể tạo ra lượng chuỗi thời gian lớn. Cần kiểm soát tag trước khi mở rộng histogram.

## 9. Những lỗi thường gặp khi tổng hợp percentile

- **Lấy trung bình p95 giữa các instance:** kết quả không phải p95 toàn cụm vì percentile riêng không chứa phân phối gốc.
- **Cộng p95 giữa các tag:** percentile không phải đại lượng cộng dồn; cần tổng hợp bucket hoặc mẫu gốc.
- **Dùng client-side percentile cho dashboard toàn service:** giá trị được tính riêng tại từng meter/instance và không thể gộp chính xác.
- **Gộp histogram sau khi đã tính quantile:** phải cộng bucket trước, sau đó mới gọi hàm percentile.
- **Bỏ nhãn `le` khi cộng bucket:** histogram classic cần giữ ranh giới bucket để tính quantile.
- **Bucket không nhất quán giữa instance:** các bucket không tương thích làm kết quả tổng hợp không đáng tin cậy.
- **Giữ quá nhiều tag trong `group by`:** kết quả vẫn bị chia thành nhiều nhóm và không phản ánh p95 toàn service.
- **Bỏ tag cần phân tích:** nếu muốn p95 theo route, phải giữ route trong phép nhóm bucket.
- **Quên chi phí histogram:** số bucket nhân với tổ hợp tag và số instance làm tăng số chuỗi thời gian.
- **Cộng hoặc trung bình percentile qua thời gian:** percentile của các cửa sổ thời gian riêng cũng không tạo ra percentile của toàn bộ khoảng dài hơn.

## 10. Checklist trước khi xây dashboard percentile

- [ ] Xác định percentile cần xem ở cấp meter, tag group, instance hay toàn service.
- [ ] Nếu chỉ cần percentile cục bộ, xác định rõ phạm vi của client-side percentile.
- [ ] Nếu cần tổng hợp qua tag hoặc instance, cấu hình histogram bucket.
- [ ] Gộp bucket tương ứng trước khi tính percentile.
- [ ] Giữ `le` trong truy vấn histogram cổ điển.
- [ ] Giữ các tag muốn phân tích và bỏ các tag muốn gộp khỏi `group by`.
- [ ] Bảo đảm mọi instance dùng cùng đơn vị và ranh giới bucket.
- [ ] Xác minh tên metric và nhãn thực tế tại endpoint export.
- [ ] Tính chi phí cardinality, bucket và số instance.
- [ ] Không lấy trung bình hoặc cộng các percentile đã tính sẵn để suy ra percentile tổng hợp.

Giới hạn cốt lõi cần nhớ là percentile đã tính sẵn chỉ mô tả phân phối tại nơi nó được tính. Muốn biết p95 của nhiều tag hoặc nhiều instance, hãy giữ dữ liệu phân phối dưới dạng histogram bucket, cộng các bucket tương ứng rồi mới tính percentile ở backend. Cách này bảo toàn đủ thông tin cần thiết để có một thống kê tổng hợp có ý nghĩa.
