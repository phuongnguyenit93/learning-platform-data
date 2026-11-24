# Dashboard request rate trong Spring Boot

Khi một service bắt đầu chậm, câu hỏi đầu tiên thường là traffic có thay đổi hay không. Request rate tăng đột ngột có thể làm thread pools, database connections hoặc downstream services bị bão hòa. Request rate giảm mạnh có thể báo hiệu lỗi routing, deploy thất bại hoặc khách hàng không truy cập được ứng dụng. Một dashboard request rate tốt giúp nhìn thấy lưu lượng theo thời gian, so sánh theo route và method, đồng thời đặt tín hiệu này cạnh latency và error rate để hiểu tác động vận hành.

Trong Spring Boot, Micrometer và Actuator có thể xuất HTTP server request metrics; Prometheus thu thập time series và Grafana trình bày dashboard. Dashboard chỉ hữu ích khi metric dimensions được chuẩn hóa: dùng route template như /api/orders/{id}, không dùng raw URL chứa order ID. Cách đặt labels quyết định cả khả năng phân tích lẫn chi phí cardinality.

Bài **Dashboard request rate** thuộc chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**. Module tập trung thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích request rate và cách đọc đơn vị requests/second.
- Hiểu Counter/Timer HTTP metrics và cách Prometheus tính rate.
- Viết PromQL dùng rate() và increase() cho request counters.
- Thiết kế dashboard theo service, method, route template và status class.
- Kết hợp request rate với latency và error rate theo RED method.
- Tránh cardinality cao do raw path, user ID hoặc request ID.
- Thiết kế panel, variables và time range trong Grafana.
- Đặt alert có window, threshold và traffic floor hợp lý.

## 2. Request rate là gì?

Request rate là số request được xử lý trong một đơn vị thời gian, thường biểu diễn bằng requests per second (req/s hoặc RPS). Với một counter tích lũy, request rate được tính từ mức tăng counter trong một cửa sổ thời gian.

Ví dụ service nhận 12.000 requests trong 5 phút:

\[
\text{Average RPS} = \frac{12,000}{5 \times 60} \approx 40
\]

Đây là trung bình trong cửa sổ 5 phút. Traffic thực tế có thể có burst ở từng giây; dashboard nên cho phép chọn cửa sổ quan sát phù hợp.

### Vì sao cần xem rate theo thời gian?

- Rate tăng nhanh: có thể là traffic bình thường, campaign, retry storm hoặc client loop.
- Rate giảm bất thường: có thể do outage, routing/configuration issue hoặc upstream không gửi request.
- Rate ổn định nhưng latency tăng: có thể do dependency chậm hoặc resource contention.
- Rate giảm và error ratio tăng: một phần requests có thể fail trước khi hoàn tất hoặc bị chặn tại gateway.

Không diễn giải một điểm rate riêng lẻ như bằng chứng outage. So sánh với baseline theo giờ/ngày, deployment events và các tín hiệu RED khác.

## 3. HTTP request metrics trong Spring Boot

Với Spring Boot Actuator và Micrometer instrumentation phù hợp, HTTP server requests thường được ghi bằng một Timer như http.server.requests. Timer cung cấp count và duration; Prometheus registry thường export các time series tương ứng, trong đó count có thể được dùng để tính request rate.

Dependencies thường cần:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Spring Boot BOM quản lý version tương thích. Tên meter, labels và export format có thể thay đổi theo Spring Boot/Micrometer version và web stack; xác minh bằng Actuator metrics hoặc Prometheus exposition của ứng dụng.

### Expose Prometheus endpoint

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Endpoint scrape thường là /actuator/prometheus. Chỉ expose trong network/authorization policy phù hợp. Nếu management server dùng port riêng hoặc base path khác, cập nhật Prometheus target tương ứng.

### Kiểm tra meter trước khi dựng dashboard

Trong môi trường development, có thể xem:

```text
GET /actuator/metrics/http.server.requests
GET /actuator/prometheus
```

Actuator metrics endpoint giúp kiểm tra meter và available tags. Prometheus exposition cho thấy tên series/labels thực tế mà scraper nhận được. Không đoán labels từ dashboard mẫu; hãy dùng output của đúng ứng dụng và version.

## 4. Counter, Timer và Prometheus rate

Counter là giá trị tăng dần theo sự kiện. Timer trong Micrometer ghi số lần và thời lượng; khi export sang Prometheus, Timer thường tạo count/sum và có thể có histogram buckets nếu bật.

Với HTTP request Timer, series count thường được export dưới tên tương tự http_server_requests_seconds_count trong Prometheus naming convention. Tên chính xác phụ thuộc registry và naming convention; kiểm tra exposition trước khi viết query.

### rate()

