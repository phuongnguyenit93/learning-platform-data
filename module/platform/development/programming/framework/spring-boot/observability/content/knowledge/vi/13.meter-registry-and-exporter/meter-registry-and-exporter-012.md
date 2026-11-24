# Kiểm thử metric export

Trong chương **Meter registry và exporter** của mô-đun **SPRING_BOOT_OBSERVABILITY**, **kiểm thử metric export** là việc xác minh một số đo được tạo trong ứng dụng Spring Boot **thực sự đi đến đúng nơi thu thập, có tên/nhãn/đơn vị chính xác và vẫn được thu thập ổn định**. Việc gọi `Counter.increment()` không tự chứng minh Prometheus đã nhận dữ liệu; tương tự, một endpoint `/actuator/prometheus` trả HTTP 200 chưa bảo đảm dashboard đang truy vấn đúng series.

Mô-đun học cách thiết lập observability bằng **Micrometer Observation, metrics, logs và distributed tracing**, có xét context propagation, cardinality, exporter và sampling để điều tra lỗi, độ trễ và hành vi thực tế. Bài này tập trung vào nhánh **metrics** và cách kiểm chứng từng ranh giới trong pipeline; logs và traces được dùng như nguồn đối chiếu chứ không thay thế phép thử metrics.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **kiểm thử meter tại ứng dụng**, **kiểm thử exporter**, **kiểm thử scrape/push** và **kiểm thử truy vấn backend**.
2. Viết unit test cho `Counter` và `Timer` bằng `SimpleMeterRegistry`.
3. Viết integration test Spring Boot xác nhận metric do service tạo xuất hiện ở `/actuator/metrics` và `/actuator/prometheus`.
4. Kiểm tra tên metric được đổi theo backend, labels, units, histogram và counter reset.
5. Xác minh một Prometheus target đang **UP**, scrape thành công và có mẫu dữ liệu hữu ích, thay vì chỉ nhìn HTTP status.
6. Phân biệt lỗi instrumentation, registry, endpoint exposure/security, network, scraper và query.
7. Kiểm thử các trường hợp lỗi thực tế như high-cardinality tags, thiếu histogram, sai authentication và khác biệt giữa metrics với trace sampling.
8. Xây dựng checklist kiểm chứng trước khi triển khai exporter trên môi trường thực.

## 2. Định nghĩa “export thành công” ở từng tầng

Một phép đo chạy qua nhiều tầng. Mỗi tầng có thể hoạt động hoặc thất bại độc lập:

~~~mermaid
flowchart LR
    A["Nghiệp vụ gọi Counter/Timer<br/>hoặc Micrometer Observation"]
    B["MeterRegistry / metrics handler"]
    C["Registry cho backend<br/>ví dụ Prometheus"]
    D["Actuator /prometheus<br/>endpoint"]
    E["Prometheus scrape target"]
    F["Prometheus TSDB"]
    G["PromQL / dashboard / alert"]
    A --> B --> C --> D --> E --> F --> G
~~~

Với registry **push** như một pipeline OTLP metrics, nhánh từ registry có thể là publisher → collector → backend, không đi qua `/actuator/prometheus`. Bài tập chính dùng Prometheus **pull/scrape** để dễ kiểm thử.

| Tầng kiểm chứng | Câu hỏi | Bằng chứng phù hợp |
| --- | --- | --- |
| **Instrumentation** | Mã đo có thực sự được thực thi? | Unit test counter/timer thay đổi khi gọi service. |
| **MeterRegistry** | Meter đúng tên và tags có được đăng ký? | `MeterRegistry.find(...)` hoặc Actuator metrics endpoint. |
| **Exporter** | Registry tạo dữ liệu có tên, đơn vị và labels phù hợp backend? | Nội dung thô của `/actuator/prometheus`. |
| **Transport/scrape** | Prometheus có kết nối, xác thực và đọc payload thành công? | Target status, `up`, scrape metrics và logs scraper. |
| **Storage/query** | Samples có mặt trong backend và truy vấn được? | PromQL theo job/instance/labels đúng. |
| **Vận hành** | Khi service lỗi, restart hoặc thay đổi cấu hình, pipeline có còn đáng tin? | Kiểm thử âm tính, cảnh báo scrape và kiểm tra dữ liệu sau deploy. |

