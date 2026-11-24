# PrometheusMeterRegistry trong Spring Boot: đăng ký, xuất và truy vấn metrics

Ứng dụng Spring Boot đã có `Counter`, `Timer` hay `Gauge` nhưng dashboard Prometheus không hiển thị dữ liệu. Nguyên nhân có thể không nằm ở instrumentation: meter đã được ghi đúng nhưng ứng dụng chưa có registry Prometheus, endpoint chưa được expose, Prometheus scrape sai địa chỉ, nhãn không khớp truy vấn hoặc time series đã bị loại do cấu hình. Để điều tra đúng, cần hiểu vai trò của **`PrometheusMeterRegistry`** trong toàn bộ đường đi của metrics.

Trong module **SPRING_BOOT_OBSERVABILITY**, việc thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing phải phân biệt rõ **thu thập metrics**, **chuyển metrics sang định dạng mà backend hiểu**, **truyền trace context** và **xuất traces**. Bài học này thuộc chương **Meter registry và exporter**, tập trung vào `PrometheusMeterRegistry`: cách registry chuyển meters thành dữ liệu Prometheus, cấu hình qua Actuator, kiểm thử scrape, quản lý histogram, tags/cardinality và sử dụng metrics cùng logs, traces để chẩn đoán lỗi, độ trễ trong môi trường thực.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `PrometheusMeterRegistry`, cơ chế **pull/scrape** của Prometheus và sự khác biệt với `MeterRegistry` chung.
2. Thiết lập `spring-boot-starter-actuator` cùng `micrometer-registry-prometheus` cho ứng dụng Spring Boot.
3. Đăng ký hoặc quan sát `Counter`, `Gauge`, `Timer` và histogram, đọc output scrape và đối chiếu tên/đơn vị.
4. Viết PromQL cho request rate, error ratio, p95 và tỷ lệ đạt ngưỡng SLO khi có histogram phù hợp.
5. Giới hạn label cardinality, bảo vệ endpoint metrics và phát hiện sai lệch giữa registry, scrape target và backend.
6. Kiểm thử registry không cần Prometheus server, rồi xác minh pipeline end-to-end ở môi trường thử nghiệm.
7. Phân biệt metrics exporter với tracing exporter, sampling, propagation và liên kết các tín hiệu observability.

## 1. PrometheusMeterRegistry là gì?

Micrometer cung cấp abstraction `MeterRegistry` để ứng dụng đo dữ liệu mà không phải viết logic phụ thuộc từng backend. `PrometheusMeterRegistry` là implementation dành cho Prometheus: nó giữ và cung cấp biểu diễn của các meters theo định dạng mà Prometheus có thể scrape. Thay vì ứng dụng chủ động gọi API gửi từng lần tăng counter lên Prometheus, **Prometheus server chủ động yêu cầu dữ liệu từ một HTTP endpoint**.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Counter` | Đếm số sự kiện tăng dần | Tổng số lần xử lý đơn |
| `Timer` | Ghi số lần và thời gian của thao tác hoàn tất | Độ trễ tạo đơn |
| `Gauge` | Đọc trạng thái hiện tại | Số đơn đang chờ xử lý |
| `MeterRegistry` | Lưu/đăng ký meters và điều phối cách biểu diễn | Bean được inject vào Spring service |
| `PrometheusMeterRegistry` | Registry xuất metrics theo định dạng Prometheus | `registry.scrape()` |
| Actuator `/actuator/prometheus` | HTTP endpoint đưa dữ liệu registry ra ngoài | URL để Prometheus scrape |
| Prometheus server | Thu thập định kỳ, lưu time series và chạy PromQL | Dashboard, recording rules, alert rules |
| Grafana hoặc giao diện khác | Trình bày và phân tích metrics | Panel p95, error rate, backlog |

Một `PrometheusMeterRegistry` **không phải Prometheus server** và không tự tạo dashboard. Nó chỉ là một phần của pipeline metrics trong ứng dụng.

### 1.1. Luồng dữ liệu từ Spring Boot tới dashboard

~~~mermaid
flowchart LR
    Service["Spring Boot<br/>Business code"] --> Observation["Micrometer Observation"]
    Service --> Meters["Counter / Timer / Gauge<br/>JVM, HTTP, business"]
    Observation --> MeterHandler["MeterObservationHandler"]
    MeterHandler --> Meters
    Meters --> Registry["PrometheusMeterRegistry"]
    Registry --> Endpoint["Actuator /actuator/prometheus"]
    Prom["Prometheus server"] -- "HTTP GET theo scrape_interval" --> Endpoint
    Endpoint -- "Time series + labels + values" --> Prom
    Prom --> Query["PromQL / recording rules"]
    Query --> Grafana["Dashboard / Alerting"]
~~~

Với cơ chế **pull** thông thường:

1. Code và instrumentation ghi dữ liệu vào meters, hoặc gauge cung cấp giá trị khi được đọc.
2. `PrometheusMeterRegistry` chuẩn bị biểu diễn phù hợp với định dạng scrape.
3. Actuator đưa dữ liệu registry qua `/actuator/prometheus`.
4. Prometheus server lấy mẫu định kỳ theo `scrape_interval` và lưu vào TSDB.
5. Dashboard hoặc alert thực thi PromQL để phân tích cửa sổ thời gian.

**Không có scrape thì chưa có dữ liệu ở Prometheus**, dù Actuator có thể đang hiển thị meter đúng. Ngược lại, Prometheus server báo target `UP` chỉ chứng minh lần scrape thành công; chưa chứng minh từng metric nghiệp vụ mong muốn đã được đăng ký hoặc đã có traffic.

### 1.2. Phân biệt push và pull

| Thuộc tính | Prometheus pull/scrape | Push-based metrics exporter |
| --- | --- | --- |
| Bên chủ động | Prometheus server gọi endpoint | Ứng dụng/agent/collector gửi dữ liệu |
| Đường dữ liệu | HTTP scrape của target | Gửi định kỳ hoặc theo batch |
| Nhu cầu mở cổng | Prometheus cần truy cập endpoint | Ứng dụng cần kết nối tới receiver |
| Phát hiện target lỗi | Thường dựa trên `up` và scrape health | Tùy pipeline, queue và tín hiệu exporter |
| Dùng với ứng dụng Spring Boot | `PrometheusMeterRegistry` + Actuator | Một registry/exporter khác, ví dụ OTLP metrics |

**Prometheus Pushgateway** là một thành phần chuyên biệt và không nên xem như cách thay thế mặc định cho việc scrape mọi service dài hạn. Với application HTTP chạy liên tục, pull/scrape thường là mô hình nền tảng dễ kiểm soát.

## 2. Thiết lập Spring Boot và Actuator

Ví dụ dành cho một ứng dụng **Spring Boot 3.x** dùng dependency management/BOM tương ứng. Trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-boot-starter-actuator` tích hợp Micrometer và các endpoint phục vụ quan sát ứng dụng. `micrometer-registry-prometheus` cung cấp implementation Prometheus registry. Khi các điều kiện auto-configuration được đáp ứng, Spring Boot tạo và cấu hình registry cùng các meters phù hợp; **không cần tự tạo bean `PrometheusMeterRegistry` trong mọi service**.

