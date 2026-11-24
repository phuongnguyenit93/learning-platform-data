# Viết truy vấn kiểm tra lưu lượng, lỗi và độ trễ từ dữ liệu Micrometer

## Mục tiêu thực hành

Trong bài thực hành này, bạn sẽ dùng metrics do Spring Boot và Micrometer tạo ra để trả lời ba câu hỏi vận hành:

1. Ứng dụng đang nhận bao nhiêu request mỗi giây?
2. Bao nhiêu phần trăm request trả về lỗi?
3. Độ trễ trung bình và percentile 95 của request là bao nhiêu?

Bạn sẽ bật Prometheus endpoint, xác minh dữ liệu scrape, cấu hình histogram cho HTTP Timer và viết PromQL cho traffic, error rate, latency cùng SLO. Cuối bài, bạn sẽ kiểm tra các truy vấn trên một luồng request thành công và thất bại.

Sau khi hoàn thành, bạn có thể:

- Đọc tên metric Micrometer sau khi Prometheus exporter chuyển đổi.
- Dùng rate() và increase() để phân tích lưu lượng trong một khoảng thời gian.
- Tính tỷ lệ lỗi từ status code hoặc outcome.
- Tính latency trung bình từ Timer count và sum.
- Tính p95 bằng histogram_quantile() khi histogram đã được bật.
- Đo tỷ lệ request hoàn tất trong một ngưỡng SLO.
- Nhận biết khi dữ liệu hoặc cấu hình histogram chưa đủ để trả lời câu hỏi.

## Bối cảnh và dữ liệu sử dụng

Giả sử bạn có một ứng dụng Spring Boot xử lý API đơn hàng. Ứng dụng đã có Spring MVC hoặc WebFlux và dùng Micrometer qua Spring Boot Actuator. Spring Boot tự instrument HTTP server request và ghi Timer có tên logic là http.server.requests.

Khi dùng Prometheus registry, metric Timer thường được export thành các series:

| Series | Ý nghĩa |
|---|---|
| http_server_requests_seconds_count | Số request đã được ghi nhận |
| http_server_requests_seconds_sum | Tổng thời gian xử lý, đơn vị giây |
| http_server_requests_seconds_max | Giá trị lớn nhất trong cửa sổ max đang được theo dõi; không phải counter tích lũy và có thể giảm về 0 sau khi cửa sổ hết hạn |
| http_server_requests_seconds_bucket | Histogram bucket, nếu histogram được bật |

Tên thực tế có thể thay đổi theo naming convention và phiên bản exporter. Luôn mở /actuator/prometheus để xác minh tên và labels mà ứng dụng đang export.

Các tag HTTP thường gặp gồm method, uri, status, outcome và exception. Tag uri của Spring Boot thường là route template như /api/orders/{id}; hãy kiểm tra output thực tế của ứng dụng trước khi viết truy vấn.

## Chuẩn bị ứng dụng

### Thêm dependency

Với Maven, thêm Actuator và Prometheus registry. Hãy để Spring Boot dependency management quản lý phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Nếu dự án đã có Actuator hoặc Prometheus registry thì không cần thêm dependency lần nữa. Khởi động ứng dụng và xác minh dependency tree dùng đúng registry.

### Cấu hình endpoint và histogram

Thêm vào application.properties:

~~~properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,250ms,500ms,1s
~~~

Hai thuộc tính distribution bật histogram và thêm các ranh giới SLO cho HTTP Timer. Histogram là điều kiện cần để Prometheus có bucket series cho truy vấn percentile và tỷ lệ đáp ứng ngưỡng.

Endpoint Prometheus chứa toàn bộ metric được registry export. Chỉ expose endpoint qua mạng nội bộ hoặc cơ chế bảo vệ phù hợp; không công khai Actuator endpoint không cần thiết ra Internet.

### Xác minh dữ liệu scrape

Khởi động ứng dụng rồi mở:

~~~text
http://localhost:8080/actuator/prometheus
~~~

Tìm các dòng bắt đầu bằng http_server_requests_seconds. Bạn cần thấy ít nhất count và sum sau khi có request. Khi histogram được bật, output cần có các dòng bucket với label le.

Ví dụ minh họa:

