# Cảnh báo số series metrics tăng nhanh

> **Chương:** Alerting  
> **Bối cảnh:** Spring Modulith Documentation & Observability — phát hiện sớm sự gia tăng số time series do nhãn metrics có cardinality cao, theo dõi riêng metrics theo application module và cảnh báo trước khi Prometheus hoặc backend metrics bị quá tải.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích một time series được định danh bởi metric name và tập label như thế nào.
2. Phân biệt **active series**, **series churn** và **sample ingestion rate**.
3. Theo dõi số series hiện hành của Prometheus bằng `prometheus_tsdb_head_series` và các thống kê TSDB.
4. Dùng `scrape_series_added`, series-created counters và PromQL để nhận diện tăng trưởng bất thường.
5. Tạo alert cho tổng series, tốc độ tăng, churn và một metric cụ thể.
6. Dùng module identifier để giới hạn phạm vi điều tra trong ứng dụng Spring Modulith.
7. Nhận diện các nhãn nguy hiểm như request ID, order ID, trace ID, URL động và exception message.
8. Giảm cardinality ở instrumentation, metric relabeling và cấu hình scrape mà vẫn giữ các tín hiệu vận hành cần thiết.

## 2. Time series và cardinality là gì?

Prometheus lưu dữ liệu dưới dạng time series. Mỗi series được định danh bởi:

- Tên metric, ví dụ `module_invocations_seconds_count`.
- Tập label key-value của series, ví dụ `module_identifier="payments"` và `instance="shop-1:8080"`.

Hai sample có cùng metric name nhưng khác một label value sẽ thuộc hai time series khác nhau:

~~~text
http_requests_total{method="GET", route="/orders"}
http_requests_total{method="POST", route="/orders"}
http_requests_total{method="GET", route="/payments"}
~~~

**Cardinality** là số lượng tổ hợp series riêng biệt được tạo ra từ metric name và các label values. Chỉ cần một label thay đổi, Prometheus tạo một series mới.

Ví dụ:

~~~text
http_requests_total{route="/orders/{id}", status="200"}
http_requests_total{route="/orders/{id}", status="500"}
~~~

Nếu route được chuẩn hóa thành `/orders/{id}`, số giá trị route vẫn hữu hạn. Nhưng nếu ghi URL thật:

~~~text
http_requests_total{route="/orders/10001", status="200"}
http_requests_total{route="/orders/10002", status="200"}
http_requests_total{route="/orders/10003", status="200"}
~~~

thì mỗi order ID có thể tạo thêm một series. Với hệ thống có nhiều đơn hàng, số series tăng theo traffic và thời gian.

## 3. Vì sao số series tăng nhanh gây rủi ro?

Mỗi time series cần metadata, index entry và cấu trúc lưu trữ. Khi cardinality tăng:

- Prometheus cần thêm RAM để quản lý head series và index.
- WAL, head chunks và block storage tăng.
- Query phải xử lý nhiều series hơn, làm dashboard và alert chậm.
- Scrape, remote write và backend metrics tiêu thụ thêm CPU/băng thông.
- Dịch vụ metrics có thể chạm soft limit/hard limit hoặc phát sinh chi phí ingest/active series cao hơn.

Một dashboard vẫn có thể hiển thị bình thường trong lúc cardinality đã tăng nhanh. Vì vậy cần cảnh báo dựa trên **số series và tốc độ tăng**, không chờ tới khi query timeout hoặc scrape thất bại.

### 3.1. Cardinality có thể tăng theo tích của các nhãn

Giả sử một metric có:

- 5 module.
- 4 HTTP method.
- 6 status code.
- 20 instance.

Số tổ hợp tối đa theo các dimension này là:

~~~text
5 × 4 × 6 × 20 = 2.400 series
~~~

Nếu thêm `order_id` với 100.000 giá trị, giới hạn lý thuyết có thể tăng lên hàng trăm triệu tổ hợp. Trong thực tế không phải mọi tổ hợp đều xuất hiện, nhưng một label có tập giá trị không giới hạn vẫn có thể làm series tăng rất nhanh.