### 2.1. Cấu hình application.yml

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  metrics:
    tags:
      application: order-service
      environment: staging
~~~

Đây là cấu hình **môi trường thử nghiệm**. Trong production cần bảo vệ endpoint bằng mạng quản trị, ingress rule, xác thực/ủy quyền hoặc chính sách tương đương; không nên công khai `/actuator/prometheus` cho Internet. Common tags `application`, `environment` giúp gắn các time series với dịch vụ/môi trường, nhưng chúng phải có tập giá trị ổn định.

Endpoint thường xuất hiện tại `http://localhost:8080/actuator/prometheus` nếu ứng dụng chạy port 8080 và không đổi management base path/port. Với cấu hình khác, kiểm tra lại URL thật.

### 2.2. Kiểm tra từng lớp

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/prometheus
~~~

Không đánh đồng ba endpoint:

- `/actuator/health` trả trạng thái health của ứng dụng theo các indicator đã cấu hình; `UP` không bảo đảm mọi metric nghiệp vụ có dữ liệu.
- `/actuator/metrics` là endpoint chẩn đoán của Spring Boot Actuator để liệt kê và xem thông tin meters theo tên Micrometer.
- `/actuator/prometheus` phục vụ **định dạng scrape** cho Prometheus. Tên ở endpoint này có thể khác tên meter gốc.

Hãy gửi ít nhất một request tới route nghiệp vụ rồi kiểm tra `http.server.requests` và các meters custom. Một số meter chỉ xuất hiện sau khi được đăng ký hoặc sau khi có dữ liệu.

### 2.3. Cấu hình Prometheus server để scrape

Ví dụ `prometheus.yml` tối giản cho local development khi Prometheus và Spring Boot có thể kết nối trực tiếp qua `localhost:8080`:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "order-service"
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["localhost:8080"]
        labels:
          environment: staging
~~~

Nếu Prometheus chạy **trong container khác**, `localhost:8080` trỏ về container Prometheus, **không tự động trỏ về ứng dụng Spring Boot**. Thay target bằng DNS/service name có thể truy cập được trong network tương ứng, ví dụ `order-service:8080` khi môi trường container thực tế cung cấp tên đó. Trong Kubernetes, cách phát hiện và scrape target có thể do service discovery, Prometheus Operator hoặc ServiceMonitor/PodMonitor đảm nhiệm; đây không phải tính năng tự động chỉ từ một bean Java.

Trong giao diện Prometheus, kiểm tra trạng thái target và truy vấn:

~~~promql
up{job="order-service"}
~~~

`up=1` thường cho biết scrape của target thành công; `up=0` cho biết lần scrape gặp lỗi. Nếu target hoàn toàn không xuất hiện, có thể là vấn đề discovery/configuration chứ không phải bản thân ứng dụng. Không dùng `up` để xác nhận một metric cụ thể tồn tại: hãy truy vấn tên series đó.

## 3. Tên metric, labels và định dạng Prometheus

Micrometer dùng tên có dấu chấm như `http.server.requests`, `jvm.memory.used`, `orders.checkout.duration`. Registry Prometheus chuyển tên và đơn vị sang định dạng metrics thích hợp. Ví dụ minh họa phổ biến:

| Meter Micrometer | Đầu ra Prometheus thường thấy | Giải thích |
| --- | --- | --- |
| `http.server.requests` (Timer) | `http_server_requests_seconds_count` và `_seconds_sum` | Số lần request và tổng số giây |
| `orders.checkout.duration` (Timer) | `orders_checkout_duration_seconds_count` | Timer đã chuẩn hóa tên/đơn vị |
| `jvm.memory.used` (Gauge) | `jvm_memory_used_bytes` | Giá trị bộ nhớ theo byte |
| `orders.processed` (Counter) | `orders_processed_total` | Counter tích lũy |
| `orders.queue.pending` (Gauge) | Tên gauge có thể kèm đơn vị như `_tasks` | Đọc giá trị hiện tại |

Đây là các **quy ước thường gặp**, không phải cam kết tên đầu ra cho mọi version/provider. Hãy xem `/actuator/prometheus` trước khi dùng tên trong truy vấn hoặc alert.

### 3.1. Counter và reset sau restart

Một counter là giá trị tích lũy trong vòng đời process, ví dụ:

~~~text
# Ví dụ text mô phỏng, không phải scrape nguyên văn
orders_processed_total{application="order-service",channel="web"} 1250
~~~

Nếu process restart, counter có thể trở về giá trị ban đầu. Để đo tốc độ xử lý, dùng:

~~~promql
sum(rate(orders_processed_total{application="order-service"}[5m]))
~~~

`rate` tính tốc độ tăng mỗi giây trên cửa sổ, có xử lý counter reset theo ngữ nghĩa Prometheus. Nếu muốn ước lượng **số sự kiện** trong một cửa sổ, dùng `increase(...[5m])`. Không lấy chênh lệch thủ công của hai số scrape khi hệ thống có restart hoặc scrape thất bại.

### 3.2. Gauge là giá trị tại thời điểm quan sát

Một gauge như `orders.queue.pending` mô tả backlog hiện tại. Không dùng `rate(gauge[5m])` như thể đây là counter. Có thể xem chuỗi giá trị trực tiếp, hoặc dùng `avg_over_time`, `max_over_time` khi cần phân tích mức trung bình/đỉnh **trong các mẫu đã scrape**.

Một backlog tăng rồi giảm hoàn toàn giữa hai lần scrape có thể không được quan sát. Nếu muốn đếm tổng công việc được nhận và hoàn tất, nên có counter tương ứng, không chỉ gauge.

### 3.3. Tag trong Micrometer trở thành label ở Prometheus

~~~java
Counter counter = Counter.builder("orders.processed")
        .description("Number of processed orders")
        .tag("channel", "web")
        .register(meterRegistry);

counter.increment();
~~~

Tag `channel=web` có thể xuất thành label `channel="web"`. Các hệ thống deployment thường thêm `job`, `instance` từ cấu hình target và các labels khác. Một label thay đổi theo mỗi request, ví dụ `order_id` hoặc `trace_id`, có thể làm cardinality tăng rất mạnh.

**Không bao giờ đưa mật khẩu, access token, email, số điện thoại, request payload hoặc ID người dùng vào metric labels.** Cần phân biệt nhãn có tập giá trị hữu hạn (phù hợp metrics) với metadata high-cardinality (chỉ cân nhắc đưa vào tracing nếu thật sự cần và an toàn).

## 4. Sử dụng PrometheusMeterRegistry trực tiếp

Trong Spring Boot, nên inject `MeterRegistry` chung do framework quản lý. Khi cần kiểm thử registry riêng, viết thư viện độc lập hoặc minh họa API, có thể khởi tạo `PrometheusMeterRegistry` thủ công.

**Lưu ý phiên bản:** Micrometer sử dụng Prometheus Java client mới ở các phiên bản hiện đại (ví dụ dòng Micrometer 1.13+). Import của registry mới là `io.micrometer.prometheusmetrics.PrometheusMeterRegistry`. Các hướng dẫn cũ dùng `io.micrometer.prometheus.PrometheusMeterRegistry` và mô-đun `micrometer-registry-prometheus-simpleclient` có thể không áp dụng cho cấu hình dùng client mới. Chọn dependency, package và API tương ứng với **BOM của Spring Boot đang chạy**; không trộn hai nhánh client một cách tùy ý.

### 4.1. Ví dụ Java không phụ thuộc Spring container

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

import java.time.Duration;

