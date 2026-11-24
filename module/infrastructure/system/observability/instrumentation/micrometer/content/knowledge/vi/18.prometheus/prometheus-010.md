# Exemplar và điều kiện liên kết phép đo với trace

Metrics cho biết hệ thống đang hoạt động như thế nào ở mức tổng hợp: request rate, tỷ lệ lỗi, latency p95 hoặc số lượng message. Khi một biểu đồ cho thấy spike bất thường, người vận hành thường cần tìm một request cụ thể để hiểu nguyên nhân. **Exemplar** tạo cầu nối giữa hai mức quan sát này bằng cách gắn metadata tham chiếu đến trace vào một mẫu metric.

Với Micrometer và Prometheus, exemplar thường mang trace_id và span_id của một thao tác đã được tracing ghi nhận. Người vận hành có thể chọn exemplar trên biểu đồ metrics rồi mở trace tương ứng trong hệ thống tracing như Tempo, Jaeger hoặc Zipkin. Exemplar không thay thế metrics hay trace; nó giúp chuyển từ dấu hiệu tổng hợp sang một ví dụ cụ thể.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, việc liên kết này chỉ hoạt động khi ứng dụng có trace context tại thời điểm ghi metric, registry có thể lấy thông tin span, dữ liệu được xuất theo OpenMetrics và Prometheus được cấu hình lưu exemplar. Bài này giải thích các điều kiện đó, cách cấu hình Spring Boot, cách kiểm tra dữ liệu xuất và những nguyên nhân khiến liên kết metric–trace không xuất hiện.

## 1. Exemplar là gì?

Exemplar là metadata gắn với một mẫu của time series. Nó có thể chứa một tập label riêng, giá trị mẫu và timestamp; trường hợp phổ biến là lưu trace ID và span ID để tham chiếu đến trace bên ngoài.

Ví dụ một dòng OpenMetrics có exemplar:

~~~text
# TYPE payment_requests_total counter
payment_requests_total 128.0 # {trace_id="4bf92f3577b34da6a3ce929d0e0e4736",span_id="00f067aa0ba902b7"} 1.0 1713310767.908
~~~

Phần trước dấu # là mẫu metric thông thường. Phần sau dấu # là exemplar gắn với mẫu đó. Trace ID và span ID cho phép công cụ trực quan hóa tìm trace tương ứng trong tracing backend.

Exemplar là một tham chiếu đến dữ liệu khác, không chứa toàn bộ span hay trace. Trace vẫn phải được ghi và lưu bởi hệ thống tracing. Nếu exemplar có trace ID nhưng trace chưa được export, đã hết retention hoặc người dùng không có quyền truy cập, thao tác mở trace sẽ không tìm thấy dữ liệu.

## 2. Exemplar không phải tag của metric

Cần phân biệt label của time series với label của exemplar:

| Đặc điểm | Metric tag/label | Exemplar metadata |
|---|---|---|
| Mục đích | Phân loại và truy vấn chuỗi thời gian | Tham chiếu một mẫu cụ thể đến trace hoặc dữ liệu ngoài |
| Ví dụ | service, method, status | trace_id, span_id |
| Tạo series mới? | Mỗi tổ hợp label tạo một time series riêng | Không tạo dimension/time series mới |
| Số lượng | Phải giới hạn chặt để kiểm soát cardinality | Được lưu cho một số mẫu được chọn |
| Cách dùng | Lọc, nhóm và tổng hợp PromQL | Chuyển từ metric sang trace cụ thể |

Không đưa trace_id hoặc span_id vào tag của Counter, Timer hay DistributionSummary. Mỗi request thường có ID riêng; nếu đưa ID đó thành label, số time series sẽ tăng theo số request và tạo cardinality rất cao.

Exemplar giải quyết nhu cầu liên kết này bằng metadata gắn với mẫu metric. Nó giữ metric labels ổn định, trong khi vẫn cho phép chọn một số mẫu có trace context để điều tra sâu.

## 3. Luồng liên kết từ metric đến trace

