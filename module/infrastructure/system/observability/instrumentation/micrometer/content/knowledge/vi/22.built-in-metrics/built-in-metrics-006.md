# Phép đo HTTP phía máy chủ và chuẩn hóa đường dẫn yêu cầu

Spring Boot Actuator tích hợp Micrometer để tự động ghi nhận thời gian xử lý HTTP ở phía máy chủ. Meter phổ biến là `http.server.requests`, một `Timer` ghi nhận số request hoàn tất và thời lượng xử lý. Các tag như method, status, outcome và URI giúp phân tích lưu lượng theo nhóm request.

Đường dẫn cần được chuẩn hóa về route template, ví dụ `/orders/{orderId}`, thay vì giữ giá trị thực tế như `/orders/12345`. Nếu dùng URL thô làm tag, mỗi ID tài nguyên hoặc mỗi đường dẫn ngẫu nhiên có thể tạo một chuỗi thời gian mới. Cardinality tăng nhanh làm tốn bộ nhớ, chi phí ingest và khiến dashboard khó sử dụng.

## HTTP server metrics được tạo như thế nào?

Khi ứng dụng dùng Spring Boot Actuator cùng web stack được hỗ trợ, Spring Boot tích hợp observation cho request phía máy chủ. Với Spring MVC, observation được tạo quanh vòng đời xử lý request của servlet; với WebFlux, observation được gắn vào luồng xử lý reactive. Micrometer chuyển observation thành meter và registry xuất dữ liệu đến backend.

Meter mặc định thường có tên:

```text
http.server.requests
```

Đây là `Timer`, nên dữ liệu cơ bản gồm:

- `count`: tổng số request đã hoàn tất được ghi nhận.
- `total time`: tổng thời gian xử lý của các request.
- `max`: thời lượng lớn nhất trong cửa sổ thống kê hiện tại của registry; giá trị có thể hết hạn hoặc giảm khi không còn mẫu mới tùy cấu hình registry.
- Histogram bucket hoặc percentile nếu được cấu hình và registry hỗ trợ.

Các tag phổ biến gồm `method`, `uri`, `status`, `outcome` và thông tin lỗi/exception. Tập tag chính xác có thể khác theo phiên bản Spring Boot, Spring Framework và web stack. Hãy kiểm tra meter thực tế trong Actuator hoặc endpoint exposition thay vì giả định mọi phiên bản đều có cùng tập tag.

Spring Boot cũng có thể xuất các meter riêng của web server hoặc container, chẳng hạn số thread và connection của Tomcat. Các meter đó bổ sung thông tin tài nguyên máy chủ; chúng không thay thế `http.server.requests`, vốn đo thời lượng và số lượng request.

## Những chiều dữ liệu của một request

Các tag giúp chia metric tổng hợp thành nhóm có ý nghĩa vận hành:

| Tag | Ví dụ giá trị | Câu hỏi có thể trả lời |
|---|---|---|
| `method` | `GET`, `POST`, `PUT` | Method nào tạo nhiều lưu lượng hoặc chậm? |
| `uri` | `/orders/{orderId}` | Route nào có latency hoặc error rate cao? |
| `status` | `200`, `404`, `500` | Mã HTTP nào xuất hiện nhiều? |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Tỷ lệ thành công và lỗi theo nhóm ra sao? |
| `exception` hoặc tag lỗi tương đương | Tên exception hoặc giá trị fallback | Nhóm lỗi nào gắn với request? |

Tên tag và cách biểu diễn exception phụ thuộc phiên bản và convention đang dùng. `method`, `status`, `outcome` thường có tập giá trị hữu hạn. `uri` chỉ an toàn cho cardinality khi chứa route template hoặc giá trị fallback có giới hạn.

Không đưa các giá trị sau vào tag HTTP:

- ID người dùng, đơn hàng, tài khoản hoặc session.
- URL đầy đủ có query string.
- Tên file do người dùng gửi lên.
- Request ID, trace ID hoặc correlation ID.
- Nội dung exception tùy ý hoặc thông báo lỗi chứa dữ liệu đầu vào.

Metric dùng để phân tích theo nhóm. Nếu cần tìm một request cụ thể, dùng log hoặc distributed trace với ID tương quan; không tạo một time series cho mỗi request.

## Chuẩn hóa URI bằng route template

Giả sử controller khai báo endpoint:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    @GetMapping("/{orderId}")
    public OrderResponse getOrder(@PathVariable String orderId) {
        return orderService.find(orderId);
    }
}
```

Hai request sau cùng khớp một route:

```text
GET /orders/10001
GET /orders/10002
```

Giá trị tag `uri` được chuẩn hóa theo route template:

```text
/orders/{orderId}
```

Nhờ đó, cả hai request được ghi vào cùng một meter ID cho tổ hợp tag tương ứng. Dữ liệu vẫn có thể phân tích theo method, status và outcome, nhưng không phát sinh một chuỗi mới cho mỗi đơn hàng.

Đường dẫn có query string cũng cần được chuẩn hóa. Các request:

```text
GET /orders?page=1
GET /orders?page=2
GET /orders?page=3
```

nên cùng thuộc route `/orders`; giá trị `page` là tham số đầu vào, không phải chiều metric mặc định. Nếu cần phân tích giá trị query, hãy cân nhắc log hoặc trace, hoặc ánh xạ thành một nhóm hữu hạn có lý do rõ ràng.

### Đường dẫn không khớp route

Request không khớp handler, chẳng hạn một URL 404 ngẫu nhiên, không có route template hợp lệ. Convention mặc định thường dùng giá trị fallback có giới hạn như `UNKNOWN` thay vì lưu toàn bộ đường dẫn. Hành vi cụ thể phụ thuộc web stack và phiên bản Spring Boot.

Đây là điểm quan trọng khi ứng dụng nhận nhiều request không hợp lệ hoặc bị dò quét. Nếu metric ghi raw path cho request 404, các đường dẫn như `/random-a`, `/random-b` và `/random-c` sẽ tạo các chuỗi riêng dù không có endpoint tương ứng. Hãy giữ fallback hữu hạn cho request không khớp route.

## Kiểm tra meter qua Actuator

Thêm Actuator vào ứng dụng:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Expose endpoint `metrics` trong môi trường phát triển:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Sau khi ứng dụng chạy, gọi:

```text
GET /actuator/metrics/http.server.requests
```

Endpoint trả về các measurement và danh sách tag có sẵn cho meter. Có thể lọc theo một tag, ví dụ:

```text
GET /actuator/metrics/http.server.requests?tag=method:GET&tag=uri:/orders/{orderId}
```

Khi gọi URL có dấu ngoặc nhọn hoặc ký tự đặc biệt, client HTTP có thể cần URL-encode giá trị tag. Tên tag và giá trị phải khớp chính xác dữ liệu thực tế của meter. Endpoint Actuator giúp kiểm tra dữ liệu trong registry của ứng dụng; nó không chứng minh Prometheus hoặc backend khác đã scrape/ingest thành công.

Trong production, chỉ expose các endpoint cần thiết và bảo vệ chúng bằng mạng nội bộ, xác thực hoặc chính sách truy cập phù hợp.

## Kiểm tra exposition Prometheus

Nếu ứng dụng dùng Prometheus registry, thêm dependency:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Expose endpoint Prometheus:

```properties
management.endpoints.web.exposure.include=health,prometheus
```

Đọc:

```text
GET /actuator/prometheus
```

Tên meter Micrometer `http.server.requests` thường được chuyển thành các metric dạng:

```text
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_max
```

Tag Micrometer trở thành label Prometheus. Một mẫu minh họa:

```text
http_server_requests_seconds_count{
  method="GET",
  uri="/orders/{orderId}",
  status="200",
  outcome="SUCCESS"
} 42
```

Tên metric, tập label và hậu tố phụ thuộc registry cùng phiên bản. Luôn lấy endpoint exposition làm căn cứ để viết PromQL.

## Đọc lưu lượng và lỗi bằng PromQL

Sau khi xác nhận tên và label thực tế, có thể tính tốc độ request theo route:

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count[5m])
)
```