public class PrometheusRegistryDemo {
    public static void main(String[] args) {
        try (PrometheusMeterRegistry registry =
                     new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {

            Counter processed = Counter.builder("orders.processed")
                    .tag("channel", "web")
                    .register(registry);
            processed.increment(3);

            Timer reservation = Timer.builder("orders.reservation")
                    .description("Duration of reserving inventory")
                    .tag("operation", "reserve")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(Duration.ofMillis(500))
                    .register(registry);
            reservation.record(Duration.ofMillis(120));
            reservation.record(Duration.ofMillis(750));

            String scrapeText = registry.scrape();
            System.out.println(scrapeText);
        }
    }
}
~~~

Code trên:

1. Tạo registry độc lập và đăng ký một `Counter` cùng một `Timer`.
2. Ghi ba lần xử lý đơn và hai mẫu thời gian giữ hàng.
3. Bật histogram và bucket ở ngưỡng 500 ms cho timer (nếu registry hỗ trợ).
4. Gọi `scrape()` để lấy **nội dung text**, chưa cần chạy Prometheus server.
5. Đóng registry khi kết thúc ví dụ.

Một output thực có thể chứa các series như `orders_processed_total`, `orders_reservation_seconds_count`, `orders_reservation_seconds_sum` và bucket `orders_reservation_seconds_bucket`. Tên, metadata HELP/TYPE và cách biểu diễn cụ thể phụ thuộc client/registry version.

**Trong ứng dụng Spring Boot không nên lặp lại đoạn khởi tạo registry này trong mỗi request hoặc service.** Nếu bạn tự tạo một registry tách khỏi bean đang được Actuator expose, metrics ghi vào registry đó có thể không xuất hiện tại `/actuator/prometheus`.

### 4.2. Inject registry vào service Spring Boot

Một cách đơn giản hơn trong ứng dụng thực tế:

~~~java
package com.example.orders;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderMetrics {
    private final Counter processedWebOrders;

    public OrderMetrics(MeterRegistry registry) {
        this.processedWebOrders = Counter.builder("orders.processed")
                .description("Processed orders")
                .tag("channel", "web")
                .register(registry);
    }

    public void processedSuccessfully() {
        processedWebOrders.increment();
    }
}
~~~

Counter được đăng ký **một lần khi bean được tạo**, sau đó tăng mỗi khi xảy ra sự kiện nghiệp vụ thành công. Nếu định nghĩa `orders.processed` là số đơn xử lý hoàn tất, **không tăng counter trước khi transaction thực sự thành công**. Với các nguồn `web`/`batch`, nên chuẩn hóa channel và quản lý một tập meter hữu hạn.

Khi hệ thống đã có `Observation` và metrics handler đo cùng một thao tác, cần chọn một nguồn đo chính để tránh đăng ký hoặc đếm trùng metrics có cùng ngữ nghĩa.

## 5. Histogram, percentile và SLO với PrometheusMeterRegistry

Trong các hệ thống cần theo dõi độ trễ p95/p99, `Timer` có thể xuất **classic histogram** với các bucket tích lũy. Ví dụ cấu hình Spring Boot:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 1s
      minimum-expected-value:
        http.server.requests: 1ms
      maximum-expected-value:
        http.server.requests: 5s
~~~

Những thuộc tính này áp dụng lên meter `http.server.requests` khi instrumentation HTTP phù hợp đang hoạt động:

- `percentiles-histogram`: bật các bucket hỗ trợ tính percentile ở backend.
- `slo`: thêm các ranh giới được chọn vì yêu cầu vận hành, ví dụ đúng **500 ms**.
- `minimum-expected-value` / `maximum-expected-value`: định hướng vùng bucket được tạo để tránh các ngưỡng vô ích; **không phải timeout và không có nghĩa loại bỏ request vượt max**.

Một classic histogram xuất các series dạng `_bucket{le="..."}`, `_count` và `_sum`. `le` là ngưỡng **ít hơn hoặc bằng**, và đối với HTTP Timer xuất sang Prometheus đơn vị thường là **giây**:

~~~text
# Dữ liệu minh họa đã giản lược labels
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.1"} 4
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.3"} 8
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.5"} 9
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="+Inf"} 10
http_server_requests_seconds_count{method="POST",uri="/orders"} 10
http_server_requests_seconds_sum{method="POST",uri="/orders"} 3.225
~~~

Các bucket **tích lũy**; không cộng các bucket với nhau để tính số request. Với 10 request ở ví dụ, 9 request hoàn tất trong tối đa 500 ms, tương đương 90%. Đây là dữ liệu giả định để giải thích công thức, không phải kết quả tự động của Spring Boot.

### 5.1. p95 của route /orders

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      method="POST", uri="/orders"
    }[5m])
  )
)
~~~

Trong **classic histogram**, phải giữ label `le` khi cộng các bucket. `histogram_quantile` nội suy từ bucket, nên đây là **ước lượng**, không phải số đo chính xác của từng request. Muốn p99, thay `0.95` bằng `0.99`.

Không lấy trung bình p95 của nhiều instance để suy ra p95 toàn cụm. Hãy cộng tốc độ tăng của **các bucket cùng ranh giới** rồi mới tính percentile. Nếu các instance được cấu hình bộ bucket khác nhau, việc cộng gộp sẽ khó diễn giải; cần duy trì bucket contract nhất quán.

### 5.2. Tỷ lệ request ≤ 500 ms

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  method="POST", uri="/orders", le="0.5"
}[30m]))
/
sum(rate(http_server_requests_seconds_count{
  method="POST", uri="/orders"
}[30m]))
~~~

Biểu thức trả về phần request thuộc phạm vi đã lọc và có thời gian không vượt quá 0,5 giây. Nếu định nghĩa SLI chỉ tính request hợp lệ hoặc thành công, phải áp dụng **cùng bộ lọc** ở tử và mẫu, đồng thời biết rằng “nhanh” và “thành công” là hai khái niệm khác nhau.

### 5.3. Request rate và error ratio

Lưu lượng request mỗi giây:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/orders", method="POST"
}[5m]))
~~~

Ví dụ tỷ lệ lỗi 5xx dựa vào nhãn `status` khi series thật có label này:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/orders", method="POST", status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  uri="/orders", method="POST"
}[5m]))
~~~

