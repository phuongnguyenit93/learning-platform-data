# Dashboard latency cho Spring Boot

Trong chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**, dashboard latency giúp trả lời ba câu hỏi: request nào đang chậm, độ trễ tăng ở lớp nào và mức ảnh hưởng có đủ lớn để cần cảnh báo hay không. Một dashboard tốt trình bày latency theo thời gian, phân vị và nhóm operation ổn định, đồng thời cho phép chuyển từ số liệu tổng hợp sang traces/logs để điều tra request đại diện.

Latency không nên được biểu diễn chỉ bằng một giá trị trung bình. Mean có thể che khuất một nhóm request rất chậm; p95/p99 cho thấy trải nghiệm ở phần đuôi phân phối. Tuy vậy, percentile chỉ có ý nghĩa khi histogram được cấu hình đúng, sample đủ lớn và các series được tổng hợp theo cùng dimension. Dashboard cần đi cùng error rate, throughput và saturation để giải thích latency.

Trong **SPRING_BOOT_OBSERVABILITY**, Micrometer metrics cung cấp measurements từ Spring Boot HTTP server/client, database pool và custom observations; tracing cung cấp chi tiết từng request/operation. Bài này thiết kế dashboard latency từ service overview đến endpoint/dependency, giải thích histogram và percentiles, đưa ví dụ PromQL, alert windows, exemplars và cách kiểm chứng dashboard.

## 1. Latency là gì và nên đo ở đâu?

Latency là thời gian một operation cần để hoàn tất. Trong ứng dụng web, cần xác định rõ boundary đo:

- **HTTP server latency:** từ khi server nhận request tới khi response hoàn tất ở instrumentation boundary.
- **HTTP client latency:** thời gian gọi một downstream service.
- **Database latency:** thời gian thao tác JDBC/transaction hoặc query span theo instrumentation.
- **Messaging latency:** thời gian publish hoặc consumer processing; queue wait time là một đại lượng riêng.
- **Business operation latency:** thời gian hoàn thành một bước nghiệp vụ được instrument bằng Observation.

Không cộng trực tiếp các latency này nếu chúng có boundary chồng lấp. Ví dụ HTTP server duration đã bao gồm thời gian chờ database và HTTP client; cộng server duration với các dependency durations sẽ đếm trùng.

```text
Client
  |
  v
HTTP server observation -------------------- total request latency
  |
  +--> application processing
  |
  +--> database observation ---------------- DB duration
  |
  +--> HTTP client observation ------------- downstream duration
  |
  +--> messaging publish observation ------- send duration
```

Dashboard tổng quan thường bắt đầu bằng server latency. Dashboard drill-down dùng client/database/business operation latency để tìm lớp gây chậm. Trace cho biết các span nằm trong một request cụ thể và quan hệ giữa chúng.

## 2. Mean, median và percentile

| Thống kê | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| Mean (average) | Tổng duration chia số observations | Theo dõi xu hướng tổng quát, cần đọc cùng percentiles |
| p50 | 50% observations có duration không vượt quá giá trị này | Đại diện trải nghiệm ở giữa phân phối |
| p90 | 90% observations không vượt quá giá trị này | Quan sát nhóm request chậm hơn phần lớn traffic |
| p95 | 95% observations không vượt quá giá trị này | Theo dõi tail latency phổ biến |
| p99 | 99% observations không vượt quá giá trị này | Theo dõi tail latency nghiêm trọng |
| Max | Observation chậm nhất trong cửa sổ/series | Tìm outlier, nhạy với một sample đơn lẻ |

Ví dụ p95 = 800 ms nghĩa là khoảng 95% observations trong phạm vi tính toán có duration không quá 800 ms; khoảng 5% còn lại chậm hơn. Nó không có nghĩa mọi request đều mất 800 ms.

