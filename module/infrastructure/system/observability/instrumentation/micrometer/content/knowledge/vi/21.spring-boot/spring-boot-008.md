# Phân biệt tên meter trong Actuator với tên được xuất sang Prometheus

Trong ứng dụng Spring Boot dùng Micrometer, cùng một meter có thể được nhìn thấy dưới hai tên khác nhau tùy endpoint đang truy cập. Endpoint Actuator Metrics hiển thị tên meter theo định danh Micrometer mà ứng dụng đăng ký. Endpoint Prometheus hiển thị tên đã được chuyển đổi theo quy ước đặt tên của Prometheus, đồng thời có thể bổ sung đơn vị và hậu tố theo loại metric.

Ví dụ, mã ứng dụng đăng ký **orders.created**. Actuator có thể tra cứu meter bằng tên **orders.created**, trong khi Prometheus thường nhận counter với tên **orders_created_total**. Đây là cùng một phép đo ở hai lớp biểu diễn khác nhau, không phải hai meter nghiệp vụ riêng biệt.

## 1. Hai endpoint, hai mục đích

Spring Boot Actuator và Micrometer cung cấp hai endpoint thường được dùng khi kiểm tra metrics:

| Endpoint | Mục đích | Dạng dữ liệu |
| --- | --- | --- |
| /actuator/metrics | Liệt kê meter mà ứng dụng đang quản lý | Danh sách tên meter Micrometer |
| /actuator/metrics/{name} | Xem measurement và tags của một meter | JSON theo Meter.Id |
| /actuator/prometheus | Cung cấp dữ liệu để Prometheus scrape | Prometheus exposition format |

Endpoint /actuator/metrics giúp nhà phát triển kiểm tra instrumentation trong ứng dụng. Endpoint /actuator/prometheus phục vụ hệ thống Prometheus thu thập dữ liệu. Hai endpoint đọc cùng registry nhưng trình bày dữ liệu theo hai hợp đồng khác nhau.

~~~mermaid
flowchart TD
    A["Mã ứng dụng"] --> B["MeterRegistry"]
    B --> C["Meter.Id<br/>orders.created"]
    B --> D["Actuator Metrics endpoint"]
    B --> E["PrometheusMeterRegistry"]
    D --> F["/actuator/metrics/orders.created<br/>JSON, tên Micrometer"]
    E --> G["Prometheus NamingConvention"]
    G --> H["/actuator/prometheus<br/>orders_created_total"]
~~~

Không dùng tên đã chuẩn hóa cho Prometheus để tra cứu endpoint Actuator Metrics. Ngược lại, không giả định tên canonical có dấu chấm trong mã sẽ xuất hiện nguyên dạng trong Prometheus.

## 2. Tên canonical của meter trong Micrometer

Khi đăng ký meter, ứng dụng cung cấp tên và tags cho MeterRegistry:

~~~java
Counter created = registry.counter(
    "orders.created",
    "channel", "web"
);
created.increment();
~~~

Tên orders.created là tên canonical mà instrumentation sử dụng. Nó là một phần của Meter.Id, cùng với tags và metadata khác. Trong Actuator Metrics, tên này được dùng để tìm meter:

~~~text
GET /actuator/metrics/orders.created
~~~

Có thể lọc theo tag:

~~~text
GET /actuator/metrics/orders.created?tag=channel:web
~~~

Phản hồi JSON có thể có cấu trúc tương tự:

~~~json
{
  "name": "orders.created",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 12.0
    }
  ],
  "availableTags": [
    {
      "tag": "channel",
      "values": ["web", "mobile"]
    }
  ]
}
~~~

Phản hồi thực tế còn phụ thuộc meter, tags, description, base unit và phiên bản Spring Boot. Với Timer, danh sách measurements có thể bao gồm COUNT, TOTAL_TIME và MAX. Endpoint này cho biết meter mà registry đang quản lý và các thống kê Micrometer cung cấp; nó không mô phỏng định dạng scrape của Prometheus.