Một luồng điển hình với Spring Boot, Micrometer Tracing và Prometheus:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Micrometer Tracing tạo span"]
    B --> C["Mã ứng dụng ghi Counter / Timer"]
    C --> D["PrometheusMeterRegistry"]
    B --> E["Tracing exporter"]
    E --> F["Tempo / Jaeger / Zipkin"]
    D --> G["/actuator/prometheus"]
    G -->|"OpenMetrics scrape"| H["Prometheus"]
    H --> I["Metrics dashboard"]
    I -->|"Chọn exemplar"| F
~~~

Các bước chính:

1. Request đi vào ứng dụng và tracing instrumentation tạo trace/span context.
2. Trong lúc span còn hoạt động, mã ứng dụng ghi nhận Counter hoặc Timer.
3. Prometheus registry lấy trace context hiện hành để gắn exemplar vào mẫu metric được hỗ trợ.
4. Endpoint metrics xuất dữ liệu ở định dạng OpenMetrics.
5. Prometheus scrape endpoint và lưu exemplar nếu tính năng exemplar storage đã được bật.
6. Grafana hoặc công cụ tương đương hiển thị marker exemplar và dùng trace ID để mở trace trong tracing backend.

Metric và trace đi theo hai luồng export khác nhau. Prometheus lưu metrics và exemplar; tracing backend lưu trace. Cả hai phải dùng cùng trace ID để liên kết.

## 4. Điều kiện ở phía ứng dụng

Để Micrometer/Prometheus tạo exemplar có trace context, cần đáp ứng các điều kiện sau.

### Có tracing implementation và bridge tương thích

Ứng dụng cần có Micrometer Tracing cùng tracer implementation như OpenTelemetry hoặc Brave. Spring Boot Actuator cung cấp auto-configuration cho Micrometer Tracing. Khi Micrometer Tracing được cấu hình, Spring Boot có thể tự cung cấp SpanContext cho Prometheus registry.

Nếu dùng Prometheus registry mới (micrometer-registry-prometheus), thành phần cung cấp context là io.prometheus.metrics.tracer.common.SpanContext. Với registry legacy dựa trên Prometheus simpleclient (micrometer-registry-prometheus-simpleclient), API tương ứng là SpanContextSupplier.

Không trộn ví dụ cấu hình của registry mới và legacy. Hãy kiểm tra dependency thực tế để biết ứng dụng đang dùng loại client nào. Với Spring Boot và Micrometer Tracing được auto-configure, thường không cần tự viết SpanContext hoặc SpanContextSupplier.

### Có span đang hoạt động tại thời điểm ghi metric

Exemplar cần trace/span context khi meter ghi nhận mẫu. Ví dụ, Timer được ghi trong một HTTP request có span đang hoạt động có thể gắn exemplar. Nếu metric được cập nhật bởi một tác vụ nền không có trace context, registry không có trace ID để gắn.

Với xử lý bất đồng bộ, context phải được truyền qua executor, thread hoặc message boundary theo cơ chế context propagation của tracing implementation. Nếu công việc chạy trên thread khác nhưng không mang theo span context, exemplar có thể không xuất hiện dù request ban đầu đã được trace.

### Trace phải được sampling và export

Spring Boot mặc định chỉ đưa các trace đã được sampled vào exemplar. Nếu request không được sampler chọn, metric vẫn có thể được ghi nhận bình thường nhưng không có exemplar tương ứng.

Cấu hình xác suất sampling là quyết định về chi phí và độ bao phủ tracing. Trong môi trường phát triển có thể tăng sampling để dễ kiểm tra. Trong production, chọn xác suất hoặc chính sách sampling theo tải, ngân sách lưu trữ và yêu cầu điều tra. Không bật sampling 100% một cách mặc định cho hệ thống có lưu lượng lớn mà chưa đánh giá chi phí.

Spring Boot có thuộc tính management.tracing.exemplars.include để điều khiển trace nào được đưa vào exemplar. Với Prometheus, chế độ all không được hỗ trợ; cần tuân theo giới hạn của exporter và tracing integration đang dùng.