Với classic histogram, mỗi tổ hợp label còn tạo nhiều bucket series cùng `_sum` và `_count`. Vì vậy histogram và các nhãn có cardinality cao có thể nhân chi phí lưu trữ.

## 4. Phân biệt active series, churn và sample rate

Ba tín hiệu này liên quan nhưng không thay thế nhau:

| Tín hiệu | Đo điều gì? | Metric/nguồn thường dùng | Điều có thể bỏ sót |
| --- | --- | --- | --- |
| **Active series** | Số series đang được theo dõi trong head block | `prometheus_tsdb_head_series` | Không cho biết series được tạo mới nhanh đến đâu |
| **Series churn** | Tốc độ tạo và loại bỏ series | `prometheus_tsdb_head_series_created_total`, `prometheus_tsdb_head_series_removed_total`, `scrape_series_added` | Tổng active series có thể vẫn ổn định dù churn rất cao |
| **Sample ingestion rate** | Số sample được ingest mỗi giây | `rate(prometheus_tsdb_head_samples_appended_total[5m])` | Nhiều sample không nhất thiết đồng nghĩa nhiều series mới |

Ví dụ: một label `request_id` liên tục thay đổi. Series cũ ngừng nhận sample và series mới được tạo. Active series có thể dao động quanh một mức tương tự, nhưng series churn rất cao.

Ngược lại, một histogram có nhiều bucket và label combinations có thể tạo nhiều active series ổn định, dù churn thấp.

## 5. Những metric nên theo dõi trên Prometheus

Prometheus cung cấp các self-metrics hữu ích:

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| `prometheus_tsdb_head_series` | Gauge | Số series trong head block của một Prometheus instance |
| `prometheus_tsdb_head_series_created_total` | Counter | Tổng số series được tạo trong head |
| `prometheus_tsdb_head_series_removed_total` | Counter | Tổng số series bị loại khỏi head |
| `prometheus_tsdb_head_samples_appended_total` | Counter | Tổng số sample được append; có thể có label `type` |
| `scrape_series_added` | Gauge theo target | Ước lượng số series mới được thêm trong lần scrape gần nhất |
| `scrape_samples_scraped` | Gauge theo target | Số sample target expose trong lần scrape |
| `scrape_samples_post_metric_relabeling` | Gauge theo target | Số sample còn lại sau metric relabeling |

`prometheus_tsdb_head_series` là số series trong head block của **một Prometheus instance**. Một series có thể còn được tính trong head một khoảng thời gian sau khi ngừng nhận sample; không nên hiểu gauge này là số series có sample đúng trong giây hiện tại.

`scrape_series_added` là số series mới được thêm ước lượng cho lần scrape của target; nó hữu ích để tìm job/instance đột nhiên tạo nhiều series. `scrape_samples_post_metric_relabeling` là số sample còn lại sau relabeling, **không phải số unique time series**.

Tên và khả năng có mặt của một số self-metrics phụ thuộc phiên bản Prometheus và cách scrape. Hãy kiểm tra endpoint `/metrics` của Prometheus trước khi đưa chúng vào alert rule.

## 6. Xem chi tiết cardinality qua TSDB Status API

Khi alert kích hoạt, cần biết metric nào và label nào đang đóng góp nhiều series. Prometheus có endpoint:

~~~bash
curl -G "http://localhost:9090/api/v1/status/tsdb" \
  --data-urlencode "limit=20"
~~~

Response có thể chứa:

| Trường | Ý nghĩa |
| --- | --- |
| `headStats.numSeries` | Tổng số series trong head block |
| `seriesCountByMetricName` | Số series theo từng metric name |
| `labelValueCountByLabelName` | Số giá trị khác nhau theo từng label name |
| `memoryInBytesByLabelName` | Tổng độ dài byte của các label values theo label name |
| `seriesCountByLabelPair` | Số series theo từng cặp label key-value |

Tham số `limit` giới hạn số phần tử trả về cho từng nhóm thống kê; mặc định API trả một số mục đầu tiên. Endpoint này rất hữu ích để tìm metric hoặc label đáng nghi sau khi có cảnh báo.