### Quy tắc đặt tên trong mã

- Dùng tên canonical có ý nghĩa, thường theo dạng phân cấp với dấu chấm, ví dụ orders.create.duration.
- Giữ tên ổn định giữa các phiên bản ứng dụng.
- Dùng tags để phân loại theo chiều có tập giá trị hữu hạn.
- Không mã hóa channel, user ID hoặc request ID vào tên meter.
- Đặt base unit và description khi chúng giúp người đọc hiểu đại lượng.

Tên canonical là hợp đồng ở lớp instrumentation. Nó không cần tuân theo chính xác quy tắc ký tự của mọi backend vì registry chịu trách nhiệm chuyển đổi khi export.

## 3. Prometheus NamingConvention chuyển đổi tên như thế nào?

Prometheus có quy ước đặt tên metric và label riêng. Prometheus registry áp dụng NamingConvention để chuyển tên Micrometer thành tên hợp lệ và phù hợp với semantics của Prometheus.

Các thay đổi thường gặp:

- Dấu chấm hoặc dấu gạch nối trong tên canonical được chuyển thành dấu gạch dưới.
- Ký tự không phù hợp với quy tắc tên metric được chuẩn hóa.
- Đơn vị được thêm vào tên khi phù hợp với quy ước Prometheus.
- Counter được biểu diễn với hậu tố _total.
- Timer được biểu diễn theo đơn vị cơ sở là giây và có các series count, sum, max; histogram có thêm bucket nếu được bật.

Ví dụ tổng quát:

| Meter trong mã Micrometer | Dạng tên thường thấy trong Prometheus |
| --- | --- |
| orders.created (Counter) | orders_created_total |
| orders.queue.depth (Gauge) | orders_queue_depth |
| orders.create.duration (Timer) | orders_create_duration_seconds_count, _sum, _max |
| uploads.payload.size (DistributionSummary, base unit bytes) | uploads_payload_size_bytes_count, _sum, _max |

Tên cụ thể còn phụ thuộc loại meter, base unit, cấu hình histogram/percentile, naming convention và phiên bản registry/client. Vì vậy, hãy xem exposition thực tế khi viết truy vấn.

## 4. Counter: hậu tố total trong Prometheus

Counter Micrometer biểu diễn một giá trị tích lũy chỉ tăng trong vòng đời meter. Prometheus biểu diễn loại metric này như counter và thường xuất tên series với hậu tố _total.

Mã instrumentation:

~~~java
registry.counter(
    "orders.created",
    "channel", "web"
).increment();
~~~

Prometheus exposition có thể trông như sau:

~~~text
# HELP orders_created_total
# TYPE orders_created_total counter
orders_created_total{channel="web"} 12.0
~~~

Actuator Metrics vẫn tra cứu bằng orders.created, còn truy vấn Prometheus dùng orders_created_total. Khi viết PromQL, dùng tên đã xuất:

~~~promql
sum(rate(orders_created_total[5m]))
~~~

Không tự thêm hậu tố _total vào tên canonical khi đăng ký Counter chỉ vì thấy hậu tố này ở Prometheus. Registry đã xử lý việc biểu diễn counter theo quy ước của backend. Nếu tên canonical vốn có hậu tố hoặc có cấu hình đặc biệt, hãy xác minh exposition để tránh hậu tố lặp hoặc xung đột.

## 5. Timer: đơn vị giây và các series thành phần

Timer ghi nhận số lần thực hiện và thời gian. Micrometer cho phép ghi bằng nhiều đơn vị, nhưng Prometheus quy ước thời gian theo giây. Registry chuyển đổi giá trị khi export.

~~~java
Timer timer = Timer.builder("orders.create.duration")
    .description("Thời gian tạo đơn hàng")
    .tag("channel", "web")
    .register(registry);

timer.record(() -> orderService.create(command));
~~~

Trong Prometheus, các series phổ biến gồm:

~~~text
orders_create_duration_seconds_count{channel="web"} 12
orders_create_duration_seconds_sum{channel="web"} 1.84
orders_create_duration_seconds_max{channel="web"} 0.42
~~~

Ý nghĩa:

- _count: số lần ghi nhận.
- _sum: tổng thời gian của các lần ghi nhận, tính bằng giây.
- _max: giá trị lớn nhất theo semantics thống kê của Timer và cửa sổ mà registry duy trì.

Nếu bật histogram, Prometheus còn nhận các bucket:

~~~text
orders_create_duration_seconds_bucket{channel="web",le="0.1"} 4
orders_create_duration_seconds_bucket{channel="web",le="0.3"} 9
orders_create_duration_seconds_bucket{channel="web",le="+Inf"} 12
~~~

Bucket là số lượng quan sát tích lũy có giá trị nhỏ hơn hoặc bằng ngưỡng le. Tên metric canonical vẫn là orders.create.duration trong Micrometer và Actuator; các hậu tố _seconds_count, _seconds_sum, _seconds_bucket thuộc cách biểu diễn của Prometheus.

Truy vấn p95 trên histogram có thể dùng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_create_duration_seconds_bucket[5m])
  )
)
~~~

Truy vấn này cần histogram được bật và bucket được export. Nếu chỉ có count/sum/max mà không có bucket, không thể tính histogram quantile bằng truy vấn trên.

## 6. DistributionSummary và base unit

DistributionSummary ghi nhận phân phối của một đại lượng không nhất thiết là thời gian, chẳng hạn kích thước payload. Base unit giúp registry chuyển đổi và đặt tên phù hợp với backend.

~~~java
DistributionSummary payloadSize = DistributionSummary
    .builder("uploads.payload.size")
    .description("Kích thước payload được tiếp nhận")
    .baseUnit("bytes")
    .register(registry);

payloadSize.record(64 * 1024);
~~~

Prometheus có thể xuất các series dạng:

~~~text
uploads_payload_size_bytes_count 1
uploads_payload_size_bytes_sum 65536
uploads_payload_size_bytes_max 65536
~~~

Nếu không khai báo base unit, tên xuất có thể không chứa phần đơn vị. Không thêm đơn vị vào tên canonical rồi đồng thời khai báo base unit nếu điều đó làm tên xuất lặp đơn vị. Hãy chọn một quy ước nhất quán và kiểm tra tên cuối cùng.

## 7. Tags trong Actuator trở thành labels trong Prometheus

Micrometer gọi các chiều phân loại là tags. Prometheus gọi các chiều này là labels. Giá trị thường được giữ nguyên về ý nghĩa, trong khi key có thể được chuẩn hóa để phù hợp quy tắc đặt tên của Prometheus.

Mã:

~~~java
registry.counter(
    "orders.created",
    "channel", "web",
    "result", "success"
).increment();
~~~

Actuator JSON có thể hiển thị:

~~~json
{
  "name": "orders.created",
  "availableTags": [
    {"tag": "channel", "values": ["web"]},
    {"tag": "result", "values": ["success"]}
  ]
}
~~~

Prometheus exposition có thể hiển thị:

~~~text
orders_created_total{channel="web",result="success"} 1.0
~~~

Tags không làm thay đổi tên canonical của meter; chúng tạo các chiều phân biệt meter hoặc series. Trong Prometheus, mỗi tổ hợp label values có thể tạo một time series riêng.

### Common tags

Common tags được thêm ở cấp registry, ví dụ service và environment. Chúng thường xuất hiện trong cả endpoint Actuator lẫn labels của Prometheus, nhưng vẫn chịu quy tắc chuyển đổi tên label của registry.

~~~java
registry.config().commonTags(
    "service", "order-service",
    "environment", "production"
);
~~~

Không đưa request ID, user ID, email hoặc order ID vào tags. Cardinality cao làm tăng số time series, dung lượng lưu trữ và chi phí truy vấn.

## 8. Cấu hình endpoint trong Spring Boot