Tính tỷ lệ request 5xx:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Kết quả là tỷ lệ từ 0 đến 1 cho mỗi route có dữ liệu. Có thể nhân 100 để hiển thị phần trăm. Cần xử lý trường hợp không có request trong cửa sổ để tránh diễn giải mẫu số bằng 0 thành error rate 0%.

Tính thời gian xử lý trung bình theo route:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_sum[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Kết quả là giây/request. Không lấy trung bình các giá trị mean riêng của từng instance; hãy cộng rate của tổng thời gian và số lần rồi chia để có trung bình toàn nhóm.

## Bật histogram để phân tích latency percentile

Timer cơ bản cung cấp count, sum và max. Nếu cần ước lượng p95 hoặc p99 có thể tổng hợp giữa nhiều instance, bật histogram cho meter `http.server.requests`:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 250ms, 500ms, 1s
```

`percentiles-histogram` yêu cầu xuất bucket histogram. `slo` thêm các ranh giới cụ thể có ý nghĩa với mục tiêu vận hành. Tên thuộc tính và cách bind phụ thuộc phiên bản Spring Boot; xác nhận với metadata cấu hình của phiên bản dự án nếu cấu hình không được áp dụng.

Khi histogram được xuất theo Prometheus classic format, có thể truy vấn p95:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Histogram bucket có thể cộng giữa các instance nếu chúng dùng cùng ranh giới. Percentile tính phía client của từng JVM thì không thể lấy trung bình để thành percentile toàn dịch vụ. Histogram cũng tạo thêm nhiều chuỗi; số bucket nhân với tổ hợp tag và số instance, vì vậy chỉ bật khi dashboard hoặc cảnh báo cần.

## Giới hạn cardinality của URI

Cardinality của `http.server.requests` phụ thuộc số tổ hợp method, uri, status, outcome và các tag khác. Nếu `uri` là route template, số giá trị thường gắn với số endpoint được khai báo. Nếu `uri` chứa raw path, số giá trị có thể tăng theo số tài nguyên hoặc số request không hợp lệ.

Ví dụ không an toàn:

```text
/orders/10001
/orders/10002
/orders/10003
```

Ví dụ đã chuẩn hóa:

```text
/orders/{orderId}
```

Với một route có 3 method, 5 nhóm status, 4 outcome và 30 URI template, số tổ hợp tối đa trước khi tính instance là:

\[
3 \times 5 \times 4 \times 30 = 1.800
\]

Nếu có 10 instance, cùng các tổ hợp có thể tạo ra 18.000 chuỗi cơ bản. Bật histogram sẽ nhân thêm số bucket và các measurement liên quan.

Có thể đặt giới hạn bảo vệ bổ sung bằng `MeterFilter`:

```java
@Bean
MeterFilter limitHttpUriValues() {
    return MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            100,
            MeterFilter.deny());
}
```

Giới hạn này từ chối meter mới khi số giá trị `uri` vượt ngưỡng. Nó không chuẩn hóa raw path thành route template và không sửa các meter đã đăng ký trước đó. Biện pháp chính vẫn là dùng route template và fallback hữu hạn ngay tại convention tạo tag.

## Khi nào cần tùy chỉnh observation convention?

Convention mặc định của Spring Boot thường đã dùng route mapping để tạo giá trị URI có cardinality thấp. Chỉ tùy chỉnh khi framework hoặc router của ứng dụng không cung cấp route template phù hợp, hoặc cần một cách nhóm endpoint có chủ đích.

Với Spring MVC/WebFlux dựa trên Observation API, có thể cung cấp `ServerRequestObservationConvention` bean để tùy chỉnh low-cardinality key values. Khi làm vậy:

1. Dùng route pattern đã được router phân giải, ví dụ `/customers/{customerId}`.
2. Ánh xạ endpoint không khớp về một số giá trị fallback hữu hạn như `UNKNOWN` hoặc `NOT_FOUND`.
3. Không lấy raw request URI, query string, user ID hoặc request ID làm low-cardinality value.
4. Giữ các chiều mặc định hữu ích như method, status và outcome, trừ khi có lý do vận hành rõ ràng để thay đổi.
5. Kiểm thử route có path variable, query string, 404 và route lồng nhau để phát hiện cardinality bất ngờ.

API tùy chỉnh observation convention có thể khác giữa các phiên bản Spring Framework. Nên kế thừa convention mặc định tương ứng phiên bản nếu có thể, chỉ thay đổi phần cần thiết và xác nhận bean được web stack sử dụng. Không dùng `MeterFilter` để cố đoán route bằng cách xóa chuỗi số trong raw path; cách đó dễ làm hỏng các route hợp lệ và không xử lý được mọi kiểu ID.

## Tránh ghi nhận trùng request

Khi Actuator đã tự động tạo `http.server.requests`, không cần tạo thêm một Timer cùng tên cho mỗi request trong controller. Làm vậy có thể gây xung đột meter hoặc đếm trùng thời lượng.

Nếu cần đo một đoạn nghiệp vụ bên trong request, hãy dùng metric riêng, ví dụ `checkout.payment.duration`, để phân biệt thời gian xử lý thanh toán với toàn bộ thời gian HTTP. Hai meter trả lời hai câu hỏi khác nhau:

- `http.server.requests`: request mất bao lâu từ góc nhìn server observation.
- `checkout.payment.duration`: thao tác thanh toán bên trong luồng nghiệp vụ mất bao lâu.

Không đặt cùng tên và cùng tag cho hai phép đo có ranh giới thời gian khác nhau.

## Kiểm thử route normalization

Integration test với server Spring Boot thật giúp xác nhận URI tag được tạo theo route template. Ví dụ dưới đây giả định ứng dụng có endpoint `GET /orders/{orderId}` và cấu hình `@SpringBootTest(webEnvironment = RANDOM_PORT)`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpServerMetricsTest {
    @Autowired
    TestRestTemplate http;

    @Autowired
    MeterRegistry registry;

    @Test
    void groupsDifferentOrderIdsUnderOneRouteTemplate() {
        Timer before = registry.find("http.server.requests")
                .tag("method", "GET")
                .tag("uri", "/orders/{orderId}")
                .timer();
        long initialCount = before == null ? 0 : before.count();

        ResponseEntity<String> first = http.getForEntity("/orders/10001", String.class);
        ResponseEntity<String> second = http.getForEntity("/orders/10002", String.class);

        assertThat(first.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(second.getStatusCode().is2xxSuccessful()).isTrue();

        Timer after = registry.find("http.server.requests")
                .tag("method", "GET")
                .tag("uri", "/orders/{orderId}")
                .timer();

        assertThat(after).isNotNull();
        assertThat(after.count()).isGreaterThanOrEqualTo(initialCount + 2);
    }
}
```