Percentile được tính trên phân phối trong một cửa sổ và tập series cụ thể. Không lấy p95 của từng instance rồi average để ra p95 toàn service; percentile không có tính cộng gộp như sum/count. Với Prometheus histogram, tổng hợp bucket counts trước rồi mới tính quantile.

## 3. Histogram và cấu hình distribution

Để tính percentile có thể tổng hợp giữa instances, cần histogram buckets được export. Micrometer timer có thể publish count, total time và histogram buckets tùy registry/configuration.

Ví dụ cấu hình distribution cho HTTP server requests:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,500ms,1s,2s
```

Property và meter name cần kiểm tra theo Spring Boot/Micrometer version. SLO boundaries là các bucket hữu ích cho mục tiêu latency; histogram configuration làm tăng số time series, do đó cần kiểm soát dimensions và số lượng buckets.

Có thể bật histogram cho custom timer theo convention/configuration tương ứng. Không bật histogram cho mọi meter theo wildcard nếu chưa đánh giá cardinality, storage và scrape volume.

### Histogram và summary

| Kiểu | Đặc điểm | Khả năng tổng hợp |
| --- | --- | --- |
| Histogram | Export bucket counts cùng count/sum | Có thể gộp buckets giữa instances rồi tính quantile |
| Client-side summary/percentile | Tính quantile tại process và export kết quả | Không thể gộp percentile thành percentile chính xác toàn service |

Nếu cần service-wide p95/p99 trên nhiều replica, histogram thường phù hợp hơn. Kiểm tra registry đang dùng có hỗ trợ histogram và exporter chuyển đổi metric ra sao.

## 4. Dashboard overview: RED method

RED là cách tổ chức dashboard cho request-driven services:

- **Rate:** số requests mỗi giây.
- **Errors:** tỷ lệ request thất bại.
- **Duration:** thời gian xử lý request.

| Panel | Nội dung | Câu hỏi |
| --- | --- | --- |
| Request rate | Requests/second | Traffic có thay đổi không? |
| Error rate | 5xx hoặc outcome error / tổng requests | Có nhiều request thất bại không? |
| Latency p50/p95/p99 | Server request duration | Người dùng đang chờ bao lâu? |
| Requests by route | Rate theo route template | Endpoint nào nhận nhiều traffic? |
| Latency by route | p95/p99 theo route template | Route nào đóng góp tail latency? |

Không gộp tất cả status codes thành error nếu mục tiêu cần phân biệt client errors và server errors. Một số hệ thống coi 4xx là lỗi nghiệp vụ/client, còn SLO availability chỉ tính 5xx hoặc outcome theo contract. Định nghĩa rõ error classification trước khi viết panel.

## 5. Ví dụ PromQL cho latency

Prometheus thường chuyển timer histogram thành series dạng _bucket, _sum, _count. Tên metric thực tế có thể được chuẩn hóa từ Micrometer meter name, ví dụ http_server_requests_seconds_bucket; hãy kiểm tra endpoint exposition trước khi dùng query.

### Request rate

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

### Mean latency

```promql
sum(rate(http_server_requests_seconds_sum[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

### Service-wide p95

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

### Service-wide p99

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

### p95 theo route

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Các query là mẫu cho Prometheus classic histograms. Label thực tế có thể là uri, method, status, outcome, exception hoặc tên khác theo Micrometer version/convention. Giữ route template thay vì raw path có path variables. Nếu histogram chưa được bật/export, query quantile không thể trả kết quả có ý nghĩa.

## 6. Chọn dimensions và kiểm soát cardinality

| Dimension | Dùng? | Ghi chú |
| --- | --- | --- |
| Service name | Có | Nhận diện workload |
| Instance/pod | Có chọn lọc | Hữu ích để tìm một replica bất thường |
| HTTP method | Có | Tập giá trị nhỏ |
| Route template | Có | Ví dụ /orders/{id}, không dùng raw URL |
| Status/outcome | Có | Tập giá trị hữu hạn |
| Dependency name | Có | Tên service/database ổn định |
| Tenant ID/user ID | Không | Cardinality cao và có thể là dữ liệu cá nhân |
| Request ID/Trace ID | Không | Gần như mỗi request một giá trị |
| Query string | Không | Dữ liệu động và có thể nhạy cảm |

Nếu dashboard cần xem latency theo tenant, dùng analytics/log query được kiểm soát hoặc trace search theo policy, không thêm tenant ID vào metric labels mặc định.

## 7. Drill-down từ service tới endpoint và dependency

Một dashboard latency nên tổ chức từ tổng quan đến chi tiết:

1. **Service overview:** rate, error rate, p50/p95/p99 và saturation.
2. **Route view:** latency và error rate theo route template/method.
3. **Dependency view:** HTTP client, datasource pool, database operation và messaging.
4. **Instance view:** so sánh replicas để phát hiện một pod lệch chuẩn.
5. **Trace view:** mở trace đại diện từ exemplar hoặc truy vấn trace backend.

Không cần đặt mọi metric lên một dashboard duy nhất. Dùng dashboard links/variables để chuyển từ service overview sang route/dependency panels với cùng service và time range.

### Liên kết latency với saturation

Latency tăng có thể do CPU, thread pool, connection pool, queue hoặc downstream saturation. Đọc latency cùng các tín hiệu:

| Tín hiệu | Metric concept | Cách diễn giải |
| --- | --- | --- |
| CPU pressure | Process/system CPU | CPU cao cùng latency tăng có thể chỉ ra compute saturation |
| JVM pauses | GC pause duration/count | Pause dài có thể tạo latency spikes |
| Thread pool | Active threads, queue/rejected tasks | Queue wait hoặc pool cạn |
| HTTP client pool | Active/pending connections, acquire time | Downstream connection acquisition chậm |
| Datasource pool | Active/idle/max/pending, acquire time | JDBC requests chờ connection |
| Messaging | Queue depth, oldest age, consumer rate | Async workflow bị backlog |

Latency panel chỉ cho biết symptom; saturation panels và traces giúp xác định nguyên nhân.

## 8. Dùng traces để giải thích tail latency

Khi p99 tăng, mở một số traces chậm trong cùng khoảng thời gian. So sánh server span duration, database spans và số lần gọi database, HTTP client spans/retry/timeout, lock/wait hoặc custom business spans, async boundaries và context propagation.

Một trace đơn lẻ là ví dụ, không đại diện toàn bộ phân phối. Chọn nhiều traces chậm và một trace bình thường để so sánh. Nếu backend hỗ trợ exemplars, histogram bucket có thể liên kết sample metric với Trace ID mà không cần thêm Trace ID thành label.

Exemplar availability phụ thuộc registry, exporter, backend và scrape configuration. Không phải mọi Prometheus deployment tự động hiển thị trace links; kiểm tra integration thực tế.

## 9. Chọn time window và tránh dashboard gây hiểu nhầm

Time window ảnh hưởng độ ổn định của percentile:

- Window quá ngắn: ít observations, p99 dao động mạnh hoặc không có đủ buckets.
- Window quá dài: che mất spike ngắn và phản ứng chậm với sự cố mới.
- Traffic thấp: p99 có thể không ổn định vì sample count ít.
- Traffic thay đổi theo giờ: cần so sánh cùng khung thời gian hoặc baseline phù hợp.

| Cửa sổ | Dùng để |
| --- | --- |
| 1–5 phút | Điều tra sự cố đang diễn ra |
| 15–30 phút | Quan sát xu hướng gần và sự phục hồi |
| 1–6 giờ | Phân tích thay đổi tải trong ngày |
| 7 ngày | Baseline theo ngày/chu kỳ traffic |

Đây là gợi ý, không phải ngưỡng cố định. Chọn range theo traffic volume, scrape interval, histogram và mục tiêu SLO.

Không so sánh p99 của hai service có traffic volume khác nhau mà bỏ qua sample count. Hiển thị request count/rate cạnh percentile để người xem biết dữ liệu có đủ lớn không.

## 10. Alert dựa trên latency và SLO

Dashboard giúp người vận hành hiểu tình trạng; alert cần kích hoạt khi trải nghiệm vượt ngưỡng trong thời gian đủ dài. Đặt ngưỡng dựa trên SLO/contract của service, không sao chép một con số chung.

Ví dụ policy:

- p95 vượt latency objective liên tục trong một cửa sổ.
- Tỷ lệ requests vượt một latency boundary tăng.
- Error rate và latency cùng tăng.
- Latency cao chỉ trên route quan trọng.
- Tail latency tăng kèm saturation của datasource/HTTP client pool.

Với SLO latency dạng “tỷ lệ request hoàn tất dưới T”, histogram có thể tính tỷ lệ observations nằm dưới bucket T. Đây thường là cơ sở tốt hơn alert trên p99 đơn lẻ ở traffic thấp.

### Multi-window alert

Alert nhiều cửa sổ giúp tránh phản ứng với spike ngắn: cửa sổ ngắn phát hiện mức vi phạm nghiêm trọng hiện tại; cửa sổ dài xác nhận vi phạm có kéo dài và ảnh hưởng đáng kể.

Với availability/error-budget SLO, multi-window burn-rate alert có thể phù hợp. Với latency SLO, định nghĩa good/bad events theo latency boundary rồi dùng tỷ lệ bad events; không mặc định áp dụng công thức availability nếu SLO latency được định nghĩa khác.

## 11. Ví dụ alert theo latency bucket

Giả sử service có objective: ít nhất 99% request hoàn tất trong 500 ms. Với classic histogram có bucket le="0.5", có thể tính tỷ lệ request vượt 500 ms:

```promql
1 -
(
  sum(rate(http_server_requests_seconds_bucket{le="0.5"}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
)
```

Kết quả là tỷ lệ request chậm hơn 500 ms trong cửa sổ 5 phút (với lưu ý về bucket và metric labels). Có thể alert khi tỷ lệ bad events vượt error budget allowance trong thời gian đủ dài và sample count đạt mức tối thiểu.

Không đặt threshold chỉ dựa vào ví dụ 1%. Chuyển SLO thành alert threshold theo mức độ vi phạm, traffic và thời gian ảnh hưởng mà tổ chức chấp nhận. Thêm for duration và điều kiện minimum traffic để tránh alert khi chỉ có một vài request.

## 12. Dashboard latency cho các lớp khác nhau

| Dashboard | Panel latency |
| --- | --- |
| HTTP server | p50/p95/p99 theo route, method và status/outcome |
| HTTP client | p95 theo dependency/remote service, timeout và retry |
| Database | JDBC acquire/usage time, query span duration, transaction duration |
| Messaging | Producer send duration, consumer processing duration, queue age |
| Business operations | Observation timer theo operation name và outcome |
| JVM/runtime | GC pause, thread scheduling và process saturation để đối chiếu |

Không dùng datasource connection usage time thay cho query duration; usage có thể bao gồm toàn bộ khoảng thời gian connection được giữ. Không dùng consumer processing duration thay cho queue wait age; message có thể chờ lâu trước khi được consumer xử lý.

## 13. Kiểm chứng dashboard trước khi dùng production

Dashboard cần được kiểm tra như một sản phẩm vận hành:

1. Xác nhận metric names, units và labels từ /actuator/prometheus hoặc registry thực tế.
2. Kiểm tra histogram buckets được export và có bucket phù hợp latency objective.
3. Tạo traffic test có latency bình thường và latency chậm có kiểm soát.
4. So sánh count/sum/bucket với số observations đã tạo.
5. Xác minh p95/p99 được tính sau khi aggregate histogram buckets, không average quantiles giữa replicas.
6. Kiểm tra route template không tạo series theo path variable.
7. Kiểm tra dashboard hiển thị sample count/rate bên cạnh percentile.
8. Xác minh trace exemplar/link hoạt động nếu được cấu hình.
9. Test alert với dữ liệu mô phỏng vượt và không vượt objective.
10. Kiểm tra dashboard variables/time range không vô tình loại mất một service hoặc instance.

### Ma trận test dashboard

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có traffic | Percentile hiển thị no data/empty đúng nghĩa, không báo 0 ms giả |
| Traffic bình thường | Rate, count và latency hợp lý |
| Một route chậm | Route panel phản ánh p95/p99 tăng |
| Một instance chậm | Instance breakdown chỉ ra replica lệch chuẩn |
| Database chậm | Dependency panel và traces cho thấy DB contribution |
| Histogram chưa bật | Dashboard cảnh báo/hiển thị thiếu dữ liệu percentile rõ ràng |
| Traffic thấp | Percentile được đọc cùng sample count |
| Route path chứa ID | Series vẫn dùng route template |
| SLO latency vi phạm | Alert kích hoạt theo window/policy |
| Recovery | Alert resolve và latency trở lại baseline |

## 14. Bài tập tình huống

Một API Spring Boot có 20 replica. Dashboard cho thấy mean latency 120 ms, p50 là 90 ms, p95 là 700 ms và p99 là 2,4 giây. Request rate tăng 30% trong giờ cao điểm. Datasource active connections thường xuyên gần max, pending threads tăng; HTTP client latency tới pricing-service vẫn ổn định.

**Câu hỏi:**

1. Vì sao mean 120 ms không đủ để kết luận API đáp ứng tốt?
2. Những dashboard panels nào giúp xác định database pool là nghi phạm?
3. Vì sao không average p95 của 20 replicas để tính p95 service?
4. Cần xem traces nào để xác nhận database contribution?
5. Nếu objective là 99% request dưới 500 ms, nên theo dõi bad-event ratio nào?

**Gợi ý phân tích:**

- p95/p99 cho thấy tail latency đáng kể dù phần lớn request nhanh; mean che khuất nhóm request chậm.
- Xem datasource active/idle/max/pending, acquire duration, usage duration, DB query spans, lock waits và HTTP server p95 theo route.
- Percentile không cộng gộp tuyến tính; aggregate histogram buckets trước khi tính service-wide quantile.
- Mở nhiều traces chậm và trace bình thường trong cùng window; so sánh DB spans, transaction duration và các dependency spans.
- Dùng histogram bucket 500 ms để tính tỷ lệ request vượt boundary, kèm sample count và multi-window policy.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Latency boundaries | Phân biệt server, client, DB, messaging và business duration |
| Percentiles | Đọc mean, p50, p95, p99 và sample count |
| Histogram | Cấu hình bucket phù hợp và hiểu cardinality |
| RED dashboard | Kết hợp rate, errors và duration |
| PromQL | Aggregate histogram buckets trước quantile |
| Dimensions | Dùng route template/service/dependency ổn định |
| Drill-down | Chuyển overview → route → dependency → trace |
| Exemplars | Liên kết metric sample với trace nếu backend hỗ trợ |
| Alert/SLO | Alert theo latency objective và time window |
| Validation | Kiểm tra dữ liệu, query, variables và alert behavior |

**Ghi nhớ:** Dashboard latency cần thể hiện phân phối, không chỉ mean. Dùng p50/p95/p99 cùng request count/rate, error rate và saturation; bật histogram với bucket phù hợp SLO và aggregate buckets trước khi tính quantile toàn service. Chọn dimensions có cardinality thấp như service, method, route template và dependency; tránh request/user/trace IDs làm metric labels. Drill-down từ HTTP server sang database/client/messaging rồi mở traces đại diện. Alert theo latency objective và cửa sổ đủ ổn định, đồng thời kiểm chứng dashboard bằng traffic test trước khi dựa vào nó trong production.