Để dùng cả hai endpoint, ứng dụng cần Actuator và Prometheus registry:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Để expose cả metrics endpoint và Prometheus scrape endpoint:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

Sau khi ứng dụng chạy:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/orders.created
curl "http://localhost:8080/actuator/metrics/orders.created?tag=channel:web"
curl http://localhost:8080/actuator/prometheus
~~~

Lệnh thứ hai dùng tên canonical của Micrometer. Lệnh cuối trả về exposition để Prometheus scrape, trong đó tên đã được chuẩn hóa. Nếu chỉ expose prometheus, endpoint metrics có thể không truy cập được; ngược lại, expose metrics không tự tạo Prometheus registry nếu dependency tương ứng chưa có.

Trong production, cần cấu hình bảo mật cho Actuator endpoints. Không nên expose toàn bộ management endpoints ra mạng công khai chỉ để tiện debug.

## 9. Đọc cùng một meter qua hai endpoint

Giả sử service đăng ký:

~~~java
Counter counter = registry.counter(
    "orders.created",
    "channel", "web"
);

counter.increment(3);
~~~

Actuator lookup:

~~~text
GET /actuator/metrics/orders.created?tag=channel:web
~~~

Prometheus exposition:

~~~text
orders_created_total{channel="web"} 3.0
~~~

Hai kết quả nói về cùng một meter:

| Thuộc tính | Actuator Metrics | Prometheus |
| --- | --- | --- |
| Tên | orders.created | orders_created_total |
| Tag/label | channel=web | channel="web" |
| Dạng dữ liệu | JSON measurements | Text exposition |
| Người sử dụng chính | Developer, operator khi debug ứng dụng | Prometheus scraper và PromQL |
| Quy ước đơn vị/hậu tố | Theo Meter.Id và measurements | Theo Prometheus NamingConvention |

Khi debug, bắt đầu từ tên canonical trong Actuator để xác nhận instrumentation có đăng ký meter. Sau đó kiểm tra exposition để xác nhận registry đã chuyển đổi và xuất meter đúng như mong muốn.

## 10. Va chạm tên sau khi chuẩn hóa

Hai tên canonical khác nhau có thể trở thành cùng một tên sau khi chuyển sang định dạng Prometheus. Ví dụ:

~~~text
cache.hit-rate
cache.hit_rate
~~~

Cả hai có thể được chuẩn hóa thành:

~~~text
cache_hit_rate
~~~

Ngoài ra, quy tắc thêm đơn vị hoặc hậu tố theo loại meter có thể làm hai tên canonical khác nhau trở nên khó phân biệt ở backend. Registry có thể từ chối meter, cảnh báo hoặc xử lý theo implementation khi phát hiện xung đột.

Để tránh:

- Dùng một quy ước tên canonical nhất quán.
- Không dùng dấu chấm, dấu gạch dưới và dấu gạch nối tùy tiện cho cùng một khái niệm.
- Không tạo hai meter cùng mục đích nhưng khác loại với tên dễ chuẩn hóa thành một.
- Đặt base unit rõ ràng và không lặp đơn vị trong tên.
- Kiểm tra exposition sau khi thêm meter mới.

Nếu Actuator hiển thị hai tên khác nhau nhưng Prometheus chỉ thấy một series hoặc gặp lỗi đăng ký, hãy kiểm tra kết quả chuẩn hóa và các hậu tố do registry thêm vào.

## 11. NamingConvention và phiên bản registry

Micrometer dùng NamingConvention của registry để chuyển tên meter và tag key sang quy ước backend. Prometheus registry cung cấp convention riêng; naming convention có thể khác với registry khác như StatsD hoặc OTLP.

Vì vậy:

- Không giả định tên xuất từ Prometheus giống tên xuất từ OTLP hoặc StatsD.
- Không viết truy vấn PromQL dựa trên tên canonical trong mã nếu chưa xác nhận tên exposition.
- Khi nâng Micrometer hoặc Prometheus Java Client, kiểm tra lại tên, unit, suffix và histogram exposition.
- Nếu ứng dụng tùy chỉnh NamingConvention, ghi nhận thay đổi như một phần hợp đồng metrics vì dashboard và alert có thể phụ thuộc tên đã xuất.

