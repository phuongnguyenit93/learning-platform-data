# publishPercentileHistogram để công bố dữ liệu phục vụ tính phân vị phía nhận

Micrometer có thể công bố phân phối của Timer và DistributionSummary theo dạng histogram để hệ thống giám sát tính percentile ở phía nhận dữ liệu. Với Prometheus, ứng dụng bật `publishPercentileHistogram()` để xuất các bucket; PromQL dùng `histogram_quantile()` tính p50, p95 hoặc p99 từ những bucket đó.

Điểm mạnh của cách này là các bucket có thể được tổng hợp giữa nhiều tag hoặc nhiều instance trước khi tính percentile. Ví dụ, có thể tính p95 của toàn bộ request trên một cụm dịch vụ bằng cách cộng bucket của từng instance rồi mới gọi `histogram_quantile()`. Đây là khác biệt quan trọng so với percentile được tính riêng trong từng instance bằng `publishPercentiles()`: các percentile riêng lẻ không thể cộng hoặc lấy trung bình để tạo percentile chính xác cho toàn cụm.

Histogram tạo thêm chuỗi thời gian và chi phí lưu trữ. Vì vậy, cần chọn meter cần công bố, giới hạn phạm vi giá trị, thêm các bucket SLO có ý nghĩa và kiểm soát cardinality của tag.

## 1. Percentile trả lời câu hỏi gì?

Percentile mô tả vị trí của một giá trị trong phân phối quan sát. Với thời lượng request:

- p50 là trung vị: khoảng một nửa số request có thời lượng nhỏ hơn hoặc bằng giá trị này.
- p95 là ngưỡng mà khoảng 95% request nằm ở hoặc dưới.
- p99 cho thấy phần đuôi chậm hơn của phân phối, nơi các request hiếm nhưng có thể ảnh hưởng rõ đến trải nghiệm.

Ví dụ, nếu p95 của thời lượng request là 800 ms, có thể diễn giải rằng khoảng 95% quan sát trong cửa sổ đang xét có thời lượng không vượt quá xấp xỉ 800 ms. Đây là giá trị ước lượng từ dữ liệu histogram, không phải cam kết rằng mọi request đều hoàn tất trong 800 ms.

Percentile hữu ích vì giá trị trung bình có thể che khuất phần đuôi. Giả sử phần lớn request hoàn tất trong 50 ms nhưng một nhóm nhỏ mất vài giây. Trung bình có thể vẫn khá thấp trong khi người dùng gặp các lần phản hồi rất chậm. p95 và p99 giúp nhận ra tình trạng đó.

Percentile luôn gắn với một tập quan sát và một khoảng thời gian cụ thể. Khi xem p95 trên dashboard, cần biết đó là p95 của 5 phút gần nhất, 1 giờ hay toàn bộ thời gian lưu trữ.

## 2. Hai cách công bố percentile trong Micrometer

Timer và DistributionSummary hỗ trợ hai cách chính để quan sát percentile:

| Cách | Nơi tính percentile | Có thể tổng hợp giữa instance/tag? | Cách dùng |
|---|---|---|---|
| `publishPercentiles(...)` | Trong ứng dụng | Không | Micrometer tính percentile cho từng meter ID và xuất giá trị percentile |
| `publishPercentileHistogram()` | Phía hệ thống nhận | Có, bằng cách tổng hợp bucket trước khi tính | Micrometer xuất histogram buckets để Prometheus hoặc backend tương thích tính percentile |

### Percentile tính tại ứng dụng

Ví dụ:

~~~java
Timer.builder("http.server.requests")
        .publishPercentiles(0.50, 0.95, 0.99)
        .register(registry);
~~~

Micrometer tính các percentile được yêu cầu trong ứng dụng rồi công bố chúng cùng định danh meter. Cách này có thể hữu ích với backend không hỗ trợ tính percentile từ histogram.