~~~text
# TYPE http_server_requests_seconds histogram
http_server_requests_seconds_bucket{method="GET",uri="/api/orders",status="200",outcome="SUCCESS",le="0.1"} 37
http_server_requests_seconds_bucket{method="GET",uri="/api/orders",status="200",outcome="SUCCESS",le="0.25"} 82
http_server_requests_seconds_bucket{method="GET",uri="/api/orders",status="200",outcome="SUCCESS",le="0.5"} 96
http_server_requests_seconds_bucket{method="GET",uri="/api/orders",status="200",outcome="SUCCESS",le="1.0"} 100
http_server_requests_seconds_bucket{method="GET",uri="/api/orders",status="200",outcome="SUCCESS",le="+Inf"} 100
http_server_requests_seconds_count{method="GET",uri="/api/orders",status="200",outcome="SUCCESS"} 100
http_server_requests_seconds_sum{method="GET",uri="/api/orders",status="200",outcome="SUCCESS"} 18.4
~~~

Đây chỉ là dữ liệu minh họa để đọc cấu trúc. Bucket là bộ đếm tích lũy: bucket le="0.5" chứa mọi request có duration nhỏ hơn hoặc bằng 0,5 giây. Bucket +Inf phải bằng count.

## Kết nối Prometheus

Thêm job scrape vào prometheus.yml:

~~~yaml
scrape_configs:
  - job_name: orders-api
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - localhost:8080
~~~

Khởi động hoặc reload Prometheus theo cách triển khai của bạn. Trong Prometheus UI, mở Status → Targets và xác nhận target orders-api có trạng thái UP.

Nếu Prometheus chạy trong container, localhost bên trong container là chính container đó. Dùng hostname hoặc địa chỉ mạng mà container có thể truy cập tới ứng dụng.

## Tạo traffic để có dữ liệu

Gửi request tới endpoint thành công và endpoint lỗi đã có trong ứng dụng. Ví dụ:

- GET /api/orders trả về 2xx.
- GET /api/orders/fail cố ý trả về 5xx trong môi trường lab.
- GET /api/orders/slow thực hiện một thao tác chậm có kiểm soát, nếu ứng dụng có endpoint này.

Không tạo endpoint lỗi hoặc chậm trên môi trường production chỉ để chạy bài thực hành. Nếu API của bạn dùng route khác, thay URL trong các bước bên dưới bằng route thật.

Trên Windows PowerShell, có thể tạo một đợt request mẫu:

~~~powershell
$base = "http://localhost:8080"

1..100 | ForEach-Object {
    try {
        Invoke-WebRequest -Uri "$base/api/orders" -UseBasicParsing -TimeoutSec 5 | Out-Null
    } catch {
    }
}

1..10 | ForEach-Object {
    try {
        Invoke-WebRequest -Uri "$base/api/orders/fail" -UseBasicParsing -TimeoutSec 5 | Out-Null
    } catch {
    }
}
~~~

Lệnh trên giả định hai route tồn tại và route fail thực sự trả về 5xx; kiểm tra status trước khi chạy truy vấn lỗi. Khối catch chỉ bỏ qua lỗi HTTP phía client để vòng lặp tiếp tục; server vẫn phải nhận và xử lý request. Sau khi gửi tải, đợi ít nhất hai chu kỳ scrape trước khi đánh giá truy vấn rate.

## Đọc dữ liệu Timer trước khi viết truy vấn

Prometheus lưu counter dạng tích lũy. Vì vậy, giá trị _count tăng dần theo thời gian, còn rate() tính tốc độ tăng trong một cửa sổ:

- count: tổng số observation từ lúc process bắt đầu hoặc từ lần reset gần nhất.
- rate(count[5m]): số observation trung bình mỗi giây trong 5 phút gần nhất.
- increase(count[5m]): số observation ước tính trong 5 phút gần nhất.
- sum: tổng thời lượng của mọi observation, đơn vị giây.
- rate(sum[5m]): số giây xử lý được cộng thêm trung bình mỗi giây trong cửa sổ.
- bucket: số observation có duration nhỏ hơn hoặc bằng ranh giới le.

Luôn áp dụng rate() trước khi sum() qua nhiều instance. Cách này cho phép Prometheus xử lý counter reset riêng từng instance trước khi cộng tổng.

## Truy vấn 1: kiểm tra lưu lượng

### Request mỗi giây toàn ứng dụng

~~~promql
sum(
  rate(http_server_requests_seconds_count[5m])
)
~~~