Đây là API quản trị của Prometheus. Không expose endpoint status ra Internet; chỉ cho phép truy cập từ mạng vận hành hoặc người có quyền quản trị. Cấu trúc response có thể thay đổi theo phiên bản, nên đối chiếu API docs của Prometheus đang chạy.

## 7. PromQL để nhìn tổng số và tốc độ tăng

### 7.1. Tổng active series

~~~promql
prometheus_tsdb_head_series
~~~

Nếu scrape nhiều Prometheus instances, hiển thị từng instance:

~~~promql
prometheus_tsdb_head_series
~~~

Hoặc tổng hợp theo cluster nếu label `cluster` được gắn nhất quán:

~~~promql
sum by (cluster) (prometheus_tsdb_head_series)
~~~

Không cộng các replica Prometheus HA rồi so với giới hạn của một replica; xác định rõ ngưỡng đang áp dụng cho từng instance hay toàn cụm.

### 7.2. Số series tăng trong 10 phút

~~~promql
delta(prometheus_tsdb_head_series[10m])
~~~

`delta()` so sánh giá trị gauge đầu và cuối cửa sổ. Kết quả dương lớn cho thấy số active series tăng trong khoảng đó; kết quả âm có thể xuất hiện khi head series bị loại bỏ.

### 7.3. Tốc độ tạo series mới

~~~promql
rate(prometheus_tsdb_head_series_created_total[5m])
~~~

Đơn vị là series mới mỗi giây. Đây là tín hiệu churn phía TSDB; nếu tăng mạnh, hãy kiểm tra `scrape_series_added` để xác định target có đóng góp nhiều series mới.

### 7.4. Series mới theo scrape target

~~~promql
max by (job, instance) (
  scrape_series_added
)
~~~

Biểu thức này cho biết target nào có số series mới lớn trong lần scrape gần nhất. Có thể dùng `topk(10, ...)` để hiển thị 10 target có giá trị cao nhất:

~~~promql
topk(10, max by (job, instance) (scrape_series_added))
~~~

### 7.5. Sample ingestion rate

~~~promql
sum by (type) (
  rate(prometheus_tsdb_head_samples_appended_total[5m])
)
~~~

Đây là tốc độ sample append, không phải tốc độ tạo series. Dùng panel này để đánh giá ingest load bổ sung cho active-series và churn panels.

## 8. Tìm metric đang tạo nhiều series

Để đếm số series theo metric name:

~~~promql
topk(
  20,
  count by (__name__) ({__name__=~"module_.*"})
)
~~~

Thay regex bằng phạm vi cần kiểm tra, ví dụ `http_.*`, `jvm_.*` hoặc `.*` cho toàn bộ metric. Query toàn TSDB có thể tốn tài nguyên vì phải quét index; không nên chạy truy vấn rộng này trên mỗi lần refresh dashboard có tần suất cao.

Với query dùng thường xuyên, tạo recording rule:

~~~yaml
groups:
  - name: metrics-cardinality
    interval: 1m
    rules:
      - record: active_series_per_metric:module
        expr: |
          label_replace(
            count by (__name__) ({__name__=~"module_.*"}),
            "metric", "$1", "__name__", "(.*)"
          )
~~~

Recording rule sao chép metric name sang label `metric`, giúp alert và dashboard dễ hiển thị từng metric. Phạm vi `module_.*` là ví dụ; cần chỉnh regex theo tên series thực tế sau khi Micrometer chuẩn hóa meter name.

Sau đó query:

~~~promql
active_series_per_metric:module
~~~

## 9. Tìm label có quá nhiều giá trị

Nếu nghi ngờ một metric đang gắn label động, đếm số giá trị khác nhau của label đó:

~~~promql
count(
  count by (order_id) (
    http_server_requests_seconds_count
  )
)
~~~

Kết quả là số giá trị `order_id` khác nhau xuất hiện trong metric được chọn. Thay `order_id` bằng label nghi vấn thực tế, ví dụ `request_id`, `trace_id`, `customer_id` hoặc `uri`.

Để xem số series theo từng giá trị label:

~~~promql
topk(
  20,
  count by (order_id) (
    http_server_requests_seconds_count
  )
)
~~~

