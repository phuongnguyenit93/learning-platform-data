# Xác minh dữ liệu thực tế ở đích trước khi dùng dashboard hoặc cảnh báo

Một meter đã được đăng ký trong ứng dụng chưa có nghĩa là hệ thống giám sát đã nhận được dữ liệu đúng. Dữ liệu có thể bị mất ở nhiều chặng: registry không xuất meter, endpoint chưa được mở, Prometheus không scrape được, OTLP exporter gửi sai endpoint, Collector loại bỏ hoặc chuyển đổi thuộc tính, backend từ chối payload, hoặc tên metric và label ở đích khác với điều dashboard đang truy vấn.

Vì vậy, trước khi xây dashboard hoặc alert, hãy xác minh dữ liệu ở chính đích nhận. Quy trình này cần trả lời bốn câu hỏi: metric có xuất hiện không, giá trị có thay đổi đúng không, tên và label có đúng không, và dữ liệu có đủ mới để dùng cho vận hành không. Bài học này đi qua các điểm kiểm tra từ ứng dụng đến backend, với ví dụ Prometheus và OTLP.

## Mục tiêu

Sau bài học, bạn có thể:

- Lần theo một metric qua các chặng từ code đến backend.
- Kiểm tra endpoint export hoặc trạng thái gửi OTLP.
- Xác minh target scrape, Collector pipeline và backend đã nhận dữ liệu.
- Đối chiếu tên metric, đơn vị, loại dữ liệu và label thực tế.
- Kiểm tra sample có mới, có tăng và có đúng phạm vi thời gian.
- Phát hiện thiếu metric, sai tag, trùng series, cardinality cao và dữ liệu stale.
- Chỉ tạo dashboard hoặc alert sau khi có bằng chứng dữ liệu ở đích.

## Đường đi của metrics và điểm cần xác minh

Micrometer cung cấp API instrumentation và registry. Registry chuyển meter sang định dạng hoặc giao thức mà hệ thống nhận hỗ trợ. Với Prometheus, Prometheus thường chủ động scrape endpoint của ứng dụng. Với OTLP, ứng dụng gửi metrics đến OpenTelemetry Collector hoặc một endpoint tương thích; Collector có thể xử lý rồi chuyển tiếp đến backend.

~~~mermaid
flowchart LR
    A[Code và Meter] --> B[MeterRegistry]
    B --> C[Endpoint hoặc Exporter]
    C --> D[Scrape target hoặc OTLP Receiver]
    D --> E[Collector / Processor]
    E --> F[Backend lưu metrics]
    F --> G[Query]
    G --> H[Dashboard và Alert]
~~~

Mỗi chặng cần một phép xác minh tương ứng:

| Chặng | Điều cần xác minh | Bằng chứng thường dùng |
|---|---|---|
| Instrumentation | Meter được tạo và cập nhật đúng | Unit test, kiểm tra registry trong ứng dụng |
| Registry/export | Meter được chuyển thành dữ liệu export | Endpoint Prometheus hoặc exporter diagnostics |
| Thu nhận | Prometheus scrape hoặc Collector nhận OTLP thành công | Target health, receiver/exporter logs, telemetry debug |
| Xử lý | Processor không loại bỏ hoặc làm sai dữ liệu | Collector logs, processor metrics, cấu hình pipeline |
| Backend | Metric và label đã được lưu | Query trực tiếp trong backend |
| Dashboard/alert | Truy vấn phản ánh đúng dữ liệu đã lưu | Query preview, alert evaluation và test rule |

Không bỏ qua bước xác minh ở backend. Endpoint ứng dụng có thể trả dữ liệu đúng trong khi Prometheus chưa scrape hoặc Collector chưa chuyển tiếp. Tương tự, Collector có thể nhận payload thành công nhưng backend vẫn từ chối hoặc ánh xạ metric theo tên khác.

## 1. Tạo một phép thử có thể dự đoán

Trước khi điều tra metric trong hệ thống đang có lưu lượng, chọn một meter có thể tạo ra thay đổi xác định. Ví dụ, ứng dụng có counter đếm đơn hàng được tạo:

~~~java
Counter ordersCreated = registry.counter(
    "checkout.orders.created",
    "channel", "web"
);

public void createOrder(CreateOrderCommand command) {
    orderService.create(command);
    ordersCreated.increment();
}
~~~

Ghi lại tên metric canonical và các tag dự kiến:

| Thuộc tính | Giá trị dự kiến |
|---|---|
| Tên trong Micrometer | checkout.orders.created |
| Tag | channel=web |
| Loại meter | Counter |
| Thay đổi thử nghiệm | Tăng 3 lần |
| Kết quả mong đợi | Counter tăng thêm 3 |

Nếu có thể, dùng một môi trường kiểm thử hoặc một thao tác nghiệp vụ an toàn để phát sinh đúng ba sự kiện. Ghi lại thời điểm thực hiện và instance xử lý. Khi kiểm tra backend, có thể so sánh mức tăng trước và sau phép thử.

Với timer hoặc summary, cũng nên dùng một lượng sample xác định. Ví dụ ghi hai thời lượng 100 ms và 300 ms sẽ làm count tăng 2 và tổng thời gian tăng 400 ms. Đối với histogram, hãy kiểm tra cả count, sum và bucket.

Không dùng request ID hoặc user ID làm tag chỉ để tìm phép thử. Ghi correlation ID trong log nếu cần xác định request cụ thể; metrics cần giữ label có miền giá trị nhỏ và ổn định.

## 2. Xác minh dữ liệu ngay tại registry và endpoint ứng dụng

### Kiểm tra registry trong bộ nhớ

Với unit test, SimpleMeterRegistry giúp xác nhận instrumentation tạo đúng meter và cập nhật đúng giá trị:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = registry.counter(
    "checkout.orders.created",
    "channel", "web"
);

counter.increment(3);

assertEquals(3.0, counter.count());
assertEquals(
    3.0,
    registry.get("checkout.orders.created")
        .tag("channel", "web")
        .counter()
        .count()
);

registry.close();
~~~

Kiểm tra này chỉ chứng minh code đã ghi vào registry. Nó chưa chứng minh endpoint hoặc exporter đã gửi dữ liệu đi.

### Kiểm tra endpoint Prometheus

Với Spring Boot Actuator và Prometheus registry, cần có dependency phù hợp và endpoint Prometheus được expose. Cấu hình web exposure có thể dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Sau khi ứng dụng khởi động, gọi endpoint:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Tìm metric tương ứng. Ví dụ tên export có thể được chuyển từ tên canonical Micrometer sang quy ước Prometheus:

~~~text
# TYPE checkout_orders_created_total counter
checkout_orders_created_total{channel="web",application="checkout"} 42
~~~

Tên và tag trong ví dụ chỉ minh họa. Tên thực tế phụ thuộc naming convention, registry, common tags và phiên bản thư viện. Hãy đọc output thực tế thay vì suy luận rằng tên canonical trong Java sẽ xuất hiện nguyên dạng.

Khi endpoint trả 404, kiểm tra endpoint có được expose và đúng port/path không. Khi endpoint trả 401 hoặc 403, kiểm tra security rules và quyền truy cập. Khi endpoint trả 200 nhưng không có metric cần tìm, kiểm tra meter đã được đăng ký, filter có từ chối meter không và tên/tag thực tế là gì.

### Kiểm tra loại meter và đơn vị

Đối với Prometheus export, kiểm tra các dấu hiệu sau:

- Counter thường có hậu tố phù hợp như _total.
- Timer thường tạo các chuỗi count và sum với đơn vị thời gian trong tên; histogram có thể có thêm bucket.
- DistributionSummary có count, sum và bucket nếu histogram được bật.
- Gauge biểu diễn giá trị hiện tại và có thể tăng hoặc giảm.
- Label names và values phản ánh đúng các tag đã cấu hình.

Đừng chỉ kiểm tra metric có tồn tại. Một timer có thể xuất count và sum nhưng thiếu bucket vì histogram chưa bật. Dashboard p95 sẽ không thể tính từ dữ liệu chỉ có count và sum.

## 3. Xác minh Prometheus scrape target

Khi dùng Prometheus pull model, endpoint ứng dụng có dữ liệu chưa đủ. Prometheus phải scrape đúng địa chỉ và scrape thành công.

Ví dụ cấu hình scrape:

~~~yaml
scrape_configs:
  - job_name: checkout
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - checkout:8080
~~~

Mở trang Targets của Prometheus hoặc truy vấn:

~~~promql
up{job="checkout"}
~~~

Giá trị 1 cho biết lần scrape gần nhất của target thành công; giá trị 0 cho biết scrape thất bại. Kiểm tra thêm last scrape, scrape duration và scrape error trong trang Targets để xác định lỗi kết nối, timeout, HTTP status hoặc parse exposition format.