rate(counter[5m]) ước lượng tốc độ tăng trung bình mỗi giây của counter trong cửa sổ 5 phút. Prometheus xử lý counter resets, ví dụ process restart làm counter quay về 0.

PromQL ví dụ:

```promql
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
)
```

Query trên tính tổng request rate theo service nếu series có label service. Nếu service identity được gắn ở scrape target dưới job hoặc application, hãy thay label tương ứng. Tránh dùng label không tồn tại.

### increase()

increase(counter[1h]) ước lượng tổng số requests tăng trong một giờ. Hữu ích cho thống kê tổng lượt gọi theo khoảng thời gian:

```promql
sum by (uri) (
  increase(http_server_requests_seconds_count[1h])
)
```

Chỉ group theo uri nếu label đó là route template có tập giá trị giới hạn. Nếu label chứa raw path, query có thể tạo quá nhiều series và dashboard khó đọc.

## 5. Thiết kế request-rate panels

| Panel | Câu hỏi | Đơn vị/gợi ý |
| --- | --- | --- |
| Total request rate | Tổng traffic hiện tại là bao nhiêu? | req/s |
| Rate by route | Route nào nhận nhiều traffic? | req/s, top routes |
| Rate by method | GET/POST/PUT/DELETE phân bố thế nào? | req/s |
| Rate by status class | Bao nhiêu request 2xx/4xx/5xx? | req/s |
| Rate by instance | Traffic có phân bố lệch giữa replicas? | req/s |
| Request volume | Tổng số requests trong khoảng chọn? | requests |

Panel tổng nên hiển thị service-level rate. Các panel phân rã giúp tìm nguồn traffic. Đừng đưa hàng chục dimensions vào cùng một chart; dùng dashboard variables hoặc drill-down để giữ biểu đồ dễ đọc.

### Total request rate

```promql
sum(
  rate(http_server_requests_seconds_count[5m])
)
```

Query này cộng tất cả series. Nếu Prometheus scrape nhiều replicas, phép sum thường cho tổng service rate. Xác minh không scrape trùng cùng target qua nhiều jobs; duplicate scraping có thể làm rate bị đếm hai lần.

### Rate theo route và method

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count[5m])
)
```

Nếu labels thực tế dùng route thay cho uri, điều chỉnh query. Chỉ group theo labels có semantics ổn định.

### Rate theo status class

Nếu status label là mã HTTP:

```promql
sum by (status) (
  rate(http_server_requests_seconds_count[5m])
)
```

Để gộp theo status class 2xx/4xx/5xx, cần label đã được normalize thành class hoặc dùng recording rule/label transformation phù hợp. Không giả định regex grouping tự tạo label mới trong PromQL.

## 6. RED method: đặt request rate cạnh latency và errors

RED là cách quan sát service request path qua:

- **Rate:** requests mỗi giây.
- **Errors:** số hoặc tỷ lệ requests thất bại.
- **Duration:** thời gian xử lý request, thường xem percentile.

Request rate một mình không thể xác định service đang khỏe. Ví dụ RPS vẫn cao trong khi 50% requests trả 5xx. Một dashboard nên đặt total rate, error ratio và latency p95/p99 gần nhau để người trực có thể so sánh cùng time range.

### Error ratio

Ví dụ khi status label là HTTP status code:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count[5m])),
  1e-9
)
```

Query trả tỷ lệ 5xx trên tổng request rate. Nếu status label hoặc meter naming khác, thay cho phù hợp. Với traffic thấp, ratio có thể dao động mạnh; alert cần thêm minimum request volume hoặc dùng window dài hơn.

### Latency percentile

Nếu histogram buckets được bật và export theo Prometheus histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Đây là p95 latency tổng hợp. Cần bảo đảm histogram buckets thực sự được export; percentile không thể được tính chính xác từ count/sum đơn thuần. Với Micrometer percentile histograms, cấu hình và series names cần xác minh theo registry/version.

## 7. Route normalization và cardinality

Request-rate dashboard thường cần phân rã theo route. Hãy dùng route template:

| Raw request path | Route template |
| --- | --- |
| /api/orders/1001 | /api/orders/{id} |
| /api/orders/1002 | /api/orders/{id} |
| /api/customers/abc-9 | /api/customers/{id} |

Nếu mỗi ID tạo một uri label khác nhau, mỗi request có thể tạo time series mới. Hậu quả là Prometheus memory tăng, query chậm và top routes bị nhiễu bởi hàng nghìn path.

Không thêm request ID, trace ID, customer/order/user IDs, raw query string, email, token, session ID, payload fields hoặc exception message vào metric labels.

Nếu framework instrumentation chưa cung cấp route template đúng, dùng observation convention/customizer để chuẩn hóa route theo framework-supported route pattern. Không tự lấy raw URI làm fallback.