Truy vấn này chỉ có ý nghĩa nếu metric có label đó. Với TSDB lớn, ưu tiên TSDB Status API hoặc cardinality explorer để khảo sát tổng thể; chỉ dùng PromQL theo metric cụ thể khi đã thu hẹp phạm vi.

## 10. Alert cho tổng active series

Ví dụ rule cảnh báo khi Prometheus head vượt 1,5 triệu series:

~~~yaml
groups:
  - name: prometheus-cardinality
    rules:
      - alert: PrometheusHeadSeriesHigh
        expr: prometheus_tsdb_head_series > 1500000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Prometheus head series đang ở mức cao"
          description: "Instance {{ $labels.instance }} đang có {{ $value }} active series."
~~~

Ngưỡng 1,5 triệu chỉ là ví dụ. Không có một ngưỡng active series đúng cho mọi Prometheus host: khả năng phụ thuộc RAM, CPU, scrape interval, label count, histogram buckets, retention và query workload. Hãy xác lập baseline và kiểm thử tải để đặt ngưỡng warning/critical theo năng lực thực tế.

Nếu backend là Mimir hoặc dịch vụ metrics được quản lý, hãy dùng metric active-series và quota/limit của backend đó. `prometheus_tsdb_head_series` chỉ mô tả head block của Prometheus instance đang export metric này, không đại diện tự động cho toàn bộ remote backend.

## 11. Alert cho tăng trưởng đột biến và series churn

Tổng series chưa vượt ngưỡng vẫn có thể có một đợt tăng bất thường sau deployment. Thêm alert theo tốc độ:

~~~yaml
groups:
  - name: prometheus-cardinality-growth
    rules:
      - alert: PrometheusHeadSeriesGrowingFast
        expr: delta(prometheus_tsdb_head_series[10m]) > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Số active series tăng nhanh"
          description: "Head series tăng hơn 10.000 trong cửa sổ 10 phút."

      - alert: PrometheusSeriesChurnHigh
        expr: increase(prometheus_tsdb_head_series_created_total[10m]) > 20000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Prometheus đang tạo nhiều series mới"
          description: "TSDB đã tạo hơn 20.000 series trong 10 phút."

      - alert: ScrapeSeriesAddedHigh
        expr: max by (job, instance) (scrape_series_added) > 500
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Một scrape target đang tạo nhiều series mới"
          description: "Target {{ $labels.job }}/{{ $labels.instance }} thêm nhiều series trong mỗi lần scrape."
~~~

Các ngưỡng 10.000, 20.000 và 500 là giá trị minh họa. Đặt theo baseline của môi trường và scrape interval. Với hệ thống bình thường có deployment tạo thêm series, có thể dùng `for` dài hơn hoặc loại trừ giai đoạn rollout đã biết.

`PrometheusSeriesChurnHigh` hữu ích khi active series không tăng nhiều nhưng series mới liên tục được tạo. Đây là dấu hiệu thường gặp khi label chứa ID hoặc giá trị động.

## 12. Alert riêng cho metrics của Spring Modulith

Trong Spring Modulith, module entry observation mặc định dùng tên `module.invocations`. Những low-cardinality keys phù hợp để phân nhóm là:

- `module.identifier`: định danh kỹ thuật của application module.
- `module.name`: tên hiển thị của module.
- `module.invocation-type`: kiểu invocation, ví dụ bean hoặc event listener.

`module.method` là high-cardinality metadata. Nó hữu ích trên span để tìm method cụ thể, nhưng không nên đưa thành metric tag.

Các event publication metrics như `module.events.published` cũng có thể được phân nhóm theo module và event type. Tuy nhiên, nếu customizer thêm `orderId`, `customerId` hoặc giá trị nghiệp vụ riêng cho từng event vào metric tag, số series sẽ tăng theo dữ liệu.

### 12.1. Đếm series theo module

Nếu series Modulith đã có label `module_identifier`, có thể xem số series theo module:

~~~promql
count by (module_identifier) (
  {__name__=~"module_.*", module_identifier!=""}
)
~~~

Query này đếm các series thuộc metric name bắt đầu bằng `module_.*` theo module identifier. Nó hữu ích để phát hiện một module có số series tăng bất thường sau khi thêm convention hoặc event metrics.