Một target khỏe không chứng minh mọi metric đều có mặt. Nó chỉ cho biết Prometheus scrape endpoint thành công. Vẫn cần truy vấn metric cụ thể:

~~~promql
checkout_orders_created_total{job="checkout"}
~~~

Nếu up bằng 1 nhưng metric không tồn tại, hãy so sánh endpoint output với query, kiểm tra relabeling, metric relabeling và filter ở phía ứng dụng. Metric có thể bị đổi tên hoặc loại bỏ trên đường đi.

### Kiểm tra sample có mới

Có thể dùng timestamp của sample để xem dữ liệu có được cập nhật gần đây:

~~~promql
time() - timestamp(checkout_orders_created_total{job="checkout"})
~~~

Kết quả biểu thị tuổi của sample theo giây tại thời điểm truy vấn. Giá trị lớn có thể do scrape không chạy, metric không được cập nhật, hoặc metric là gauge chỉ thay đổi khi trạng thái nguồn thay đổi. Với counter, sample vẫn được scrape định kỳ ngay cả khi giá trị không tăng; đừng nhầm giá trị không tăng với sample stale.

Prometheus có thể giữ sample cuối cùng trong một khoảng thời gian sau khi target biến mất hoặc series không còn được xuất. Vì vậy hãy kiểm tra cả target health và timestamp, không chỉ nhìn thấy một giá trị trong biểu đồ.

## 4. Xác minh OTLP exporter và Collector

Với OTLP, ứng dụng chủ động gửi metrics đến receiver. Endpoint HTTP thường có dạng:

~~~text
http://otel-collector:4318/v1/metrics
~~~

Nếu dùng OTLP/gRPC, ứng dụng gửi đến endpoint gRPC của Collector, thường dùng cổng 4317. Hãy xác nhận protocol, port, TLS và endpoint path khớp giữa exporter và receiver. Không dùng URL HTTP /v1/metrics cho một exporter đang cấu hình gRPC.

Ví dụ cấu hình OTLP trong Spring Boot:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        resource-attributes:
          service.name: checkout
          service.version: 1.4.0
          deployment.environment: staging
~~~

Tên property và khả năng cấu hình có thể khác theo phiên bản Spring Boot/Micrometer. Hãy đối chiếu dependency và metadata cấu hình của phiên bản dự án đang chạy.

### Kiểm tra Collector pipeline

Collector cần có receiver OTLP, processor và exporter tương ứng. Ví dụ pipeline tối giản dùng debug exporter để quan sát payload và Prometheus exporter để cung cấp endpoint cho Prometheus scrape:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  debug:
    verbosity: detailed
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, prometheus]
~~~

Cấu hình này minh họa đường nhận OTLP và hai đích export. Trong production, cần thêm processor giới hạn bộ nhớ, bảo mật endpoint, cấu hình TLS/authentication khi cần và exporter tới backend thật. Không mở receiver hoặc debug output công khai nếu payload có thể chứa dữ liệu nội bộ.

Kiểm tra log Collector để tìm các dấu hiệu:

- Receiver đã nhận request metrics.
- Batch processor đã flush dữ liệu.
- Exporter gửi thành công hoặc báo lỗi.
- Có telemetry bị từ chối, dropped hoặc retry.
- Backend trả lỗi xác thực, quota, schema hoặc giới hạn kích thước payload.

Collector có thể nhận dữ liệu thành công nhưng processor vẫn loại bỏ metric hoặc exporter không gửi được tới backend. Vì vậy hãy kiểm tra cả receiver, processor và exporter.

### Kiểm tra resource attributes

Resource attributes mô tả nguồn phát telemetry, thường gồm:

- service.name
- service.version
- deployment.environment
- service.namespace
- cloud.region hoặc các thuộc tính hạ tầng phù hợp

Các thuộc tính này giúp phân biệt service và deployment ở backend. Kiểm tra giá trị thực tế tại đích, không chỉ cấu hình trong application.yml. Nếu service.name bị thiếu hoặc khác nhau giữa các replica cùng một service, dashboard có thể chia dữ liệu thành nhiều nhóm ngoài ý muốn.

Resource attributes khác với metric attributes/tags. Resource mô tả nguồn phát; metric attributes mô tả chiều của một metric cụ thể. Đừng đưa request ID hoặc user ID vào resource chỉ để liên kết một request.

## 5. Đối chiếu tên, đơn vị và loại dữ liệu ở đích

Registry và backend có thể chuyển đổi tên metric, đơn vị hoặc kiểu dữ liệu. Một số ví dụ:

| Micrometer | Dữ liệu export có thể gặp | Điều cần xác minh |
|---|---|---|
| Counter orders.created | orders_created_total hoặc Sum monotonic qua OTLP | Counter có đúng tính tích lũy không |
| Timer request.duration | count/sum/bucket với đơn vị thời gian | Tên và đơn vị là seconds, milliseconds hay đơn vị khác |
| DistributionSummary payload.size | count/sum/bucket theo base unit | Giá trị sum có cùng đơn vị với ứng dụng không |
| Gauge queue.depth | Gauge data point | Giá trị có phản ánh trạng thái hiện tại không |
| FunctionTimer | Count và total time tích lũy | TimeUnit đầu vào và đơn vị export có đúng không |

Với OTLP, backend có thể hiển thị metric theo tên canonical, tên đã chuẩn hóa hoặc tên do hệ thống chuyển đổi. Với Prometheus, Micrometer thường áp dụng quy tắc tên Prometheus, gồm dấu gạch dưới và hậu tố type/unit. Hãy dùng tên ở backend làm căn cứ khi viết query.

### Kiểm tra histogram

Nếu cần p95/p99, kiểm tra histogram thực tế có bucket hay không. Với Prometheus classic histogram, thường thấy:

~~~text
http_server_requests_seconds_bucket{le="0.1",route="/orders"} 120
http_server_requests_seconds_bucket{le="0.3",route="/orders"} 180
http_server_requests_seconds_bucket{le="+Inf",route="/orders"} 200
http_server_requests_seconds_count{route="/orders"} 200
http_server_requests_seconds_sum{route="/orders"} 32.4
~~~

Bucket classic là bộ đếm tích lũy: bucket có ngưỡng lớn hơn hoặc bằng một ngưỡng nhỏ hơn sẽ chứa ít nhất số quan sát của bucket nhỏ. Bucket +Inf phải bằng count nếu histogram được xuất đầy đủ.

Nếu chỉ thấy _count và _sum mà không thấy bucket, dữ liệu hiện tại không đủ để tính histogram percentile bằng histogram_quantile. Kiểm tra publishPercentileHistogram hoặc SLO configuration, filter và registry mapping.

Với OTLP Histogram hoặc Exponential Histogram, cấu trúc bucket khác classic Prometheus histogram. Hãy xem data model và query function của backend; không áp dụng truy vấn PromQL classic vào một metric OTLP chưa được chuyển đổi sang dạng tương ứng.

## 6. Kiểm tra label và cardinality thực tế

Tên metric đúng nhưng label sai vẫn có thể làm dashboard trống hoặc tạo quá nhiều series. Kiểm tra:

- Tag key có bị đổi tên bởi MeterFilter hoặc naming convention không.
- Giá trị tag có được chuẩn hóa về đúng tập dự kiến không.
- Có tag nào bị thêm từ common tags hoặc resource attributes không.
- Có label động như request_id, user_id, order_id hoặc raw URL không.
- Các replica có dùng cùng tên và cùng quy ước label không.

Với Prometheus, có thể dùng truy vấn để xem các tổ hợp series:

~~~promql
count by (route, method, status) (
  http_server_requests_seconds_count
)
~~~

Để xem số series theo metric:

~~~promql
count(http_server_requests_seconds_count)
~~~

Số series cao bất thường có thể xuất phát từ tag có miền giá trị lớn, nhiều instance, histogram bucket hoặc nhiều phiên bản metric name cùng tồn tại. Hãy kiểm tra từng yếu tố thay vì chỉ giảm scrape interval hoặc xóa label trong dashboard.

Không dùng label_replace hoặc aggregation để che giấu cardinality ở dashboard. Cần xử lý nguồn tag ở instrumentation hoặc MeterFilter, rồi xác minh dữ liệu export mới.

## 7. Kiểm tra giá trị tăng đúng bằng phép thử có kiểm soát

Đối với counter, chụp giá trị trước, phát sinh số sự kiện đã biết, đợi scrape/export tiếp theo rồi đọc lại. Ví dụ nếu phát sinh thêm ba đơn hàng:

~~~promql
increase(checkout_orders_created_total{channel="web"}[5m])
~~~

Kết quả có thể không đúng tuyệt đối bằng ba nếu cửa sổ truy vấn chứa các sự kiện khác hoặc scrape boundary không trùng thời điểm thử. Trong môi trường thử nghiệm yên tĩnh, hãy ghi lại giá trị trước/sau và so sánh mức tăng.