Tuy nhiên, mỗi meter ID có kết quả riêng. Nếu từng instance xuất p95 riêng, không thể cộng p95 của các instance hoặc lấy trung bình các p95 để suy ra p95 của toàn cụm. Percentile không phải đại lượng có tính cộng gộp.

### Histogram để tính percentile phía nhận

Ví dụ:

~~~java
Timer.builder("http.server.requests")
        .publishPercentileHistogram()
        .register(registry);
~~~

Micrometer xuất các bucket histogram phù hợp với backend hỗ trợ percentile có thể tổng hợp. Prometheus có thể cộng các bucket giữa các chuỗi thời gian rồi dùng `histogram_quantile()` để tính percentile của tập dữ liệu đã tổng hợp.

Nếu backend không hỗ trợ percentile histogram có thể tổng hợp, `publishPercentileHistogram()` không tạo ra histogram cho backend đó. Hãy kiểm tra khả năng của registry và hệ thống nhận trước khi bật cấu hình.

Với Prometheus và Atlas, histogram phía nhận thường là lựa chọn phù hợp khi cần tính percentile sau khi tổng hợp nhiều chiều. Không cần đồng thời bật percentile phía ứng dụng nếu histogram đã đáp ứng yêu cầu; ngoài việc dư thừa, hai dạng dữ liệu có cách tổng hợp khác nhau. Prometheus Java Client 1.x cũng không hỗ trợ xuất đồng thời cả hai dạng dưới cùng một tên metric.

## 3. Bucket histogram hoạt động như thế nào?

Histogram chia miền giá trị thành các khoảng có ranh giới xác định, gọi là bucket. Mỗi bucket cho biết có bao nhiêu quan sát nằm ở hoặc dưới ranh giới tương ứng trong histogram dạng cumulative của Prometheus.

Ví dụ histogram thời lượng có các ranh giới 100 ms, 300 ms, 1 giây và vô cực:

| Bucket `le` | Số quan sát tích lũy |
|---|---:|
| 0,1 giây | 120 |
| 0,3 giây | 260 |
| 1 giây | 295 |
| +Inf | 300 |

Diễn giải:

- 120 quan sát có thời lượng không vượt quá 100 ms.
- 260 quan sát có thời lượng không vượt quá 300 ms, bao gồm cả 120 quan sát trong bucket trước.
- 295 quan sát có thời lượng không vượt quá 1 giây.
- Tổng cộng có 300 quan sát; 5 quan sát còn lại lớn hơn 1 giây.

Các bucket Prometheus là bucket tích lũy. Số quan sát nằm riêng trong khoảng 100–300 ms được tính bằng hiệu giữa bucket `le="0.3"` và bucket `le="0.1"`, tức 140 trong ví dụ.

Bucket `+Inf` bao gồm mọi quan sát và giúp tổng số quan sát trong histogram khớp với count. Ranh giới bucket quyết định độ chi tiết mà hệ thống nhận có thể dùng để ước lượng percentile. Histogram không giữ lại thời lượng chính xác của từng request.

## 4. Bật publishPercentileHistogram cho Timer

Timer phù hợp để đo thời lượng request, lời gọi dịch vụ, truy vấn hoặc một thao tác đã hoàn tất. Có thể bật histogram và bổ sung các bucket SLO:

~~~java
Timer requestTimer = Timer.builder("http.server.requests")
        .description("HTTP request duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1)
        )
        .minimumExpectedValue(Duration.ofMillis(1))
        .maximumExpectedValue(Duration.ofSeconds(10))
        .register(registry);

requestTimer.record(() -> controller.handle(request));
~~~

Ý nghĩa cấu hình:

- `publishPercentileHistogram()` yêu cầu Micrometer công bố bucket để backend tính percentile có thể tổng hợp.
- `serviceLevelObjectives(...)` bổ sung các ranh giới bucket quan trọng với mục tiêu vận hành.
- `minimumExpectedValue(...)` và `maximumExpectedValue(...)` giới hạn phạm vi bucket được tạo cho percentile histogram và ảnh hưởng đến độ chính xác cũng như bộ nhớ của histogram nội bộ.