### 12.2. Alert theo từng metric Modulith

Sau khi tạo recording rule `active_series_per_metric:module` ở phần 8:

~~~yaml
groups:
  - name: modulith-cardinality
    rules:
      - alert: ModulithMetricSeriesHigh
        expr: active_series_per_metric:module > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Metric Modulith có nhiều series"
          description: "Metric {{ $labels.metric }} đang có {{ $value }} series."
~~~

Ngưỡng 1.000 chỉ là ví dụ. Một Timer histogram có nhiều bucket và nhiều module/instance có thể có số series lớn hơn counter đơn giản. Đặt budget riêng theo metric family và số module dự kiến.

## 13. Thiết kế dashboard cardinality

Một dashboard chuyên theo dõi cardinality nên có các panel:

| Panel | Query/nguồn | Câu hỏi |
| --- | --- | --- |
| Active head series | `prometheus_tsdb_head_series` | Tổng series hiện tại có gần ngưỡng không? |
| Series growth 10m | `delta(prometheus_tsdb_head_series[10m])` | Số series đang tăng hay giảm? |
| Series created/sec | `rate(prometheus_tsdb_head_series_created_total[5m])` | Churn có tăng không? |
| New series by target | `scrape_series_added` theo job/instance | Target nào tạo nhiều series mới? |
| Series by metric | `active_series_per_metric:module` | Metric nào đóng góp nhiều series? |
| Series by module | Query `count by (module_identifier)` | Module nào tăng số series? |
| Samples/sec | `rate(prometheus_tsdb_head_samples_appended_total[5m])` | Ingestion load có tăng không? |
| Label cardinality | `/api/v1/status/tsdb` | Label name/value pair nào đáng nghi? |

Hiển thị cả giá trị hiện tại và xu hướng theo thời gian. Một panel top metrics giúp xác định metric gây tăng series; panel new series by target giúp khoanh vùng exporter hoặc application instance vừa thay đổi.

## 14. Ngăn cardinality từ instrumentation

Giải pháp bền vững nhất là thiết kế metric labels có tập giá trị hữu hạn ngay tại nơi tạo metrics.

| Tránh đưa vào metric label | Dùng dimension ổn định thay thế |
| --- | --- |
| `order_id` | Loại operation hoặc trạng thái xử lý |
| `customer_id`, email, user ID | `customer_tier` với tập giá trị hữu hạn nếu thực sự cần |
| `trace_id`, `span_id`, request ID | Dùng trace/log correlation |
| URL đầy đủ có path parameter | Route template như `/orders/{id}` |
| Exception message | Error category hoặc exception class có tập giá trị kiểm soát |
| SQL query nguyên văn | Tên operation/repository hoặc query name ổn định |
| Timestamp, UUID, token | Không dùng làm label |
| `module.method` | Dùng `module.identifier` và xem method trong trace |

Với Spring Modulith:

- Giữ `module.identifier` làm dimension chính.
- Dùng `module.name` và `module.invocation-type` nếu cần phân nhóm.
- Không tùy biến observation convention để đưa method, order ID hoặc dữ liệu request vào low-cardinality tags.
- Với `ModulithEventMetricsCustomizer`, chỉ thêm tag có tập giá trị hữu hạn; không lấy trực tiếp giá trị riêng của từng event làm label.
- Nếu bật histogram cho `module.invocations`, kiểm tra số bucket và số tổ hợp label để dự tính số series.

## 15. Giảm series ở Prometheus bằng metric relabeling

Nếu cần chặn metric family quá tốn kém trước khi ingest, có thể dùng `metric_relabel_configs`.

Ví dụ loại bỏ một nhóm metric debug không cần thiết:

~~~yaml
scrape_configs:
  - job_name: "shop-service"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["shop-service:8080"]
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: "debug_.*"
        action: drop
~~~

Metric relabeling được áp dụng ở bước cuối trước khi sample được ingest. Nó giúp bỏ các series không cần lưu ở Prometheus, nhưng không làm exporter ngừng tạo metric hoặc giảm lượng dữ liệu đã truyền qua network trong scrape response.

### 15.1. Cẩn thận khi dùng labeldrop