Nếu rất ít traffic, mẫu số có thể bằng 0. Dashboard và alert cần quy tắc xử lý dữ liệu thiếu, cửa sổ đo và ngưỡng lưu lượng tối thiểu. Histogram và timer không mặc nhiên chứa một nhãn lỗi cho mọi custom meter: điều đó phụ thuộc convention và instrumentation của ứng dụng.

### 5.4. Classic histogram và native histogram

Những query dùng `_bucket` và `le` trong bài này hướng đến **classic histogram**. Các phiên bản Prometheus có khả năng xử lý **native histogram** bằng kiểu dữ liệu và một số biểu thức khác. Đừng dùng nguyên xi câu lệnh classic trên hệ thống chỉ xuất/lưu native histogram. Trước khi chọn query, xác minh registry, protocol scrape và cấu hình Prometheus backend thật.

## 6. Labels, cardinality và giới hạn chi phí

Trong Prometheus, mỗi tổ hợp **tên metric + tập labels** tạo nên một time series. Nếu histogram có nhiều bucket, số series còn được nhân theo số ngưỡng.

Giả sử HTTP timer có:

- 8 route được chuẩn hóa;
- 3 HTTP methods;
- 4 nhóm status/outcome;
- 20 instance;
- 25 bucket.

Số bucket series về mặt mô hình có thể lên đến **8 × 3 × 4 × 20 × 25 = 24.000**, chưa tính `_count`, `_sum` và các labels khác. Con số này minh họa cách cardinality nhân lên, **không phải số series cố định mà Spring Boot luôn tạo**.

| Label | Giá trị minh họa | Khuyến nghị |
| --- | --- | --- |
| `application` | `order-service` | Ổn định, hữu ích |
| `environment` | `staging`, `production` | Tập giá trị hữu hạn |
| `method` | `GET`, `POST` | Thường có thể tổng hợp |
| `uri` | `/orders/{id}` | Dùng route template, không dùng raw URL |
| `status` | `200`, `500` | Hữu hạn, cần cho error ratio |
| `instance` | Target do Prometheus gán | Cần để vận hành, nhân theo số instance |
| `order.id` | Mỗi đơn một giá trị | **Không đưa vào metric label** |
| `trace.id` | Mỗi trace một giá trị | **Không đưa vào metric label** |
| `exception.message` | Chuỗi tự do | Không phù hợp, có thể chứa dữ liệu nhạy cảm |

### 6.1. Common tags và MeterFilter

Trong Spring Boot, `management.metrics.tags.*` có thể thêm các common tags ổn định. Với yêu cầu phức tạp hơn, `MeterFilter` có thể:

- từ chối một meter không cần xuất;
- đổi tên hoặc biến đổi một số tags trong phạm vi được kiểm soát;
- áp dụng chính sách giới hạn hoặc quản lý metadata trước khi đăng ký.

Tuy nhiên, `MeterFilter` không thay thế thiết kế đúng ở code nghiệp vụ. Nếu một nhóm đăng ký một counter mới cho **mỗi order ID**, nên sửa thiết kế gốc thay vì chờ filter giải quyết sau khi cardinality đã tăng.

### 6.2. Giữ metric contract ổn định

Thay đổi tên `orders.processed`, nhãn `channel` hoặc đơn vị thời gian có thể khiến dashboard/alert mất dữ liệu mà không gây lỗi HTTP request. Trước khi đổi schema:

1. Liệt kê những PromQL queries, recording rules và alerts đang dùng.
2. Kiểm tra các tên series sau khi registry chuyển đổi naming convention.
3. Ước lượng cardinality và chi phí khi thêm labels/buckets.
4. Thiết kế giai đoạn chuyển tiếp nếu cần hỗ trợ query cũ và mới.
5. Ghi lại thời điểm rollout, theo dõi series mới và loại bỏ metric cũ khi an toàn.

**Metrics là một giao diện vận hành**: thay đổi hợp đồng metrics cần được review như một thay đổi tương thích của ứng dụng.

## 7. Bảo vệ và vận hành endpoint scrape

Endpoint `/actuator/prometheus` có thể tiết lộ tên dịch vụ, metrics tài nguyên, route, trạng thái lỗi và thông tin môi trường. Vì vậy:

- Chỉ expose endpoint cần thiết; giới hạn network, ingress và quyền truy cập.
- Bảo vệ đường truyền theo môi trường triển khai (ví dụ TLS hoặc private network).
- Dùng cơ chế xác thực phù hợp nếu scrape đi qua hạ tầng yêu cầu auth.
- Không đưa PII, token hay thông tin bí mật vào metric names, descriptions hoặc labels.
- Giới hạn lượng metrics, số series và scrape payload để tránh quá tải ứng dụng/Prometheus.
- Theo dõi phiên bản Micrometer, registry và Prometheus; thay đổi client có thể ảnh hưởng tên/định dạng.

### 7.1. Scrape interval và freshness

Với `scrape_interval=15s`, Prometheus thường lấy mẫu mỗi 15 giây khi target sẵn sàng. Một gauge biến đổi ngắn hơn interval có thể bỏ lỡ đỉnh. Một counter tích lũy vẫn có thể được dùng để suy ra số sự kiện giữa hai mẫu thành công, miễn là trạng thái quá trình và việc reset được xử lý đúng.

Khi dashboard hiển thị một giá trị quá cũ:

1. Kiểm tra target `up` và thời điểm scrape cuối cùng.
2. Kiểm tra network, timeout, HTTP status, authentication và format trả về.
3. Xác minh ứng dụng có còn tạo/cập nhật meter đó không.
4. Kiểm tra recording rules, truy vấn labels và retention.

Tần suất scrape ngắn hơn làm tăng chi phí thu thập và lưu trữ. Hãy chọn interval dựa trên yêu cầu phát hiện sự cố và ngân sách metrics, không mặc định rằng càng ngắn càng tốt.

### 7.2. Restart, pod churn và series biến mất

Trong Kubernetes hoặc môi trường autoscaling, instance có thể xuất hiện rồi biến mất. Prometheus đánh dấu series không còn được scrape theo quy tắc staleness; dashboard cần được thiết kế để cộng gộp qua các instance đang hoạt động phù hợp. Dùng `rate` trên counter thay vì coi các giá trị counter tích lũy giữa hai pod là có thể so sánh trực tiếp.

Không gắn pod UID hoặc deployment hash vào **nhãn nghiệp vụ tự tạo** chỉ để điều tra request; hạ tầng có thể đã quản lý nhãn target đủ dùng. Các nhãn thay đổi thường xuyên làm tăng số series lịch sử và chi phí retention.

## 8. Kiểm thử PrometheusMeterRegistry

Để xác minh instrumentation được đăng ký và có thể scrape, có thể viết unit test với registry trong bộ nhớ. Test này **không đòi hỏi một Prometheus server**.

### 8.1. Unit test cho Counter và Timer

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

class PrometheusMeterRegistryTest {

    @Test
    void exposesCounterAndTimerForScrape() {
        try (PrometheusMeterRegistry registry =
                     new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            Counter counter = Counter.builder("orders.processed")
                    .tag("channel", "web")
                    .register(registry);
            counter.increment(2);

            Timer timer = Timer.builder("orders.reservation")
                    .tag("operation", "reserve")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(Duration.ofMillis(500))
                    .register(registry);
            timer.record(Duration.ofMillis(120));

            String output = registry.scrape();

            assertThat(counter.count()).isEqualTo(2.0);
            assertThat(timer.count()).isEqualTo(1L);
            assertThat(output).contains("orders_processed_total");
            assertThat(output).contains("orders_reservation_seconds_count");
            assertThat(output).contains("orders_reservation_seconds_bucket");
            assertThat(output).contains("channel=\"web\"");
        }
    }
}
~~~

**Đọc assertion theo mục đích:** đây là test kiểm tra output của **dòng Prometheus registry đã chọn**. Nếu version Micrometer/Prometheus client đổi format hoặc quy tắc tên, cần kiểm tra thực tế rồi điều chỉnh test có chủ đích, không thay test bằng một assertion quá yếu chỉ vì nó thất bại.

Nếu phụ thuộc hiện tại dùng Prometheus legacy client, import và API cần được điều chỉnh cho đúng branch tương ứng. Không tự thêm cả hai loại Prometheus registry vào classpath mà chưa đánh giá ảnh hưởng auto-configuration.

### 8.2. Integration test trong Spring Boot

Trong một ứng dụng thực tế, integration test nên xác minh:

1. Spring tạo `PrometheusMeterRegistry` hoặc một registry/CompositeMeterRegistry có kết nối tới Prometheus registry theo cấu hình.
2. Service inject đúng `MeterRegistry` do Spring quản lý, không tự tạo registry tách biệt.
3. Gọi nghiệp vụ làm Counter hoặc Timer tăng đúng như hợp đồng.
4. `/actuator/prometheus` trả HTTP 200 ở môi trường test được phép expose, có series mong đợi.
5. Labels như `application`, `method`, `uri` được chuẩn hóa; không chứa ID động hoặc PII.
6. Histogram có bucket SLO cần thiết nếu dự án yêu cầu p95/p99 hoặc tỷ lệ đúng hạn.

Test endpoint nên dùng `MockMvc` hoặc HTTP test client phù hợp để tránh phải triển khai Prometheus bên ngoài. Unit test kiểm tra registry và metrics content, integration test kiểm tra **bean/Actuator/configuration wiring**, còn end-to-end test mới kiểm tra Prometheus scrape và dashboard.

### 8.3. Kiểm thử pipeline thật

Ở staging, tạo một đợt traffic đã biết, sau đó kiểm tra từng chặng:

| Chặng | Bằng chứng |
| --- | --- |
| Java instrumentation | Counter/Timer thay đổi sau thao tác |
| Spring registry | Meter hiển thị trong `/actuator/metrics` |
| Prometheus endpoint | Scrape text có series và tags đúng |
| Prometheus target | `up=1`, không có scrape errors |
| Prometheus TSDB | PromQL tìm thấy series có timestamp mới |
| Dashboard/alert | Query, cửa sổ đo và ngưỡng phản ánh lưu lượng thật |

Nếu dashboard không có dữ liệu nhưng `/actuator/prometheus` đúng, **đừng sửa instrumentation vội**. Ưu tiên kiểm tra target discovery, mạng, labels và query của backend.

## 9. Metrics, logs và distributed tracing phối hợp thế nào?