Với Timer, các giá trị SLO và min/max dùng kiểu Duration nên đơn vị trong mã dễ đọc. Registry chuyển đổi thời lượng sang đơn vị cơ sở của backend; Prometheus thường biểu diễn thời lượng bằng giây.

Không nên đặt max quá rộng nếu phần lớn request chỉ kéo dài vài trăm mili giây. Phạm vi bucket quá lớn có thể làm tăng số bucket và bộ nhớ trong khi không cung cấp thêm nhiều giá trị hữu ích cho câu hỏi vận hành.

## 5. Bật histogram cho DistributionSummary

DistributionSummary đo phân phối của một đại lượng số không phải thời gian, chẳng hạn kích thước payload, số bản ghi trong batch hoặc số byte được xử lý.

~~~java
DistributionSummary payloadSize = DistributionSummary
        .builder("http.request.payload.size")
        .description("HTTP request payload size")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .serviceLevelObjectives(1_024.0, 10_240.0, 102_400.0)
        .minimumExpectedValue(1.0)
        .maximumExpectedValue(1_000_000.0)
        .register(registry);

payloadSize.record(requestBody.length);
~~~

Với DistributionSummary, SLO và min/max là giá trị số theo đơn vị của đại lượng mà ứng dụng ghi nhận. Trong ví dụ này, các ranh giới là byte vì meter khai báo base unit là `bytes`.

Không nên để DistributionSummary phát hành toàn bộ miền bucket mặc định nếu đại lượng có phạm vi nhỏ và đã biết. Tài liệu Micrometer khuyến nghị giới hạn minimum và maximum expected value khi bật percentile histogram cho DistributionSummary, vì cấu hình mặc định của summary không có hai giới hạn này và có thể tạo toàn bộ tập bucket được định trước.

## 6. Chọn minimumExpectedValue và maximumExpectedValue

Micrometer dùng một bộ ranh giới histogram được xác định trước cho percentile histogram. `minimumExpectedValue` và `maximumExpectedValue` chọn phần ranh giới nằm trong phạm vi cần quan sát. Hai giá trị này cũng ảnh hưởng đến phạm vi và bộ nhớ của HdrHistogram dùng bên trong.

Với Timer, cấu hình mặc định của Micrometer hiện hành giới hạn phạm vi ở khoảng 1 ms đến 1 phút. Bộ sinh có 276 bucket tiềm năng; sau khi giới hạn theo phạm vi mặc định của Timer, có 73 bucket cho mỗi tổ hợp tag. Các con số cụ thể có thể phụ thuộc phiên bản và cấu hình.

Với DistributionSummary, nếu không giới hạn min/max, histogram có thể dùng toàn bộ 276 bucket tiềm năng. Hãy chọn phạm vi phù hợp với dữ liệu thực tế và các mục tiêu cần theo dõi.

Quy trình lựa chọn:

1. Xem phân phối thực tế hoặc ước lượng hợp lý về giá trị nhỏ nhất và lớn nhất.
2. Xác định các ngưỡng có ý nghĩa vận hành, ví dụ thời lượng 100 ms, 300 ms, 1 giây.
3. Chọn phạm vi min/max bao phủ phần lớn quan sát cần phân tích.
4. Kiểm tra số bucket và lượng chuỗi thời gian được xuất.
5. Điều chỉnh khi phân phối thực tế thay đổi hoặc khi dashboard cần độ phân giải khác.

Min/max là cấu hình cho thống kê phân phối và bucket, không phải kiểm tra hợp lệ của dữ liệu nghiệp vụ. Không dùng chúng thay cho validation đầu vào. Hãy kiểm tra hành vi của registry đang dùng đối với các giá trị ngoài phạm vi trước khi diễn giải dữ liệu ở các biên.

## 7. Thêm bucket SLO bằng serviceLevelObjectives