Có thể xóa label cụ thể:

~~~yaml
metric_relabel_configs:
  - action: labeldrop
    regex: "request_id|trace_id|order_id"
~~~

Chỉ làm điều này sau khi xác nhận các series vẫn được định danh duy nhất. Xóa một label có thể khiến hai series khác nhau trở thành cùng một label set, gây xung đột sample hoặc mất dimension cần thiết.

Ưu tiên sửa instrumentation để không phát label không phù hợp. Metric relabeling là biện pháp bảo vệ ở tầng ingest, không thay thế thiết kế metric đúng.

## 16. Dùng scrape limits như hàng rào bảo vệ

Prometheus hỗ trợ một số giới hạn theo scrape:

~~~yaml
scrape_configs:
  - job_name: "shop-service"
    metrics_path: "/actuator/prometheus"
    sample_limit: 50000
    label_limit: 30
    static_configs:
      - targets: ["shop-service:8080"]
~~~

- `sample_limit`: số sample tối đa được chấp nhận cho mỗi scrape sau metric relabeling.
- `label_limit`: số label tối đa trên mỗi sample.
- Các giới hạn về label name/value length cũng có thể được cấu hình theo phiên bản.

**Nếu vượt `sample_limit`, toàn bộ scrape bị đánh dấu thất bại**; Prometheus không chỉ bỏ phần sample vượt ngưỡng. Vì vậy cần theo dõi `up`, scrape errors và `scrape_samples_post_metric_relabeling` khi bật giới hạn.

Sample limit và label limit là hàng rào bảo vệ khi target phát dữ liệu bất thường. Chúng không tự giảm cardinality hợp lệ và có thể khiến metrics của target biến mất nếu đặt quá thấp.

## 17. Runbook khi alert cardinality kích hoạt

Khi nhận cảnh báo, đi theo trình tự:

1. **Xác định phạm vi:** alert ở một Prometheus instance, toàn cluster hay remote metrics backend?
2. **Xác định loại tăng:** active series tăng, churn tăng hay sample ingestion rate tăng?
3. **Tìm target:** xem `scrape_series_added` theo `job` và `instance`.
4. **Tìm metric:** xem `seriesCountByMetricName` trong TSDB Status API hoặc recording rule theo metric.
5. **Tìm label:** xem `labelValueCountByLabelName`, `memoryInBytesByLabelName` và `seriesCountByLabelPair`.
6. **Đối chiếu thay đổi:** kiểm tra deployment, thay đổi instrumentation, exporter version, histogram buckets hoặc metric relabeling vừa áp dụng.
7. **Xác định giá trị động:** kiểm tra request ID, URL đầy đủ, trace ID, customer ID, exception message hoặc event-specific value.
8. **Khắc phục tại nguồn:** chuẩn hóa route, bỏ label không giới hạn, giới hạn tập giá trị hoặc giảm bucket/dimension không cần thiết.
9. **Áp dụng biện pháp ingest tạm thời nếu cần:** metric relabeling có kiểm thử, tránh xóa label làm trùng series.
10. **Xác nhận:** theo dõi active series, series creation rate, scrape health và query latency sau thay đổi.

Không chỉ tăng RAM hoặc tăng quota để xử lý một label bị thiết kế sai. Nếu mỗi request tạo thêm một series, tài nguyên lớn hơn chỉ làm thời điểm quá tải đến muộn hơn.

## 18. Bài thực hành: mô phỏng label explosion trong module metrics

**Bối cảnh:** ứng dụng Spring Modulith có các module `orders`, `payments` và `inventory`. Một thay đổi instrumentation vô tình thêm `order_id` vào metric Timer của module `orders`.

Thực hiện:

1. Chạy Prometheus scrape ứng dụng và ghi baseline `prometheus_tsdb_head_series`.
2. Gửi một lượng request ổn định và theo dõi `module.invocations` cùng các label `module_identifier`, `module_name`, `module_invocation_type`.
3. Trong môi trường thử nghiệm, tạo một metric minh họa có label `order_id` nhận giá trị mới ở mỗi request.
4. Gửi nhiều request với order ID khác nhau; theo dõi `scrape_series_added` và `prometheus_tsdb_head_series_created_total`.
5. Dùng `/api/v1/status/tsdb?limit=20` để xác định metric và label có cardinality tăng.
6. So sánh active series với series churn; quan sát trường hợp series được tạo và loại bỏ liên tục.
7. Bỏ `order_id` khỏi metric label, giữ ID trong log hoặc trace để điều tra từng đơn hàng.
8. Kiểm tra lại số active series và tốc độ tạo series sau khi sửa.
9. Tạo alert rule cho tổng active series, growth và per-metric series.
10. Thử `sample_limit` trong môi trường thử nghiệm và xác nhận scrape failure được cảnh báo; sau đó gỡ giới hạn thử nghiệm nếu không phù hợp.

Mẫu bảng kết quả:

| Chỉ số | Trước thay đổi | Có order_id label | Sau khi sửa |
| --- | --- | --- | --- |
| Active series | Ghi baseline | Tăng theo request hoặc churn | Trở về mức ổn định |
| Series created rate | Thấp/ổn định | Tăng nhanh | Giảm |
| `scrape_series_added` | Thấp | Tăng ở target orders | Giảm |
| Series theo metric | Ghi baseline | Metric Timer orders tăng | Giảm |
| Module dimension | Identifier hữu hạn | Có thêm order ID không giới hạn | Chỉ còn dimension hữu hạn |
| Scrape health | Bình thường | Theo dõi nguy cơ chạm limit | Bình thường |

**Tiêu chí hoàn thành:** phân biệt được active series, churn và sample rate; xác định được metric/label gây tăng; cấu hình được alert tổng và alert theo metric; sửa instrumentation để giữ dimension module hữu hạn.

## 19. Ghi nhớ

Một quy trình cảnh báo cardinality nên theo dõi ba tầng:

~~~text
ACTIVE SERIES
  prometheus_tsdb_head_series
  → Tổng series đang được giữ trong head

SERIES GROWTH / CHURN
  head_series_created_total
  scrape_series_added
  → Series mới được tạo ở đâu và nhanh đến mức nào?

METRIC / LABEL BREAKDOWN
  /api/v1/status/tsdb
  recording rules + PromQL
  → Metric hoặc label nào gây tăng?
~~~

Với Spring Modulith, `module.identifier`, `module.name` và `module.invocation-type` là các dimension low-cardinality phù hợp để nhóm metrics. `module.method` và định danh riêng từng request nên ở trace/log. Khi series tăng nhanh, tìm metric và label tạo ra chúng trước khi tăng tài nguyên hoặc quota.

### Tài liệu tham khảo

- [Prometheus — Data model](https://prometheus.io/docs/concepts/data_model/) — metric name, labels và định danh time series.
- [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/) — tránh labels có cardinality cao như user ID/email.
- [Prometheus — Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/) — `scrape_series_added`, `scrape_samples_scraped` và `scrape_samples_post_metric_relabeling`.
- [Prometheus — HTTP API: TSDB Stats](https://prometheus.io/docs/prometheus/latest/querying/api/#tsdb-stats) — head series, series theo metric, label value count và memory theo label.
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/) — `metric_relabel_configs`, `sample_limit` và `label_limit`.
- [Grafana — Examples of high-cardinality alerts](https://grafana.com/docs/grafana/latest/alerting/examples/high-cardinality-alerts/) — alert active series, series growth và high ingestion rate.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — module observation keys và event publication metrics.
- [Spring Modulith — ModulithObservations.LowKeys API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html) — các low-cardinality keys của module entry observation.
- [Spring Modulith — ModulithObservations.HighKeys API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html) — metadata high-cardinality như `module.method`.

> **Lưu ý phiên bản:** self-metrics Prometheus, TSDB Status API và các giới hạn scrape có thể khác theo phiên bản. Tên series sau chuẩn hóa còn phụ thuộc Micrometer registry. Hãy kiểm tra `/metrics`, `/api/v1/status/tsdb` và `/actuator/prometheus` trên hệ thống thực tế trước khi triển khai alert rule. Bài được soạn trong STEP 4; Content QA chuyên môn thuộc bước riêng.
