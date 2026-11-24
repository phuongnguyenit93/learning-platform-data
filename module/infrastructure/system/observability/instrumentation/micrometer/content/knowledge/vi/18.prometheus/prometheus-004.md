# Chuyển tên, đơn vị và tag Micrometer thành chuỗi Prometheus

Micrometer cho phép ứng dụng Java đặt tên meter theo ngữ nghĩa nghiệp vụ, chẳng hạn `orders.created` hoặc `checkout.payment.duration`. Khi dùng Prometheus registry, tên meter và tag được chuyển sang quy ước đặt tên của Prometheus trước khi xuất ra endpoint exposition. Đơn vị cũng có thể được thể hiện trong tên metric, còn tag trở thành label dùng để phân biệt các chuỗi thời gian.

Vì vậy, tên nhìn thấy trong mã Java không nhất thiết giống tên được truy vấn trong PromQL. Muốn đọc đúng dữ liệu, cần hiểu ba bước: Micrometer định danh meter bằng tên và tag; Prometheus naming convention chuẩn hóa tên và khóa tag; registry xuất một hoặc nhiều chuỗi metric tùy loại meter và cấu hình phân phối.

## Từ Meter.Id đến chuỗi thời gian

`Meter.Id` mang tên, tập tag, loại meter và metadata như description hoặc base unit. Phần cốt lõi dùng để phân biệt một meter trong registry là tên cùng tập tag; loại meter cũng cần tương thích khi nhiều nơi đăng ký cùng định danh. Ví dụ:

```java
Counter.builder("orders.created")
        .tag("channel", "web")
        .register(registry);
```

Meter có tên `orders.created` và tag `channel=web`. Trong Prometheus, một chuỗi thời gian được nhận diện bởi tên metric cùng toàn bộ tập label. Nếu cùng metric được xuất với `channel="web"` và `channel="mobile"`, Prometheus lưu hai chuỗi khác nhau.

```mermaid
flowchart TD
    A[Meter.Id trong Micrometer] --> B[Tên: orders.created]
    A --> C[Tag: channel = web]
    B --> D[Prometheus naming convention]
    C --> E[Chuyển tag key thành label name]
    D --> F[orders_created_total]
    E --> G[channel="web"]
    F --> H[Prometheus time series]
    G --> H
```

Quy tắc chuyển đổi là trách nhiệm của Prometheus registry. Mã nghiệp vụ nên đặt tên rõ nghĩa và dùng tag ổn định; không nên tự đổi tên meter thành dạng Prometheus ngay trong service chỉ để đoán trước exporter sẽ xuất gì.

## Chuẩn hóa tên metric

Prometheus yêu cầu tên metric tuân theo cú pháp identifier. Prometheus naming convention của Micrometer chuyển các tên meter theo quy tắc phù hợp với định dạng đó. Trong cách đặt tên thông dụng:

- Dấu chấm phân tách các phần của tên Micrometer được chuyển thành dấu gạch dưới.
- Các ký tự không phù hợp với tên metric Prometheus được chuẩn hóa, thường thành dấu gạch dưới.
- Tên metric được bổ sung hậu tố đơn vị hoặc hậu tố loại metric khi registry cần thể hiện chúng.
- Counter thường được xuất với hậu tố `_total` để thể hiện giá trị tích lũy.

Ví dụ chuyển đổi thường gặp:

| Tên meter Micrometer | Tên metric Prometheus minh họa | Ghi chú |
|---|---|---|
| `orders.created` | `orders_created_total` | Counter được thể hiện là tổng tích lũy |
| `worker.queue.depth` | `worker_queue_depth` | Gauge phản ánh giá trị hiện tại |
| `http.server.requests` (Timer) | `http_server_requests_seconds_count`, `http_server_requests_seconds_sum` | Timer xuất count và tổng thời gian theo giây |
| `http.request.payload.size` (base unit `bytes`) | `http_request_payload_size_bytes_count`, `http_request_payload_size_bytes_sum` | DistributionSummary xuất count và tổng lượng theo byte |

Đây là các tên minh họa theo Prometheus convention phổ biến của Micrometer. Tên cuối cùng còn phụ thuộc phiên bản registry, loại meter, base unit và cấu hình histogram. Hãy xem exposition thực tế của ứng dụng trước khi viết truy vấn hoặc alert.