## 8. Grafana dashboard: variables và layout

Một dashboard thực dụng thường có variables:

- service: service/job được chọn.
- environment: dev/staging/prod.
- instance: replica cụ thể, thường có giá trị All.
- route: route template có traffic.

Variables phải dựa trên labels tồn tại và được kiểm soát. Không tạo variable từ customer IDs hoặc request IDs.

### Layout đề xuất

```text
Row 1: Total RPS | 5xx ratio | p95 latency | p99 latency
Row 2: RPS by route | RPS by method | RPS by status class
Row 3: RPS by instance | Request volume | Deployment annotations
```

Đặt dashboard time range mặc định phù hợp với ca trực (ví dụ 1 giờ) và refresh interval không quá ngắn so với scrape interval. Nếu scrape mỗi 15 giây, refresh mỗi 1 giây không làm dữ liệu mới hơn mà chỉ tăng query load.

### Dashboard annotations

Thêm annotations cho deploy, config changes, incident start/end hoặc scaling events. Khi RPS thay đổi, annotation giúp phân biệt traffic pattern bình thường với thay đổi do release hoặc infrastructure.

## 9. Alert từ request rate

Alert cần phản ánh một failure mode cụ thể. Một số ví dụ:

- Request rate giảm về gần 0 trong giờ service được kỳ vọng có traffic.
- Request rate tăng đột biến vượt baseline và gây saturation.
- 5xx ratio tăng trong khi traffic đủ lớn.
- Traffic lệch mạnh giữa instances.

Không alert chỉ vì RPS thấp nếu service có traffic không đều hoặc không có traffic vào ban đêm. Dùng lịch hoạt động, baseline hoặc tín hiệu từ upstream để xác định khi nào low traffic là bất thường.

### Ví dụ alert cho 5xx ratio

```yaml
groups:
  - name: spring-boot-http
    rules:
      - alert: HighHttp5xxRatio
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count[5m])) > 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: HTTP 5xx ratio is above 5 percent
```

Đây là ví dụ rule, cần thay metric name/labels theo scrape output thực tế. Ngưỡng 5% và traffic floor 1 RPS chỉ là điểm khởi đầu; chọn theo SLO, traffic profile và error budget.

### Alert cho traffic drop

Traffic drop nên so sánh với baseline cùng thời điểm hoặc một minimum expected rate. Một biểu thức đơn giản:

```promql
sum(rate(http_server_requests_seconds_count[10m])) < 0.1
```

Chỉ phù hợp với service luôn được kỳ vọng có traffic. Nếu traffic tự nhiên thay đổi theo giờ, dùng baseline/time-of-week hoặc synthetic probe thay vì ngưỡng tuyệt đối.

## 10. Scrape interval, rate window và dashboard refresh

Prometheus scrape interval quyết định tần suất lấy samples. Rate window nên dài hơn vài scrape intervals để có đủ samples và giảm nhiễu. Ví dụ scrape mỗi 15 giây có thể bắt đầu với rate(...[5m]).

| Tham số | Vai trò | Lưu ý |
| --- | --- | --- |
| Scrape interval | Tần suất Prometheus scrape | Cân bằng freshness và load |
| Rate window | Khoảng dữ liệu dùng tính RPS | Quá ngắn dễ nhiễu/thiếu samples |
| Dashboard refresh | Tần suất Grafana chạy lại query | Không cần nhanh hơn dữ liệu mới |
| Alert evaluation interval | Tần suất đánh giá rules | Chọn phù hợp detection objective |
| for duration | Thời gian điều kiện alert phải liên tục đúng | Giảm false positives ngắn hạn |

Không nhầm rate window với alert for: rate window tính tốc độ từ samples; for yêu cầu điều kiện alert tồn tại liên tục trước khi firing.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Dashboard RPS bằng 0 | Sai metric name/labels hoặc scrape target down | Kiểm tra /actuator/prometheus và Prometheus targets |
| RPS tăng gấp đôi | Scrape trùng target/job hoặc query cộng duplicate series | Kiểm tra scrape configuration và labels |
| Route panel có hàng nghìn dòng | uri label chứa raw path/ID | Chuẩn hóa route template |
| Rate query không có data | Rate window quá ngắn hoặc thiếu samples | Tăng window và kiểm tra scrape interval |
| RPS dao động mạnh | Traffic thấp, window ngắn hoặc scrape jitter | Tăng window và xem request volume |
| 5xx ratio tăng khi traffic rất thấp | Denominator nhỏ | Thêm traffic floor và for duration |
| p95/p99 không hiển thị | Histogram buckets chưa bật/export | Kiểm tra _bucket series |
| Dashboard khác Actuator count | Aggregation window, scrape gap hoặc duplicate registry | So sánh raw counter và PromQL window |
| Traffic drop nhưng service khỏe | Service không có expected traffic tại thời điểm đó | So với baseline/synthetic probe |
| Instance traffic lệch | Load balancing, sticky sessions hoặc replica health | Kiểm tra ingress, routing và instance metrics |
| Query dashboard chậm | Quá nhiều label combinations hoặc panels nặng | Giảm cardinality, dùng recording rules |