Bucket mặc định được thiết kế để hỗ trợ ước lượng percentile trên một dải giá trị. Tuy nhiên, vận hành thường có các ngưỡng cụ thể cần đo trực tiếp, chẳng hạn:

- 95% request phải hoàn tất trong 300 ms.
- 99% request phải hoàn tất trong 1 giây.
- Payload thông thường không vượt quá 100 KB.

`serviceLevelObjectives(...)` thêm các ranh giới histogram theo các ngưỡng này:

~~~java
Timer.builder("checkout.duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1)
        )
        .register(registry);
~~~

Khi dùng cùng percentile histogram trên backend hỗ trợ percentile có thể tổng hợp, các ranh giới SLO được thêm vào tập bucket do Micrometer tạo. Trên backend không hỗ trợ percentile histogram tổng hợp, cấu hình SLO vẫn có thể xuất histogram chỉ gồm các ranh giới SLO.

SLO bucket hữu ích cho việc tính tỷ lệ quan sát nằm dưới một ngưỡng. Ví dụ, bucket `le="0.3"` cho biết số request có thời lượng không vượt quá 300 ms. Từ đó có thể tính tỷ lệ đạt mục tiêu mà không cần ước lượng percentile.

Không nên thêm quá nhiều ranh giới gần nhau nếu không có câu hỏi vận hành tương ứng. Mỗi bucket bổ sung làm tăng dữ liệu phải xuất và lưu trữ.

## 8. Tính percentile phía Prometheus bằng histogram_quantile

Khi Timer `http.server.requests` bật percentile histogram, Prometheus thường nhận chuỗi thời gian bucket với tên tương tự `http_server_requests_seconds_bucket`. Tên thực tế phụ thuộc naming convention và phiên bản Prometheus registry; hãy kiểm tra endpoint scrape.

### p95 của toàn bộ request

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Các bước:

1. `rate(...[5m])` tính tốc độ tăng của từng bucket trong 5 phút.
2. `sum by (le)` cộng các bucket tương ứng qua instance và các chiều tag.
3. `histogram_quantile(0.95, ...)` ước lượng p95 từ histogram đã tổng hợp.

Phải giữ label `le` trong phép tổng hợp để Prometheus phân biệt ranh giới bucket. Nếu bỏ `le`, histogram không còn cấu trúc cần thiết để tính quantile.

### p99 theo HTTP method