### Tránh tự thêm hậu tố vào tên meter

Nên đặt tên meter theo đại lượng, ví dụ `checkout.payment.duration`, sau đó khai báo hoặc để registry xác định đơn vị. Với Timer, registry biết đại lượng là thời gian và xuất đơn vị chuẩn theo quy ước của nó. Nếu tự đặt tên đã có `_seconds` rồi registry lại thêm đơn vị, metric có thể bị lặp hậu tố hoặc tạo tên khó hiểu.

Tương tự, Counter nên có tên mô tả sự kiện như `orders.created`; registry sẽ xuất hậu tố counter phù hợp. Không cần đặt tên nguồn thành `orders_created_total` rồi lại kỳ vọng mọi registry xử lý giống nhau.

## Đơn vị và base unit

Đơn vị giúp người đọc biết một giá trị biểu diễn đại lượng nào và giúp backend áp dụng cách hiển thị hoặc truy vấn phù hợp. Micrometer có thể lấy đơn vị từ loại meter, chẳng hạn Timer đo thời gian, hoặc từ `baseUnit(...)` do ứng dụng khai báo cho meter tùy chỉnh.

### Timer chuẩn hóa thời gian

Timer nhận thời lượng qua API Java và quản lý chuyển đổi đơn vị. Ví dụ:

```java
import java.time.Duration;

Timer requestDuration = Timer.builder("http.server.request.duration")
        .description("Thời gian xử lý HTTP request")
        .register(registry);

requestDuration.record(Duration.ofMillis(250));
```

Với Prometheus registry, thời gian thường được xuất theo giây và đơn vị được thể hiện trong tên metric, ví dụ `http_server_request_duration_seconds_count` và `http_server_request_duration_seconds_sum`. Nếu ghi 250 ms, tổng thời gian xuất ra tương đương 0,25 giây. Không nhân hoặc chia thêm trong PromQL chỉ vì code Java dùng `Duration.ofMillis(...)`.

### DistributionSummary dùng baseUnit

Với đại lượng không phải thời gian, khai báo `baseUnit` để nói rõ đơn vị:

```java
DistributionSummary payloadSize = DistributionSummary.builder(
                "http.request.payload.size")
        .description("Kích thước request payload")
        .baseUnit("bytes")
        .register(registry);

payloadSize.record(8_192);
```

Với Prometheus convention, đơn vị `bytes` thường được thêm vào tên metric, tạo các tên dạng `http_request_payload_size_bytes_count` và `http_request_payload_size_bytes_sum`. `baseUnit("bytes")` mô tả đơn vị xuất; nó không tự chuyển giá trị truyền vào `record(...)`. Code phải bảo đảm số `8_192` thực sự là byte.

Nếu nguồn dữ liệu là KiB, cần đổi sang byte trước khi ghi nhận hoặc chọn một đơn vị chuẩn khác và giữ nhất quán. Không ghi byte và record vào cùng một DistributionSummary.

### Counter và Gauge không tự có đơn vị

Counter thường đếm số lần sự kiện xảy ra. Gauge thường phản ánh một giá trị hiện tại. Nếu đại lượng cần đơn vị như byte, connection hoặc item, hãy mô tả rõ trong tên, description hoặc base unit phù hợp với builder và registry. Đừng giả định registry có thể suy ra đơn vị từ ý nghĩa nghiệp vụ của tên.

## Tag Micrometer trở thành label Prometheus

Tag key trong Micrometer được chuyển thành label name. Label name phải tuân theo cú pháp Prometheus, nên các ký tự không hợp lệ trong key có thể được chuẩn hóa. Ví dụ:

```java
registry.counter(
        "http.server.requests",
        "http.method", "GET",
        "status.code", "200")
        .increment();
```

Các label name được xuất có thể là `http_method` và `status_code`. Label value như `GET` hoặc `200` được xuất thành giá trị chuỗi của label; chúng không được ghép vào tên metric. Trong exposition, dữ liệu có dạng minh họa:

```text
http_server_requests_total{http_method="GET",status_code="200"} 1.0
```

