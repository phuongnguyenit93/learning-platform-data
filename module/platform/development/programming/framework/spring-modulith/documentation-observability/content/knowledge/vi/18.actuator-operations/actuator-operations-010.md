# Giám sát lỗi endpoint và thời gian phản hồi

## Mục tiêu học tập

Trong học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, Spring Modulith giúp mô tả ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Bài này tập trung vào cách dùng **Spring Boot Actuator, Micrometer và hệ thống metrics** để phát hiện endpoint có tỷ lệ lỗi tăng, phản hồi chậm hoặc suy giảm theo thời gian.

Sau bài học, bạn có thể:

1. Giải thích vai trò của Actuator, Micrometer Observation và meter `http.server.requests`.
2. Đọc các tag `method`, `uri`, `status`, `outcome` và `error` để phân loại lỗi theo endpoint.
3. Dùng `/actuator/metrics` để chẩn đoán metric tại một instance và hiểu vì sao endpoint này không phải metrics backend.
4. Cấu hình Prometheus registry và `/actuator/prometheus` để thu thập metrics liên tục.
5. Viết truy vấn PromQL cho request rate, tỷ lệ lỗi 5xx, latency p95 và SLO bucket.
6. Phân biệt 4xx, 5xx, exception được xử lý và lỗi thực sự của server.
7. Hiểu histogram, percentile, SLO và các giới hạn khi chỉ dùng giá trị trung bình.
8. Đối chiếu HTTP metrics với trace và module entry spans của Spring Modulith để tìm module gây chậm.
9. Thiết kế dashboard, alert và quy trình điều tra mà không tạo tag cardinality cao.
10. Expose và bảo vệ Actuator endpoints đúng cách trong môi trường vận hành.

**Bối cảnh:** Module graph cho biết cấu trúc module; Actuator cung cấp thông tin quản trị; event metrics cho biết xu hướng publication; tracing cho thấy đường đi của một request qua các module. HTTP metrics trả lời câu hỏi **endpoint nào đang lỗi hoặc chậm trên diện rộng**, còn module spans giúp tìm **đoạn xử lý nào bên trong request gây ra vấn đề**.

> **Phạm vi phiên bản:** Ví dụ chính tham chiếu Spring Boot 4.2 và Spring Framework 7.1. Spring Boot 3.x có cùng khái niệm Micrometer và meter `http.server.requests`, nhưng cấu hình, dependency và một số semantic keys có thể khác theo release. Hãy dùng BOM và reference guide đúng phiên bản dự án.

---

## 1. Giám sát endpoint cần quan sát điều gì?

Một endpoint không chỉ cần trả về HTTP 200. Trong vận hành, ta cần biết:

- **Lưu lượng:** endpoint được gọi bao nhiêu lần trong một khoảng thời gian?
- **Tỷ lệ lỗi:** có bao nhiêu request trả về 5xx, bao nhiêu request bị từ chối bằng 4xx?
- **Thời gian phản hồi:** request mất bao lâu từ lúc server bắt đầu xử lý tới khi hoàn tất?
- **Phân vị độ trễ:** p50, p90, p95 hoặc p99 cho thấy phần lớn request và nhóm request chậm hoạt động thế nào?
- **Xu hướng:** chỉ số có thay đổi sau deployment, tăng traffic, thay đổi database hoặc thay đổi dependency không?
- **Phạm vi:** vấn đề xảy ra ở toàn service, một route, một HTTP method hay một nhóm instance?

Ví dụ service thương mại điện tử có các endpoint:

| Endpoint | Vai trò | Điều cần theo dõi |
| --- | --- | --- |
| `POST /api/orders` | Tạo đơn | 5xx, timeout, p95 và lưu lượng. |
| `GET /api/orders/{id}` | Xem đơn | p95, 404 và lưu lượng. |
| `POST /api/payments` | Khởi tạo thanh toán | 5xx, timeout và độ trễ phụ thuộc ngoài. |
| `GET /api/catalog` | Xem danh mục | Lưu lượng, p95 và cache behavior. |

Không nên chỉ nhìn một chỉ số. Request rate tăng có thể là tín hiệu tốt; tỷ lệ 404 tăng có thể do người dùng nhập sai ID hoặc do route bị thay đổi; p95 tăng trong khi trung bình ổn định có thể cho thấy một nhóm request đang chậm nghiêm trọng.

### 1.1. Phân biệt health check và endpoint performance

`/actuator/health` trả trạng thái health theo các health indicators. Nó hữu ích cho liveness/readiness và tình trạng dependency, nhưng **không phải dashboard độ trễ của từng endpoint**.

Một ứng dụng có thể trả `UP` trong khi:

- `POST /api/orders` có p95 tăng lên vài giây;
- database pool gần hết connection;
- payment provider timeout;
- một route trả 5xx ở tỷ lệ cao nhưng process vẫn sống.

Vì vậy, health endpoint và HTTP metrics cần được dùng cho các câu hỏi khác nhau.

## 2. Metric mặc định: http.server.requests

Với Spring MVC và Spring WebFlux, Spring Boot tự động instrument các request đi qua controllers và functional handlers. Metric mặc định có tên:

~~~text
http.server.requests
~~~

Metric này là một **timer** của Micrometer. Nó ghi nhận số lần request, tổng thời gian và các thống kê phân phối được cấu hình. Một số registry có thể hiển thị các meter con hoặc tên đã chuẩn hóa khác nhau.