Kết quả là request per second (RPS) trung bình trong 5 phút gần nhất. Dùng truy vấn này để quan sát tổng tải của service.

### Request mỗi giây theo route và HTTP method

~~~promql
sum by (method, uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Truy vấn này cho biết route nào đang nhận nhiều tải. Nếu có nhiều instance, sum() gộp các instance nhưng vẫn giữ method và uri.

### Số request trong 5 phút gần nhất

~~~promql
sum by (uri) (
  increase(http_server_requests_seconds_count[5m])
)
~~~

increase() trả về số request ước tính trong cửa sổ 5 phút. Nó phù hợp với câu hỏi có bao nhiêu request trong khoảng thời gian, còn rate() phù hợp với biểu đồ tốc độ.

### Top 5 route có lưu lượng cao

~~~promql
topk(
  5,
  sum by (uri) (
    rate(http_server_requests_seconds_count[5m])
  )
)
~~~

Nếu uri có giá trị UNKNOWN hoặc NOT_FOUND, hãy kiểm tra các request không được map vào route template. Không thay uri bằng raw URL hoặc ID request để làm truy vấn chi tiết hơn; cách đó tạo cardinality lớn.

## Truy vấn 2: kiểm tra lỗi

### Tốc độ request 5xx

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
~~~

status=~"5.." chọn các HTTP status thuộc nhóm 5xx. Truy vấn trả về số lỗi server mỗi giây theo route.

### Tỷ lệ lỗi 5xx theo route

~~~promql
100 *
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Kết quả là phần trăm request 5xx trong tổng request theo route. Nếu không có request trong cửa sổ, phép chia có thể cho NaN khi cả tử số và mẫu số bằng 0; nếu không có series phù hợp thì kết quả là No data. Hãy xử lý trạng thái không có traffic riêng, đừng diễn giải nó thành tỷ lệ lỗi 0%.

### Phân biệt 4xx và 5xx

~~~promql
sum by (status) (
  rate(http_server_requests_seconds_count{status=~"4.."}[5m])
)
~~~

~~~promql
sum by (status) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
~~~

4xx thường đại diện request không hợp lệ, không được phép hoặc tài nguyên không tồn tại; 5xx thường đại diện lỗi phía server hoặc dependency. Tuy nhiên, hãy dùng semantics API của hệ thống để phân loại, vì một số ứng dụng dùng status code đặc thù cho nghiệp vụ.

### Tỷ lệ lỗi toàn service

~~~promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Truy vấn này thích hợp cho một stat panel toàn service. Nếu cần tách lỗi do dependency, timeout hoặc validation, hãy instrument thêm một error category có tập giá trị hữu hạn ở lớp nghiệp vụ; status HTTP không luôn thể hiện nguyên nhân gốc.

## Truy vấn 3: kiểm tra độ trễ

### Độ trễ trung bình

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_sum[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Tử số là tổng số giây xử lý được ghi nhận mỗi giây; mẫu số là số request mỗi giây. Tỷ số là thời gian xử lý trung bình theo giây. Có thể nhân 1000 để hiển thị millisecond.

Trung bình có thể che giấu một nhóm request rất chậm. Ví dụ, phần lớn request mất 20 ms nhưng một số request mất vài giây vẫn có thể khiến người dùng gặp trải nghiệm xấu mà mean không thể hiện rõ.

### Percentile 95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Đây là p95 theo route: 95% request trong phân phối ước tính có duration không vượt quá giá trị trả về. Đơn vị kết quả là giây.

Nếu cần xem theo method và route:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, method, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

histogram_quantile() cần histogram bucket và label le. Nếu không có series _bucket, hãy kiểm tra percentiles-histogram hoặc SLO boundaries đã được bật trước khi meter được tạo và Prometheus đã scrape lại dữ liệu mới.

### Không nhầm percentile client-side với histogram

Micrometer có thể tính percentile tại từng instance, nhưng percentile tính ở client không thể được cộng gộp chính xác giữa nhiều instance bằng PromQL. Để tính p95 toàn service, bật percentile histogram và truy vấn bucket. Histogram là dữ liệu phân phối có thể tổng hợp; percentile riêng lẻ của từng instance thì không.

### Kiểm tra tỷ lệ đáp ứng SLO 500 ms

Vì đã cấu hình SLO boundary 500 ms, Prometheus có bucket le="0.5". Truy vấn:

~~~promql
100 *
sum by (uri) (
  rate(http_server_requests_seconds_bucket{le="0.5"}[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Kết quả là phần trăm request hoàn tất trong tối đa 500 ms. Nếu mục tiêu SLO là 95%, panel cần duy trì giá trị ít nhất 95 trong cửa sổ đánh giá đã thống nhất.

Ranh giới le="0.5" có đơn vị giây vì metric Timer được export theo seconds. Nếu đổi SLO boundary, kiểm tra label le trong scrape output để dùng đúng giá trị.

## Tạo dashboard tối thiểu

Tạo năm panel trong Grafana hoặc Prometheus UI:

| Panel | Truy vấn | Cách đọc |
|---|---|---|
| Request rate | Tổng rate của _count | RPS toàn service |
| 5xx rate | Rate của _count với status 5xx | Lỗi server mỗi giây |
| 5xx percentage | Tỷ lệ 5xx trên tổng request | Tỷ lệ lỗi theo phần trăm |
| p95 latency | histogram_quantile trên _bucket | Độ trễ của nhóm request chậm |
| SLO 500 ms | Bucket le=0.5 chia count | Tỷ lệ request nằm trong ngưỡng |

Chọn cùng cửa sổ 5 phút cho các panel đầu tiên để dễ so sánh. Với hệ thống ít traffic, cửa sổ dài hơn như 10 hoặc 15 phút có thể ổn định hơn; với cảnh báo nhanh, hãy cân nhắc cả độ trễ scrape và độ nhạy của rate window.

## Đọc một ví dụ kết quả

Giả sử trong cửa sổ 5 phút, route /api/orders ghi nhận:

| Kết quả | Số lượng |
|---|---:|
| Tổng request | 252 |
| HTTP 2xx | 240 |
| HTTP 5xx | 12 |
| Request hoàn tất trong 500 ms | 235 |
| p95 latency | 420 ms |

Tỷ lệ lỗi 5xx:

\[
\frac{12}{252}\times 100 \approx 4.76\%
\]

Tỷ lệ đáp ứng ngưỡng 500 ms:

\[
\frac{235}{252}\times 100 \approx 93.25\%
\]

Nếu SLO yêu cầu 95% request dưới 500 ms, route này chưa đạt SLO dù p95 420 ms nhỏ hơn 500 ms. Hai số liệu trả lời hai câu hỏi khác nhau: p95 là quantile, còn SLO ratio là tỷ lệ observation nằm trong ranh giới đã chọn.

Các con số trên chỉ minh họa cách diễn giải; kết quả truy vấn thực tế được tính từ dữ liệu Prometheus của ứng dụng.

## Bài tập thực hành

Thực hiện lần lượt và lưu các truy vấn vào file dashboard hoặc ghi chú lab:

1. Tạo traffic thành công và xác nhận http_server_requests_seconds_count tăng.
2. Tạo một đợt request 5xx trong môi trường lab.
3. Viết truy vấn RPS toàn service và RPS theo uri.
4. Viết truy vấn increase() để đếm request trong 5 phút.
5. Viết truy vấn tỷ lệ 5xx theo uri và toàn service.
6. Viết truy vấn 4xx riêng để phân biệt lỗi client với lỗi server.
7. Bật histogram và SLO boundaries 100 ms, 250 ms, 500 ms, 1 giây.
8. Viết truy vấn mean latency và p95 latency theo uri.
9. Viết truy vấn tỷ lệ request hoàn tất trong 500 ms.
10. Tạo dashboard có traffic, error percentage, p95 và SLO compliance.

### Câu hỏi kiểm tra

- Vì sao nên dùng rate() trên từng series trước khi sum()?
- Vì sao _count tăng dần nhưng rate(_count[5m]) có thể giảm?
- Vì sao p95 không thể tính bằng cách lấy trung bình p95 của các instance?
- Điều kiện nào khiến histogram_quantile() không trả về kết quả?
- Nếu tỷ lệ lỗi hiển thị No data, điều đó có đồng nghĩa không có lỗi không?
- Vì sao route template an toàn hơn raw URL khi dùng làm tag?

## Tiêu chí hoàn thành

| Tiêu chí | Kết quả mong đợi |
|---|---|
| Prometheus target | UP |
| Scrape endpoint | Có http_server_requests_seconds_count và _sum |
| Histogram | Có series _bucket và label le |
| Traffic query | Có RPS toàn service và theo route |
| Error query | Phân biệt 4xx, 5xx và tính được error percentage |
| Latency query | Tính được mean và p95 theo route |
| SLO query | Tính được phần trăm request dưới 500 ms |
| Cardinality | Dùng route template, không dùng ID hoặc raw URL |

## Xử lý sự cố khi truy vấn không có dữ liệu

### Không thấy http_server_requests_seconds_count

- Xác nhận Actuator và Prometheus registry có trong dependency tree.
- Kiểm tra endpoint /actuator/prometheus có được expose.
- Gửi request vào ứng dụng trước khi tìm metric.
- Kiểm tra target Prometheus đang UP và scrape đúng port/path.
- Xác minh ứng dụng đang dùng đúng MeterRegistry.

### Có count nhưng không có bucket

- Bật management.metrics.distribution.percentiles-histogram.http.server.requests.
- Cấu hình SLO boundaries đúng tên metric.
- Khởi động lại ứng dụng nếu cấu hình được thay đổi lúc startup.
- Tạo request mới và chờ Prometheus scrape.
- Kiểm tra trực tiếp output của /actuator/prometheus để tìm _bucket.

### p95 bằng 0 hoặc không hợp lý

- Xác nhận truy vấn dùng _bucket và giữ label le trong phép sum.
- Dùng rate() với cửa sổ đủ dài so với scrape interval.
- Không bỏ label le trước histogram_quantile().
- Không gộp các metric khác đơn vị hoặc khác semantics.
- Kiểm tra histogram đã có đủ request trong cửa sổ.

### Error percentage không khớp log

- Kiểm tra status label và filter 5xx.
- Phân biệt HTTP 4xx, HTTP 5xx và exception đã được xử lý thành response 2xx.
- Kiểm tra retry: một thao tác nghiệp vụ có thể tạo nhiều HTTP request.
- Đảm bảo tử số và mẫu số dùng cùng cửa sổ và cùng nhóm route.
- Kiểm tra metric không bị lọc hoặc đổi tag bởi MeterFilter.

### Không có label uri mong đợi

- Kiểm tra route template mà Spring MVC/WebFlux cung cấp.
- Request chưa map vào handler có thể được nhóm dưới giá trị đặc biệt.
- Không thêm raw path hoặc ID vào tag để thay thế.
- Nếu cần business operation, tạo metric riêng với tag operation có tập giá trị hữu hạn.

## Lưu ý khi dùng truy vấn trong production

- Dùng rate window lớn hơn vài lần scrape interval để tránh biểu đồ quá nhiễu.
- Dùng cùng labels giữa tử số và mẫu số của tỷ lệ.
- Tránh sum trước rate khi tổng hợp counter từ nhiều instance.
- Không dùng p95 client-side để đại diện percentile toàn service.
- Bật histogram có cân nhắc vì mỗi bucket và tổ hợp tag tạo thêm time series.
- Giữ tag keys ổn định và giá trị có cardinality thấp.
- Dùng route template thay URL động.
- Đặt alert theo SLO và traffic đủ lớn; không cảnh báo chỉ vì một request đơn lẻ chậm.
- Bảo vệ Prometheus scrape endpoint và giới hạn quyền truy cập dashboard.

## Kết luận

Từ Timer của Micrometer, Prometheus có thể cung cấp count, sum và histogram bucket để phân tích lưu lượng, lỗi và độ trễ. Dùng rate() để tính tốc độ, increase() để ước lượng số request trong cửa sổ, tỷ lệ 5xx để theo dõi lỗi, sum/count để tính mean và histogram_quantile() để tính p95. Khi có SLO bucket, bạn còn có thể đo tỷ lệ request nằm dưới một ngưỡng thời gian cụ thể. Điều kiện quan trọng là xác minh metric name, labels và histogram trực tiếp từ scrape output trước khi tin vào dashboard.

## Tài liệu tham khảo

- [Spring Boot - Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP server request metrics và cấu hình distribution.
- [Spring Boot - Prometheus Endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus): expose Prometheus scrape endpoint.
- [Micrometer - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer count, total time, max và histogram.
- [Micrometer - Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): percentile histogram, SLO boundaries và aggregatable quantiles.
- [Prometheus - Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate(), increase(), histogram_quantile() và topk().
- [Prometheus - Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): cách đọc histogram và tổng hợp quantile qua nhiều instance.