Registry sẽ escape các ký tự đặc biệt cần thiết trong giá trị label theo định dạng exposition. Tuy vậy, không nên dùng giá trị tự do hoặc dữ liệu nhạy cảm làm label. Các giá trị như user ID, email, request ID, token hoặc URL đầy đủ vừa có thể làm lộ dữ liệu vừa tạo cardinality rất lớn.

### Tập label xác định một chuỗi

Hai mẫu có cùng tên metric nhưng khác một label value là hai chuỗi thời gian:

```text
orders_created_total{channel="web"} 12
orders_created_total{channel="mobile"} 8
```

Một mẫu có thêm hoặc thiếu label cũng là một chuỗi khác. Thứ tự label trong exposition không làm thay đổi danh tính chuỗi; điều quan trọng là tên metric và toàn bộ tập label.

Nếu có 3 giá trị `channel`, 5 giá trị `status` và 4 giá trị `region`, số tổ hợp tối đa của một metric family là:

\[
3 \times 5 \times 4 = 60
\]

Đây là giới hạn tổ hợp trước khi tính thêm số instance và số chuỗi mà histogram tạo ra. Hãy chỉ chọn label thực sự cần để phân nhóm dashboard hoặc alert.

## Common tags trở thành label chung

Micrometer cho phép thêm common tags vào các meter trong một registry:

```java
registry.config().commonTags(
        "service", "checkout",
        "environment", "production",
        "region", "ap-southeast-1");
```

Các common tag này được thêm vào meter khi registry xuất dữ liệu. Một dòng exposition có thể trông như sau:

```text
orders_created_total{channel="web",service="checkout",environment="production",region="ap-southeast-1"} 12
```

Common tags hữu ích để lọc theo dịch vụ, môi trường hoặc vùng triển khai. Chúng cũng làm tăng số chiều label và số chuỗi khi giá trị khác nhau giữa các tiến trình. Cấu hình common tags trước khi các meter được đăng ký để đảm bảo tất cả meter có cùng tập chiều.

Prometheus thường tự gắn target labels như `job` và `instance` khi scrape. Các nhãn này đến từ cấu hình scrape và service discovery, không nhất thiết là tag do Micrometer tạo. Khi phân tích cardinality toàn hệ thống, cần tính cả tag ứng dụng lẫn nhãn target do Prometheus thêm.

Tránh tạo common tag `instance` nếu Prometheus đã tự gắn nhãn target cùng tên. Trùng tên giữa common tag và target label có thể dẫn đến xung đột hoặc hành vi ghi đè tùy cấu hình scrape. Hãy chọn một nguồn sở hữu cho mỗi chiều dữ liệu.

## Một meter có thể xuất thành nhiều chuỗi

Tên và tag chưa phải toàn bộ câu chuyện. Loại meter quyết định số measurement được xuất:

| Meter | Dữ liệu Prometheus thường thấy | Ghi chú |
|---|---|---|
| Counter | Một chuỗi tổng tích lũy, thường có hậu tố `_total` | Mỗi tổ hợp label tạo một chuỗi |
| Gauge | Một chuỗi giá trị hiện tại | Không biểu diễn lịch sử các lần thay đổi giữa hai scrape |
| Timer | `_count`, `_sum`, thường có `_max` | Đơn vị thời gian thường được chuẩn hóa về giây |
| DistributionSummary | `_count`, `_sum`, có thể có `_max` | Đơn vị phụ thuộc base unit được khai báo |
| Timer hoặc DistributionSummary bật histogram | Thêm các chuỗi `_bucket` với label `le` | Mỗi ranh giới bucket làm tăng số chuỗi |
| Percentile phía client | Các giá trị percentile được xuất theo quy tắc registry | Không thể cộng p95 của từng instance để ra p95 toàn cụm |

Ví dụ Timer bật histogram:

```java
Timer requestTimer = Timer.builder("http.server.request.duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(500),
                Duration.ofSeconds(2))
        .tag("route", "/orders/{orderId}")
        .register(registry);
```

Prometheus classic histogram có thể xuất các chuỗi dạng:

```text
http_server_request_duration_seconds_bucket{le="0.1",route="/orders/{orderId}"} 120
http_server_request_duration_seconds_bucket{le="0.5",route="/orders/{orderId}"} 190
http_server_request_duration_seconds_bucket{le="2.0",route="/orders/{orderId}"} 199
http_server_request_duration_seconds_bucket{le="+Inf",route="/orders/{orderId}"} 200
http_server_request_duration_seconds_count{route="/orders/{orderId}"} 200
http_server_request_duration_seconds_sum{route="/orders/{orderId}"} 31.4
```