Một Prometheus histogram có thể cho biết p95 của `POST /orders` tăng từ 250 ms lên 1,4 giây trong 10 phút, nhưng không cho biết chính xác request nào chậm tại database hay inventory-service. Traces và logs giải quyết phần điều tra đó.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Prom as Prometheus
    participant Trace as Trace backend
    Client->>Order: POST /orders
    Note over Order: HTTP Observation / Timer
    Order->>Inventory: HTTP + traceparent
    Inventory-->>Order: timeout
    Order-->>Client: HTTP 503
    Note over Order: Metrics count, error, duration
    Prom->>Order: GET /actuator/prometheus
    Order-->>Prom: Counter, histogram buckets, labels
    Order-->>Trace: Spans qua exporter nếu được sampling giữ
~~~

Quy trình điều tra hợp lý:

1. **Metrics phát hiện xu hướng:** request rate, error ratio, p95/p99, CPU, pool connections, queue backlog.
2. **Traces giải thích đường đi:** chọn trace chậm có span HTTP server, business operation và HTTP client tới inventory-service.
3. **Logs cho thông tin sự kiện:** tìm mã lỗi/timeout theo trace ID hoặc cùng khoảng thời gian, tránh log payload nhạy cảm.
4. **Đối chiếu phụ thuộc:** so sánh độ trễ/5xx của inventory-service, trạng thái connection pool và thời điểm rollout.
5. **Khắc phục rồi đo lại:** kiểm tra SLO, error budget hoặc các chỉ số liên quan đã phục hồi.

### 9.1. Sampling của trace không phải sampling mặc định của metrics

Nếu tracing sampling là 10%, nhiều request **không có trace được lưu**, nhưng Timer/Counter của ứng dụng vẫn có thể ghi nhận các lần thực thi đã được instrument. Không dùng “không tìm thấy trace” làm bằng chứng rằng không có request hoặc không có lỗi.

Ngược lại, một trace tồn tại không chứng minh Prometheus đã scrape thành công. Các pipeline có thể lỗi độc lập:

| Pipeline | Các điểm cần kiểm tra |
| --- | --- |
| Metrics | Micrometer meter → `PrometheusMeterRegistry` → Actuator → scrape target → Prometheus |
| Traces | Micrometer Observation → tracing bridge/handler → sampling → exporter/Collector → trace backend |
| Logs | Logging framework → MDC/trace correlation → log transport → log backend |

### 9.2. Context propagation và exemplars

Để span của `order-service` và `inventory-service` cùng trace, HTTP client/server phải truyền và nhận ngữ cảnh tương thích, ví dụ header W3C `traceparent`. Với `@Async` hoặc executor, cần cơ chế propagation phù hợp khi chuyển thread. **`PrometheusMeterRegistry` không tự truyền trace context**.

Một số môi trường có **exemplars**: sample metric hoặc bucket có thể mang tham chiếu trace để mở trực tiếp trace từ dashboard. Khả năng này phụ thuộc client Prometheus, Micrometer, tracing, định dạng scrape và backend hỗ trợ; không bảo đảm chỉ cần thêm dependency là có exemplar. Không đưa trace ID vào label cho **mọi time series** như một cách thay thế, vì sẽ làm cardinality bùng nổ.

## 10. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `/actuator/prometheus` trả 404 | Thiếu dependency, chưa expose endpoint hoặc sai path/port | Kiểm tra classpath, Actuator exposure và management port |
| `/actuator/metrics` có meter nhưng Prometheus endpoint không có | Registry Prometheus chưa cấu hình, meter bị filter hoặc khác registry | Kiểm tra bean/registry, dependency và scrape output |
| Endpoint xuất metric nhưng Prometheus không có series | Target chưa được discovery, scrape fail, network/auth/TLS sai | Kiểm tra targets, `up`, scrape errors |
| Prometheus `up=1` nhưng thiếu metric nghiệp vụ | Meter chưa đăng ký, chưa có traffic, query lọc sai labels | Tìm series trong scrape text rồi so sánh PromQL |
| Counter giảm sau deploy | Process restart nên counter reset | Dùng `rate`/`increase` theo cửa sổ |
| Gauge không có giá trị | Đối tượng được gauge quan sát đã bị GC hoặc nguồn đọc lỗi | Giữ strong reference, kiểm tra callback |
| Histogram không có `_bucket` | Chưa bật histogram/SLO buckets hoặc registry không hỗ trợ | Kiểm tra cấu hình distribution và tên meter |
| p95 sai khi cộng nhiều instance | Lấy trung bình percentile hoặc không giữ `le` | Dùng `sum by(le)(rate(bucket))` |
| Truy vấn tỷ lệ lỗi trả no data | Sai nhãn `status`/`uri`, không có traffic hoặc mẫu số 0 | Kiểm tra labels thực và request count |
| Cardinality tăng mạnh | Raw URL, user ID, trace ID hoặc số lượng bucket quá nhiều | Giới hạn labels, route template, budget metrics |
| Metrics có nhưng traces mất | Sampling, propagation, OTLP exporter hoặc Collector | Kiểm tra pipeline tracing riêng |
| Trace có nhưng logs không liên kết | MDC/log pattern hoặc scope không được duy trì | Kiểm tra logging và trace/span ID |

### 10.1. Chẩn đoán theo thứ tự tránh suy đoán