Một lần nâng cấp registry có thể giữ nguyên code instrumentation nhưng thay đổi chi tiết exposition. Đây là lý do cần integration test cho endpoint /actuator/prometheus thay vì chỉ kiểm thử Counter/Timer bằng SimpleMeterRegistry.

## 12. Kiểm thử và chẩn đoán

### Kiểm tra instrumentation qua Actuator

Sau khi gọi thao tác nghiệp vụ, truy cập:

~~~text
/actuator/metrics/orders.created
~~~

Nếu meter không xuất hiện, kiểm tra:

- Code có thực sự gọi registry.counter(...) hoặc đăng ký meter không.
- Meter có bị MeterFilter từ chối không.
- Có đang inject đúng registry được Spring Boot quản lý không.
- Tên canonical và tags có đúng không.

### Kiểm tra export qua Prometheus

Truy cập:

~~~text
/actuator/prometheus
~~~

Tìm tên đã chuẩn hóa, ví dụ orders_created_total. Nếu Actuator có meter nhưng Prometheus exposition không có, kiểm tra:

- Prometheus registry dependency và auto-configuration.
- MeterFilter hoặc cấu hình export.
- Xung đột tên sau NamingConvention.
- Endpoint có expose và registry có scrape format phù hợp không.

### Integration test với PrometheusMeterRegistry

Có thể kiểm tra exposition trực tiếp bằng registry thật:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PrometheusNamingTest {

    @Test
    void exportsCounterUsingPrometheusName() {
        PrometheusMeterRegistry registry =
            new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

        Counter counter = registry.counter(
            "orders.created",
            "channel", "web"
        );
        counter.increment();

        String exposition = registry.scrape();

        assertThat(exposition)
            .contains("orders_created_total")
            .contains("channel=\"web\"");

        registry.close();
    }
}
~~~

Package io.micrometer.prometheusmetrics áp dụng cho Prometheus registry dùng client 1.x trong các dòng Micrometer tương ứng. Nếu dự án dùng artifact simpleclient cũ, package import sẽ khác. Hãy dùng đúng registry artifact do dependency management của dự án chọn.

Kiểm thử này xác nhận tên trong exposition của registry. Integration test Spring Boot có thể bổ sung bước gọi HTTP đến /actuator/prometheus để kiểm tra cả endpoint mapping và exposure.

## 13. Checklist khi đối chiếu tên metric

- [ ] Đã xác định tên canonical mà code đăng ký.
- [ ] Dùng tên canonical để truy vấn /actuator/metrics/{name}.
- [ ] Đã bật và expose endpoint metrics nếu cần debug bằng Actuator.
- [ ] Đã thêm Prometheus registry dependency đúng phiên bản.
- [ ] Dùng exposition thực tế để xác định tên metric Prometheus.
- [ ] Đã kiểm tra hậu tố _total của Counter.
- [ ] Đã kiểm tra đơn vị giây và hậu tố của Timer.
- [ ] Đã kiểm tra base unit của DistributionSummary.
- [ ] Đã đối chiếu tags trong Actuator với labels trong Prometheus.
- [ ] Đã kiểm tra va chạm sau khi chuẩn hóa tên.
- [ ] Đã xác minh histogram buckets nếu truy vấn percentile/SLO.
- [ ] Đã có integration test cho Prometheus exposition.

Tên meter trong Actuator phản ánh định danh Micrometer mà ứng dụng đăng ký. Tên trong Prometheus là kết quả của NamingConvention cùng quy tắc biểu diễn loại metric và đơn vị. Hãy dùng tên canonical để debug instrumentation qua Actuator và dùng tên đã xuất để viết PromQL. Kiểm tra cả hai endpoint giúp phân biệt lỗi đăng ký meter với lỗi chuyển đổi hoặc export.