Các bucket Prometheus là bucket tích lũy: bucket `le="0.5"` chứa tất cả quan sát nhỏ hơn hoặc bằng 0,5 giây, bao gồm những quan sát đã nằm trong bucket 0,1 giây. Đây là ví dụ minh họa; số bucket, nhãn và tên metric thực tế phụ thuộc cấu hình và registry.

Histogram cho phép backend cộng bucket tương ứng từ nhiều instance rồi ước lượng percentile. Nếu chỉ xuất percentile tính tại client, mỗi instance có percentile riêng và không thể gộp bằng phép cộng hoặc trung bình đơn giản.

## Kiểm tra tên và label thực tế qua endpoint

Với Spring Boot, thêm Actuator và Prometheus registry:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Expose endpoint Prometheus trong `application.properties`:

```properties
management.endpoints.web.exposure.include=health,prometheus
```

Sau khi ứng dụng khởi động, gọi endpoint:

```text
GET /actuator/prometheus
```

Trong nội dung trả về, kiểm tra:

1. Dòng `# HELP` để xem mô tả metric và tên family.
2. Dòng `# TYPE` để xem loại metric mà exporter công bố.
3. Tên metric thực tế và các hậu tố như `_total`, `_seconds`, `_bytes`, `_count`, `_sum`, `_max` hoặc `_bucket`.
4. Tập label name và label value sau khi common tags được áp dụng.
5. Label `le` của histogram và các ranh giới bucket đã cấu hình.

Không dựa hoàn toàn vào tên meter trong code để viết PromQL. Endpoint exposition là bằng chứng trực tiếp về cách registry hiện tại chuyển đổi metric.

## Truy vấn PromQL theo tên sau chuyển đổi

Sau khi xác nhận tên ở endpoint, dùng tên Prometheus trong truy vấn. Ví dụ đếm tốc độ tạo đơn hàng:

```promql
sum by (service) (
  rate(orders_created_total[5m])
)
```

Tính thời gian xử lý trung bình từ Timer:

```promql
sum by (service) (
  rate(http_server_request_duration_seconds_sum[5m])
)
/
sum by (service) (
  rate(http_server_request_duration_seconds_count[5m])
)
```

