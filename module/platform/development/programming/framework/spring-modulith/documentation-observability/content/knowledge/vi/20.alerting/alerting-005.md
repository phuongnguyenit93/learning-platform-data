# Cảnh báo telemetry không được export

## 1. Vì sao phải cảnh báo khi telemetry không tới nơi?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, telemetry giúp đội phát triển quan sát ranh giới và tương tác giữa các application module. Ví dụ, module `ordering` nhận yêu cầu đặt hàng, gọi `payment`, phát `OrderPlaced` và module `notification` xử lý event. Module graph cho biết cấu trúc phụ thuộc; event metrics cho biết publication; module-entry spans, traces và logs giúp hiểu một lần thực thi.

Các tín hiệu này chỉ có giá trị khi chúng đi hết pipeline. Nếu ứng dụng ngừng export span, Prometheus không scrape được metrics, log agent ngừng gửi log hoặc collector không chuyển dữ liệu tới backend, dashboard có thể trống dù nghiệp vụ vẫn chạy bình thường. Khi đó đội vận hành mất khả năng phát hiện lỗi, latency bất thường và sự cố giữa các module.

**Telemetry không được export** có thể xảy ra ở nhiều tầng:

1. Ứng dụng không tạo tín hiệu do instrumentation hoặc cấu hình bị thiếu.
2. Ứng dụng tạo tín hiệu nhưng exporter không gửi được.
3. Collector không nhận, từ chối hoặc drop dữ liệu.
4. Collector nhận dữ liệu nhưng queue, processor hoặc exporter downstream bị lỗi.
5. Backend nhận dữ liệu nhưng ingest, index hoặc truy vấn không hoạt động.
6. Dashboard truy vấn sai datasource, label hoặc time range.

Vì vậy, không nên chỉ cảnh báo “dashboard không có dữ liệu”. Cần theo dõi từng chặng và có một phép kiểm tra end-to-end để biết dữ liệu thực sự đến backend hay chưa.

Bài học thuộc chương **Alerting** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này hướng dẫn dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác khi ứng dụng Spring Boot vận hành, gồm module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt đường export của metrics, traces và logs.
- Xác định tín hiệu health ở ứng dụng, exporter, collector và backend.
- Viết PromQL cảnh báo collector down, receiver từ chối dữ liệu, exporter lỗi và queue đầy.
- Phân biệt telemetry không có dữ liệu do không có traffic với telemetry pipeline bị hỏng.
- Dùng synthetic canary để kiểm tra dữ liệu đi hết pipeline.
- Kết nối cảnh báo telemetry với Spring Modulith module-entry spans và event metrics.
- Thiết kế severity, thời gian chờ, no-data handling và runbook.
- Tránh tạo alert giả do sampling, cardinality hoặc endpoint quản trị bị bảo vệ.

## 2. Trước tiên, phân biệt ba đường telemetry

Metrics, traces và logs thường không dùng chung một đường export. Cần theo dõi riêng từng tín hiệu.

| Tín hiệu | Nguồn trong ứng dụng | Đường truyền thường gặp | Điểm kiểm tra |
| --- | --- | --- | --- |
| **Metrics** | Micrometer meters, Spring Boot Actuator. | Prometheus scrape `/actuator/prometheus`, hoặc metrics exporter/collector theo cấu hình. | Scrape target, `up`, sample freshness, scrape errors. |
| **Traces** | Micrometer Observation + Micrometer Tracing bridge. | OTLP exporter gửi span tới OpenTelemetry Collector, sau đó tới tracing backend. | Exporter errors, collector accepted/refused spans, queue và backend ingestion. |
| **Logs** | SLF4J/Logback hoặc logging implementation khác. | stdout/file → agent/collector → log backend. | Agent health, read errors, dropped records, backend ingestion và log freshness. |

Một ứng dụng có thể vẫn export metrics bình thường trong khi traces mất do OTLP exporter lỗi. Logs có thể tiếp tục được ghi ra stdout dù log shipper không chạy. Ngược lại, tracing backend có dữ liệu nhưng Prometheus scrape endpoint bị lỗi.

**Đừng gộp ba tín hiệu thành một alert chung.** Mỗi pipeline cần health indicator và runbook riêng; dashboard tổng quan có thể ghép chúng lại để người trực thấy tình trạng toàn hệ thống.

### 2.1. Pipeline minh họa

~~~mermaid
flowchart TB
    subgraph APP["Spring Boot + Spring Modulith"]
        MOD["Module-entry observations"]
        EVT["Event metrics"]
        HTTP["HTTP / application metrics"]
        TRACE["Micrometer Tracing"]
        LOG["Application logs"]
    end
    PROM["Prometheus"]
    COL["OpenTelemetry Collector"]
    LOGAGENT["Log agent / log collector"]
    TRACEBACK["Tempo / Jaeger"]
    LOGBACK["Loki / log backend"]
    MOD --> TRACE
    EVT --> PROM
    HTTP --> PROM
    TRACE --> COL --> TRACEBACK
    LOG --> LOGAGENT --> LOGBACK
~~~

Sơ đồ mô tả một cách triển khai phổ biến. Có thể thay datasource/backend theo hạ tầng thực tế; điều quan trọng là xác định rõ điểm bắt đầu, giao thức và điểm nhận cuối của từng pipeline.

### 2.2. Module graph không phải health check của telemetry

Endpoint `/actuator/modulith` cho biết cấu trúc application module được nhận diện. Nó không chứng minh span đã được export, event listener đã hoàn tất hay collector đang hoạt động.

Tương tự, event counter `module.events.published` tăng cho biết publication được instrument; nó không chứng minh consumer span đã đến tracing backend. Cần có tín hiệu kiểm tra export độc lập.

