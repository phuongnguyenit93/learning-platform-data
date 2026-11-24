# Viết dashboard latency và error

## Bối cảnh và mục tiêu

Một API có thể vẫn trả về HTTP 200 nhưng phản hồi chậm đến mức người dùng bỏ cuộc. Một API khác có độ trễ thấp nhưng thường xuyên trả về HTTP 500. Nếu dashboard chỉ hiển thị CPU, memory hoặc tổng số request, đội vận hành sẽ khó nhận ra hai vấn đề này và càng khó xác định endpoint nào đang gây ảnh hưởng.

Trong bài thực hành này, bạn xây dựng dashboard theo phương pháp RED (Rate, Errors, Duration) từ các metric HTTP do Spring Boot Actuator và Micrometer cung cấp, sau đó hiển thị chúng trên Grafana bằng dữ liệu Prometheus:

- **Rate**: số request mỗi giây, tổng thể và theo route.
- **Errors**: tốc độ request lỗi và tỷ lệ HTTP 5xx. Theo dõi HTTP 4xx riêng để phân biệt lỗi đầu vào của client với lỗi xử lý phía server.
- **Duration**: độ trễ p50, p95 và p99. Các percentile giúp thấy nhóm request chậm mà giá trị trung bình thường che khuất.

Khi hoàn thành, dashboard phải giúp trả lời được: lưu lượng hiện tại là bao nhiêu, người dùng đang chờ bao lâu, lỗi tập trung ở endpoint nào và các chỉ số thay đổi vào thời điểm nào.

## 1. Luồng dữ liệu và điều kiện chuẩn bị

Luồng quan sát trong bài thực hành:

~~~mermaid
flowchart LR
    A[Client gửi HTTP request] --> B[Spring Boot application]
    B --> C[Micrometer Observation và Timer]
    C --> D[/actuator/prometheus]
    D --> E[Prometheus scrape metrics]
    E --> F[Grafana dashboard]
~~~

Ứng dụng cần có Actuator và Prometheus registry. Với Gradle, khai báo các dependency sau; phiên bản được quản lý bởi Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Nếu dự án dùng Maven, thêm spring-boot-starter-actuator và micrometer-registry-prometheus vào dependencies, đồng thời để Spring Boot parent hoặc BOM quản lý phiên bản.

Cấu hình endpoint Prometheus và histogram cho HTTP server trong application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      slo:
        "http.server.requests": 100ms,300ms,1s
~~~

http.server.requests là tên metric Micrometer trước khi được Prometheus chuẩn hóa. percentiles-histogram yêu cầu Micrometer xuất histogram để Prometheus có thể tính percentile trên dữ liệu đã scrape. Các mốc SLO bổ sung bucket tại 100 ms, 300 ms và 1 giây; chúng hữu ích khi dashboard cần đo tỷ lệ request nằm dưới một ngưỡng cụ thể. Hãy chọn ngưỡng theo mục tiêu dịch vụ thực tế, không coi các giá trị trong ví dụ là tiêu chuẩn chung.

Chỉ expose endpoint cần thiết. Trong môi trường triển khai thật, bảo vệ /actuator/prometheus bằng mạng nội bộ, authentication hoặc cơ chế kiểm soát truy cập phù hợp; không mở endpoint metrics công khai cho mọi client.

Sau khi khởi động ứng dụng, gọi một vài API rồi kiểm tra:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Tìm các series có tên bắt đầu bằng http_server_requests_seconds. Tùy phiên bản Spring Boot, registry và cấu hình tag, tên hoặc tập tag có thể khác đôi chút. Hãy quan sát metric thực tế trước khi viết truy vấn; các truy vấn tiếp theo giả định metric timer HTTP mặc định đã được xuất với tên Prometheus nêu trên.

Ví dụ cấu hình Prometheus scrape ứng dụng đang chạy trong cùng mạng Docker với tên service app:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: spring-boot-app
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["app:8080"]
~~~

Nếu chạy Prometheus trực tiếp trên máy phát triển, thay app:8080 bằng địa chỉ mà Prometheus có thể truy cập, chẳng hạn localhost:8080. Trong giao diện Prometheus, kiểm tra trạng thái target là UP và thử truy vấn http_server_requests_seconds_count trước khi chuyển sang Grafana.

## 2. Hiểu metric trước khi viết PromQL