Với timer, kiểm tra count và sum tăng theo số lần đo cùng tổng thời lượng. Với gauge, thay đổi trạng thái nguồn rồi xác minh sample phản ánh giá trị mới ở lần scrape/export tiếp theo. Với function-tracking meter, bảo đảm hàm nguồn là tích lũy và không giảm.

Đừng kỳ vọng một gauge chỉ thay đổi khi có event sẽ tạo sample mới ngay khi giá trị không đổi. Hãy phân biệt sample được scrape định kỳ với giá trị đo thay đổi.

## 8. Phân biệt dữ liệu thiếu, dữ liệu bằng 0 và dữ liệu stale

Ba trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| Không có series | Metric chưa được tạo, bị lọc, không export hoặc backend không nhận | Kiểm tra endpoint, target, Collector và query |
| Series có giá trị 0 | Metric tồn tại và hiện có giá trị bằng 0 | Xác minh meter đã đăng ký và semantics của meter |
| Series stale | Dữ liệu cuối cùng đã cũ hoặc nguồn không còn gửi | Kiểm tra timestamp, target health và exporter errors |

Counter bằng 0 có thể là hợp lệ khi chưa có sự kiện. Gauge bằng 0 có thể phản ánh queue rỗng. Không có series thường là một vấn đề khác và không nên tự động thay bằng 0 trong dashboard nếu điều đó che mất lỗi thu thập.

Một số query có thể dùng absent(metric_name) để phát hiện metric hoàn toàn không tồn tại:

~~~promql
absent(checkout_orders_created_total)
~~~

Đối với một target, kiểm tra up riêng. Đối với metric quan trọng, có thể dùng alert khi series không xuất hiện trong khoảng thời gian mong đợi, nhưng cần tính đến việc meter chỉ được tạo khi có event. Nếu metric không được tạo cho đến khi sự kiện đầu tiên xảy ra, alert absent ngay sau startup có thể báo sai.

## 9. Viết truy vấn dashboard sau khi xác minh

Khi metric đã có ở backend, xác định câu hỏi trước khi viết query. Ví dụ:

| Câu hỏi | Truy vấn minh họa |
|---|---|
| Tốc độ tạo đơn hàng | sum(rate(checkout_orders_created_total[5m])) |
| Tốc độ theo channel | sum by (channel) (rate(checkout_orders_created_total[5m])) |
| Số request đang quan sát theo route | sum by (route) (rate(http_server_requests_seconds_count[5m])) |
| Thời lượng trung bình | rate(http_server_requests_seconds_sum[5m]) / rate(http_server_requests_seconds_count[5m]) |
| p95 toàn service từ histogram | histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket[5m]))) |

Đây là truy vấn Prometheus minh họa. Tên metric và label phải thay bằng tên đã xác minh ở backend. Với OTLP, backend có thể dùng ngôn ngữ truy vấn hoặc tên khác; giữ nguyên logic tổng hợp nhưng điều chỉnh cú pháp theo hệ thống nhận.

Khi tạo panel, kiểm tra đơn vị hiển thị. Một metric thời gian được export bằng seconds nhưng panel gắn đơn vị milliseconds sẽ hiển thị sai 1.000 lần. Tương tự, tỷ lệ từ 0 đến 1 cần định dạng phần trăm đúng cách, tránh nhân 100 hai lần.

## 10. Xây alert từ dữ liệu đã xác minh

Alert cần kiểm tra cả điều kiện metric và độ tin cậy của nguồn dữ liệu. Ví dụ cảnh báo tỷ lệ lỗi HTTP 5xx trong năm phút:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
> 0.05
~~~

Biểu thức trên chỉ hợp lệ nếu metric thực tế có label status và count được export như ví dụ. Nếu tên label là status_class hoặc status_code, phải sửa truy vấn theo dữ liệu đã kiểm tra.

Trước khi bật alert:

1. Mở query trong backend và xác nhận có dữ liệu trong khoảng thời gian dài hơn cửa sổ alert.
2. Kiểm tra denominator khác 0 và xử lý trường hợp không có traffic.
3. Kiểm tra alert evaluation khi service không có series.
4. Chọn thời gian for phù hợp để tránh cảnh báo do dao động ngắn.
5. Phân biệt alert về ứng dụng với alert về pipeline thu thập metrics.
6. Kiểm tra labels và annotations để người trực vận hành hiểu service, environment và hành động tiếp theo.