### Metric type phải hỗ trợ exemplar

Prometheus/OpenMetrics hỗ trợ exemplar trên một số loại metric như Counter và Histogram. Vì vậy, exemplar thường hữu ích với Counter và các quan sát phân phối của Timer hoặc DistributionSummary khi histogram được xuất.

Không nên giả định mọi Gauge hoặc mọi loại series đều có exemplar. Hãy kiểm tra metric type, registry và endpoint exposition thực tế. Với Timer, nếu cần histogram bucket để phân tích latency và gắn exemplar vào các quan sát phân phối, hãy cấu hình histogram phù hợp.

## 5. Cấu hình Spring Boot

Một ứng dụng Spring Boot thường cần các nhóm dependency sau:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Thêm Micrometer Tracing bridge phù hợp:
    // OpenTelemetry hoặc Brave.
    // Thêm exporter tương ứng để gửi trace đến tracing backend.
}
~~~

Tên dependency và starter tracing cụ thể phụ thuộc phiên bản Spring Boot và tracer được chọn. Hãy dùng dependency management/BOM của Spring Boot để giữ các phiên bản tương thích. Spring Boot hiện hỗ trợ các lựa chọn như OpenTelemetry với OTLP và Brave với Zipkin.

Ví dụ application.yml cho endpoint Prometheus và sampling:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus

  tracing:
    sampling:
      probability: 0.1
~~~

probability là ví dụ cấu hình sampling; chọn giá trị theo yêu cầu vận hành. Khi thử nghiệm local, có thể tăng xác suất để dễ tạo trace mẫu. Trong production, sampling cần được cân nhắc cùng tải và chính sách lưu trace.

Để trace có thể được mở từ exemplar, ứng dụng còn phải cấu hình exporter gửi span đến tracing backend. Cách cấu hình endpoint và credential phụ thuộc tracer/exporter và phiên bản Spring Boot. Chỉ tạo trace ID trong ứng dụng là chưa đủ nếu trace không được gửi và lưu ở backend.

## 6. Prometheus cần OpenMetrics và exemplar storage

Exemplar chỉ được xuất trong định dạng OpenMetrics; chúng không xuất hiện trong định dạng Prometheus text thông thường. Vì vậy, khi kiểm tra endpoint, hãy yêu cầu OpenMetrics:

~~~bash
curl --silent \
  -H 'Accept: application/openmetrics-text; version=1.0.0' \
  http://localhost:8080/actuator/prometheus
~~~

Endpoint /actuator/prometheus phải được expose và có thể truy cập từ máy kiểm tra. Nếu ứng dụng dùng management port hoặc base path riêng, hãy thay URL cho đúng cấu hình.

Prometheus cũng phải bật exemplar storage. Với các phiên bản Prometheus hỗ trợ tính năng này, có thể bật feature flag:

~~~bash
prometheus --enable-feature=exemplar-storage
~~~

Exemplar storage có giới hạn dung lượng dạng buffer vòng; nó không phải kho trace và không thay thế retention của tracing backend. Tham số max_exemplars của Prometheus điều khiển dung lượng buffer exemplar. Khi buffer đầy, exemplar cũ có thể bị loại khỏi vùng lưu trữ.

Cấu hình scrape vẫn trỏ đến endpoint metrics thông thường:

~~~yaml
scrape_configs:
  - job_name: checkout-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - checkout-service:8080
~~~

Prometheus cần thương lượng hoặc được cấu hình để nhận OpenMetrics. Khi endpoint chỉ trả Prometheus text format, exemplar sẽ không xuất hiện dù ứng dụng đã có trace context.

## 7. Ví dụ ghi Timer trong một span

Giả sử một HTTP request đã có span do Micrometer Tracing tạo. Service ghi thời gian xử lý bằng Timer:

~~~java
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final Timer checkoutTimer;

    public CheckoutMetrics(MeterRegistry registry) {
        this.checkoutTimer = Timer.builder("checkout.process")
                .description("Time spent processing checkout")
                .publishPercentileHistogram()
                .register(registry);
    }

    public <T> T record(Supplier<T> operation) {
        return checkoutTimer.record(operation);
    }
}
~~~

Đoạn code trên không truyền trace ID vào tag và cũng không tự tạo exemplar. Khi một span được tracing implementation quản lý đang hoạt động trong lúc Timer ghi nhận, Prometheus registry có thể lấy SpanContext đã được cấu hình và gắn exemplar vào mẫu được hỗ trợ.

Nếu operation được chuyển sang một thread hoặc executor khác, cần bảo đảm tracing context được propagate. Nếu context bị mất, Timer vẫn ghi nhận latency nhưng exemplar không có trace ID.

Với Counter, cách sử dụng tương tự: tăng Counter trong lúc span đang hoạt động. Exemplar có thể được gắn với mẫu Counter nếu registry và metric type hỗ trợ.

## 8. Đọc exemplar trong OpenMetrics exposition

Một exemplar trong OpenMetrics có dạng minh họa:

~~~text
# TYPE checkout_process_seconds histogram
checkout_process_seconds_bucket{le="0.5"} 42 # {trace_id="4bf92f3577b34da6a3ce929d0e0e4736",span_id="00f067aa0ba902b7"} 0.37 1713310767.908
checkout_process_seconds_bucket{le="1.0"} 48
checkout_process_seconds_count 50
checkout_process_seconds_sum 18.4
~~~

Dòng đầu có mẫu bucket le="0.5" và exemplar gắn với một quan sát có trace context. Dữ liệu exemplar có thể gồm:

- trace_id: định danh trace.
- span_id: định danh span liên quan.
- Giá trị quan sát và timestamp của exemplar.

Đây là định dạng minh họa để nhận biết vị trí exemplar; tên metric và cấu trúc series thực tế phụ thuộc registry, cấu hình histogram và quy tắc chuẩn hóa tên.

Nếu gọi endpoint với Prometheus text format, phần exemplar có thể bị bỏ qua. Hãy dùng content negotiation OpenMetrics để kiểm tra.

## 9. Mở trace từ dashboard

Khi Prometheus đã lưu exemplar và Grafana được cấu hình data source tracing phù hợp, người vận hành có thể chọn marker exemplar trên panel metric để mở trace tương ứng.

Để liên kết hoạt động, cần:

1. Panel truy vấn đúng metric có exemplar.
2. Grafana đọc được exemplar từ Prometheus data source.
3. Trace data source được cấu hình, chẳng hạn Tempo, Jaeger hoặc Zipkin.
4. Quy tắc liên kết sử dụng đúng trường trace ID mà exemplar cung cấp.
5. Tracing backend còn giữ trace đó và người dùng có quyền đọc.

Nếu exemplar xuất hiện nhưng click không mở trace, vấn đề có thể nằm ở trace data source, mapping trace ID, tenant hoặc retention. Prometheus chỉ lưu tham chiếu exemplar; nó không lưu toàn bộ span.

Một số nền tảng có thể cấu hình trace-to-logs hoặc trace-to-metrics để điều hướng hai chiều. Những liên kết đó là cấu hình của công cụ trực quan hóa và data source, không được tạo tự động chỉ bởi việc thêm Prometheus registry.

## 10. Exemplar không thay thế việc thiết kế metrics và traces

Metrics và traces có vai trò bổ sung:

- Metrics cho biết xu hướng, tỷ lệ, tổng lượng và phân vị ở quy mô dịch vụ.
- Traces cho biết đường đi của một request qua các service, thời gian từng span và quan hệ gọi nhau.
- Exemplars nối một mẫu metric đáng chú ý với trace cụ thể để điều tra.

Không ghi mọi request thành một metric riêng chỉ để có liên kết trace. Hãy giữ metric name và label ổn định, còn trace ID được gắn trong exemplar. Cũng không nên coi exemplar là cơ chế đảm bảo có trace cho mọi mẫu: sampling và giới hạn lưu trữ khiến exemplar thường thưa hơn số mẫu metric.