### Checklist kiểm tra

1. Xác nhận Actuator Prometheus endpoint trả HTTP metrics.
2. Xác nhận Prometheus target UP và scrape không bị duplicate.
3. Kiểm tra metric name, counter suffix và labels thực tế.
4. Xác minh route label là template, không chứa IDs.
5. So sánh rate() với increase() trong cùng time range.
6. Đặt rate window dài hơn vài scrape intervals.
7. Đối chiếu RPS với errors, latency và deployment annotations.
8. Kiểm tra dashboard variables chỉ dùng labels có cardinality phù hợp.

## 12. Thực hành: dựng dashboard request rate cho order-service

**Bối cảnh:** order-service chạy ba replicas, Prometheus scrape mỗi 15 giây. Đội vận hành cần xem tổng RPS, traffic theo route và phát hiện 5xx tăng.

### Phần A — Chuẩn bị

1. Thêm Actuator và Prometheus registry.
2. Expose /actuator/prometheus trong internal network.
3. Xác nhận http.server.requests và count series có trong exposition.
4. Cấu hình Prometheus scrape ba replicas với labels service/environment/instance.
5. Xác minh route label là route template.

### Phần B — Tạo panels

| Panel | PromQL khởi đầu | Đơn vị |
| --- | --- | --- |
| Total RPS | sum(rate(http_server_requests_seconds_count[5m])) | req/s |
| RPS by route | sum by (uri) (rate(http_server_requests_seconds_count[5m])) | req/s |
| RPS by method | sum by (method) (rate(http_server_requests_seconds_count[5m])) | req/s |
| 5xx ratio | 5xx rate / total rate | percent |
| Request volume | sum(increase(http_server_requests_seconds_count[1h])) | requests |

Thay metric name và labels theo exposition thực tế. Thêm variables service/environment/instance, dashboard annotations và time range 1 giờ.

### Phần C — Kiểm chứng

| Ca | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| A — Normal traffic | Gửi traffic ổn định | Total RPS phản ánh tổng ba replicas |
| B — Route distribution | Tăng traffic một route | Panel route tương ứng tăng |
| C — Error burst | Tạo 5xx có kiểm soát | 5xx rate/ratio tăng |
| D — Traffic drop | Dừng load generator | RPS giảm sau rate window |
| E — Restart replica | Restart một instance | Counter reset được rate() xử lý |
| F — Duplicate scrape | Tạm cấu hình scrape trùng trong test | Phát hiện RPS bị đếm lặp |
| G — Dynamic path | Gửi nhiều IDs khác nhau | Route series vẫn gộp theo template |
| H — Alert duration | Tạo lỗi ngắn hơn và dài hơn for | Chỉ lỗi kéo dài mới firing |

### Phần D — Câu hỏi tự đánh giá

1. Request rate khác tổng request count như thế nào?
2. Vì sao Prometheus rate() phù hợp với counter?
3. increase() hữu ích trong panel nào?
4. Vì sao cần route template thay cho raw URL?
5. Request rate cần đặt cạnh những tín hiệu RED nào?
6. Vì sao alert traffic drop cần expected traffic/baseline?
7. Rate window liên hệ thế nào với scrape interval?
8. for duration khác rate window ra sao?
9. Scrape duplicate làm sai RPS như thế nào?
10. Khi RPS ổn định nhưng p95 tăng, nên điều tra tín hiệu nào tiếp theo?

## 13. Ghi nhớ

**Dashboard request rate** cho biết service nhận và xử lý bao nhiêu requests mỗi giây, cách traffic phân bố theo route/method/status và thời điểm lưu lượng thay đổi. Spring Boot/Micrometer cung cấp HTTP request Timer metrics; Prometheus dùng rate() để tính RPS và increase() để ước lượng request volume trong một khoảng thời gian. Grafana trình bày các truy vấn này cùng variables, time range và deployment annotations.

Đặt request rate cạnh error ratio và latency theo RED method để hiểu tác động thay vì đọc RPS riêng lẻ. Dùng route templates và dimensions có cardinality thấp; raw URL, request IDs và customer IDs không phù hợp làm metric labels. Chọn rate window dựa trên scrape interval, đặt alert theo SLO/baseline và thêm traffic floor/for để hạn chế cảnh báo nhiễu. Xác minh metric names, labels và scrape targets từ exposition thực tế trước khi đưa dashboard vào vận hành.