**Đừng coi một phép thử ở tầng trên thay thế toàn bộ các tầng dưới.** Ví dụ unit test thành công không chứng minh exporter đã cấu hình. Ngược lại, `up=1` chỉ chứng minh Prometheus scrape target thành công trong thời điểm đo, không chứng minh tất cả metrics nghiệp vụ đều tồn tại.

## 3. Chuẩn bị ứng dụng Spring Boot

Ví dụ bên dưới dành cho một ứng dụng Spring Boot **3.x, Java 17+**, dùng Spring MVC và dependency management tương thích với phiên bản Spring Boot đang triển khai.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Một cấu hình **chỉ cho local hoặc môi trường thử nghiệm được bảo vệ**:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

Ý nghĩa:

- **Actuator** cung cấp hạ tầng metrics và endpoint chẩn đoán.
- **Prometheus registry** xuất dữ liệu theo định dạng có thể scrape.
- **Exposure** quyết định những Actuator endpoint được công bố qua HTTP, nhưng **không thay thế authentication, authorization và network policy**.
- **Common tags** giúp phân biệt application/environment, nhưng không được chứa request ID hoặc dữ liệu biến đổi theo từng yêu cầu.

Cần xác minh môi trường thật có dùng đúng management port, base path và security chain hay không. Nếu thêm `spring-boot-starter-security` hoặc một `SecurityFilterChain` tùy chỉnh, các request kiểm thử phải có xác thực phù hợp. Không vô hiệu hóa security chỉ để các bài test trả HTTP 200.