Một alert về tỷ lệ lỗi không thể thay thế alert về scrape failure hoặc OTLP export failure. Nếu telemetry ngừng đến, query lỗi có thể không có dữ liệu để đánh giá. Cần có cảnh báo độc lập cho target down, Collector exporter failures hoặc backend ingestion errors.

## Checklist xác minh trước dashboard và alert

- [ ] Meter được đăng ký đúng tên và loại trong ứng dụng.
- [ ] Tag có miền giá trị hữu hạn, không chứa ID cá thể.
- [ ] Endpoint export trả dữ liệu hoặc exporter gửi thành công.
- [ ] Prometheus target đang UP hoặc OTLP receiver xác nhận đã nhận.
- [ ] Collector processor/exporter không drop hoặc reject dữ liệu.
- [ ] Backend có metric với tên và resource attributes dự kiến.
- [ ] Label keys/values khớp với truy vấn.
- [ ] Đơn vị và loại dữ liệu đúng.
- [ ] Count/sum/bucket hoặc gauge value thay đổi theo phép thử.
- [ ] Sample có độ mới phù hợp với scrape interval hoặc export step.
- [ ] Cardinality nằm trong ngân sách dự kiến.
- [ ] Query dashboard trả dữ liệu đúng và có đơn vị hiển thị chính xác.
- [ ] Alert xử lý đúng trường hợp no traffic, missing series và telemetry unavailable.
- [ ] Có alert độc lập cho lỗi pipeline thu thập.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Endpoint có metric nhưng dashboard trống | Prometheus chưa scrape, query dùng sai tên hoặc label | Kiểm tra Targets và query trực tiếp |
| Target UP nhưng metric không có | Meter chưa được tạo, filter từ chối hoặc metric bị relabel/drop | So sánh endpoint với dữ liệu backend |
| OTLP exporter báo gửi thành công nhưng backend không thấy | Collector processor/exporter hoặc backend mapping | Kiểm tra Collector pipeline và backend ingestion |
| Metric xuất hiện dưới tên khác | NamingConvention hoặc chuyển đổi của backend | Đọc endpoint/export payload thực tế |
| p95 không có dữ liệu | Chỉ có count/sum, chưa có histogram bucket | Kiểm tra histogram/SLO configuration |
| Giá trị sai 1.000 lần | Nhầm seconds và milliseconds | Xác minh base unit và panel unit |
| Dashboard có nhiều đường không mong muốn | Tag cardinality cao hoặc resource attributes không đồng nhất | Kiểm tra label set và nguồn tag |
| Dữ liệu đứng yên | Không có event, scrape/export dừng hoặc nguồn gauge không cập nhật | Kiểm tra timestamp, target và nguồn meter |
| Alert không kích hoạt khi metrics mất | Query không có series hoặc thiếu alert pipeline riêng | Thêm alert absent/target/export failure phù hợp |

## Ghi nhớ

- Meter được ghi trong ứng dụng chưa chứng minh backend đã nhận dữ liệu.
- Xác minh lần lượt instrumentation, registry/export, receiver/scrape, processor, exporter và backend.
- Dùng phép thử có thể dự đoán để đối chiếu count, sum, bucket hoặc gauge value.
- Đọc tên metric, label, resource attributes và đơn vị ở đích; không suy luận từ tên trong Java.
- Percentile tổng hợp cần histogram phù hợp; count và sum không đủ để tính p95.
- Phân biệt không có series, giá trị 0 và dữ liệu stale.
- Kiểm tra scrape/export freshness và lỗi pipeline riêng với lỗi ứng dụng.
- Chỉ xây dashboard và alert sau khi query trực tiếp ở backend trả dữ liệu đúng.
- Alert phải xử lý no traffic và telemetry unavailable, không chỉ điều kiện lỗi nghiệp vụ.

Một dashboard đáng tin cậy bắt đầu từ dữ liệu đã được xác minh ở nơi lưu trữ. Khi tên, tag, đơn vị, thời điểm và loại data point đều đúng, truy vấn mới có ý nghĩa; khi đó alert mới có cơ sở để hướng dẫn người vận hành hành động.

## Tài liệu tham khảo

- [Micrometer: Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html) — endpoint scrape, naming convention và cấu hình Prometheus.
- [Micrometer: OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html) — export OTLP, step, resource attributes và data point mapping.
- [Spring Boot Actuator: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — cấu hình registry và endpoint metrics trong Spring Boot.
- [Prometheus: Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) — truy vấn vector, series và timestamp.
- [OpenTelemetry Collector configuration](https://opentelemetry.io/docs/collector/configuration/) — receiver, processor, exporter và pipeline.