~~~promql
histogram_quantile(
  0.99,
  sum by (le, method) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Truy vấn giữ lại `method` để tính percentile riêng cho GET, POST hoặc các method khác, đồng thời cộng dữ liệu giữa các instance. Chỉ giữ các chiều thực sự cần so sánh; không nhóm theo ID request hoặc URL có giá trị động.

### p50 và p95

Có thể tạo nhiều truy vấn với cùng histogram:

~~~promql
histogram_quantile(
  0.50,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
~~~

p50 phản ánh phần trung tâm của phân phối; p95 giúp quan sát phần đuôi chậm hơn. So sánh cả hai giúp nhận biết tình huống phần lớn request nhanh nhưng một nhóm nhỏ có độ trễ cao.

## 9. Tổng hợp bucket trước khi tính percentile

Percentile không phải giá trị có thể cộng gộp. Nếu có ba instance với p95 lần lượt là 100 ms, 300 ms và 500 ms, không thể lấy trung bình ba giá trị này để suy ra p95 của toàn hệ thống.

Histogram giải quyết vấn đề bằng cách tổng hợp số quan sát trong cùng các bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Đây là thứ tự đúng: tính rate trên từng chuỗi bucket, cộng các chuỗi có cùng ranh giới, sau đó tính percentile. Không tính percentile từng instance rồi mới cộng hoặc lấy trung bình các percentile.

Nếu muốn percentile theo từng service:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Giữ `service` trong nhóm giúp tách kết quả theo service, còn `le` giữ cấu trúc histogram. Cần bảo đảm mỗi chuỗi có cùng định nghĩa đơn vị và ranh giới bucket trước khi cộng.

## 10. Tính tỷ lệ đạt SLO trực tiếp từ bucket

Nếu có SLO 300 ms, bucket `le="0.3"` của Timer biểu diễn số quan sát có thời lượng không vượt quá 300 ms trong định dạng giây của Prometheus.

Tỷ lệ request hoàn tất trong 300 ms:

~~~promql
sum(rate(http_server_requests_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Nếu muốn hiển thị phần trăm, nhân kết quả với 100. Kết quả cho biết tỷ lệ request nằm dưới ngưỡng 300 ms trong cửa sổ 5 phút.

Tỷ lệ request vượt ngưỡng có thể tính bằng:

~~~promql
1 -
(
  sum(rate(http_server_requests_seconds_bucket{le="0.3"}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
)
~~~

Khi mẫu số bằng 0, không có request trong cửa sổ; dashboard và alert cần xử lý trường hợp này theo quy ước của hệ thống. Đừng diễn giải no data thành tỷ lệ đạt 0% hoặc 100% nếu chưa xác định chính sách.

SLO bucket cũng giúp tránh việc chỉ nhìn p95. Nếu mục tiêu chính thức là 95% request dưới 300 ms, tỷ lệ quan sát dưới ngưỡng cho thấy trực tiếp mức độ đáp ứng mục tiêu.

## 11. Đọc count, sum và throughput cùng histogram

Histogram không chỉ phục vụ percentile. Timer còn xuất count và sum để quan sát lưu lượng và thời gian trung bình.

Số request mỗi giây:

~~~promql
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Thời lượng trung bình:

~~~promql
sum(rate(http_server_requests_seconds_sum[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Percentile p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
~~~

Đặt throughput, average và p95 cạnh nhau giúp đọc tình trạng rõ hơn. Ví dụ, throughput tăng mạnh trong khi p95 tăng có thể chỉ ra hệ thống chịu tải cao hoặc một phụ thuộc bên ngoài bị chậm. Average ổn định nhưng p99 tăng có thể cho thấy chỉ một nhóm request bị ảnh hưởng.

Với Timer, Prometheus thường xuất `_seconds_count`, `_seconds_sum` và `_seconds_max`; khi bật percentile histogram sẽ bổ sung chuỗi `_seconds_bucket`. Tên và chi tiết output phụ thuộc registry implementation, vì vậy cần kiểm tra scrape output của phiên bản đang chạy.

## 12. Cấu hình histogram qua Spring Boot

Nếu dùng Spring Boot Actuator và registry phù hợp, có thể cấu hình histogram theo tên meter bằng application properties:

~~~properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,300ms,1s
management.metrics.distribution.minimum-expected-value.http.server.requests=1ms
management.metrics.distribution.maximum-expected-value.http.server.requests=10s
~~~

Các thuộc tính này lần lượt bật percentile histogram, thêm ranh giới SLO và giới hạn phạm vi giá trị kỳ vọng cho Timer `http.server.requests`. Hãy kiểm tra phiên bản Spring Boot đang dùng và cú pháp cấu hình tương ứng trước khi áp dụng.

Có thể cấu hình trực tiếp trong code bằng builder khi chỉ một component sở hữu meter. Cấu hình qua properties hoặc MeterFilter hữu ích khi muốn áp dụng quy tắc cho các meter được tạo bởi thư viện dùng chung mà không sửa mã của thư viện đó.

Không bật histogram đại trà cho tất cả meter nếu chưa đánh giá chi phí. Bắt đầu với một số Timer quan trọng như HTTP request, truy vấn database hoặc lời gọi phụ thuộc ngoài, sau đó mở rộng khi có nhu cầu.

## 13. Chi phí cardinality và số lượng bucket

Mỗi bucket histogram thường trở thành một chuỗi thời gian riêng cho mỗi tổ hợp tag và mỗi instance. Số chuỗi thời gian tăng theo:

- Số meter được cấu hình histogram.
- Số bucket được xuất cho mỗi meter.
- Số tổ hợp tag.
- Số instance hoặc replica.
- Các chuỗi count, sum, max và metadata bổ sung.

Ví dụ, một Timer có 73 bucket, 10 tổ hợp tag và 20 instance có thể tạo khoảng 14.600 chuỗi bucket, chưa tính count, sum, max và các chuỗi khác. Nếu tag có hàng nghìn giá trị, số chuỗi tăng rất nhanh.

Các biện pháp kiểm soát:

1. Chỉ bật percentile histogram cho meter có nhu cầu percentile rõ ràng.
2. Giới hạn min/max theo phân phối và ngưỡng cần quan sát.
3. Chọn một số SLO boundary có ý nghĩa thay vì thêm quá nhiều bucket.
4. Giữ tag ở cardinality thấp, ví dụ method, outcome hoặc nhóm service.
5. Không dùng user ID, request ID, trace ID, order ID hoặc URL đầy đủ làm tag metrics.
6. Đánh giá số chuỗi thời gian sau khi bật histogram ở môi trường thử nghiệm.

Không nên đánh đổi mọi chi phí để có độ phân giải histogram rất cao. Bucket phù hợp với câu hỏi vận hành thường hữu ích hơn một histogram dày nhưng không được dùng trong dashboard hoặc alert.

## 14. Chọn bucket theo mục tiêu quan sát

Không có một bộ bucket tối ưu cho mọi ứng dụng. Chọn bucket dựa trên phân phối và ngưỡng mà đội vận hành cần hiểu.

Với thời lượng request:

| Mục tiêu | Ví dụ ranh giới |
|---|---|
| Nhận biết request rất nhanh | 50 ms, 100 ms |
| Theo dõi ngưỡng tương tác | 300 ms, 500 ms |
| Theo dõi request chậm | 1 s, 2 s, 5 s |
| Xác định timeout hoặc ngưỡng cảnh báo | Gần timeout của dependency hoặc SLA |

Với kích thước payload:

| Mục tiêu | Ví dụ ranh giới |
|---|---|
| Payload nhỏ | 1 KB, 5 KB |
| Payload thông thường | 10 KB, 50 KB |
| Payload lớn | 100 KB, 500 KB, 1 MB |

Đây chỉ là ví dụ. Hãy lấy dữ liệu thực tế, xác định các vùng quan trọng và điều chỉnh bucket để percentile hoặc SLO được ước lượng đủ hữu ích.

Nếu p95 thường nằm giữa hai bucket rất xa nhau, độ phân giải ở vùng đó chưa đủ. Có thể thêm SLO boundary gần ngưỡng cần theo dõi hoặc điều chỉnh min/max để giữ thêm bucket mặc định trong vùng đó.

## 15. Kiểm thử cấu hình histogram

Unit test có thể xác minh Timer và DistributionSummary vẫn ghi nhận count, sum đúng:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
Timer timer = Timer.builder("http.server.requests")
        .register(registry);

timer.record(250, TimeUnit.MILLISECONDS);
timer.record(500, TimeUnit.MILLISECONDS);

assertThat(timer.count()).isEqualTo(2);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(750.0);
~~~

Kiểm thử này xác minh dữ liệu ghi nhận cơ bản. Nó không chứng minh backend sẽ xuất histogram bucket.

Với Prometheus registry, nên có kiểm thử tích hợp xác nhận bucket xuất ra:

~~~java
PrometheusMeterRegistry registry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

Timer.builder("http.server.requests")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300)
        )
        .register(registry)
        .record(250, TimeUnit.MILLISECONDS);

String scrape = registry.scrape();
assertThat(scrape).contains("http_server_requests_seconds_bucket");
~~~

Ngoài sự hiện diện của bucket, nên kiểm tra:

- Các ranh giới SLO mong đợi có trong scrape output.
- Tên metric và đơn vị phù hợp với query PromQL.
- Các tag được xuất đúng và không có giá trị động.
- Histogram có cùng tập tag keys trên các chuỗi cùng tên.
- Số lượng chuỗi thời gian tăng ở mức dự kiến.
- Truy vấn histogram_quantile trả về giá trị hợp lý khi có đủ sample.

Nếu test bằng SimpleMeterRegistry, đừng giả định nó có hành vi xuất histogram giống Prometheus. Hãy dùng registry hỗ trợ aggregable percentile histogram cho kiểm thử exporter.

## 16. Những lỗi thường gặp

**Bật publishPercentiles rồi cộng percentile giữa các instance.** Percentile tính ở ứng dụng không có tính cộng gộp. Dùng percentile histogram và tổng hợp bucket trước khi tính quantile.

**Bật publishPercentileHistogram nhưng backend không hỗ trợ.** Không phải registry nào cũng xuất histogram có thể tổng hợp. Kiểm tra hỗ trợ của backend và scrape output.

**Tính histogram_quantile sau khi bỏ label le.** Label `le` xác định ranh giới bucket. Giữ label này trong phép tổng hợp.

**Tính percentile từng instance rồi lấy trung bình.** Cách đó không cho percentile của toàn cụm. Cộng rate của từng bucket trước, rồi mới tính percentile.

**Không giới hạn phạm vi DistributionSummary.** Histogram có thể tạo toàn bộ tập bucket tiềm năng. Chọn min/max theo miền dữ liệu thực tế.

**Bật histogram cho mọi meter.** Bucket nhân với tag cardinality và số instance làm tăng đáng kể số chuỗi thời gian. Chỉ bật ở meter có nhu cầu.

**Nhầm SLO bucket với percentile.** SLO bucket cho biết số quan sát dưới một ngưỡng đã định; percentile là giá trị ước lượng tại một vị trí của phân phối. Hai loại thông tin bổ sung cho nhau.

**Dùng SLO boundary không đúng đơn vị.** Timer dùng Duration trong code và thường xuất giây ở Prometheus; DistributionSummary dùng giá trị theo base unit của đại lượng. Xác minh đơn vị trước khi viết query.

## 17. Checklist triển khai

Trước khi bật `publishPercentileHistogram()`, hãy xác minh:

- [ ] Meter là Timer hoặc DistributionSummary và có câu hỏi percentile cụ thể.
- [ ] Backend hỗ trợ histogram có thể tổng hợp.
- [ ] Đã chọn giữa percentile phía ứng dụng và histogram phía nhận.
- [ ] Đã xác định SLO boundary cần theo dõi.
- [ ] Min/max bao phủ miền giá trị thực tế và không tạo bucket thừa.
- [ ] Query PromQL giữ label `le` và tính rate từng bucket trước khi tổng hợp.
- [ ] Tag có cardinality thấp và tập tag keys nhất quán.
- [ ] Đã kiểm tra số chuỗi thời gian và scrape output.
- [ ] Dashboard phân biệt percentile, throughput, average và tỷ lệ đạt SLO.
- [ ] Đã kiểm thử registry/exporter thực tế thay vì chỉ kiểm tra SimpleMeterRegistry.

## 18. Kết luận

`publishPercentileHistogram()` yêu cầu Micrometer công bố histogram buckets để hệ thống nhận tính percentile từ dữ liệu đã tổng hợp. Với Prometheus, dùng `histogram_quantile()` sau khi tính rate trên từng bucket và cộng theo label `le`. Cách này cho phép tính p95 hoặc p99 trên toàn cụm và theo các chiều tag đã chọn.

Hãy phân biệt histogram phía nhận với `publishPercentiles()` tính tại ứng dụng, chọn SLO boundaries có ý nghĩa, giới hạn min/max và kiểm soát cardinality. Histogram đem lại góc nhìn phần đuôi và khả năng tổng hợp mạnh hơn, nhưng mỗi bucket tạo thêm dữ liệu cần xuất và lưu trữ. Cấu hình có chủ đích và kiểm thử scrape output giúp percentile phản ánh đúng mục tiêu vận hành với chi phí hợp lý.