### Endpoint nào để kiểm tra?

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` trả JSON liệt kê các meter đã được ghi nhận. `/actuator/prometheus` trả dữ liệu exporter để scraper đọc. Nếu ứng dụng có management port riêng, phải thay cổng 8080 bằng cổng và host của management endpoint.

## 4. Tạo một metric có kết quả dự đoán được

Để test đáng tin, dùng một **metric probe riêng** có tên cố định, tags hữu hạn và hành vi đo được; không phụ thuộc việc máy có sắp chạy GC hay bao nhiêu HTTP request do test framework tạo.

Ví dụ một Spring service:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class ExportProbeMetrics {

    private final MeterRegistry meters;

    public ExportProbeMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void recordSuccess() {
        meters.counter("demo.export.requests", "outcome", "success")
                .increment();

        // Số liệu tổng hợp có kiểm soát cho bài test;
        // trong ứng dụng thật hãy đo duration thực tế.
        meters.timer("demo.export.duration", "operation", "probe")
                .record(25, TimeUnit.MILLISECONDS);
    }
}
~~~

Khi gọi `recordSuccess()` một lần:

- Counter `demo.export.requests` với `outcome=success` tăng thêm 1.
- Timer `demo.export.duration` với `operation=probe` có thêm một mẫu 25 ms.
- Dữ liệu do code tạo nằm trong `MeterRegistry` mà Spring Boot inject; registry có thể phân phối cho các exporters phù hợp.

Trong nghiệp vụ thật, không hard-code duration 25 ms; thay bằng `Timer.record(...)` bao quanh lời gọi hoặc sử dụng Micrometer Observation để ghi duration của một operation. Đoạn code này chỉ tạo **mốc kiểm chứng có thể lặp lại** cho các bài test export.

Một lỗi cần tránh là thay giá trị `outcome` bằng request ID:

~~~java
// Không làm: một tag mới gần như cho mỗi request.
meters.counter("demo.export.requests", "request.id", requestId)
        .increment();
~~~

Dùng `outcome=success/error` vì có tập giá trị nhỏ. High-cardinality identifiers phải được quản lý trong logs hoặc trace attributes có chính sách phù hợp, không đưa vào metrics labels.

## 5. Unit test: meter có được ghi đúng không?

Kiểm thử đầu tiên không cần web server hay Prometheus. `SimpleMeterRegistry` giúp giữ phép đo trong bộ nhớ, phù hợp với unit test logic instrumentation.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ExportProbeMetricsTest {

    @Test
    void recordsExpectedCounterAndTimer() {
        try (SimpleMeterRegistry meters = new SimpleMeterRegistry()) {
            ExportProbeMetrics probe = new ExportProbeMetrics(meters);

            probe.recordSuccess();
            probe.recordSuccess();

            assertThat(meters.get("demo.export.requests")
                    .tag("outcome", "success")
                    .counter()
                    .count()).isEqualTo(2.0);

            var timer = meters.get("demo.export.duration")
                    .tag("operation", "probe")
                    .timer();

            assertThat(timer.count()).isEqualTo(2L);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
                    .isCloseTo(50.0,
                            org.assertj.core.data.Offset.offset(0.001));
        }
    }
}
~~~

Từ unit test này, bạn biết:

1. Tên và tags ở tầng Micrometer đã đúng.
2. Hai lần gọi làm counter tăng hai đơn vị.
3. Timer có hai mẫu, tổng duration 50 ms theo dữ liệu test.
4. Không có nhãn biến đổi theo mỗi request trong phép đo này.

**Chưa chứng minh được:** endpoint Actuator được expose, registry Prometheus tồn tại, scraper có quyền truy cập hoặc backend đã nhận samples. `SimpleMeterRegistry` không phải bộ giả lập toàn bộ Prometheus pipeline.

Nếu test không tìm thấy meter, hãy xem lại code path, tên meter, tags và registry được truyền vào. Không xử lý lỗi này bằng cách sửa Prometheus scrape config: lỗi nằm trước exporter.

## 6. Integration test: từ Spring bean đến endpoint export

Bước tiếp theo kiểm tra **registry thật do Spring Boot cấu hình** và các endpoint Actuator chạy qua HTTP. Ví dụ với ứng dụng Spring MVC, một Spring Boot application hiện có và `spring-boot-starter-test`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.endpoints.web.exposure.include=health,metrics,prometheus"
    }
)
class MetricsExportIntegrationTest {

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private ExportProbeMetrics probe;

    @Test
    void exportsCustomMetricViaPrometheus() {
        // Tạo dữ liệu trước khi đọc exporter.
        probe.recordSuccess();

        ResponseEntity<String> diagnostic = http.getForEntity(
                "/actuator/metrics/demo.export.requests", String.class);

        assertThat(diagnostic.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(diagnostic.getBody())
                .contains("demo.export.requests")
                .contains("COUNT");

        ResponseEntity<String> scrape = http.getForEntity(
                "/actuator/prometheus", String.class);

        assertThat(scrape.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(scrape.getBody())
                .contains("demo_export_requests")
                .contains("outcome=\"success\"");
    }
}
~~~

Đây là test **minh họa cho Spring Boot 3.x**. Nó giả định dự án có một `@SpringBootApplication` phát hiện được, không tách management server sang cổng riêng, Prometheus registry có trên test classpath và endpoint được phép truy cập trong test context. Nếu hệ thống bật Spring Security, phải dùng test client với identity được ủy quyền thay vì bỏ xác thực.

**Tại sao assertions không cố định toàn bộ chuỗi metric?** Actuator hiển thị tên theo Micrometer (`demo.export.requests`), còn Prometheus exporter dùng naming convention theo backend (`demo_export_requests...`, có thể có hậu tố như `_total`). Kiểm thử có thể kiểm tra tên/labels cần thiết, sau đó thêm assertion cụ thể theo phiên bản exporter thực tế của dự án. Không dùng `contains("demo")` quá rộng làm bằng chứng duy nhất.

Kiểm thử trên chưa cần một Prometheus server: nó chứng minh **Spring Boot đã tạo dữ liệu exporter tại HTTP endpoint**. Bước kiểm tra backend vẫn phải thực hiện riêng.

### Lưu ý về tính cô lập của test

- Dùng tên metric dành riêng cho test và tags ổn định; đừng sửa các registry toàn cục mà không khôi phục.
- Nếu nhiều test dùng chung Spring ApplicationContext, counter có thể **tích lũy** giữa các test. Tránh assertion “count phải bằng đúng 1” trong test tích hợp tái sử dụng context; hoặc tạo bối cảnh test riêng và kiểm soát lifecycle.
- Không phụ thuộc thứ tự xuất hiện của các series, tags hay comment trong Prometheus text: thứ tự đó không phải API nghiệp vụ.
- Nếu security/management port được tùy chỉnh, test HTTP cần dùng đúng URL, credentials, TLS và role.
- Một phép kiểm thử được 200 không đủ; phải xác nhận **metric đã ghi xuất hiện với labels/đơn vị đúng**.

## 7. Kiểm tra bằng tay: tên, tag, đơn vị và giá trị

Sau khi gọi một endpoint nghiệp vụ có ghi metrics, có thể xem:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/demo.export.requests
curl -s http://localhost:8080/actuator/prometheus
~~~

Ví dụ **kết quả minh họa** tại Actuator:

~~~json
{
  "name": "demo.export.requests",
  "measurements": [
    {"statistic": "COUNT", "value": 2.0}
  ],
  "availableTags": [
    {"tag": "outcome", "values": ["success"]}
  ]
}
~~~

Với Prometheus registry, một counter có thể xuất dưới dạng:

~~~text
# TYPE demo_export_requests_total counter
demo_export_requests_total{outcome="success",application="order-api",environment="local"} 2.0
~~~

Đây chỉ là ví dụ về naming/output; xác nhận định dạng và tên cuối cùng ở exporter phiên bản thật. Trong những trường hợp khác, Actuator output có thể liệt kê các tags khác hoặc Prometheus exporter thay đổi vị trí hậu tố theo naming convention.

### Thử một tag filter ở Actuator

~~~bash
curl -s --get \
  --data-urlencode "tag=outcome:success" \
  http://localhost:8080/actuator/metrics/demo.export.requests
~~~

Tham số `tag=key:value` lọc dữ liệu đo theo tags. Nó không phải PromQL và không truy vấn kho dữ liệu Prometheus; Actuator cho thấy trạng thái phép đo tại process được hỏi.

### So sánh duration

Nếu timer `demo.export.duration` nhận hai mẫu 25 ms:

~~~text
Expected: count=2, totalTime=50 ms=0.05 seconds
~~~

Prometheus có thể xuất `demo_export_duration_seconds_count` và `demo_export_duration_seconds_sum`. **Không** so sánh giá trị `0.05` giây với `50` ms mà chưa chuyển đơn vị. Trước khi assert, đọc tên metric, `baseUnit` và dữ liệu exporter thực.

## 8. Kiểm thử Prometheus scrape end-to-end

Khi ứng dụng đã có endpoint, cấu hình Prometheus để scrape theo chu kỳ. Ví dụ trong một lab:

~~~yaml
scrape_configs:
  - job_name: "order-api"
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["order-api.internal:8080"]
~~~

`order-api.internal` là hostname minh họa; nó phải phân giải từ **mạng của Prometheus**, không chỉ từ laptop của người phát triển. Endpoint cần được bảo vệ qua network boundary và, khi phù hợp, TLS/xác thực.

Các bước xác minh:

1. Mở target status của Prometheus hoặc truy vấn API targets để thấy job `order-api`.
2. Kiểm tra target **UP**, lần scrape gần nhất và thông báo lỗi nếu DOWN.
3. Đọc số lượng samples đã scrape, scrape duration và scrape interval để nhận diện endpoint chậm hoặc payload quá lớn.
4. Truy vấn metric probe theo đúng `job`, `instance` và labels.
5. Gọi `recordSuccess()` thêm một số lần có kiểm soát, đợi ít nhất một chu kỳ scrape phù hợp, rồi kiểm tra counter tăng.
6. Giám sát scrape sau restart hoặc cập nhật security config.

Ví dụ PromQL:

~~~promql
up{job="order-api"}
~~~

Nếu `up=1`, Prometheus gần đây đã scrape thành công target tương ứng. **Nó không chứng minh rằng `demo_export_requests_total` đã tồn tại**. Muốn kiểm tra metric cụ thể, truy vấn riêng:

~~~promql
demo_export_requests_total{job="order-api",outcome="success"}
~~~

Với số liệu nhiều thời điểm, xem mức tăng:

~~~promql
increase(demo_export_requests_total{job="order-api",outcome="success"}[10m])
~~~

Kết quả `increase(...)` có thể không bằng số sự kiện nguyên chính xác vì Prometheus thực hiện ngoại suy từ các mẫu trong cửa sổ và xử lý counter resets. Khi unit test, kiểm tra count trực tiếp ở registry; khi test backend, kiểm tra xu hướng tăng và tính liên tục trong cửa sổ phù hợp, không bắt `increase` bằng đúng `N` tuyệt đối.

Các metrics nội bộ do Prometheus tạo, chẳng hạn `up` và `scrape_duration_seconds`, **không phải meter do ứng dụng tự xuất**. Đó là tín hiệu về chất lượng thu thập.

### Target UP nhưng data không đúng

Nếu target UP mà dashboard không có metric:

- Meter có thật trong registry chưa? Nó đã được ghi sau khi khởi động chưa?
- Prometheus exporter có xuất đúng tên/hậu tố và labels không?
- Query có lọc nhầm `application`, `environment`, `instance` hoặc `job`?
- `metric_relabel_configs` trong Prometheus có loại series đó không?
- Có thay đổi naming convention, collector hay registry version sau deploy không?

Lúc này không nên sửa application business logic nếu raw endpoint đã xuất metric đúng; hãy kiểm tra đường scrape và truy vấn.

## 9. Kiểm thử bảo mật và ranh giới mạng

Metric exporter có thể tiết lộ routes, dependency names, môi trường và trạng thái runtime. Trong production, `/actuator/prometheus` nên chỉ mở cho scraper được ủy quyền, không công khai tùy tiện trên Internet.

Bộ kiểm thử nên bao gồm:

| Người gọi | Truy cập kỳ vọng | Bằng chứng |
| --- | --- | --- |
| Prometheus service account hoặc scraper hợp lệ | Được đọc `/actuator/prometheus`. | HTTP 200, target UP, có samples. |
| Người dùng công khai không được phép | Không xem được telemetry. | Network bị chặn hoặc HTTP 401/403, tùy chính sách. |
| Người vận hành có quyền chẩn đoán | Đọc được `/actuator/metrics` khi được cấp quyền. | HTTP 200 và JSON phù hợp. |
| Danh tính không có quyền | Không đọc được endpoint hoặc endpoint bị ẩn. | 401/403/404 theo thiết kế của hạ tầng. |

Nếu endpoint trả 401/403 cho scraper, sửa **identity, role, credentials và TLS/network**, không đơn giản bỏ security để cho target UP. Nếu dùng management port riêng, test từ mạng của Prometheus chứ không chỉ từ localhost trên máy ứng dụng.

Không đưa username/password trực tiếp vào tài liệu commit hay đường dẫn URL có thể bị ghi vào logs. Với Basic auth, chỉ dùng qua HTTPS hoặc đường truyền đã được bảo vệ tương đương, và cấp quyền hạn chế cho scraper.

Một phép thử âm tính rất quan trọng là từ một network không được cấp quyền, endpoint **không được trả 200** kèm thông tin metrics.

## 10. Histogram và kiểm thử metric distribution

Counter và timer sum/count thường chưa đủ để tính P95/P99 tổng hợp qua nhiều instance. Nếu dashboard dùng histogram, phải xác minh exporter thực sự có bucket series.

Ví dụ cấu hình Spring Boot 3.x:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Khi histogram hoạt động và được Prometheus registry xuất với tên thông dụng, có thể có:

~~~text
http_server_requests_seconds_bucket{le="0.1",...} ...
http_server_requests_seconds_bucket{le="0.5",...} ...
http_server_requests_seconds_bucket{le="+Inf",...} ...
~~~

Ví dụ truy vấn P95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="order-api",uri="/checkout",method="POST"
    }[5m])
  )
)
~~~

Kiểm thử cần xác minh:

1. `_bucket` có thật trong payload exporter, không chỉ có `_sum` và `_count`.
2. Buckets có **đơn vị giây** đúng với tên series.
3. `uri` là **route template**, không phải URL chứa request ID.
4. Query gộp bucket theo `le` và các chiều cần giữ, tránh nhầm nhiều service/environment.
5. Có dữ liệu đủ trong cửa sổ quan sát; trên tải quá thấp P95 biến động đáng kể.

Histogram làm tăng số series, nên kiểm thử cả lượng samples và cardinality sau khi bật. Tracing sampling **không tạo bucket series** và không phải cách sửa metric histogram còn thiếu.

## 11. Kiểm thử cardinality và metadata

Một exporter có thể hoạt động “thành công” theo HTTP status nhưng phát lượng metric tags quá lớn. Vì vậy cần thêm điều kiện chất lượng dữ liệu.

Ví dụ không nên dùng:

~~~java
registry.counter("checkout.requests", "requestId", requestId)
        .increment();
~~~

Một request ID mới tạo một tổ hợp nhãn mới. Với 100 request/giây, 24 giờ có khoảng:

~~~text
100 × 60 × 60 × 24 = 8.640.000 request/ngày
~~~

Nếu mỗi ID khác nhau, chỉ riêng chiều `requestId` đã tạo hàng triệu giá trị nhãn. Đây là rủi ro về memory, ingestion, index và chi phí lưu trữ.

Thay bằng:

~~~java
registry.counter("checkout.requests",
        "operation", "checkout",
        "outcome", "success").increment();
~~~

Khi kiểm thử payload:

- Xác nhận nhãn có tập giá trị hữu hạn như `operation`, `outcome`, `method` và `uri` đã chuẩn hóa.
- Không có `requestId`, `userId`, email, token hoặc URL raw chứa định danh trong metric labels.
- Common tags như `application`, `environment` được gắn đúng và không nhân số series ngoài dự kiến.
- Kiểm tra số series/samples trên backend sau khi bật một metric mới.
- Nếu cần ID để điều tra một request cụ thể, dùng logs/MDC và trace attributes theo chính sách quyền riêng tư, không biến chúng thành labels metrics.

Một test kiểm tra **schema tên và tags được phép** có thể phát hiện sai sót trước khi triển khai exporter.

## 12. Export push, composite registry và những khác biệt cần kiểm thử

Không phải exporter nào cũng giống Prometheus pull/scrape.

| Kiểu export | Cách di chuyển dữ liệu | Cần kiểm thử thêm |
| --- | --- | --- |
| **Prometheus pull** | Server Prometheus gọi HTTP vào endpoint ứng dụng. | Exposure, routing, authentication, TLS, scrape target, content format. |
| **Push registry** | Ứng dụng gửi metrics định kỳ tới backend/collector. | Endpoint đích, credentials, batch/step interval, retry, timeout, hàng đợi. |
| **Composite registry** | Một `MeterRegistry` có thể chuyển meters đến nhiều registry con. | Mỗi đích thực sự nhận dữ liệu, tên/đơn vị và tags được ánh xạ đúng. |
| **OTLP metrics** | Metrics được xuất theo OTLP pipeline tương ứng. | Collector receiver/exporter, resource attributes, temporality, backend mapping. |

OTLP **metrics exporter** là nhánh riêng với OTLP **tracing exporter**. Có tracing exporter đúng không chứng minh metrics export qua OTLP đã hoạt động. Tương tự, Prometheus scrape đúng không chứng minh traces/logs được lưu.

Khi kiểm thử push, ngoài một số đo ở registry, phải xác minh backend/collector thực nhận metric, không có lỗi authentication hoặc batch bị drop. Có thể sử dụng một test collector hoặc backend thử nghiệm được phép kiểm tra; không đưa credentials thật vào repository.

**Composite registry và số lần ghi:** code nghiệp vụ chỉ tăng counter một lần. Registry chịu trách nhiệm chuyển số đo tới các đích tương ứng; không tăng hai lần để “gửi cho hai backend”, vì sẽ làm sai số liệu.

## 13. Liên hệ với Micrometer Observation và tracing

Một custom `Observation` có thể tạo metrics qua metrics handler và tracing spans qua tracing handler:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void reserve(ObservationRegistry observations) {
    Observation.createNotStarted("inventory.reserve", observations)
            .lowCardinalityKeyValue("operation", "reserve")
            .observe(() -> {
                // Logic giữ tồn kho thực tế đặt tại đây.
            });
}
~~~

Ví dụ trên chỉ minh họa API; khi tích hợp thật, logic nghiệp vụ sẽ được thay bằng một lời gọi phù hợp. Để metric xuất hiện:

1. Observation phải được tạo và hoàn thành qua vòng đời đúng.
2. `ObservationRegistry` có metrics handler phù hợp.
3. Handler ghi vào `MeterRegistry` được cấu hình.
4. Registry/exporter thực sự công bố số đo.
5. Backend scrape/nhận và lưu dữ liệu.

Nếu tracing cũng được bật, một số hoạt động có span và logs có thể chứa `traceId`/`spanId` khi context active. Nhưng **metric timer không mặc nhiên có trace ID của từng request**, vì metrics dùng để tổng hợp. Trace sampling có thể giữ một phần nhỏ các request; số lần gọi trong metrics thường không bị giảm tương ứng.

Khi gặp mất trace sau một HTTP hop, cần kiểm tra context propagation như `traceparent`, instrumentation, async context và tracing exporter. Sửa Prometheus metric export không thể tự nối lại parent–child spans.

## 14. Runbook: exporter trả 200 nhưng dashboard trống

Giả sử người vận hành gọi `/actuator/prometheus` và thấy data, nhưng dashboard `order-api` không hiện `demo.export.requests`.

Đi theo chuỗi kiểm chứng:

1. **Ứng dụng:** chạy nhánh `recordSuccess()`, kiểm tra `/actuator/metrics/demo.export.requests` có meter và tags đúng.
2. **Exporter:** đọc raw `/actuator/prometheus`, tìm tên đã đổi theo Prometheus conventions, ví dụ `demo_export_requests_total`.
3. **Mạng:** từ nơi Prometheus chạy, kiểm tra hostname, port, base path, TLS/identity và policy.
4. **Scraper:** kiểm tra target UP/DOWN, lỗi parse, timeout và scrape sample count; xác minh `metrics_path` đúng.
5. **Backend:** truy vấn `up{job="order-api"}`, sau đó truy vấn meter cụ thể không thêm nhiều label filters.
6. **Cardinality/filters:** kiểm tra metric relabeling, retention, common tags, dropped series và điều kiện lọc.
7. **Dashboard:** đối chiếu time range, datasource, environment/job/instance, đơn vị và query.
8. **Sau sửa:** tạo thêm một số mẫu, đợi các lần scrape phù hợp, xác nhận series và counters tăng ổn định.

Đừng thay đổi đồng thời cả application instrumentation, exporter và dashboard; cách đó khiến không biết lớp nào đã sửa được vấn đề. Ưu tiên tìm **ranh giới đầu tiên trong pipeline không có bằng chứng**.

## 15. Bảng chẩn đoán nhanh

| Triệu chứng | Khả năng cần kiểm tra | Cách xác nhận |
| --- | --- | --- |
| Unit test không thấy meter | Code path chưa chạy, sai tên/tags, dùng registry khác. | `SimpleMeterRegistry.find(...)`, số lần gọi service. |
| Actuator `/metrics` không thấy custom metric | Chưa có mẫu, meter chưa được ghi, filter loại meter. | Gọi probe, xem meter names và tags. |
| `/actuator/prometheus` trả 404 | Thiếu Prometheus registry, endpoint không expose/bị disable hoặc URL sai. | Dependency, management port/path, exposure. |
| `/actuator/prometheus` trả 401/403 | Sai quyền hoặc authentication của caller. | Spring Security/proxy, role và credentials. |
| Endpoint 200 nhưng metric không xuất | Meter chưa được ghi, registry không nhận, tên khác hoặc bị filter. | Đối chiếu Actuator JSON với raw exporter text. |
| Prometheus target DOWN | Network, TLS, auth, timeout, parse error hoặc URL sai. | Targets UI/API, log scraper, gọi từ mạng Prometheus. |
| `up=1` nhưng query rỗng | Sai tên/hậu tố, job/instance, label selector hoặc metric relabeling. | Bỏ filters từng bước, so payload thô. |
| Timer thấy `_count`/`_sum` nhưng không có `_bucket` | Chưa bật histogram hoặc phiên bản/registry không xuất buckets. | Xem cấu hình distribution và raw exporter. |
| Số liệu giảm sau restart | Counter/timer được reset khi process khởi động lại. | Xem instance/restart và dùng `rate()`/`increase()` phù hợp. |
| Series tăng đột biến | Nhãn theo request ID, user ID, URL raw hoặc quá nhiều tag dimensions. | Kiểm tra metadata và số active series. |
| Metrics đầy đủ nhưng trace thiếu | Sampling/bridge/exporter/propagation tracing khác pipeline metrics. | Kiểm tra tracing riêng, dùng logs để đối chiếu. |

## 16. Bài tập tự kiểm tra

### Bài 1: Test nào chứng minh điều gì?

`SimpleMeterRegistry` cho thấy counter `demo.export.requests` tăng từ 0 lên 2, nhưng Prometheus target DOWN. Có thể báo metric export đã hoàn thành end-to-end không?

**Đáp án:** Không. Unit test chỉ chứng minh meter ghi đúng. Cần kiểm tra exporter endpoint, reachability, target status và truy vấn backend.

### Bài 2: `up=1` có đủ không?

Prometheus báo `up{job="order-api"}=1` nhưng không có `demo_export_requests_total`. Có thể kết luận service chưa nhận request không?

**Đáp án:** Chưa đủ. Có thể code chưa gọi probe, metric bị filter, naming khác, exporter chưa có meter, hoặc backend relabel/query sai. Cần kiểm tra từng tầng.

### Bài 3: Sai đơn vị

Timer ghi hai mẫu 25 ms nhưng dashboard hiển thị total time 0,05 giây. Đây có phải lỗi exporter không?

**Đáp án:** Không. `50 ms = 0,05 giây`. Prometheus timer metrics thường biểu diễn theo giây, còn API trong Java có thể dùng millisecond/nanosecond. Kiểm tra base unit trước khi báo lỗi.

### Bài 4: Lỗi xác thực

Sau khi bật security, `/actuator/prometheus` trả 200 khi Ops gọi thủ công, còn Prometheus target báo 401. Giải pháp nên làm là gì?

**Đáp án:** Xác minh identity và credentials/role của scraper, vị trí network/TLS và URL nó thực gọi. Không tắt auth chỉ để target UP. Sau khi sửa, xác nhận có samples trong backend.

### Bài 5: Kiểm thử histogram

Dashboard dùng `histogram_quantile` nhưng `http_server_requests_seconds_bucket` không tồn tại. Có thể tính P95 toàn cụm chính xác bằng cách lấy trung bình P95 từng instance không?

**Đáp án:** Không. Cần histogram hoặc mô hình phân bố phù hợp; không tính P95 toàn cụm bằng trung bình các P95. Bật histogram có chọn lọc, kiểm tra bucket series và chi phí cardinality.

### Bài 6: Tracing sampling

Ứng dụng xử lý 1.000 request; metrics đếm gần đủ nhưng backend traces chỉ giữ khoảng 100 trace. Có nghĩa metrics export bị lỗi không?

**Đáp án:** Không. Tracing có thể sampling khoảng 10%, trong khi metrics vẫn tổng hợp các request. Hai nhánh có chính sách thu thập và exporter khác nhau.

## 17. Checklist kiểm thử metric export trước production

- [ ] Có unit test xác minh counter/timer thay đổi đúng khi code nghiệp vụ chạy.
- [ ] Có integration test dùng Spring Boot registry thật, không chỉ `SimpleMeterRegistry`.
- [ ] `/actuator/metrics` hiển thị tên, tags và số đo dự kiến.
- [ ] `/actuator/prometheus` xuất đúng tên/labels/đơn vị, với Prometheus registry trên classpath.
- [ ] Prometheus target được kiểm tra từ đúng network của scraper và có xác thực/TLS phù hợp.
- [ ] `up=1` và truy vấn metric cụ thể đều trả dữ liệu; không chỉ kiểm tra mỗi target.
- [ ] Có kiểm thử counter tăng sau nhiều lần ghi, xử lý restart/reset đúng.
- [ ] Histogram buckets thực sự tồn tại nếu dashboard/alert sử dụng P95/P99.
- [ ] Không phát request ID, user ID, email hoặc dữ liệu nhạy cảm dưới dạng metric tags.
- [ ] Common tags, exporter naming và metric relabeling phù hợp với dashboard.
- [ ] Endpoint quản trị không trả dữ liệu cho caller không được phép.
- [ ] Có cảnh báo mất scrape, lỗi authentication/timeout, không chỉ cảnh báo nghiệp vụ.
- [ ] Metrics, logs và traces được đối chiếu đúng vai trò; sampling tracing không bị nhầm với metric export.
- [ ] Sau deploy, kiểm tra dữ liệu từ từng instance và backend qua một khoảng thời gian đủ dài.

**Ghi nhớ:** Kiểm thử metric export không kết thúc ở `Counter.increment()` hoặc HTTP 200 của `/actuator/prometheus`. Một quy trình đáng tin cậy cần đi từ **đúng phép đo trong MeterRegistry**, qua **đúng dữ liệu exporter**, tới **scrape/push thành công và series truy vấn được**, đồng thời bảo vệ endpoint và kiểm soát cardinality. Khi mỗi tầng có bằng chứng riêng, bạn có thể tin metrics đủ để phát hiện bất thường, rồi phối hợp logs và distributed tracing để điều tra lỗi, độ trễ trên Spring Boot.