Ước lượng p95 từ histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
```

Tên metric trong các ví dụ là tên minh họa tương ứng với meter được mô tả. Trong ứng dụng thật, thay bằng tên lấy từ endpoint exposition. Đặc biệt, không áp dụng `rate()` cho một metric đã được exporter xuất dưới dạng delta hoặc rate; cần xác nhận temporality và loại metric trước khi truy vấn.

## Tránh trùng tên sau chuẩn hóa

Hai tên meter khác nhau có thể trở thành cùng một tên Prometheus sau khi chuẩn hóa. Ví dụ `orders.created` và `orders_created` có thể cùng được chuyển thành `orders_created`. Nếu chúng có ý nghĩa hoặc loại meter khác nhau, việc trùng tên có thể gây xung đột metric family hoặc làm dữ liệu khó diễn giải.

Tương tự, tag key như `http.method` và `http_method` có thể chuẩn hóa thành cùng label name. Trước khi chuẩn hóa quy ước tên trong dự án, hãy kiểm tra tên metric và tag key sau chuyển đổi để tránh xung đột.

Các nguyên tắc nên áp dụng:

- Dùng một quy ước đặt tên nhất quán, thường là các thành phần chữ thường phân tách bằng dấu chấm ở lớp Micrometer.
- Không dùng đồng thời nhiều cách viết chỉ khác dấu chấm, dấu gạch dưới hoặc ký tự đặc biệt.
- Không tạo hai meter khác loại có cùng tên metric sau chuẩn hóa.
- Đặt tên tag key nhất quán giữa các module.
- Khi đổi tên meter hoặc tag, kiểm tra lại dashboard, alert và recording rule đang phụ thuộc tên cũ.

`MeterFilter` có thể đổi tên hoặc đổi tag trước khi đăng ký, nhưng mapping cần được thiết kế nhất quán và kiểm thử. Không dùng filter để che giấu xung đột tên mà chưa xác định rõ metric nào là nguồn chuẩn.

## Cardinality sau khi chuyển thành label

Mỗi tổ hợp tên metric và tập label tạo một chuỗi thời gian. Nếu một Timer có 4 giá trị `method`, 5 nhóm `status`, 20 route template và 8 instance, số tổ hợp chuỗi cơ bản có thể đạt:

\[
4 \times 5 \times 20 \times 8 = 3.200
\]

Nếu Timer bật histogram với 15 bucket, số chuỗi bucket có thể lên đến khoảng:

\[
3.200 \times 15 = 48.000
\]

Đây là ước lượng cho bucket, chưa cộng `_count`, `_sum`, `_max`, bucket `+Inf` hoặc các chiều target khác. Vì vậy, tag và histogram phải được chọn theo câu hỏi vận hành thực tế.

Không gắn các giá trị không giới hạn như `userId`, `orderId`, `requestId`, email, token hoặc URL chứa ID làm label. Với HTTP, dùng route template như `/orders/{orderId}` thay vì `/orders/12345`. Dùng log hoặc trace để điều tra từng request cụ thể.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| PromQL báo không tìm thấy metric | Dùng tên Micrometer thay vì tên sau chuẩn hóa | Đọc `/actuator/prometheus` và dùng đúng tên được xuất |
| Metric có hậu tố đơn vị khác dự kiến | Registry thêm base unit hoặc chuẩn hóa theo loại meter | Kiểm tra Timer, `baseUnit` và tên exposition |
| Label name khác tag key trong code | Naming convention đã chuẩn hóa ký tự | Kiểm tra label name trong exposition |
| Metric bị trùng family | Hai tên nguồn chuẩn hóa thành cùng tên hoặc xung đột loại meter | Chuẩn hóa quy ước tên và kiểm tra filter rename |
| Số chuỗi tăng mạnh | Tag có nhiều giá trị hoặc histogram quá nhiều bucket | Giảm cardinality, chuẩn hóa route và chỉ bật histogram cần thiết |
| Không thấy `le` | Histogram chưa được bật hoặc registry dùng kiểu xuất khác | Kiểm tra cấu hình histogram và loại Prometheus client/registry |
| Giá trị thời gian sai đơn vị | Diễn giải giây thành mili giây hoặc tự chuyển đổi hai lần | Timer thường xuất giây; kiểm tra suffix và đơn vị ở exposition |
| Có label `instance` hoặc `job` dù code không khai báo | Prometheus gắn target labels khi scrape | Phân biệt label do ứng dụng xuất với label do scrape config thêm |

## Checklist triển khai

- [ ] Tên meter được đặt theo quy ước nhất quán ở lớp Micrometer.
- [ ] Đã kiểm tra tên metric sau Prometheus naming convention.
- [ ] Không tự thêm hậu tố đơn vị hoặc `_total` khi registry đã quản lý phần đó.
- [ ] Timer được hiểu theo đơn vị xuất, thường là giây.
- [ ] DistributionSummary khai báo `baseUnit` đúng và giá trị ghi nhận dùng cùng đơn vị.
- [ ] Tag key được kiểm tra sau chuẩn hóa thành label name.
- [ ] Label value có tập hữu hạn, không chứa định danh hoặc dữ liệu nhạy cảm.
- [ ] Common tags không xung đột với target labels như `job` và `instance`.
- [ ] Histogram bucket và các measurement mở rộng được tính vào cardinality.
- [ ] Đã kiểm tra `# HELP`, `# TYPE`, tên metric và label trực tiếp tại endpoint exposition.
- [ ] PromQL, dashboard và alert sử dụng tên metric đã xác minh.

Micrometer giữ API meter độc lập với backend; Prometheus registry chuyển tên, đơn vị và tag sang metric name cùng label theo quy ước Prometheus. Một meter có thể tạo nhiều chuỗi khi có nhiều tag hoặc khi Timer/DistributionSummary xuất histogram. Hãy dùng endpoint exposition làm nguồn xác nhận cuối cùng, giữ tên và label ổn định, chuẩn hóa đơn vị trước khi ghi nhận và kiểm soát cardinality để dữ liệu có thể truy vấn đáng tin cậy.