Micrometer ghi nhận HTTP server request bằng timer. Khi xuất sang Prometheus, timer thường tạo ra các series sau:

| Series | Ý nghĩa | Cách sử dụng |
|---|---|---|
| http_server_requests_seconds_count | Tổng số request đã ghi nhận | Tính request rate và mẫu số của error ratio |
| http_server_requests_seconds_sum | Tổng thời gian xử lý cộng dồn, tính bằng giây | Tính thời gian trung bình trong một khoảng |
| http_server_requests_seconds_max | Giá trị lớn nhất theo cửa sổ thời gian của timer | Tham khảo để phát hiện outlier; không thay thế p95/p99 |
| http_server_requests_seconds_bucket | Số request có thời gian nhỏ hơn hoặc bằng giới hạn le của bucket | Tính histogram quantile và tỷ lệ đáp ứng ngưỡng SLO |

Các tag HTTP thường gặp gồm method, status, outcome, uri và exception. uri nên là route template do framework cung cấp, ví dụ /api/orders/{id}, để nhiều request đến các ID khác nhau vẫn thuộc cùng một chuỗi metric. Hãy kiểm tra tag thực tế tại /actuator/prometheus, đặc biệt khi ứng dụng có custom observation convention hoặc filter.

Đơn vị của timer trong tên Prometheus là giây. Vì vậy, p95 bằng 0.3 có nghĩa là 300 ms. Khi cấu hình panel Grafana, chọn unit seconds (s) hoặc chuyển đổi nhất quán sang milliseconds; đừng gắn nhãn milliseconds cho một giá trị vẫn đang tính bằng giây.

Histogram bucket là dữ liệu tích lũy: bucket le="0.3" đếm request hoàn thành trong tối đa 0,3 giây, còn bucket có giới hạn lớn hơn bao gồm cả những request đã nằm trong bucket nhỏ hơn. Khi tính quantile, phải giữ lại nhãn le trong phép tổng hợp để histogram_quantile dựng lại phân phối. Không lấy trung bình các p95 của từng instance vì phép tính đó không tạo ra p95 toàn hệ thống.

## 3. Viết các truy vấn PromQL

Các ví dụ dùng label job="$job", trong đó $job là biến dashboard Grafana. Nếu chưa tạo biến này, thay matcher bằng tên job thật hoặc bỏ matcher job khi chỉ có một ứng dụng. Bộ lọc uri!~"/actuator.*" loại các route Actuator khỏi lưu lượng nghiệp vụ; điều chỉnh bộ lọc nếu ứng dụng dùng đường dẫn quản trị khác.

### 3.1. Request rate

Tổng request mỗi giây trong cửa sổ 5 phút:

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])
)
~~~

Để so sánh lưu lượng giữa các route và HTTP method:

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])
)
~~~

rate() tính tốc độ tăng trung bình mỗi giây từ counter trong cửa sổ được chọn. Cửa sổ 5 phút làm đường biểu diễn bớt nhiễu so với việc chỉ nhìn một scrape. Nếu cần điều tra một đợt tăng lưu lượng rất ngắn, có thể thu hẹp cửa sổ, nhưng nên giữ đủ mẫu scrape để kết quả ổn định.

### 3.2. Độ trễ p95 và p99

p95 tổng thể của ứng dụng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="$job",
      uri!~"/actuator.*"
    }[5m])
  )
)
~~~

p95 theo route:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="$job",
      uri!~"/actuator.*"
    }[5m])
  )
)
~~~

Đổi 0.95 thành 0.99 để tính p99. Có thể thêm method vào phần sum by (le, uri, method) nếu cần phân biệt GET và POST. Khi gom nhiều instance, phải cộng các bucket tương ứng trước rồi mới gọi histogram_quantile; cách này giữ đúng phân phối tổng hợp theo các bucket đã xuất.

Để đối chiếu, thời gian trung bình trong 5 phút được tính bằng tổng thời gian chia cho số request:

~~~promql
sum(rate(http_server_requests_seconds_sum{
  job="$job",
  uri!~"/actuator.*"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])),
  1e-9
)
~~~

Average hữu ích để theo dõi xu hướng chung nhưng có thể che khuất một nhóm request rất chậm. Dashboard vận hành nên ưu tiên p95/p99, đồng thời giữ average như chỉ số tham khảo nếu đội ngũ cần.

### 3.3. Tỷ lệ lỗi HTTP 5xx