Test gọi hai ID khác nhau và xác nhận count của cùng route template tăng ít nhất hai lần. Trong dự án thực tế, có thể cần thêm tag `status` hoặc `outcome` khi tìm meter nếu convention của phiên bản đang dùng yêu cầu. Tránh assert tổng count tuyệt đối vì các test khác hoặc request nền có thể dùng cùng registry.

Nên bổ sung trường hợp 404 với nhiều đường dẫn ngẫu nhiên và xác nhận chúng được gom vào một giá trị fallback hữu hạn. Đây là cách kiểm tra quan trọng để phát hiện raw path lọt vào tag `uri`.

## Quy trình điều tra cardinality HTTP tăng bất thường

Khi số chuỗi `http.server.requests` tăng nhanh:

1. Kiểm tra số lượng giá trị label `uri` ở backend.
2. Liệt kê một số giá trị `uri` dài hoặc có ID để tìm raw path.
3. So sánh route template với request mapping của ứng dụng.
4. Kiểm tra request không khớp route và cách convention gán fallback.
5. Kiểm tra custom observation convention, filter rename và common tags.
6. Tính thêm số method, status, outcome, instance và histogram bucket.
7. Sửa nguồn tạo URI tag, sau đó kiểm tra lại endpoint exposition và cardinality backend.