Nếu `/actuator/prometheus` trả một chuỗi rỗng hoặc thiếu metric, hãy bắt đầu tại **ứng dụng**: bean registry có tồn tại không, meter đã được tạo chưa, endpoint có được bật không? Nếu endpoint có dữ liệu nhưng PromQL không thấy, chuyển sang **Prometheus**: target, labels, network, scrape errors, retention và truy vấn. Chỉ sau khi xác định nơi thiếu dữ liệu mới sửa cấu hình hoặc instrumentation.

Đừng tìm cách khắc phục lỗi scrape bằng cách tăng tracing sampling; hai cơ chế không phụ thuộc nhau.

## 11. Checklist cấu hình production

| Mục kiểm tra | Bằng chứng đạt |
| --- | --- |
| Micrometer và Prometheus registry tương thích | Dependency theo BOM, đúng Prometheus client branch |
| Spring Boot dùng registry thống nhất | Service inject registry do Boot quản lý |
| Endpoint scrape đúng và được bảo vệ | Path/port đúng, có network/auth phù hợp |
| Prometheus target hoạt động | `up=1`, scrape duration và lỗi được theo dõi |
| Time series có tên/đơn vị rõ ràng | Counter, Timer, Gauge có mô tả và labels hợp lý |
| Histogram được bật có chọn lọc | Bucket SLO/percentile đúng nơi cần |
| Nhãn có cardinality hữu hạn | Không có request ID/user ID/URL thô |
| Query có xử lý reset/traffic thấp | `rate`/`increase` đúng, tránh chia 0 |
| Có khả năng điều tra đa tín hiệu | Kết nối metrics với logs/traces khi cần |
| Hiểu sampling/propagation | Không kết luận sai khi trace vắng mặt |
| Có ngân sách metrics | Theo dõi số series, scrape payload, retention và chi phí |
| Thay đổi schema có review | Dashboard, recording rule và alert được cập nhật |

## 12. Bài thực hành: từ Counter/Timer đến dashboard Prometheus

**Bối cảnh:** `order-service` có endpoint `POST /orders` gọi inventory-service. Mục tiêu vận hành là phát hiện tăng lỗi 5xx và p95 quá 500 ms, đồng thời tìm được bước gây chậm trong trace mẫu.

**Nhiệm vụ:**

1. Thêm `spring-boot-starter-actuator` và `micrometer-registry-prometheus` vào Spring Boot, bật endpoint `/actuator/prometheus` trong môi trường thử nghiệm.
2. Khai báo một `Counter` `orders.processed` với tag `channel` chỉ nhận `web` hoặc `batch`. Ghi nhận sự kiện đúng thời điểm nghiệp vụ hoàn tất.
3. Dùng HTTP instrumentation có sẵn hoặc `Timer` nghiệp vụ để đo độ trễ; nếu cần p95 hoặc SLO ≤ 500 ms, bật histogram và bucket đúng mốc.
4. Chạy ứng dụng, gửi một số request nhanh/chậm và xem `/actuator/metrics` cùng `/actuator/prometheus`. Ghi tên series thật, đơn vị và labels.
5. Thiết lập Prometheus scrape target, xác nhận `up=1` và truy vấn `orders_processed_total`.
6. Viết PromQL tính request rate, error ratio, p95 và tỷ lệ request ≤ 500 ms, chỉ dùng nhãn xuất hiện thật trên dữ liệu.
7. Thử restart ứng dụng rồi giải thích tại sao counter reset và `rate` phù hợp hơn phép trừ giá trị thô.
8. Tạo lỗi timeout của inventory-service; đối chiếu metrics, logs theo trace ID và một trace chậm nếu sampling giữ lại.
9. Cố tình cấu hình sai `metrics_path` ở môi trường thử nghiệm; xác nhận target fail rồi sửa, **không thay đổi code nghiệp vụ**.
10. Ước lượng số series nếu thêm 3 vùng, 4 nhóm status và 20 bucket cho 20 instance. Giải thích lý do không thêm `order.id` vào labels.

**Kết quả mong đợi:** ứng dụng có registry Prometheus hoạt động, endpoint scrape được bảo vệ, các queries có cơ sở, unit/integration test xác minh output và một ghi chép chẩn đoán sự cố phân biệt lỗi registry/scrape với lỗi tracing/exporter.

## 13. Ghi nhớ

**`PrometheusMeterRegistry`** là cầu nối từ các `Meter` của Micrometer sang **định dạng Prometheus được thu thập theo cơ chế pull/scrape**. Trong Spring Boot, kết hợp Actuator và registry phù hợp giúp tạo endpoint `/actuator/prometheus` để Prometheus server thu thập. Tên meter, tags, bucket, đơn vị và nhãn sau khi xuất phải được kiểm tra thực tế trước khi dùng trong PromQL, dashboard hay alerts.

Một pipeline đáng tin cậy cần **registry được quản lý thống nhất**, endpoint an toàn, target scrape hoạt động, nhãn cardinality thấp và truy vấn xử lý đúng counter reset/histogram. Khi phối hợp với Micrometer Observation, logs và distributed tracing, metrics phát hiện phạm vi sự cố còn traces/logs giải thích đường đi và nguyên nhân; khả năng tương quan vẫn phụ thuộc sampling, context propagation và exporter/Collector của từng tín hiệu.

**Tài liệu tham khảo:**

- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Prometheus endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus — Histogram and Summary](https://prometheus.io/docs/practices/histograms/)