Tính phần trăm request có status 5xx trên tổng request:

~~~promql
100 *
sum(rate(http_server_requests_seconds_count{
  job="$job",
  status=~"5..",
  uri!~"/actuator.*"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])),
  1e-9
)
~~~

Kết quả là phần trăm, vì tử số và mẫu số đều là request mỗi giây. clamp_min tránh phép chia cho 0 khi không có lưu lượng. Khi không có request, hãy xem thêm request rate để nhận biết trạng thái không có traffic; số phần trăm lúc đó không đủ để kết luận dịch vụ khỏe mạnh.

Tốc độ lỗi 5xx theo status giúp xác định nhóm lỗi nào tăng lên:

~~~promql
sum by (status) (
  rate(http_server_requests_seconds_count{
    job="$job",
    status=~"5..",
    uri!~"/actuator.*"
  }[5m])
)
~~~

Tỷ lệ 5xx theo route giúp khoanh vùng endpoint:

~~~promql
100 *
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="$job",
    status=~"5..",
    uri!~"/actuator.*"
  }[5m])
)
/
clamp_min(
  sum by (uri) (
    rate(http_server_requests_seconds_count{
      job="$job",
      uri!~"/actuator.*"
    }[5m])
  ),
  1e-9
)
~~~

HTTP 4xx nên được hiển thị riêng. Ví dụ truy vấn tốc độ 4xx:

~~~promql
sum by (status) (
  rate(http_server_requests_seconds_count{
    job="$job",
    status=~"4..",
    uri!~"/actuator.*"
  }[5m])
)
~~~

4xx có thể phản ánh request sai, quyền truy cập bị từ chối hoặc tài nguyên không tồn tại. Chúng vẫn có thể ảnh hưởng trải nghiệm người dùng, nhưng không nên gộp mặc định vào tỷ lệ lỗi 5xx khi đánh giá độ tin cậy của server.

### 3.4. Tỷ lệ request đáp ứng ngưỡng latency

Vì cấu hình đã thêm SLO bucket 300 ms, có thể đo tỷ lệ request hoàn thành trong tối đa 300 ms:

~~~promql
100 *
sum(rate(http_server_requests_seconds_bucket{
  job="$job",
  uri!~"/actuator.*",
  le="0.3"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])),
  1e-9
)
~~~

Truy vấn này chỉ hoạt động khi series bucket có đúng nhãn le="0.3". Nếu không thấy bucket đó, kiểm tra cấu hình SLO, cấu hình histogram và dữ liệu thực tế trước khi tạo panel. Có thể thay 300 ms bằng ngưỡng đã được thống nhất cho dịch vụ.

## 4. Thiết kế dashboard Grafana

Tạo một dashboard tên Spring Boot - HTTP Latency & Errors, chọn Prometheus làm data source. Tạo biến dashboard $job với loại Query và truy vấn label:

~~~text
label_values(http_server_requests_seconds_count, job)
~~~

Đặt biến ở chế độ single-select hoặc multi-select tùy số service cần so sánh. Khi dùng multi-select, điều chỉnh matcher thành job=~"$job" để Prometheus nhận regex do Grafana tạo ra.

Đề xuất bố cục:

| Khu vực | Panel | Truy vấn | Cách hiển thị |
|---|---|---|---|
| Tổng quan | Request rate | Truy vấn tổng request rate ở mục 3.1 | Time series, unit req/s |
| Tổng quan | HTTP 5xx ratio | Truy vấn tỷ lệ 5xx ở mục 3.3 | Stat hoặc time series, unit percent (0-100) |
| Tổng quan | HTTP 5xx rate | Tử số của truy vấn tỷ lệ 5xx | Time series, unit req/s |
| Tổng quan | p95 latency | Truy vấn p95 tổng thể ở mục 3.2 | Time series hoặc Stat, unit seconds |
| Độ trễ | p95 theo route | Truy vấn p95 theo route | Time series, legend theo uri |
| Độ trễ | p99 tổng thể | Truy vấn p99 tổng thể | Time series, unit seconds |
| Lỗi | 5xx theo status | Truy vấn tốc độ 5xx theo status | Time series, legend theo status |
| Lỗi | 5xx ratio theo route | Truy vấn tỷ lệ 5xx theo route | Table hoặc time series |
| SLO | Request dưới 300 ms | Truy vấn SLO bucket ở mục 3.4 | Gauge hoặc Stat, unit percent (0-100) |