Exemplar hữu ích nhất khi metrics đã được thiết kế tốt: Timer có histogram cho latency, Counter cho số sự kiện, tag có cardinality thấp và dashboard có truy vấn giúp xác định thời điểm hoặc nhóm bất thường.

## 11. Nguyên nhân thường gặp khi không thấy exemplar

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Metric có nhưng không có exemplar | Không có SpanContext bean/provider, không có span đang hoạt động hoặc trace không được sampled |
| Trace được tạo nhưng exemplar không xuất hiện | Metric type hoặc registry không hỗ trợ; context bị mất ở async boundary |
| Endpoint có metric nhưng không có exemplar | Endpoint trả Prometheus text thay vì OpenMetrics |
| OpenMetrics có exemplar nhưng Prometheus không lưu | Exemplar storage chưa bật hoặc scrape protocol không nhận OpenMetrics |
| Prometheus lưu exemplar nhưng Grafana không hiển thị | Phiên bản/cấu hình data source hoặc panel chưa hỗ trợ exemplar |
| Click exemplar nhưng không tìm thấy trace | Trace chưa export, hết retention, sai trace ID mapping hoặc thiếu quyền truy cập |
| Chỉ một số request có exemplar | Sampling chỉ chọn một phần trace; đây thường là hành vi dự kiến |

Cách kiểm tra theo thứ tự:

1. Xác nhận tracing implementation hoạt động và span được tạo.
2. Xác nhận Micrometer Tracing hoặc SpanContext provider được kết nối với Prometheus registry.
3. Ghi metric trong lúc span đang hoạt động.
4. Kiểm tra sampling policy và trạng thái sampled của trace.
5. Gọi endpoint với Accept header OpenMetrics và tìm exemplar.
6. Xác nhận Prometheus bật exemplar storage và scrape đúng định dạng.
7. Truy vấn hoặc xem exemplar trong Prometheus/Grafana.
8. Dùng trace ID để tìm trace trực tiếp trong tracing backend.

## 12. Checklist triển khai metric–trace correlation

Trước khi đưa exemplar vào production, hãy xác nhận:

- Ứng dụng có Prometheus registry tương thích.
- Micrometer Tracing được cấu hình với tracer implementation và exporter phù hợp.
- Prometheus registry có SpanContext; Spring Boot có thể auto-configure khi Micrometer Tracing hiện diện.
- Metric được ghi trong lúc span context còn hoạt động.
- Context được propagate qua các thread hoặc tác vụ bất đồng bộ cần thiết.
- Sampling policy tạo đủ trace để điều tra nhưng vẫn phù hợp ngân sách.
- Endpoint xuất OpenMetrics.
- Prometheus bật exemplar storage.
- Grafana hoặc công cụ tương đương kết nối được cả metrics backend và tracing backend.
- Trace ID mapping, retention và quyền truy cập cho phép mở trace.
- trace_id và span_id không bị đưa nhầm thành metric tag.

Exemplar giúp chuyển từ một dấu hiệu tổng hợp trên metrics sang một trace cụ thể để tìm nguyên nhân. Để liên kết hoạt động, ứng dụng phải có span context đúng lúc ghi metric, Prometheus registry phải lấy được context, endpoint phải xuất OpenMetrics, Prometheus phải lưu exemplar và tracing backend phải còn trace tương ứng. Khi tất cả điều kiện được đáp ứng, metrics và traces tạo thành một quy trình điều tra liền mạch mà không làm tăng cardinality của time series.

## Tài liệu tham khảo

- [Micrometer - Prometheus registry and Exemplars](https://docs.micrometer.io/micrometer/reference/implementations/prometheus)
- [Spring Boot - Metrics and Prometheus Exemplars](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot - Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Prometheus - Exposition formats](https://prometheus.io/docs/instrumenting/exposition_formats/)
- [Prometheus - Configuration and exemplar storage](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