Những tag low-cardinality quan trọng theo semantic convention hiện hành của Spring Framework:

| Tag | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `method` | HTTP method. | `GET`, `POST`. |
| `uri` | URI pattern/route template nếu xác định được. | `/api/orders/{id}`. |
| `status` | HTTP response status code. | `200`, `404`, `500`. |
| `outcome` | Nhóm kết quả HTTP. | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR`. |
| `error` | Lớp exception nếu observation ghi nhận exception, hoặc `none`. | `TimeoutException`, `none`. |

Ở một số phiên bản convention cũ, tag `exception` được dùng hoặc xuất song song; trong Spring Framework hiện hành, `exception` được đánh dấu deprecated và `error` là key tương ứng. Hãy kiểm tra tag thực tế trong meter của dự án.

### 2.1. URI template giúp kiểm soát cardinality

Với request:

~~~text
GET /api/orders/10001
GET /api/orders/10002
GET /api/orders/10003
~~~

tag `uri` nên đại diện route template:

~~~text
uri=/api/orders/{id}
~~~

Không đưa raw path có ID cụ thể hoặc query string vào metric tag. Nếu mỗi order ID tạo một time series riêng, cardinality sẽ tăng theo số giao dịch. Raw URL có thể được giữ ở trace theo cơ chế high-cardinality, nhưng không nên biến nó thành metric label.

Nếu route không được nhận diện, convention có thể dùng giá trị fallback như `NOT_FOUND` hoặc `UNKNOWN`. Khi thấy các giá trị này tăng, kiểm tra routing, static resources, health probes, reverse proxy và các request tới URL không tồn tại.

### 2.2. Outcome không giống status

`status` là mã HTTP cụ thể; `outcome` là nhóm tổng quát. Ví dụ:

| Status | Outcome thường gặp | Diễn giải |
| --- | --- | --- |
| 200 | SUCCESS | Request hoàn tất thành công. |
| 302 | REDIRECTION | Chuyển hướng. |
| 400 | CLIENT_ERROR | Request không hợp lệ. |
| 404 | CLIENT_ERROR | Route hoặc tài nguyên không tìm thấy. |
| 429 | CLIENT_ERROR | Bị giới hạn lưu lượng. |
| 500 | SERVER_ERROR | Lỗi phía server. |
| 503 | SERVER_ERROR | Service tạm thời không sẵn sàng. |

Không phải mọi 4xx đều là lỗi vận hành. 400, 401, 403 hoặc 404 có thể phản ánh hành vi người dùng hoặc chính sách bảo vệ. Với alert availability, thường tập trung vào 5xx và timeout; với UX/API quality, theo dõi thêm các nhóm 4xx có ý nghĩa.

## 3. Metric request ghi nhận ở đâu?

Spring Framework dùng HTTP server observation để đo thời gian xử lý request. Với ứng dụng Spring MVC, instrumentation thường được thực hiện bởi `ServerHttpObservationFilter`; với WebFlux, observation được gắn vào reactive HTTP handling.

Observation có thể tạo metrics và traces thông qua Micrometer Observation handlers. Khi Spring Boot cấu hình MeterRegistry, các HTTP observations được ghi thành meter `http.server.requests`. Khi có Micrometer Tracing, cùng observation có thể tạo span.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring MVC / WebFlux"]
    B --> C["HTTP server Observation"]
    C --> D["Observation Context"]
    D --> E["Meter handler"]
    D --> F["Tracing handler"]
    E --> G["MeterRegistry"]
    G --> H["/actuator/metrics"]
    G --> I["Prometheus registry"]
    I --> J["/actuator/prometheus"]
    J --> K["Prometheus / monitoring backend"]
    F --> L["Micrometer Tracing"]
    L --> M["Trace exporter / backend"]
~~~

Điều này tạo hai góc nhìn bổ sung:

- **Metrics:** số lượng và phân phối thời gian của nhiều request.
- **Traces:** các spans cụ thể để điều tra một request hoặc workflow.

### 3.1. Phạm vi observation

HTTP server observation đo thời gian xử lý ở tầng Spring Framework. Nó không nhất thiết bao gồm mọi thời gian ở phía client, load balancer, reverse proxy hoặc network trước khi request tới ứng dụng.

Khi so sánh với browser timing hoặc API gateway latency, hãy xác định điểm bắt đầu/kết thúc của từng phép đo. Đừng kỳ vọng hai hệ thống có cùng duration nếu chúng đo những đoạn khác nhau.

## 4. Expose Actuator endpoints để chẩn đoán

Dependency nền tảng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Ví dụ cấu hình local để expose các endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

Chỉ endpoint `health` được expose qua HTTP theo mặc định. `metrics` phải được expose rõ ràng. Không mở tất cả Actuator endpoints chỉ để kiểm tra request metrics.

### 4.1. Xem danh sách meter

Khởi động ứng dụng rồi gọi:

~~~bash
curl --fail-with-body --silent --show-error \
  http://localhost:8080/actuator/metrics
~~~

Trong kết quả, tìm:

~~~text
http.server.requests
~~~

Nếu không có meter này, kiểm tra:

- ứng dụng có phải web application và đang dùng Spring MVC/WebFlux/Jersey được hỗ trợ không;
- request đã đi qua controller/functional handler chưa;
- Actuator/Micrometer auto-configuration có bị exclude không;
- ObservationRegistry có được cấu hình đúng không;
- request có được ghi nhận trong instance đang kiểm tra không.

### 4.2. Xem một metric cụ thể

~~~bash
curl --fail-with-body --silent --show-error \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

Response thường chứa:

- `name`: tên meter;
- `description`: mô tả;
- `baseUnit`: đơn vị;
- `measurements`: các thống kê như COUNT, TOTAL_TIME, MAX;
- `availableTags`: các key/value tag đang có.

Ví dụ response rút gọn mang tính minh họa:

~~~json
{
  "name": "http.server.requests",
  "baseUnit": "seconds",
  "measurements": [
    { "statistic": "COUNT", "value": 1250.0 },
    { "statistic": "TOTAL_TIME", "value": 42.7 },
    { "statistic": "MAX", "value": 1.82 }
  ],
  "availableTags": [
    { "tag": "method", "values": ["GET", "POST"] },
    { "tag": "status", "values": ["200", "404", "500"] },
    { "tag": "uri", "values": ["/api/orders", "/api/orders/{id}"] }
  ]
}
~~~

Các giá trị trên chỉ minh họa cấu trúc. Measurement thực tế phụ thuộc registry, cấu hình distribution và thời gian chạy.

### 4.3. Drill down theo endpoint và status

Actuator metrics endpoint hỗ trợ nhiều query parameter `tag`:

~~~bash
curl --fail-with-body --silent --show-error \
  --get "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders/{id}" \
  --data-urlencode "tag=method:GET" \
  --data-urlencode "tag=status:500"
~~~

Cách này giúp xác minh instance có ghi nhận request theo route/method/status hay không. Với một route cụ thể, hãy dùng đúng URI template xuất hiện trong `availableTags`.

**Giới hạn:** `/actuator/metrics` là endpoint chẩn đoán các meters hiện có của một ứng dụng. Nó không phải metrics backend, không phải endpoint để Prometheus scrape liên tục và không thay thế dashboard lịch sử.

### 4.4. Endpoint httpexchanges có ích khi nào?

Actuator có thể cung cấp `/actuator/httpexchanges` nếu ứng dụng cấu hình `HttpExchangeRepository`. Theo mặc định, repository mẫu có thể giữ một số lượng exchange gần đây (ví dụ 100), hữu ích để xem request/response gần nhất khi debug.

Nó không phải hệ thống thống kê dài hạn, không thay histogram và không nên dùng để tính p95 hoặc tỷ lệ lỗi trên traffic production. Hãy dùng metrics backend cho thống kê theo thời gian.

## 5. Thu thập liên tục với Prometheus

Để Prometheus scrape metrics, thêm registry:

~~~groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Expose endpoint Prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  metrics:
    tags:
      application: shop-service
~~~

Sau đó truy cập:

~~~text
GET /actuator/prometheus
~~~

Endpoint này xuất dữ liệu theo định dạng Prometheus scrape. Tên meter Micrometer `http.server.requests` thường được chuẩn hóa thành tên Prometheus như:

~~~text
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_max
~~~

Khi histogram được bật, có thêm series dạng `http_server_requests_seconds_bucket` với label `le`. Tên chính xác và tags phụ thuộc registry, semantic convention và naming convention đang dùng.

### 5.1. Prometheus scrape config

Ví dụ `prometheus.yml`:

~~~yaml
scrape_configs:
  - job_name: "shop-service"
    metrics_path: "/actuator/prometheus"
    scrape_interval: 15s
    static_configs:
      - targets:
          - "shop-service:8080"
~~~

Địa chỉ target phải truy cập được từ Prometheus. Nếu chạy trong Docker/Kubernetes, dùng service DNS hoặc endpoint của môi trường thay vì mặc định localhost.

### 5.2. Kiểm tra scrape

Trong Prometheus UI, kiểm tra target của `shop-service` có trạng thái UP hay không. Sau đó thử truy vấn:

~~~promql
http_server_requests_seconds_count
~~~

Nếu không có dữ liệu:

1. Kiểm tra dependency `micrometer-registry-prometheus`.
2. Kiểm tra endpoint `/actuator/prometheus` có trả text metrics.
3. Kiểm tra endpoint có được expose và được phép truy cập.
4. Kiểm tra target/port/path trong Prometheus scrape config.
5. Kiểm tra network, authentication và TLS.
6. Kiểm tra tên metric sau khi normalization.

## 6. Theo dõi request rate

Request rate là số request trên một đơn vị thời gian. Với Prometheus counter:

~~~promql
sum(
  rate(http_server_requests_seconds_count{application="shop-service"}[5m])
)
~~~

Kết quả là request/giây trung bình trên cửa sổ 5 phút, nếu label `application` được cấu hình như ví dụ.

Để nhóm theo endpoint:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{application="shop-service"}[5m])
)
~~~

Để so sánh GET và POST:

~~~promql
sum by (method, uri) (
  rate(http_server_requests_seconds_count{application="shop-service"}[5m])
)
~~~

Request rate giúp phát hiện thay đổi traffic, nhưng không cho biết service có đang hoạt động tốt không. Traffic giảm có thể là do ít người dùng, lỗi routing hoặc service không nhận được request; cần đối chiếu với gateway, health và business metrics.

## 7. Theo dõi tỷ lệ lỗi endpoint

### 7.1. Tỷ lệ lỗi 5xx toàn service

Một truy vấn cơ bản:

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    application="shop-service",
    status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    application="shop-service"
  }[5m])
)
~~~

Kết quả là tỷ lệ request 5xx trên tổng request trong cửa sổ 5 phút. Nếu mẫu số bằng 0, kết quả có thể không có giá trị; dashboard/alert cần xử lý trường hợp không có traffic.

### 7.2. Tỷ lệ lỗi 5xx theo endpoint

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    application="shop-service",
    status=~"5.."
  }[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count{
    application="shop-service"
  }[5m])
)
~~~

Dùng truy vấn này để phát hiện route nào đang tạo nhiều 5xx hơn. Có thể thêm `method` nếu muốn phân biệt GET/POST.

### 7.3. Phân biệt 4xx và 5xx

- **4xx:** request bị từ chối hoặc không hợp lệ từ góc nhìn HTTP. Một số 4xx là hành vi dự kiến, ví dụ 401 khi chưa đăng nhập hoặc 404 khi tài nguyên không tồn tại.
- **5xx:** lỗi phía server hoặc service không thể hoàn thành request. Đây thường là nhóm cần cảnh báo availability.
- **Timeout:** có thể biểu hiện bằng 5xx, lỗi client hoặc gateway timeout tùy nơi timeout được tạo. Hãy xem cả server metrics, client metrics và trace.
- **Exception:** không phải mọi exception đều dẫn tới 5xx; controller advice có thể chuyển exception thành 4xx/2xx.

Không dùng một ngưỡng chung cho mọi status code. Chẳng hạn, 404 ở endpoint tra cứu có thể bình thường; 404 tăng đột biến ở endpoint mới deploy có thể báo hiệu route mapping sai.

### 7.4. Exception được xử lý trong controller

Có trường hợp exception được xử lý bởi `@ExceptionHandler` nên request observation không tự động ghi exception vào tag `error`. Nếu cần đưa exception đã xử lý vào observation, Spring Framework cung cấp API ghi nhận handled exception:

- Servlet MVC: `ServerHttpObservationFilter.recordHandledException(request, exception)`.
- WebFlux: `ServerRequestObservationContext.recordHandledException(exchange.getAttributes(), exception)`.

Chỉ ghi exception khi muốn nó xuất hiện trong telemetry theo đúng ý nghĩa vận hành. Nếu không, metric status vẫn có thể cho thấy response 404/400 dù tag error là `none`. Đây không nhất thiết là lỗi instrumentation.

## 8. Đo thời gian phản hồi: count, total time và max

`http.server.requests` là timer. Những measurement thường gặp:

| Measurement | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `COUNT` | Số request được ghi nhận. | Request volume. |
| `TOTAL_TIME` | Tổng thời gian của các request. | Tính trung bình trong phạm vi meter. |
| `MAX` | Thời gian lớn nhất trong cửa sổ/aggregation của registry. | Nhận diện outlier, nhưng không thay percentile. |

Có thể tính trung bình sơ bộ:

\[
\text{average latency} =
\frac{\text{TOTAL\_TIME}}{\text{COUNT}}
\]

Nhưng **average không thể hiện tail latency**. Nếu 99 request mất 50 ms và 1 request mất 5 giây, trung bình có thể vẫn trông chấp nhận được trong khi một nhóm người dùng gặp trải nghiệm rất chậm.

Để theo dõi chất lượng endpoint, nên quan sát p50, p95, p99 hoặc SLO buckets thay vì chỉ dùng average/max.

## 9. Histogram và percentile cho latency

Micrometer có thể publish histogram phù hợp để backend tính percentile có thể tổng hợp qua nhiều instance. Ví dụ bật histogram cho HTTP server requests:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Có thể giới hạn phạm vi giá trị dự kiến hoặc cấu hình các bucket theo SLO. Histogram tạo thêm series, vì vậy chỉ bật cho meter thực sự cần theo dõi phân vị.

### 9.1. PromQL p95

Khi Prometheus histogram bucket đã được publish:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      application="shop-service"
    }[5m])
  )
)
~~~

Kết quả ước lượng p95 theo endpoint trong 5 phút. Đơn vị của timer Prometheus ở ví dụ là giây.

Có thể thay `0.95` bằng:

- `0.50` cho p50;
- `0.90` cho p90;
- `0.99` cho p99.

**Lưu ý:** p95 tổng hợp từ histogram buckets là ước lượng theo bucket boundaries. Nếu histogram chưa bật hoặc backend không có bucket series, truy vấn sẽ không trả kết quả mong muốn.

### 9.2. Percentile phía ứng dụng và histogram khác nhau

Micrometer có thể tính percentile ở phía ứng dụng hoặc publish histogram. Percentile tính ở từng instance thường không thể cộng/gộp chính xác thành percentile toàn cluster. Histogram buckets mới cho phép backend tổng hợp phân phối giữa nhiều instance rồi ước lượng percentile.

Vì vậy, khi cần p95 của toàn service, ưu tiên histogram phù hợp backend thay vì lấy trung bình p95 của từng pod.

## 10. Định nghĩa SLO cho thời gian phản hồi

Một SLO có thể đặt mục tiêu: **95% request tới endpoint tạo đơn hoàn tất trong 300 ms**, hoặc một tỷ lệ request thành công trong cửa sổ 30 ngày. Ngưỡng phải xuất phát từ kỳ vọng sản phẩm và trải nghiệm người dùng, không chọn chỉ vì dễ đạt.

Cấu hình bucket theo SLO:

~~~yaml
management:
  metrics:
    distribution:
      slo:
        http.server.requests:
          - 100ms
          - 300ms
          - 1s
~~~

Cấu hình này yêu cầu histogram có bucket tại các ngưỡng đã chọn cho timer đó. Tùy registry, các bucket cumulative được export dưới dạng series tương ứng.

### 10.1. Tỷ lệ request dưới 300 ms

Với bucket `le="0.3"`:

~~~promql
sum(
  rate(http_server_requests_seconds_bucket{
    application="shop-service",
    uri="/api/orders",
    le="0.3"
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    application="shop-service",
    uri="/api/orders"
  }[5m])
)
~~~

Kết quả là tỷ lệ request có duration không vượt quá khoảng 300 ms trong cửa sổ quan sát, với điều kiện bucket SLO 300 ms được xuất và label route khớp dữ liệu thực tế.

### 10.2. Error budget và availability

Nếu SLO là 99,9% request thành công, error budget là 0,1% request trong cửa sổ SLO. Có thể đo success ratio theo định nghĩa nghiệp vụ/HTTP phù hợp:

- loại trừ 4xx được coi là lỗi client nếu đó là chính sách sản phẩm;
- coi 5xx và timeout phía server là lỗi;
- xác định cách xử lý 429, 404 hoặc request bị hủy;
- tính theo traffic thực tế, tránh để endpoint ít request chi phối dashboard.

SLO phải có **định nghĩa success rõ ràng**. Không mặc định mọi 2xx đều là thành công nghiệp vụ hoặc mọi 4xx đều không quan trọng.

## 11. Dashboard nên có những biểu đồ nào?

Một dashboard vận hành endpoint có thể bắt đầu bằng:

| Panel | Nội dung | Câu hỏi |
| --- | --- | --- |
| Request rate | Requests/second theo service/uri. | Traffic đang tăng hay giảm? |
| 5xx ratio | Tỷ lệ 5xx theo service/uri. | Endpoint nào đang lỗi? |
| 4xx ratio | Tỷ lệ 4xx theo route/status. | Có thay đổi hành vi client hoặc auth? |
| Latency p50/p95/p99 | Histogram quantiles theo uri. | Người dùng có gặp request chậm? |
| SLO compliance | Tỷ lệ request dưới ngưỡng. | Endpoint có đáp ứng cam kết? |
| Status distribution | Phân bố 2xx/3xx/4xx/5xx. | Loại response nào tăng? |
| Instance breakdown | Request/error/latency theo instance. | Có pod/node riêng gặp vấn đề? |

~~~mermaid
flowchart TB
    A["HTTP server requests"] --> B["Request rate"]
    A --> C["Status / outcome"]
    A --> D["Latency histogram"]
    B --> E["Traffic dashboard"]
    C --> F["Error dashboard"]
    D --> G["p95 / SLO dashboard"]
    E --> H["Alert rules"]
    F --> H
    G --> H
    H --> I["On-call investigation"]
~~~

Nên có filter theo service, environment, instance và URI template. Không đưa raw URL, user ID hoặc order ID làm label chỉ để dashboard lọc chi tiết.

## 12. Alert khi lỗi hoặc latency vượt ngưỡng

Alert nên phản ánh mức ảnh hưởng, không chỉ một con số đơn lẻ.

Ví dụ minh họa:

| Alert | Điều kiện ví dụ | Ý nghĩa |
| --- | --- | --- |
| High server error ratio | 5xx ratio > 2% trong 5 phút và có đủ request volume. | Endpoint đang lỗi đáng kể. |
| High p95 latency | p95 > 500 ms liên tục 10 phút. | Tail latency vượt mục tiêu. |
| Sudden 404 increase | 404 rate tăng nhiều lần so với baseline. | Có thể route, client hoặc deployment thay đổi. |
| No traffic unexpectedly | Route quan trọng không có request trong khoảng thời gian dự kiến. | Có thể routing, client hoặc scrape path gặp sự cố. |
| SLO burn rate | Error budget tiêu thụ nhanh hơn mức cho phép. | Cần ưu tiên xử lý sự cố. |

Các ngưỡng này chỉ để minh họa. Hãy đặt alert theo SLO, traffic nền, mùa vụ, mức độ quan trọng và thời gian cần phản ứng. Alert 5xx cần có điều kiện request volume để tránh cảnh báo từ một lỗi đơn lẻ trong thời gian không có traffic.

### 12.1. Alert không nên dựa trên p95 của một request

Percentile cần đủ mẫu. Với endpoint ít traffic, p95 trong cửa sổ 1 phút có thể không ổn định hoặc không có dữ liệu. Có thể dùng cửa sổ dài hơn, kết hợp error rate, synthetic checks hoặc metric nghiệp vụ.

### 12.2. Phân biệt alert của app và alert của monitoring

Nếu Prometheus không scrape được target, dashboard có thể không có dữ liệu. Đây là **monitoring pipeline issue**, không nhất thiết là endpoint của ứng dụng đang trả lỗi. Cần có alert riêng cho target down/scrape failure.

## 13. Tùy biến tag theo endpoint

Mặc định `http.server.requests` đã cung cấp các tag quan trọng. Nếu cần thêm tag như API version hoặc loại request, hãy dùng `ServerRequestObservationConvention` và giữ lại tag mặc định.

Ví dụ hướng tiếp cận với Spring MVC:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.observation.ServerRequestObservationContext;

@Configuration(proxyBeanMethods = false)
class HttpObservationConfiguration {

    @Bean
    DefaultServerRequestObservationConvention serverRequestObservationConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("api.version", "v1"));
            }
        };
    }
}
~~~

Đây là ví dụ cố định một tag có tập giá trị thấp. Trong ứng dụng thật, nếu version thay đổi theo route, hãy ánh xạ về một tập hữu hạn như `v1`/`v2`.

Không thay toàn bộ convention nếu chỉ muốn thêm một tag, vì có thể vô tình bỏ mất `method`, `status`, `outcome` hoặc `uri` mặc định. Với WebFlux, convention nằm trong package reactive tương ứng; không dùng nhầm class MVC cho reactive application.

### 13.1. Không thêm high-cardinality tag

Không dùng các giá trị sau làm metric tag:

- raw URL có query string;
- order ID, customer ID hoặc user ID;
- trace ID/span ID;
- exception message;
- request payload;
- email hoặc dữ liệu cá nhân.

Nếu cần chi tiết request, dùng trace attributes hoặc structured logs với chính sách dữ liệu phù hợp. Metrics cần tag có tập giá trị hữu hạn.

## 14. Kết hợp endpoint metrics với Spring Modulith module spans

HTTP metric cho biết endpoint nào chậm; module span giúp tìm phần xử lý bên trong request.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as orders
    participant I as inventory
    participant P as payments
    participant M as Metrics
    participant T as Trace backend

    C->>O: POST /api/orders
    O->>M: http.server.requests timer
    O->>I: InventoryFacade.reserve()
    I->>T: Module entry span (inventory)
    O->>P: Publish OrderPlaced
    P->>T: Module entry span (payments listener)
    O-->>C: HTTP response
    O->>M: Record status, outcome, duration
~~~

Một quy trình điều tra:

1. Dashboard cho thấy `POST /api/orders` có p95 tăng.
2. Lọc trace của request chậm bằng exemplar hoặc trace ID nếu backend hỗ trợ.
3. Mở trace và xem module entry spans.
4. Xác định span `inventory` hoặc `payments` có duration bất thường.
5. Kiểm tra child spans tới database, HTTP client hoặc event listener.
6. Dùng log correlation để đọc thông báo chi tiết.
7. Đối chiếu module graph để hiểu module dependency và ranh giới kiến trúc.

**Không mặc định HTTP metrics có tag `module.identifier`.** Module identifier thường nằm trên module observation/span của Spring Modulith. Nếu muốn thống kê thời gian theo module, có thể dùng module spans/metrics phù hợp hoặc custom instrumentation riêng với cardinality thấp; không gắn một module tùy ý vào HTTP metric nếu không có quan hệ rõ ràng.

### 14.1. Metrics và traces bổ sung nhau

| HTTP metrics | Module spans |
| --- | --- |
| Tóm tắt request rate, status, duration theo route. | Mô tả lời gọi qua ranh giới module trong một trace cụ thể. |
| Có thể theo dõi toàn traffic mà không phụ thuộc trace sampling. | Chịu ảnh hưởng bởi instrumentation, sampling và exporter. |
| Phù hợp dashboard và alert tổng hợp. | Phù hợp điều tra một request chậm/lỗi. |
| Không chỉ ra trực tiếp module nào gây chậm. | Cho thấy module và dependency trong đường thực thi được instrument. |

## 15. Các nguyên nhân phổ biến khiến endpoint chậm

Khi p95 tăng, hãy kiểm tra theo từng lớp:

| Dấu hiệu | Nguyên nhân có thể | Metrics/traces cần xem |
| --- | --- | --- |
| HTTP span chậm, database span dài | Query chậm, lock contention, connection pool. | JDBC spans, DB metrics, active/idle connections. |
| HTTP span chậm, client span dài | Downstream API timeout hoặc network. | `http.client.requests`, client spans, retry count. |
| Request rate tăng và latency tăng | Saturation ở CPU, thread pool, database hoặc dependency. | CPU, thread pool, queue, connection pool. |
| p95 tăng nhưng p50 ổn | Một nhóm request hoặc dữ liệu đầu vào đặc biệt chậm. | p95/p99 theo route, trace mẫu và log. |
| 5xx tăng sau deploy | Regression, config sai, migration hoặc dependency mismatch. | Error ratio theo revision, logs, traces. |
| Chỉ một instance chậm | Node/pod, GC, CPU throttling, local connection pool. | Metrics theo instance, JVM/GC, container metrics. |
| 404 tăng mạnh | Client gọi route cũ, gateway rewrite sai, resource không tồn tại. | Status/uri/method, access logs, deployment changes. |

Không quy kết nguyên nhân chỉ từ một biểu đồ. Dùng trace để tìm span chậm, logs để xem lỗi chi tiết, metrics hạ tầng để xác nhận saturation và module graph để hiểu cấu trúc phụ thuộc.

## 16. Troubleshooting khi thiếu metric hoặc sai số liệu

### 16.1. Không thấy http.server.requests

- Xác minh ứng dụng chạy Spring MVC, WebFlux hoặc stack được hỗ trợ.
- Gửi request thực sự qua controller/functional handler.
- Kiểm tra Actuator/Micrometer dependency và auto-configuration.
- Kiểm tra ObservationRegistry có bị thay thế hoặc cấu hình sai không.
- Xem endpoint `/actuator/metrics` có expose và có đúng instance không.

### 16.2. Metric có nhưng tag uri là UNKNOWN hoặc NOT_FOUND

- Kiểm tra request có khớp controller mapping không.
- Kiểm tra static resources, fallback handler và reverse proxy rewrite.
- Kiểm tra đường dẫn có chứa biến động hoặc không được nhận diện như route template.
- Đối chiếu `availableTags` trước khi viết truy vấn Prometheus.

### 16.3. Không thấy exception tag dù response là 404/400

Exception có thể đã được xử lý bởi `@ExceptionHandler`. Theo mặc định, một số exception đã xử lý không được ghi nhận vào request observation như exception. Nếu muốn ghi nhận, dùng API record handled exception phù hợp Servlet MVC/WebFlux như phần 7.4.

Status và outcome vẫn là các tín hiệu để phân loại response; không nên chỉ dựa vào tag error.

### 16.4. Actuator metrics có dữ liệu nhưng Prometheus không có

- Kiểm tra `micrometer-registry-prometheus`.
- Kiểm tra `/actuator/prometheus` trả dữ liệu.
- Kiểm tra `management.endpoints.web.exposure.include`.
- Kiểm tra Prometheus target, scrape interval, path, port và network.
- Kiểm tra authentication/TLS và log scrape error.
- Nhớ rằng tên metric ở Actuator dùng dạng Micrometer, còn Prometheus dùng tên đã normalize.

### 16.5. p95 không có dữ liệu

- Histogram chưa được bật cho `http.server.requests`.
- Registry/backend không xuất bucket theo cách truy vấn đang giả định.
- PromQL đang dùng sai tên metric hoặc label.
- Endpoint chưa có đủ request trong cửa sổ.
- SLO bucket chưa cấu hình hoặc label `le` không chứa ngưỡng mong muốn.

### 16.6. Error ratio bằng NaN hoặc không có dữ liệu

Mẫu số có thể bằng 0 do không có traffic trong cửa sổ. Xem request rate trước khi đánh giá error ratio. Với endpoint ít traffic, dùng cửa sổ dài hơn hoặc synthetic check.

## 17. Bảo mật và cardinality khi expose Actuator

Actuator endpoints có thể tiết lộ thông tin về ứng dụng và hạ tầng. Spring Boot mặc định chỉ expose `health` qua HTTP. Khi thêm `metrics` hoặc `prometheus`, hãy giới hạn truy cập bằng network policy, firewall, management port riêng hoặc Spring Security.

Ví dụ expose có chủ đích:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
    access:
      max-permitted: read-only
~~~

Cấu hình access policy ở trên minh họa Spring Boot 4.2; với release khác, kiểm tra property có được hỗ trợ. Expose endpoint không đồng nghĩa mọi người dùng đều nên được phép truy cập.

Các nguyên tắc:

- Không expose toàn bộ endpoint bằng `*` nếu không có lý do.
- Bảo vệ Actuator bằng authentication/authorization hoặc mạng quản trị.
- Cân nhắc tách management port khỏi traffic public.
- Chỉ cấp quyền scrape cho Prometheus/monitoring agent.
- Không thêm raw URL, user ID, order ID hoặc trace ID vào metric tags.
- Dùng URI template và nhóm giá trị hữu hạn để giữ cardinality.
- Đặt retention và quyền truy cập metrics/logs/traces phù hợp.

## 18. Quy trình vận hành khi endpoint có lỗi hoặc chậm

~~~mermaid
flowchart TD
    A["Alert: error ratio hoặc p95 tăng"] --> B["Xác định service, route, method và time window"]
    B --> C{"5xx tăng?"}
    C -->|"Có"| D["Phân loại status/error, đọc logs"]
    C -->|"Không"| E["Xem p50/p95/p99 và request rate"]
    D --> F["Tìm trace mẫu có lỗi"]
    E --> G["Tìm trace chậm"]
    F --> H["Đọc module entry spans và child spans"]
    G --> H
    H --> I["Đối chiếu module graph, DB/client metrics"]
    I --> J["Xác định nguyên nhân và mitigation"]
    J --> K["Theo dõi error ratio, latency và SLO sau thay đổi"]
~~~

Trình tự thực hành:

1. Xác định thời điểm bắt đầu sự cố và service bị ảnh hưởng.
2. Kiểm tra request rate để biết traffic có thay đổi không.
3. Phân loại lỗi theo status, outcome, URI và method.
4. Xem latency p50/p95/p99 theo route.
5. Tìm trace có lỗi/chậm nếu sampling và exporter giữ được trace.
6. Mở module spans để xác định ranh giới module có thời gian bất thường.
7. Kiểm tra child spans, downstream metrics, database pool, CPU và thread pool.
8. Đọc log correlation để tìm thông điệp lỗi.
9. Áp dụng mitigation có kiểm soát.
10. Xác minh error ratio, latency và SLO trở lại ngưỡng.

## 19. Checklist triển khai giám sát endpoint

- [ ] Có Spring Boot Actuator và Micrometer registry phù hợp.
- [ ] Đã xác minh meter `http.server.requests` được tạo cho request thực tế.
- [ ] Đã hiểu các tags `method`, `uri`, `status`, `outcome` và `error`.
- [ ] Đã kiểm tra URI template thay vì raw URL động.
- [ ] Đã phân biệt 4xx, 5xx, handled exception và timeout.
- [ ] Đã expose `metrics` chỉ cho chẩn đoán khi cần.
- [ ] Nếu dùng Prometheus, đã thêm registry và expose `prometheus`.
- [ ] Prometheus scrape target đang UP và thu thập được series.
- [ ] Đã có dashboard request rate, error ratio, p95/p99 và status distribution.
- [ ] Histogram/SLO buckets đã bật cho timer cần theo dõi.
- [ ] Đã đặt alert theo SLO, traffic và mức độ quan trọng.
- [ ] Đã xử lý trường hợp endpoint không có traffic hoặc mẫu quá ít.
- [ ] Đã bảo vệ Actuator endpoints bằng quyền truy cập phù hợp.
- [ ] Không dùng high-cardinality tags như user ID, order ID hoặc raw URL.
- [ ] Đã kết hợp HTTP metrics với Spring Modulith module spans và log correlation.
- [ ] Có runbook điều tra lỗi, latency và scrape failure.

## 20. Bài tập tự luyện

1. **Đọc metric:** Giải thích vai trò của `http.server.requests` và các tags `method`, `uri`, `status`, `outcome`.
2. **Phân loại lỗi:** Vì sao không nên gộp mọi 4xx và 5xx thành một nhóm alert?
3. **Actuator:** Gọi endpoint nào để xem danh sách meters và drill down vào `http.server.requests`?
4. **Giới hạn:** Vì sao `/actuator/metrics` không nên được dùng làm metrics backend hoặc Prometheus scrape target?
5. **Prometheus:** Viết PromQL tính tỷ lệ 5xx theo URI trong cửa sổ 5 phút.
6. **Latency:** Vì sao average không đủ để phát hiện tail latency? p95 có ý nghĩa gì?
7. **Histogram:** Property nào bật histogram cho `http.server.requests`? Vì sao cần histogram để tổng hợp p95 trên nhiều instance?
8. **SLO:** Thiết kế bucket 100 ms, 300 ms và 1 giây cho endpoint tạo đơn; viết truy vấn tỷ lệ request dưới 300 ms.
9. **Exception:** Một exception được xử lý trong `@ExceptionHandler` nhưng metric error là none. Điều này có thể xảy ra vì sao?
10. **Spring Modulith:** HTTP metric cho thấy `POST /api/orders` chậm. Bạn dùng module entry spans để tìm module gây chậm như thế nào?
11. **Security:** Vì sao chỉ expose health mặc định? Cần làm gì khi expose metrics/prometheus?
12. **Cardinality:** Vì sao không nên dùng raw URL hoặc order ID làm metric tag?
13. **Troubleshooting:** Actuator có metric nhưng Prometheus không có. Hãy liệt kê các bước điều tra.
14. **Vận hành:** Đề xuất dashboard và alert cho hệ thống có orders, inventory và payments modules.

## 21. Tổng kết

Để giám sát lỗi endpoint và thời gian phản hồi, Spring Boot Actuator kết hợp Micrometer cung cấp meter `http.server.requests` cho các request được instrument qua Spring MVC/WebFlux. Các tag như `method`, `uri`, `status`, `outcome` và `error` giúp phân loại lưu lượng và lỗi theo route.

`/actuator/metrics` phù hợp để chẩn đoán meter trên một instance; Prometheus registry và `/actuator/prometheus` phù hợp để thu thập liên tục, tính request rate, error ratio và latency percentile. Muốn theo dõi p95/p99 hoặc SLO, cần cấu hình histogram/buckets phù hợp và hiểu giới hạn của từng registry.

Khi endpoint chậm hoặc lỗi, metrics chỉ ra **route và xu hướng**; trace và Spring Modulith module entry spans giúp tìm **module hoặc dependency** gây ra vấn đề; logs cung cấp thông điệp chi tiết. Kết hợp ba tín hiệu với module graph, kiểm thử và dữ liệu nghiệp vụ giúp nhóm phát triển kiểm chứng kiến trúc mô-đun trong vận hành mà không nhầm metric HTTP với kết quả nghiệp vụ.

### Tài liệu tham khảo chính thức

1. [Spring Boot 4.2 — Metrics: HTTP server metrics, Prometheus, histogram và metrics endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
2. [Spring Boot 4.2 — Actuator Endpoints: exposure, access control và security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
3. [Spring Boot 4.2 — Prometheus Actuator API](https://docs.spring.io/spring-boot/api/rest/actuator/prometheus.html).
4. [Spring Boot 4.2 — Metrics Actuator API](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html).
5. [Spring Framework 7.1 — Observability Support: HTTP server observations, tags và handled exceptions](https://docs.spring.io/spring-framework/reference/integration/observability.html).
6. [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).
7. [Spring Modulith — Production-ready Features: Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