Đặt các Stat quan trọng ở hàng đầu để người trực có thể đọc trạng thái hiện tại ngay khi mở dashboard. Dùng time series bên dưới để thấy thời điểm chỉ số bắt đầu thay đổi. Với panel p95 theo route, giới hạn số route hiển thị hoặc dùng bảng sắp xếp để dashboard vẫn đọc được khi ứng dụng có nhiều endpoint.

Một vài thiết lập giúp dashboard dễ sử dụng:

- Chọn khoảng thời gian mặc định như 1 giờ; cho phép mở rộng lên 6 hoặc 24 giờ khi điều tra xu hướng.
- Dùng refresh 30 giây hoặc theo nhịp vận hành. Refresh nhanh hơn chu kỳ scrape không tạo thêm dữ liệu mới.
- Đặt unit nhất quán: req/s cho rate, seconds hoặc milliseconds cho latency, percent (0-100) cho tỷ lệ.
- Thêm threshold theo SLO của dịch vụ. Ví dụ p95 mục tiêu 300 ms hoặc error ratio mục tiêu 1% chỉ là giá trị minh họa; cần thay bằng cam kết đã thống nhất.
- Giữ bộ lọc job và route hiển thị rõ ràng để người xem biết panel đang đại diện cho service nào.
- Đặt mô tả cho panel, ghi rõ cửa sổ rate(...[5m]), định nghĩa 5xx và ngưỡng latency đang áp dụng.

## 5. Đọc dashboard để điều tra sự cố

Hãy đọc các tín hiệu cùng nhau thay vì kết luận từ một panel riêng lẻ.

**p95 tăng, 5xx không tăng:** request vẫn thành công nhưng chậm. Kiểm tra route có p95 cao, traffic có tăng đột biến không, sau đó đối chiếu trace để xem thời gian nằm ở database, HTTP client gọi dịch vụ phụ thuộc, lock hay xử lý trong ứng dụng. Nếu chỉ một route bị ảnh hưởng, bắt đầu từ route đó thay vì thay đổi cấu hình toàn service.

**5xx tăng trên một hoặc vài route:** lọc theo route và status để xác định phạm vi. Đối chiếu log theo thời điểm, exception và trace ID để tìm request cụ thể. Metric cho biết xu hướng và phạm vi; log cung cấp chi tiết sự kiện; trace cho thấy request đi qua các thành phần nào và mất thời gian ở đâu.

**4xx tăng nhưng 5xx ổn định:** kiểm tra thay đổi client, API contract, xác thực hoặc quyền truy cập. Một đợt 404 có thể là crawler hoặc client dùng endpoint cũ; một đợt 401/403 có thể liên quan cấu hình token hoặc policy. Đừng xử lý chúng như lỗi server nếu chưa có bằng chứng.

**Request rate giảm đột ngột:** xem Prometheus target có còn UP không, ứng dụng có restart hoặc mất kết nối không, và traffic đầu vào có thực sự giảm không. Nếu cả request rate lẫn metric khác biến mất, hãy kiểm tra pipeline scrape trước khi kết luận ứng dụng không nhận request.

Khi cần nối dashboard với distributed tracing, dùng thời điểm, route và trace ID từ log để mở trace tương ứng. Không thêm traceId, user ID, order ID hoặc URL chứa ID động làm label metric: mỗi giá trị mới tạo thêm time series, khiến cardinality và chi phí lưu trữ tăng nhanh. Hãy giữ metric ở mức tổng hợp, còn dữ liệu định danh request thuộc về log và trace. Nếu hệ thống đã cấu hình exemplars và backend hỗ trợ, có thể dùng liên kết exemplar để chuyển từ điểm dữ liệu trên histogram đến trace mẫu.

## 6. Thực hành và xác minh

Thực hiện bài lab theo thứ tự sau:

1. Thêm Actuator và Prometheus registry, bật endpoint prometheus, cấu hình histogram và các SLO bucket.
2. Khởi động ứng dụng, gửi request đến một số API và xác nhận http_server_requests_seconds_count tăng trong /actuator/prometheus.
3. Gửi request đến một endpoint thử nghiệm có phản hồi chậm và một endpoint thử nghiệm trả về HTTP 5xx. Dùng các endpoint đã có trong ứng dụng; không đưa cơ chế gây lỗi vào endpoint nghiệp vụ chỉ để phục vụ dashboard.
4. Cấu hình Prometheus scrape target và xác nhận target UP. Kiểm tra count, bucket và các label status, uri có dữ liệu.
5. Thêm Prometheus data source trong Grafana, tạo biến $job, sau đó tạo lần lượt panel request rate, p95, 5xx ratio và 5xx theo route.
6. Gửi thêm request thành công và request lỗi, chờ ít nhất vài chu kỳ scrape rồi kiểm tra các panel thay đổi đúng hướng.
7. So sánh một truy vấn trong Grafana với cùng truy vấn chạy trực tiếp trên Prometheus để phát hiện lỗi matcher, biến dashboard hoặc đơn vị hiển thị.

### Tiêu chí hoàn thành

- Dashboard có request rate, p95 latency, 5xx rate hoặc ratio, 5xx theo status và latency theo route.
- p95/p99 được tính từ histogram bucket; phép tổng hợp giữ nhãn le và cộng bucket của các instance trước khi tính quantile.
- 4xx được quan sát riêng với 5xx.
- Panel latency hiển thị đúng đơn vị giây hoặc milliseconds; panel ratio hiển thị phần trăm.
- Dashboard có bộ lọc service, khoảng thời gian và mô tả cửa sổ tính toán.
- Không có label chứa ID người dùng, ID tài nguyên, trace ID hoặc URL động gây cardinality cao.
- Khi tạo request lỗi thử nghiệm, dashboard phản ánh được route và status liên quan sau thời gian scrape; khi không có traffic, người đọc nhận ra điều đó từ panel request rate.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không có metric HTTP | Thiếu Prometheus registry, chưa có request hoặc metric name khác | Kiểm tra dependency, gọi API và tìm http_server_requests tại endpoint Actuator |
| Có _count nhưng không có _bucket | Histogram chưa bật hoặc cấu hình chưa được bind đúng | Kiểm tra management.metrics.distribution.percentiles-histogram và slo, sau đó xem lại output Prometheus |
| p95 không có dữ liệu | Truy vấn sai tên bucket, filter job/uri không khớp hoặc không có mẫu trong cửa sổ | Chạy truy vấn metric bucket thô, bỏ dần matcher và xác nhận scrape target |
| p95 tổng thể sai lệch khi có nhiều instance | Tính quantile riêng từng instance rồi lấy trung bình | Cộng bucket theo le trước khi gọi histogram_quantile |
| Error ratio bằng 0 dù có lỗi | Status label không khớp, metric custom không ghi nhận response hoặc filter đã loại route | Kiểm tra series count theo status và xác nhận status thực tế |
| Dashboard tạo quá nhiều series | Gắn ID động, query string hoặc giá trị tùy ý vào tag | Chuyển sang route template và chỉ giữ các tag có tập giá trị hữu hạn |
| Biểu đồ latency lệch 1.000 lần | Nhầm giây với milliseconds | Kiểm tra đơn vị của metric và unit trong Grafana; Prometheus timer ở ví dụ này dùng giây |

Nếu ứng dụng dùng custom observation convention, gateway hoặc framework khác, tag và metric có thể thay đổi. Khi đó, lấy series thật từ /actuator/prometheus làm căn cứ, rồi cập nhật matcher và truy vấn theo đúng schema đang được xuất.

## 8. Bài tập mở rộng

1. Thêm panel p99 theo route và xác định route có p99 cao nhất trong một khoảng thời gian có đủ traffic.
2. Thay ngưỡng 300 ms bằng SLO đã thống nhất của một API, sau đó hiển thị tỷ lệ request đáp ứng SLO và phần trăm không đáp ứng.
3. Tạo cảnh báo khi error ratio vượt ngưỡng trong một khoảng liên tục, đồng thời đặt điều kiện request rate tối thiểu để tránh cảnh báo nhiễu khi lưu lượng gần bằng không.
4. Chọn một thời điểm p95 tăng, tìm log có trace ID tương ứng và dùng distributed trace để xác định span chiếm nhiều thời gian nhất.

Kết quả cuối cùng của bài thực hành là một dashboard RED có thể dùng trong vận hành: thể hiện lưu lượng, độ trễ và lỗi theo cùng trục thời gian, cho phép lọc theo service/route, đồng thời cung cấp điểm bắt đầu rõ ràng để tiếp tục điều tra bằng log và distributed trace.