Đừng chỉ giảm giới hạn `maximumAllowableTags` để che vấn đề. Filter có thể làm mất metric của route hợp lệ sau khi chạm ngưỡng. Cần sửa cách chuẩn hóa URI trước, sau đó dùng giới hạn như hàng rào bảo vệ.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy `http.server.requests` | Actuator thiếu, web stack không được instrument hoặc registry chưa được cấu hình | Kiểm tra dependency, web stack và registry bean |
| Tag `uri` chứa ID từng request | Raw path được dùng thay route template hoặc convention tùy chỉnh sai | Dùng route pattern và fallback hữu hạn |
| Nhiều request 404 tạo nhiều chuỗi | Đường dẫn không khớp route bị ghi nguyên văn | Ánh xạ unmatched request về giá trị cố định |
| PromQL không tìm thấy meter | Dùng tên Micrometer thay tên Prometheus đã chuẩn hóa | Đọc `/actuator/prometheus` để xác nhận metric name |
| p95 không có dữ liệu | Histogram chưa bật hoặc registry không xuất bucket | Kiểm tra cấu hình distribution và exposition |
| Timer count lớn hơn số request dự kiến | Request bị ghi nhận thêm thủ công hoặc có nhiều lớp instrumentation trùng | Dùng built-in observation và metric riêng cho đoạn nghiệp vụ |
| Filter giới hạn làm mất một số route | Số URI vượt ngưỡng hoặc filter được áp dụng sau khi meter đã tạo | Chuẩn hóa route trước và cấu hình filter sớm |
| Metric HTTP khác nhau giữa các phiên bản | Tag/convention thay đổi theo Spring Boot và web stack | Kiểm tra tag thực tế và tài liệu đúng phiên bản |

## Checklist triển khai

- [ ] `http.server.requests` được tạo bởi instrumentation của Spring Boot.
- [ ] Đã xác nhận tập tag thực tế của phiên bản và web stack đang dùng.
- [ ] Tag `uri` sử dụng route template thay vì raw path.
- [ ] Request 404 hoặc không khớp route được gom vào fallback hữu hạn.
- [ ] Query string, ID, request ID và dữ liệu nhạy cảm không trở thành tag.
- [ ] Tag method, status và outcome đủ để phân tích nhưng vẫn có cardinality hữu hạn.
- [ ] Đã kiểm tra meter qua `/actuator/metrics` và exposition backend.
- [ ] Histogram chỉ bật khi cần p95/p99 hoặc SLO bucket.
- [ ] Đã tính cardinality theo URI, method, status, instance và bucket.
- [ ] Không tạo Timer thủ công trùng với built-in HTTP request timer.
- [ ] Integration test xác nhận nhiều ID cùng route template dùng chung một nhóm metric.

HTTP server metrics cho biết request nào đang tạo lưu lượng, độ trễ và lỗi ở phía máy chủ. Giá trị `uri` cần phản ánh route template để mọi ID tài nguyên cùng endpoint được gom vào một nhóm. Khi giữ tag hữu hạn, xác minh convention thực tế và kiểm tra exposition, `http.server.requests` có thể hỗ trợ dashboard, cảnh báo latency và điều tra cardinality mà không tạo hàng loạt chuỗi theo từng URL.