## 3. Xác định telemetry bị mất ở tầng nào

Một cách điều tra hữu ích là chia pipeline thành các chặng và đặt câu hỏi cho từng chặng.

| Chặng | Câu hỏi | Dấu hiệu lỗi |
| --- | --- | --- |
| Instrumentation | Ứng dụng có tạo meter/span/log không? | Không có observation, meter hoặc log record ngay tại nguồn. |
| Exporter / scrape | Dữ liệu có rời ứng dụng không? | Export exception, scrape timeout, HTTP 401/403/5xx, DNS/TLS error. |
| Collector receiver | Collector có nhận được dữ liệu không? | Receiver refused tăng, accepted không tăng dù nguồn có traffic. |
| Processor / queue | Collector có xử lý và giữ dữ liệu được không? | Processor drop, memory pressure, queue gần đầy. |
| Collector exporter | Collector có gửi tới backend không? | Send failures, enqueue failures, queue không giảm. |
| Backend ingest | Backend có nhận và lưu dữ liệu không? | Ingestion error, write rejection, rate limit, storage failure. |
| Dashboard/query | Dữ liệu có được truy vấn đúng không? | Datasource lỗi, label selector sai, time range sai hoặc query timeout. |

Không phải metric nào cũng có sẵn ở mọi phiên bản. Tên internal metric của OpenTelemetry Collector, label và cách bật telemetry có thể thay đổi theo distribution/version. Hãy kiểm tra endpoint metrics của collector và tài liệu đúng phiên bản trước khi đưa query vào production.

## 4. Bật và bảo vệ các điểm kiểm tra trong Spring Boot

### 4.1. Actuator và Prometheus scrape

Ví dụ cấu hình cho môi trường nội bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus,modulith"
  endpoint:
    health:
      show-details: when_authorized
~~~

Dependency Prometheus registry trong Gradle (nếu dự án chưa có):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Sau khi khởi động, kiểm tra endpoint trong môi trường được phép:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/prometheus
curl -i http://localhost:8080/actuator/modulith
~~~

Không expose tất cả Actuator endpoints ra Internet. Hãy đặt management port/network policy riêng khi phù hợp, bảo vệ endpoint bằng authentication/authorization và chỉ cho Prometheus hoặc hệ thống quản trị được phép truy cập.

### 4.2. Prometheus scrape config

Ví dụ scrape endpoint của ứng dụng:

~~~yaml
scrape_configs:
  - job_name: shop-service
    metrics_path: /actuator/prometheus
    scrape_interval: 30s
    static_configs:
      - targets:
          - shop-service:8080
~~~

Đây là cấu hình minh họa. Với Kubernetes, thường dùng service discovery/ServiceMonitor/PodMonitor thay cho static target. Nếu endpoint có TLS hoặc xác thực, cấu hình scrape credentials và certificate theo chính sách hạ tầng; không đặt password trực tiếp trong file dashboard hoặc repository.

### 4.3. Tracing qua OTLP

Ví dụ Spring Boot dùng Micrometer Tracing bridge OpenTelemetry và OTLP exporter:

~~~kotlin
dependencies {
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Ví dụ endpoint OTLP/HTTP:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Property và auto-configuration phụ thuộc phiên bản Spring Boot. Hãy xác nhận ứng dụng thật sự tạo được bean tracer/exporter và endpoint đúng giao thức. Nếu dùng Brave/Zipkin, đường export khác; không áp dụng cấu hình OTLP này mà không có bridge/exporter tương ứng.

### 4.4. Logs

Trong container, ứng dụng thường ghi logs ra stdout/stderr để agent hoặc runtime thu thập. Kiểm tra riêng:

- Ứng dụng có phát log ở mức cấu hình mong đợi không?
- Container runtime có giữ log stream không?
- Agent có đọc đúng path/stream và parse timestamp không?
- Agent có báo dropped records hoặc backpressure không?
- Log backend có nhận, index và truy vấn được log mới không?

Không suy luận “không có log trên backend” nghĩa là ứng dụng không chạy. Có thể log agent hoặc backend đang lỗi.

## 5. Giám sát OpenTelemetry Collector

Collector là một mắt xích quan trọng của trace pipeline. Cần scrape internal metrics của collector bằng Prometheus hoặc hệ thống monitoring tương đương. Bản phân phối Collector và phiên bản có thể dùng cấu hình telemetry metrics khác nhau; hãy bật endpoint metrics theo tài liệu phiên bản đang triển khai và giới hạn truy cập ở mạng quản trị.

### 5.1. Scrape internal metrics

Ví dụ Prometheus scrape endpoint collector đã được cấu hình để lắng nghe tại cổng 8888:

~~~yaml
scrape_configs:
  - job_name: otel-collector
    scrape_interval: 15s
    static_configs:
      - targets:
          - otel-collector:8888
~~~

Địa chỉ 8888 chỉ là ví dụ. Kiểm tra cấu hình `service.telemetry.metrics` của Collector đang chạy và thử endpoint `/metrics` từ mạng Prometheus có thể truy cập.

### 5.2. Các nhóm internal metrics cần quan sát

Tên metric dưới đây là các tên thường gặp ở OpenTelemetry Collector Contrib. Chúng có thể khác theo phiên bản, distribution, feature gate hoặc cấu hình telemetry. Trước khi tạo alert, hãy xem `/metrics` thực tế để xác nhận tên, loại metric và label:

| Nhóm | Metric thường gặp | Ý nghĩa |
| --- | --- | --- |
| Receiver | `otelcol_receiver_accepted_spans` | Số span receiver đã nhận. |
| Receiver | `otelcol_receiver_refused_spans` | Số span receiver từ chối. |
| Processor | `otelcol_processor_dropped_spans` | Số span bị processor drop, nếu metric được phát. |
| Exporter | `otelcol_exporter_sent_spans` | Số span exporter gửi thành công. |
| Exporter | `otelcol_exporter_send_failed_spans` | Số span exporter gửi thất bại. |
| Exporter queue | `otelcol_exporter_queue_size` | Số phần tử hiện có trong queue nếu queue được bật và metric được export. |
| Exporter queue | `otelcol_exporter_queue_capacity` | Sức chứa queue nếu metric được export. |

Một số metric có thể được đặt tên theo tín hiệu cụ thể như spans, metrics hoặc logs. Hãy kiểm tra cả label `receiver`, `exporter`, `pipeline`, `service_name` hoặc label tương đương để khoanh vùng pipeline. Không copy nguyên query từ môi trường khác khi chưa xác nhận schema.

### 5.3. Alert collector không được scrape

Nếu Prometheus vẫn scrape được job nhưng target down:

~~~promql
up{job="otel-collector"} == 0
~~~

Nếu target biến mất hoàn toàn khỏi service discovery:

~~~promql
absent(up{job="otel-collector"})
~~~

Alert đầu tiên phát hiện scrape target tồn tại nhưng không scrape thành công; alert thứ hai phát hiện series không xuất hiện. Có thể dùng cả hai hoặc xử lý absent trong rule tùy cách quản lý target. Nếu collector chạy nhiều replica, group theo cluster/namespace/instance để xác định phạm vi lỗi.

### 5.4. Alert receiver từ chối span

Ví dụ:

~~~promql
sum by (receiver) (
  rate(otelcol_receiver_refused_spans[5m])
) > 0
~~~

Receiver refused tăng có thể do overload, request không hợp lệ, giới hạn kích thước hoặc lỗi tại receiver. Cần đối chiếu log collector và các metric accepted/refused khác. Không phải mọi receiver đều expose label `receiver`; chỉnh theo metric thực tế.

### 5.5. Alert exporter gửi span thất bại

~~~promql
sum by (exporter) (
  increase(otelcol_exporter_send_failed_spans[5m])
) > 0
~~~

Alert này phát hiện có lần gửi thất bại trong cửa sổ 5 phút. Nó không khẳng định toàn bộ trace bị mất: exporter có thể retry thành công sau đó. Hãy kiểm tra thêm queue, sent spans, retry và log exporter để xác định mức độ ảnh hưởng.

### 5.6. So sánh accepted và sent

Một dấu hiệu cần điều tra là collector nhận span nhưng không gửi thành công trong khi traffic vẫn hiện diện:

~~~promql
sum(rate(otelcol_receiver_accepted_spans[5m])) > 0
and
sum(rate(otelcol_exporter_sent_spans[5m])) == 0
~~~

Query này chỉ là tín hiệu gợi ý. Nó cần điều chỉnh theo pipeline/receiver/exporter tương ứng; collector có thể có nhiều receiver, nhiều exporter hoặc processor intentionally drop spans. Không so sánh tổng accepted của mọi pipeline với một exporter đơn lẻ nếu kiến trúc có fan-out hoặc routing.

### 5.7. Queue exporter gần đầy

Nếu exporter dùng sending queue và expose cả size/capacity:

~~~promql
otelcol_exporter_queue_size
/
otelcol_exporter_queue_capacity
> 0.8
~~~

Ngưỡng 80% là ví dụ để bắt đầu cảnh báo sớm. Có thể cần thời gian duy trì (`for`) để tránh alert do spike ngắn. Nếu queue metrics không có, kiểm tra cấu hình exporter queue và các metric thay thế. Queue gần đầy thường báo hiệu backend chậm, mạng lỗi hoặc exporter không drain kịp.

### 5.8. Processor drop spans

Nếu Collector version phát metric dropped spans:

~~~promql
sum by (processor) (
  increase(otelcol_processor_dropped_spans[5m])
) > 0
~~~

Không phải mọi span bị drop đều là sự cố. Tail-sampling processor chủ động loại trace không match policy; filter processor có thể loại telemetry theo thiết kế. Phân biệt intentional drop với drop do lỗi hoặc quá tải trước khi đặt severity. Có thể cần dashboard theo processor/pipeline và log để giải thích.

## 6. Cảnh báo Prometheus scrape và metrics không cập nhật

### 6.1. Ứng dụng không scrape được

~~~promql
up{job="shop-service"} == 0
~~~

Nếu target mất khỏi service discovery:

~~~promql
absent(up{job="shop-service"})
~~~

Đây là cảnh báo scrape, không phải bằng chứng ứng dụng đã dừng hoàn toàn. Endpoint có thể bị chặn bởi network policy, authentication, management port hoặc TLS configuration.

### 6.2. Metric không có sample mới

Ví dụ kiểm tra metric HTTP request không xuất hiện trong khoảng thời gian:

~~~promql
absent_over_time(
  http_server_requests_seconds_count{job="shop-service"}[10m]
)
~~~

Không dùng rule này một cách máy móc cho service ít traffic. Không có request thì HTTP request counter không tăng là bình thường. Với metric chỉ xuất hiện sau khi meter được khởi tạo, series có thể chưa tồn tại trước request đầu tiên.

### 6.3. Phân biệt scrape failure với no traffic

| Quan sát | Khả năng | Hành động |
| --- | --- | --- |
| `up=0` | Prometheus không scrape được target. | Kiểm tra mạng, endpoint, auth/TLS và app availability. |
| `up=1`, request rate bằng 0 | Scrape hoạt động nhưng chưa có request. | Xác minh traffic kỳ vọng; không alert lỗi telemetry chỉ vì traffic bằng 0. |
| `up=1`, nhiều meter khác vẫn tăng nhưng một meter biến mất | Instrumentation hoặc meter registration thay đổi. | Kiểm tra deploy, dependency, filter và naming. |
| `up` series biến mất | Target discovery hoặc scrape config không còn target. | Kiểm tra service discovery, labels và Prometheus config. |
| `up=1`, sample timestamp cũ | Scrape có thể đang nhận stale/không cập nhật đúng dữ liệu, hoặc query sai. | Kiểm tra scrape logs, target page và freshness của sample. |

Prometheus `up` xác nhận scrape endpoint trả lời thành công; nó không chứng minh mọi meter trong ứng dụng được đăng ký đúng. Cần một canary metric hoặc expected metric set cho các tín hiệu quan trọng.

## 7. Cảnh báo trace export và log shipping

### 7.1. Trace không xuất hiện không nhất thiết là exporter hỏng

Một trace có thể không xuất hiện trong backend vì nhiều lý do:

- Sampling chủ động loại trace.
- Request không đi qua instrumentation tạo span.
- Parent-based sampling kế thừa quyết định không sampled.
- Span được tạo nhưng context bị mất ở async/message boundary.
- Ứng dụng exporter không gửi được.
- Collector drop hoặc chưa quyết định tail-sampling.
- Backend ingestion/index/query gặp lỗi.

Do đó, alert kiểu `absent(trace)` ở backend rất dễ báo giả. Cần biết traffic kỳ vọng, sampling policy và có synthetic trace riêng để xác minh pipeline.

### 7.2. Theo dõi exporter tại ứng dụng

Spring Boot/Micrometer Tracing exporter có thể ghi lỗi export vào log ứng dụng hoặc logger của thư viện. Hãy thu thập các log này và theo dõi:

- Lỗi kết nối, DNS, TLS hoặc xác thực tới OTLP endpoint.
- Deadline/timeout khi gửi batch.
- Retry tăng hoặc batch bị drop sau khi retry hết.
- Queue/worker không xử lý kịp nếu exporter có cơ chế buffering.

Không giả định mọi bridge/exporter phát ra một metric Micrometer chung cho export failure. Tùy implementation, dấu hiệu đáng tin cậy có thể nằm trong exporter logs, OpenTelemetry SDK metrics hoặc collector receiver metrics.

### 7.3. Log agent và log backend

Tên metric của Fluent Bit, Vector, Filebeat, OpenTelemetry Collector hoặc agent khác không giống nhau. Khi cấu hình alert, xác định metric tương ứng với:

| Chỉ số | Điều cần phát hiện |
| --- | --- |
| Agent process/target health | Agent bị dừng hoặc không scrape được. |
| Records read/processed | Agent còn đọc được log nguồn không. |
| Records dropped/rejected | Log bị loại do parse error, buffer hoặc policy. |
| Retry/failed requests | Không gửi được tới log backend. |
| Buffer/queue utilization | Agent bị backpressure hoặc gần hết disk/memory. |
| Backend ingest/freshness | Log mới có xuất hiện và truy vấn được không. |

Các tên metric cụ thể phụ thuộc agent. Không tự đặt query theo tên giả định; xem endpoint metrics, exporter docs và dashboard mẫu của agent đang dùng.

### 7.4. Phát hiện log pipeline ngừng gửi

Không có log mới từ một module có thể là bình thường nếu module không chạy. Để xác minh pipeline, tạo một **log canary** định kỳ từ một thành phần kiểm tra, với field cố định như `telemetry.canary=true`, service và environment. Một checker truy vấn log backend và cập nhật timestamp lần thành công gần nhất:

~~~text
telemetry.canary=true
service.name=shop-service
environment=staging
~~~

Checker có thể expose metric:

~~~text
telemetry_canary_last_success_timestamp_seconds
~~~

Đây là metric custom của checker, không phải metric có sẵn của Spring Boot. Alert khi timestamp thành công cuối quá cũ:

~~~promql
time() - telemetry_canary_last_success_timestamp_seconds > 180
~~~

Chỉ dùng phép kiểm tra này khi checker thực sự query được backend và xác nhận record mới, không phải chỉ khi ứng dụng ghi log ra stdout.

## 8. Synthetic canary: xác minh end-to-end

Internal metrics của collector cho biết collector đang hoạt động, nhưng chưa chứng minh một span cụ thể đi được từ ứng dụng tới backend và có thể truy vấn. **Synthetic canary** bổ sung phép kiểm tra từ đầu tới cuối.

### 8.1. Luồng canary

~~~mermaid
sequenceDiagram
    participant C as Canary scheduler
    participant A as Spring Boot canary instrumentation
    participant O as OTLP / Prometheus / log pipeline
    participant B as Backend
    participant V as Canary verifier
    participant P as Prometheus
    C->>A: tạo span/log/metric canary
    A->>O: export telemetry
    O->>B: collector/agent chuyển tiếp
    V->>B: truy vấn record mới theo canary ID
    B-->>V: record tìm thấy
    V->>P: cập nhật last_success_timestamp
~~~

Mỗi tín hiệu cần kiểm tra riêng:

- **Metrics canary:** Prometheus scrape được một gauge/counter heartbeat mới từ target.
- **Trace canary:** ứng dụng tạo một span có tên/attribute cố định; verifier tìm thấy trace mới trong tracing backend.
- **Log canary:** ứng dụng ghi một log marker; verifier tìm thấy record mới trong log backend.

Canary phải có chi phí thấp, không gọi nghiệp vụ gây side effect và không chứa dữ liệu cá nhân. Dùng ID ngẫu nhiên ở trace/log nếu cần đối chiếu từng lần chạy, nhưng không đưa ID đó thành metric label.

### 8.2. Không để sampling làm canary trace biến mất

Nếu trace canary đi qua cùng head sampler 5% với request thông thường, có thể có 95% lần chạy không được export. Khi đó checker báo lỗi giả. Cần thiết kế một canary trace được lấy mẫu chắc chắn theo cấu hình riêng, hoặc dùng một synthetic service/pipeline có sampling 100% và chỉ tạo lưu lượng kiểm tra nhỏ.

Nếu không thể bảo đảm sampling của canary, hãy tính xác suất và dùng kiểm tra phù hợp; không coi một lần canary bị sampling loại là exporter failure.

### 8.3. Metric heartbeat và alert freshness

Verifier có thể phát metric:

~~~text
telemetry_canary_last_success_timestamp_seconds{signal="traces"}
telemetry_canary_last_success_timestamp_seconds{signal="logs"}
telemetry_canary_last_success_timestamp_seconds{signal="metrics"}
~~~

Các series trên là metric custom do checker phát. Alert tổng quát:

~~~promql
time() - telemetry_canary_last_success_timestamp_seconds > 180
~~~

Có thể group theo `signal`, `service` và `environment`. Chỉ dùng các label có miền giá trị hữu hạn; không thêm canary ID, trace ID hoặc timestamp làm label.

### 8.4. Đặt chu kỳ canary và ngưỡng

Ví dụ canary chạy mỗi phút, alert khi không thấy record mới trong ba phút. Cửa sổ cần tính đến:

- Chu kỳ chạy và jitter của scheduler.
- Scrape interval của Prometheus.
- `decision_wait` nếu trace đi qua tail-sampling processor.
- Batch/export delay và thời gian index của backend.
- Mức độ trễ chấp nhận được theo SLO telemetry.

Không đặt ngưỡng đúng bằng một chu kỳ. Nếu backend thường index sau 30 giây, một canary mỗi phút với ngưỡng 60 giây có thể gây cảnh báo chập chờn.

### 8.5. Canary không thay thế monitoring nội bộ

Nếu canary thất bại, checker chỉ cho biết pipeline end-to-end không đạt. Nó không chỉ ra ngay tầng nào hỏng. Cần kết hợp với collector internal metrics, Prometheus target health, agent health và backend ingestion metrics để khoanh vùng.

## 9. Liên hệ cảnh báo với Spring Modulith

### 9.1. Module-entry spans

Khi Spring Modulith observability được bật, module-entry observations có thể trở thành spans thông qua Micrometer Tracing. Tag module như:

- `module.identifier`
- `module.name`
- `module.method`
- `module.invocation-type`

giúp lọc trace theo module. Nếu trace không xuất hiện, kiểm tra lần lượt:

1. Lời gọi có đi qua Spring-managed module API được instrument không?
2. ObservationRegistry có tracing handler không?
3. Micrometer Tracing bridge/exporter có được cấu hình không?
4. Sampling có loại trace không?
5. OTLP receiver/collector/backend có nhận và lưu trace không?

Không tạo alert “module không có span” chỉ vì module không có traffic. Nếu module quan trọng phải được gọi định kỳ, dùng expected traffic hoặc synthetic request có chủ đích.

### 9.2. Event metrics

Spring Modulith có event publication metrics như `module.events.published` và counter riêng theo module/event type. Có thể dùng chúng để xác nhận event publication còn hoạt động, nhưng counter này không chứng minh event đã được xử lý hoặc telemetry đã tới backend.

Ví dụ, nếu metric đã được xác nhận trên `/actuator/prometheus`, có thể theo dõi rate publication theo module/event type. Nếu Prometheus scrape thành công nhưng event meter biến mất sau deploy, kiểm tra Insight Starter, event instrumentation, meter filters và thay đổi tên/label.

### 9.3. Event Publication Registry và telemetry export là hai pipeline

Event Publication Registry theo dõi publication tới transactional listener và trạng thái hoàn tất theo cơ chế được cấu hình. Nó giúp kiểm tra event processing/recovery. Collector exporter queue theo dõi việc chuyển telemetry tới backend. Hai cơ chế giải quyết hai vấn đề khác nhau.

Nếu listener thất bại, registry có thể cho biết publication chưa hoàn tất; nếu span export thất bại, collector/exporter metrics cho biết telemetry bị tắc. Đừng dùng một loại counter thay cho loại còn lại.

### 9.4. Context propagation và trace bị đứt

Listener bất đồng bộ có thể chạy trên executor thread khác. Nếu context propagation không được cấu hình, listener span có thể không liên kết với trace gốc. Đây là lỗi trace continuity, không nhất thiết là exporter failure.

Với executor nội bộ, kiểm tra `ContextPropagatingTaskDecorator` hoặc cơ chế context propagation phù hợp. Với Kafka/RabbitMQ hoặc process boundary, kiểm tra inject/extract trace context qua message headers và instrumentation của framework. Alert pipeline cần phân biệt “span không có parent” với “span không được export”.

## 10. Viết alert rules và phân cấp severity

Alert nên giúp người trực biết mức độ ảnh hưởng và hành động tiếp theo. Không đặt mọi lỗi exporter thành critical ngay lập tức nếu exporter đang retry thành công và không có dữ liệu bị mất.

| Severity | Ví dụ điều kiện | Phản ứng |
| --- | --- | --- |
| **Critical** | Collector toàn bộ target down; canary end-to-end mất kéo dài; exporter send failures liên tục kèm queue đầy. | On-call xử lý ngay, kiểm tra mất telemetry và phục hồi pipeline. |
| **Warning** | Queue vượt 80% trong một khoảng thời gian; receiver refused tăng ngắn; exporter có retry nhưng vẫn gửi được. | Kiểm tra capacity, backend latency và network. |
| **Info** | Intentional tail-sampling drop hoặc module ít traffic. | Ghi nhận để phân tích, không đánh thức on-call. |

### 10.1. Ví dụ Prometheus alert rules

Các metric Collector trong ví dụ phải được xác minh trên endpoint thực tế. Metric canary là custom metric do verifier phát:

~~~yaml
groups:
  - name: telemetry-pipeline
    rules:
      - alert: OTelCollectorTargetDown
        expr: up{job="otel-collector"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "OpenTelemetry Collector target is down"
          description: "Prometheus cannot scrape the collector metrics endpoint."

      - alert: OTelExporterSendFailures
        expr: sum(increase(otelcol_exporter_send_failed_spans[5m])) > 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Collector exporter has send failures"
          description: "Check exporter logs, queue utilization, network and backend ingestion."

      - alert: OTelExporterQueueNearlyFull
        expr: otelcol_exporter_queue_size / otelcol_exporter_queue_capacity > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Collector exporter queue is nearly full"
          description: "The exporter may be unable to drain telemetry at the incoming rate."

      - alert: TelemetryTraceCanaryStale
        expr: time() - telemetry_canary_last_success_timestamp_seconds{signal="traces"} > 180
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "No recent trace canary found in the backend"
          description: "End-to-end trace delivery or backend query may be failing."
~~~

Đây là mẫu rule cần điều chỉnh theo metric name, label, queue config và SLO của môi trường. Nếu một metric không được Collector phát, rule sẽ không hoạt động như mong đợi; xác minh bằng cách chạy query trực tiếp trong Prometheus trước khi deploy.

### 10.2. Tránh alert quá nhạy

- Dùng `for` duration để lọc spike ngắn hoặc scrape jitter.
- Dùng threshold theo baseline và SLO thay vì chọn tùy ý.
- Tách warning/critical theo thời gian và mức ảnh hưởng.
- Không alert lỗi trace chỉ vì số span giảm khi sampling policy được thay đổi có chủ đích.
- Xử lý no-data rõ ràng; phân biệt series vắng mặt với giá trị bằng 0.
- Dùng grouping để một sự cố collector không tạo hàng trăm notification theo từng span/module.

### 10.3. Gom nhóm và route bằng Alertmanager

Khi nhiều replica hoặc pipeline cùng lỗi, Alertmanager nên gom các alert cùng nguyên nhân thành một notification. Ví dụ cấu hình route khái niệm:

~~~yaml
route:
  receiver: platform-warning
  group_by: ["alertname", "cluster", "service"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: platform-oncall
    - matchers:
        - severity="warning"
      receiver: platform-warning
~~~

Các receiver cần được khai báo theo hệ thống notification của tổ chức; địa chỉ webhook, token và thông tin xác thực nên được quản lý bằng secret/config riêng. Không commit credential vào file rule hoặc dashboard.

Có thể thêm inhibition rule để critical alert che warning tương ứng khi cùng một pipeline đang down, tránh gửi hai thông báo cho cùng một sự cố. Hãy thử nghiệm route/grouping bằng alert mẫu trước khi bật notification production.

## 11. Runbook: điều tra khi telemetry không được export

Một alert tốt phải dẫn tới bước điều tra cụ thể. Dưới đây là thứ tự kiểm tra giúp xác định tầng bị lỗi mà không thay đổi nhiều cấu hình cùng lúc.

### Bước 1 — Xác nhận phạm vi và thời điểm

- Chỉ một service/module hay toàn bộ cluster?
- Chỉ traces, metrics, logs hay cả ba?
- Sự cố bắt đầu sau deploy, thay đổi sampling, rotate certificate hay thay đổi network?
- Có traffic nghiệp vụ trong khoảng thời gian đó không?
- Canary nào bị stale và lần thành công cuối là khi nào?

Nếu chỉ một module không có span, trước tiên xác minh module có traffic và đường gọi có đi qua Spring-managed boundary được instrument.

### Bước 2 — Kiểm tra nguồn ứng dụng

Với metrics:

~~~bash
curl -i http://shop-service:8080/actuator/health
curl -s http://shop-service:8080/actuator/prometheus
~~~

Với traces, kiểm tra log ứng dụng/exporter để tìm lỗi OTLP, timeout, DNS, TLS, authentication hoặc retry exhaustion. Xác minh sampling probability và bridge/exporter đã được cấu hình.

Với logs, xem stdout/stderr của container và log agent. Xác nhận ứng dụng thực sự phát record và agent còn đọc được nguồn.

### Bước 3 — Kiểm tra scrape và collector

- Prometheus target page cho biết scrape target nào down và lỗi HTTP/network cụ thể.
- Collector `/metrics` cho biết receiver accepted/refused, processor drops, exporter sent/failed và queue nếu được expose.
- Collector logs cho biết lỗi cấu hình, component không khởi tạo, authentication/TLS hoặc backend unavailable.
- Kiểm tra receiver/exporter có đúng pipeline và signal không; traces, metrics và logs có thể dùng receiver/exporter khác nhau.

### Bước 4 — Kiểm tra backend

- Backend có health/ingestion metrics hoặc API status không?
- Có write rejection, rate limit, storage full hoặc index failure không?
- Query có đúng service, environment, time range và datasource không?
- Canary verifier có query được record mới không?

Nếu collector exporter báo sent thành công nhưng backend query không thấy dữ liệu, kiểm tra tenant, namespace, retention, indexing delay và query filter.

### Bước 5 — Xác định có phải sampling có chủ đích

Với traces, kiểm tra head sampling và tail sampling policy. Trace không được sample có thể không xuất hiện dù exporter hoạt động bình thường. Nếu dùng tail sampling, bảo đảm span ứng viên tới đúng collector và các span của cùng trace được route nhất quán.

Với metrics, Prometheus scrape không phụ thuộc tracing sampling. Không giải thích việc thiếu HTTP metrics bằng sampling của traces.

### Bước 6 — Phục hồi và xác nhận

Sau khi khắc phục:

1. Kiểm tra collector receiver accepted tăng.
2. Xác nhận exporter sent tăng và send failures/queue giảm.
3. Chạy canary mới và chờ verifier tìm thấy record ở backend.
4. Kiểm tra dashboard và truy vấn trace/log theo service/environment.
5. Xác nhận alert tự resolve sau khoảng thời gian ổn định.
6. Ghi nhận nguyên nhân gốc, thời gian mất dữ liệu và các trace/log bị ảnh hưởng nếu biết.

Không chỉ restart collector rồi kết luận đã phục hồi. Cần xác nhận telemetry mới đã đi hết pipeline.

## 12. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Dashboard trống nhưng ứng dụng vẫn phục vụ request | Prometheus scrape, collector hoặc backend bị lỗi. | Kiểm tra từng chặng; dùng canary để xác nhận end-to-end. |
| `up=0` cho service | Sai target/port/path, auth/TLS hoặc app management endpoint không truy cập được. | Kiểm tra Prometheus target error và Actuator endpoint từ mạng scrape. |
| Collector target down | Collector dừng, endpoint metrics chưa bật hoặc port bị chặn. | Kiểm tra process/pod, telemetry metrics config và network policy. |
| Receiver refused tăng | Collector quá tải, request không hợp lệ hoặc giới hạn payload. | Đọc collector logs, kiểm tra memory/CPU và sender batch size. |
| Exporter send failures tăng | Backend down, DNS/TLS/auth lỗi, timeout hoặc rate limit. | Kiểm tra endpoint, certificate, credential và backend ingestion. |
| Queue tăng liên tục | Exporter không drain kịp hoặc backend/network chậm. | Kiểm tra downstream, tăng capacity có kiểm soát và điều chỉnh batch/queue. |
| Processor dropped spans tăng | Filter/tail-sampling policy hoặc processor quá tải. | Phân biệt intentional drop với overload; xem processor/pipeline labels. |
| Traces biến mất nhưng metrics vẫn có | Tracing bridge/exporter/collector trace pipeline hoặc sampling lỗi. | Kiểm tra OTLP exporter, sampling và tracing backend riêng. |
| Metrics biến mất nhưng traces vẫn có | Prometheus scrape/registry endpoint hoặc metrics pipeline lỗi. | Kiểm tra `/actuator/prometheus`, registry và Prometheus target. |
| Logs không có trong backend nhưng stdout còn | Log agent, parsing, buffer hoặc backend ingest lỗi. | Kiểm tra agent metrics/logs và backend freshness. |
| Không có span module sau deploy | Insight Starter/instrumentation thay đổi, module boundary không được đi qua hoặc sampling. | Kiểm tra dependency, module-entry observations, tracer handler và trace path. |
| Event publication tăng nhưng listener chưa hoàn tất | Publication counter không đo listener outcome. | Kiểm tra Event Publication Registry và outcome metric riêng. |
| Canary trace stale nhưng collector khỏe | Sampling loại canary, backend query sai hoặc trace chưa index. | Bảo đảm canary được sample, kiểm tra query/tenant và backend delay. |
| Alert queue đầy liên tục | Tải vượt capacity hoặc backend bị nghẽn kéo dài. | Scale đúng cách, kiểm tra persistent queue/storage và giới hạn ingest. |

## 13. Kiểm thử alert trước khi đưa vào production

Không nên chỉ viết PromQL rồi chờ sự cố thật mới biết alert có hoạt động.

### 13.1. Kiểm tra rule syntax

Với Prometheus:

~~~bash
promtool check rules telemetry-alerts.yml
~~~

Với Alertmanager:

~~~bash
amtool check-config alertmanager.yml
~~~

Các lệnh kiểm tra cú pháp/cấu trúc; chúng không chứng minh metric name có tồn tại hoặc query trả kết quả đúng. Chạy query trên Prometheus và xem trạng thái alert trong môi trường test.

### 13.2. Diễn tập lỗi có kiểm soát

Trong môi trường staging hoặc lab:

1. Tạm thời chặn collector scrape endpoint để kiểm tra alert target down.
2. Gửi OTLP tới một endpoint test không tồn tại để quan sát exporter retry/failure.
3. Tạo tải canary đủ nhỏ để kiểm tra receiver accepted và exporter sent.
4. Làm backend chậm có kiểm soát để xem queue tăng và alert warning.
5. Tạm dừng log agent để kiểm tra log canary stale.
6. Khôi phục pipeline và xác nhận alert resolve.

Không thực hiện fault injection trên production nếu chưa có kế hoạch, phạm vi và cơ chế rollback được phê duyệt.

### 13.3. Kiểm tra no-data và sampling

- Tạo khoảng thời gian không có traffic và xác nhận alert không coi đó là export failure.
- Thay đổi sampling trong staging và xác nhận trace count giảm theo chủ đích nhưng metrics vẫn tiếp tục.
- Bảo đảm canary trace được sample hoặc alert có tính đến sampling.
- Kiểm tra module không hoạt động theo lịch không tạo alert “missing span” sai.
- Kiểm tra datasource/query failure có alert riêng, không bị hiểu thành zero telemetry.

### 13.4. Kiểm tra notification

Gửi alert mẫu cho từng severity, xác nhận:

- Notification đến đúng nhóm trực.
- Nội dung có service, environment, signal, thời điểm và link dashboard/runbook.
- Alert cùng nguyên nhân được group đúng.
- Inhibition không che mất critical alert.
- Recovery/resolved notification hoạt động theo chính sách.

## 14. Checklist production

1. **Tách signal:** có health/alert riêng cho metrics, traces và logs.
2. **Giám sát source:** ứng dụng còn tạo observation, meter và log record.
3. **Giám sát scrape:** Prometheus target health và freshness được kiểm tra.
4. **Giám sát collector:** receiver accepted/refused, processor drop, exporter sent/failed và queue.
5. **Giám sát backend:** ingestion, rejection, storage, query và indexing delay.
6. **Có end-to-end canary:** xác nhận record mới truy vấn được ở backend.
7. **Hiểu sampling:** không coi intentional sampling là export failure; canary trace phải được sample chắc chắn.
8. **Theo dõi module:** module-entry spans và event metrics có schema/tag ổn định.
9. **Phân biệt event reliability:** Event Publication Registry không thay collector export health.
10. **Đặt severity và `for`:** theo SLO, thời gian chịu đựng và mức ảnh hưởng.
11. **Giảm alert noise:** grouping, inhibition, no-data handling và traffic floor.
12. **Bảo vệ endpoint:** Actuator, collector metrics, Grafana và backend chỉ mở cho đối tượng cần thiết.
13. **Kiểm thử:** validate rule, query thật, diễn tập exporter/collector/backend failure trong staging.
14. **Runbook:** mỗi alert có owner, bước kiểm tra, cách xác nhận phục hồi và escalation path.

## 15. Bài tập thực hành

### Bài 1 — Phát hiện Prometheus scrape failure

Cấu hình Prometheus scrape `/actuator/prometheus`. Tạo alert khi `up` bằng 0 trong hai phút. Trong môi trường test, đổi target port sai và quan sát trạng thái alert, sau đó khôi phục.

### Bài 2 — Theo dõi Collector exporter

Bật internal metrics cho OpenTelemetry Collector. Xác nhận metric sent/failed spans thực tế. Tạo truy vấn phát hiện send failure và queue utilization; ghi lại label/version cụ thể của môi trường.

### Bài 3 — Synthetic trace canary

Tạo span canary mỗi phút, bảo đảm span được sample và export. Viết verifier tìm trace mới ở backend, sau đó cập nhật `telemetry_canary_last_success_timestamp_seconds`. Tạm dừng collector trong staging và xác nhận alert stale.

### Bài 4 — Phân biệt ba signal

Tạo ba tình huống độc lập: Prometheus không scrape được metrics, OTLP trace exporter không gửi được và log agent dừng. Xác nhận chỉ alert tương ứng phát ra và runbook chỉ đúng tầng.

### Bài 5 — Event metrics và listener

Phát `OrderPlaced`, quan sát `module.events.published`, sau đó làm listener thất bại trong môi trường test. Đối chiếu counter publication với Event Publication Registry và outcome metric. Giải thích vì sao chúng không thể thay thế nhau.

### Bài 6 — Alert noise và no traffic

Tạo khoảng thời gian không có request nhưng scrape vẫn thành công. Kiểm tra rule missing HTTP metric không báo lỗi giả. Sau đó tắt canary pipeline để xác nhận alert freshness vẫn phát hiện mất telemetry.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể dùng một alert chung cho metrics, traces và logs?

**Đáp án:** Ba tín hiệu có nguồn, giao thức và pipeline export khác nhau. Một pipeline có thể lỗi trong khi hai pipeline còn lại hoạt động.

**Câu 2.** `up=0` có nghĩa ứng dụng đã dừng không?

**Đáp án:** Không nhất thiết. Prometheus không scrape được target; nguyên nhân có thể là mạng, endpoint, authentication, TLS hoặc ứng dụng.

**Câu 3.** Vì sao cần synthetic canary?

**Đáp án:** Internal metrics cho biết collector đang chạy, nhưng canary xác nhận một record thực sự đi từ nguồn tới backend và có thể truy vấn.

**Câu 4.** Không thấy trace có luôn là exporter failure không?

**Đáp án:** Không. Trace có thể bị sampling loại, instrumentation không tạo span, context bị mất hoặc backend query sai.

**Câu 5.** `module.events.published` có chứng minh listener xử lý thành công không?

**Đáp án:** Không. Counter phản ánh publication; cần trạng thái Event Publication Registry hoặc outcome metric để đánh giá listener.

**Câu 6.** Khi exporter queue tăng liên tục, nên kiểm tra gì?

**Đáp án:** Backend latency/availability, network, retry, exporter capacity và tốc độ ingest so với tốc độ nhận telemetry.

## 16. Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose và bảo vệ management endpoints.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics và Prometheus integration.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, bridge, sampling và exporter.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight Starter, module-entry spans và event metrics.
- [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/): cấu hình và quan sát metrics/logs nội bộ Collector.
- [OpenTelemetry Collector — Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): chẩn đoán receiver, processor, exporter và pipeline.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): định nghĩa alert rules, labels và annotations.
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): grouping, routing, inhibition và notification.
- [Grafana — Alerting](https://grafana.com/docs/grafana/latest/alerting/): quản lý alert rules, contact points và notification policies.

**Ghi nhớ:** muốn biết telemetry có được export hay không, hãy kiểm tra từng chặng của từng signal: ứng dụng tạo dữ liệu, exporter/scrape gửi đi, collector nhận và xử lý, backend ingest và truy vấn. Dùng internal metrics để khoanh vùng, synthetic canary để xác nhận end-to-end, và runbook để phân biệt lỗi pipeline với sampling hoặc no traffic. Module graph, event publication metrics và Event Publication Registry cung cấp ngữ cảnh Spring Modulith; chúng không thay thế health monitoring của telemetry pipeline.
