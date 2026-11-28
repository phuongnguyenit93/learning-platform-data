# Phân biệt lỗi ứng dụng và lỗi hệ thống quan sát

Khi dashboard không có dữ liệu, trace biến mất hoặc một cảnh báo bất thường xuất hiện, đội vận hành phải xác định **ứng dụng đang gặp sự cố hay chính hệ thống quan sát đang gặp sự cố**. Hai loại lỗi có thể tạo ra biểu hiện giống nhau nhưng nguyên nhân, mức độ ảnh hưởng và cách khắc phục khác nhau.

**Lỗi ứng dụng (application failure)** xảy ra khi chức năng hoặc luồng nghiệp vụ không đáp ứng yêu cầu: request trả lỗi, độ trễ vượt ngưỡng, database không truy cập được hoặc domain event bị listener xử lý thất bại. **Lỗi hệ thống quan sát (observability failure)** xảy ra khi metrics, logs hoặc traces không được thu thập, truyền, lưu trữ hay hiển thị đúng, trong khi ứng dụng có thể vẫn đang xử lý nghiệp vụ bình thường.

Hai nhóm lỗi cũng có thể xảy ra đồng thời. Ví dụ database bị quá tải khiến request lỗi, đồng thời OpenTelemetry Collector không gửi được trace vì exporter queue đã đầy. Vì vậy, một dashboard xanh hoặc trống không đủ để kết luận trạng thái dịch vụ.

Bài thuộc chương **Alerting** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mô-đun hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Ta sẽ kết hợp các tín hiệu này với Prometheus, Alertmanager và telemetry nội bộ của Collector để phân loại sự cố.

> Các ví dụ dùng Spring Boot 4.2, Spring Modulith 2.2, Micrometer, Prometheus và OpenTelemetry Collector. Tên metric sau khi scrape phụ thuộc registry, naming convention và phiên bản. Hãy xác nhận metric/label thực tế từ endpoint hoặc Prometheus trước khi đưa rule vào production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt application failure, observability failure và sự cố đồng thời.
2. Hiểu các tầng tạo, thu thập, vận chuyển, lưu trữ và truy vấn telemetry.
3. Dùng health, request metrics, event publication registry, logs và traces để đánh giá ứng dụng.
4. Theo dõi tình trạng Prometheus scrape, OpenTelemetry Collector và trace backend.
5. Thiết kế alert riêng cho lỗi nghiệp vụ và lỗi telemetry pipeline.
6. Viết Prometheus alerting rules với **for**, labels và annotations.
7. Dùng Alertmanager grouping, routing, inhibition và silences để quản lý thông báo.
8. Phân biệt giá trị metric bằng 0 với metric không có dữ liệu.
9. Thiết kế kiểm tra độc lập để phát hiện khi cả hệ thống quan sát bị mất.
10. Xây runbook giúp phân loại và xử lý sự cố mà không nhầm nguyên nhân.

## 2. Hai loại lỗi khác nhau

### 2.1. Application failure

Application failure là lỗi ở đường thực thi nghiệp vụ hoặc khả năng phục vụ của ứng dụng. Ví dụ:

- HTTP request trả 5xx tăng đột biến.
- p95/p99 latency vượt SLO.
- Database connection pool cạn hoặc query timeout.
- Một module gọi module khác thất bại.
- Listener nhận domain event nhưng ném exception.
- Event publication bị tồn đọng, thất bại hoặc bị bỏ hẳn theo policy.
- JVM hết memory, thread pool bão hòa hoặc ứng dụng không nhận traffic.

Trong trường hợp này, telemetry có thể vẫn hoạt động tốt: Prometheus scrape thành công, logs ghi đầy đủ stack trace, trace có span lỗi và dashboard hiển thị rõ nguyên nhân.

### 2.2. Observability failure

Observability failure là lỗi khiến đội vận hành không nhận được tín hiệu đáng tin cậy về ứng dụng. Ví dụ:

- Prometheus không scrape được **/actuator/prometheus**.
- Endpoint Actuator bị đổi port, base path hoặc access policy.
- OpenTelemetry Collector không nhận spans hoặc không export được tới backend.
- Exporter queue đầy, retry kéo dài hoặc Collector drop telemetry.
- Log agent ngừng đọc file hoặc gửi log.
- Backend tracing/logging/metrics không ingest dữ liệu.
- Dashboard truy vấn sai metric name, label hoặc time range.
- Clock lệch làm timestamp khó truy vấn.
- Sampling làm trace bị bỏ theo thiết kế, nhưng dashboard lại diễn giải nhầm là trace loss.

Ứng dụng có thể vẫn trả HTTP 200 và xử lý event bình thường trong khi observability pipeline bị hỏng.

### 2.3. Hai loại lỗi có thể xảy ra cùng lúc

~~~mermaid
flowchart TD
    A["Sự cố được phát hiện"] --> B{"Có bằng chứng nghiệp vụ lỗi?"}
    B -->|"Có"| C["Application failure"]
    B -->|"Chưa rõ"| D{"Có bằng chứng telemetry pipeline lỗi?"}
    D -->|"Có"| E["Observability failure"]
    D -->|"Không rõ"| F["Chưa đủ dữ liệu"]
    C --> G{"Telemetry pipeline có lỗi?"}
    G -->|"Có"| H["Cả hai loại lỗi"]
    G -->|"Không"| I["Ứng dụng lỗi, quan sát vẫn hoạt động"]
    E --> J["Kiểm tra ứng dụng bằng nguồn độc lập"]
    F --> K["Chạy synthetic probe / kiểm tra độc lập"]
~~~

Không có dữ liệu quan sát là một **dấu hiệu cần điều tra**, không phải bằng chứng rằng ứng dụng đang lỗi hoặc đang khỏe.

## 3. Kiến trúc quan sát và các điểm có thể hỏng

Một luồng quan sát điển hình:

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> B["Micrometer / Observation"]
    A --> C["Logging framework"]
    B --> D["Prometheus scrape"]
    B --> E["OTel SDK exporter"]
    C --> F["Log agent"]
    E --> G["OpenTelemetry Collector"]
    F --> H["Log backend"]
    G --> I["Trace backend"]
    D --> J["Prometheus TSDB"]
    J --> K["Grafana / Alert rules"]
    H --> L["Log search"]
    I --> M["Trace search"]
    K --> N["Alertmanager"]
    N --> O["On-call / incident channel"]
~~~

Mỗi đường có thể lỗi độc lập:

| Tầng | Lỗi điển hình | Tín hiệu kiểm tra |
| --- | --- | --- |
| Application | Request hoặc listener thất bại | HTTP status, business metrics, Event Publication Registry |
| Instrumentation | Không tạo meter/span hoặc thiếu tag | Actuator /metrics, log pattern, span attributes |
| Scrape/agent | Không đọc được endpoint hoặc file | Prometheus **up**, agent health, scrape errors |
| Collector | Receiver từ chối, processor drop, exporter lỗi | Collector internal metrics và logs |
| Storage/backend | Ingest lỗi, quota đầy, query chậm | Backend health, ingest errors, query API |
| Dashboard/alerting | Query sai, rule không evaluate, notification không route | Prometheus rule status, Grafana Explore, Alertmanager |
| On-call delivery | Receiver không gửi được notification | Alertmanager logs, receiver status và kênh nhận |

Đừng dùng một tín hiệu từ cùng pipeline để tự chứng minh toàn bộ pipeline đó đang khỏe. Ví dụ dashboard Grafana không thể là nguồn duy nhất xác nhận Grafana/Prometheus vẫn hoạt động.

## 4. Bảng phân loại nhanh

| Biểu hiện | Ứng dụng | Hệ thống quan sát | Nhận định ban đầu |
| --- | --- | --- | --- |
| HTTP 5xx tăng, Prometheus và traces vẫn có dữ liệu | Có dấu hiệu lỗi | Có vẻ hoạt động | Điều tra application |
| HTTP 200 bình thường, metric **up** của target Prometheus bằng 0 | Chưa có bằng chứng lỗi nghiệp vụ | Có lỗi scrape hoặc target không reachable | Điều tra endpoint, network và process |
| Synthetic probe từ bên ngoài thất bại, app metrics cũng ngừng cập nhật | Có thể lỗi | Có thể lỗi theo sau | Kiểm tra app và monitoring path độc lập |
| HTTP 200, request counter tăng, nhưng trace backend không có trace | Có vẻ hoạt động | Có thể lỗi tracing hoặc sampling | Kiểm tra sampled decision, exporter, Collector |
| Event publication tăng, listener publication bị FAILED | Có lỗi xử lý event | Có thể hoạt động | Điều tra listener và registry |
| Dashboard trống nhưng /actuator/metrics vẫn trả dữ liệu | Chưa rõ | Prometheus scrape/query/dashboard có vấn đề | Điều tra metrics pipeline |
| Log có lỗi nhưng không có trace tương ứng | Có lỗi được log | Có thể tracing bị sampling hoặc propagation/export lỗi | Dùng log và trace ID để phân tích riêng |
| Prometheus và Collector đều healthy nhưng không có request | Có thể hệ thống nhàn rỗi | Có thể hoạt động | Xác minh traffic expectation trước khi alert |

Đây là phân loại ban đầu. Cần xác minh từ ít nhất một nguồn độc lập trước khi chốt nguyên nhân.

## 5. Xác minh tình trạng ứng dụng bằng tín hiệu nghiệp vụ

### 5.1. HTTP status và request metrics

Spring Boot tự instrument request của Spring MVC và WebFlux bằng meter mặc định **http.server.requests**. Meter này có thể cung cấp số lượng request, thời gian xử lý và các tag như method, outcome, status, uri tùy convention.

Sau khi chuyển qua Prometheus naming convention, counter timer thường có dạng **http_server_requests_seconds_count**. Tuy nhiên, hãy kiểm tra **/actuator/prometheus** để xác nhận tên và label thực tế.

Ví dụ query tỷ lệ HTTP 5xx:

~~~promql
sum(rate(http_server_requests_seconds_count{job="shop-modulith", status=~"5.."}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{job="shop-modulith"}[5m])),
  1e-9
)
~~~

Nếu kết quả tăng, đó là bằng chứng về lỗi HTTP ở ứng dụng hoặc upstream path được đo. Nó chưa tự chỉ ra nguyên nhân là code, database, dependency hay gateway.

**Giới hạn:** một số exception đã được controller xử lý có thể không được ghi thành tag exception/status như người vận hành kỳ vọng. Business failure cũng có thể được trả về bằng HTTP 200 với response nghiệp vụ chứa trạng thái từ chối. Vì vậy, kết hợp request metrics với business metrics và logs.

### 5.2. Latency và saturation

Latency tăng có thể do:

- CPU throttling hoặc garbage collection kéo dài.
- Database/query chậm.
- HTTP dependency timeout.
- Thread pool hoặc connection pool bão hòa.
- Lock contention hoặc xử lý event backlog.

Một latency alert cần dùng histogram bucket đã được bật. Ví dụ nếu ứng dụng xuất **http_server_requests_seconds_bucket**:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="shop-modulith"}[5m])
  )
)
~~~

Không có histogram buckets thì query này không thể hoạt động. Đừng thay bằng một percentile gauge không thể aggregate giữa nhiều replica rồi gọi đó là p95 toàn service.

### 5.3. Health, liveness và readiness

Actuator **health** trả trạng thái của ứng dụng và các health contributors được cấu hình. Với Kubernetes, Spring Boot hỗ trợ health groups:

- **/actuator/health/liveness**: ứng dụng có còn ở trạng thái sống theo availability state hay không.
- **/actuator/health/readiness**: ứng dụng đã sẵn sàng nhận traffic hay chưa.

Hai probe có mục đích khác nhau. **Liveness không nên phụ thuộc vào database hoặc service bên ngoài**; nếu dependency ngoài bị lỗi và liveness cũng chuyển DOWN, Kubernetes có thể restart hàng loạt instance, tạo cascading failure. Readiness có thể kiểm tra dependency nếu quyết định đó phù hợp với cách hệ thống phục vụ traffic.

Nếu Actuator chạy trên management port riêng, health probe có thể thành công dù HTTP server chính không nhận request được. Spring Boot cho phép thêm đường dẫn probe lên main server port bằng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        add-additional-paths: true
~~~

Sau cấu hình này, các path mặc định **/livez** và **/readyz** có thể được phục vụ trên main port. Điều này giúp probe kiểm tra gần hơn với đường vào thực tế của ứng dụng.

### 5.4. Spring Modulith Event Publication Registry

Publication counter trả lời event đã được publish bao nhiêu lần; nó không trả lời listener đã xử lý thành công hay chưa.

Spring Modulith Event Publication Registry theo dõi trạng thái publication tới transactional listener. Các trạng thái gồm:

| Trạng thái | Ý nghĩa |
| --- | --- |
| PUBLISHED | Publication được lưu và đang chờ xử lý hoặc chờ được lấy ra |
| PROCESSING | Listener đã nhận publication và đang thực thi |
| COMPLETED | Listener kết thúc thành công |
| FAILED | Listener ném exception hoặc publication bị đánh dấu thất bại |
| RESUBMITTED | Publication lỗi đã được gửi xử lý lại |
| ABANDONED | Policy quyết định ngừng retry publication đã thất bại |

Một publication bị treo ở PROCESSING hoặc PUBLISHED có thể liên quan tới crash, listener bị kẹt hoặc worker không chạy. Cần kiểm tra tuổi publication và completion attempts, không chỉ đếm event publish.

API EventPublicationRegistry cung cấp các thao tác tìm publication chưa hoàn tất, ví dụ **findIncompletePublications()** và **findIncompletePublicationsOlderThan(Duration)**. Có thể xây một health indicator hoặc gauge riêng dựa trên các truy vấn này; đó là instrumentation bổ sung của ứng dụng, không giả định có sẵn một Prometheus metric cho mọi trạng thái registry.

## 6. Xác minh hệ thống quan sát

### 6.1. Kiểm tra Prometheus scrape

Prometheus tạo metric **up** cho mỗi scrape target:

- **up = 1**: scrape thành công ở lần đánh giá gần nhất.
- **up = 0**: scrape thất bại hoặc target không thể được scrape.

Ví dụ:

~~~promql
up{job="shop-modulith"}
~~~

**up = 0 không tự chứng minh process Spring Boot đã chết.** Nguyên nhân có thể là:

- Process không chạy hoặc port không lắng nghe.
- Network/firewall/DNS lỗi.
- Actuator port hoặc base path thay đổi.
- Endpoint không còn được expose.
- Security yêu cầu authentication mà Prometheus chưa cung cấp.
- TLS certificate hoặc scrape timeout lỗi.

Dùng thêm blackbox probe từ bên ngoài để kiểm tra URL mà client thật truy cập. Nếu scrape target down nhưng business URL vẫn trả thành công, nhiều khả năng vấn đề nằm ở management endpoint hoặc monitoring path.

### 6.2. Kiểm tra OpenTelemetry Collector

Collector có internal telemetry để tự quan sát. Tài liệu OpenTelemetry mô tả metrics cho:

- Receiver accepted/refused telemetry.
- Processor input/output.
- Exporter sent/failed telemetry.
- Exporter queue size và capacity.
- Request count, duration và size.
- Process uptime, CPU và memory.

Mặc định Collector thường expose internal Prometheus metrics ở port **8888** tại **/metrics**; xác nhận địa chỉ và config theo phiên bản đang chạy.

Các metric thường gặp có dạng:

~~~text
otelcol_receiver_accepted_spans
otelcol_receiver_refused_spans
otelcol_exporter_sent_spans
otelcol_exporter_send_failed_spans
otelcol_exporter_queue_size
otelcol_exporter_queue_capacity
~~~

Tên và suffix thực tế có thể thay đổi theo Collector version/registry. Dùng **/metrics** của Collector làm nguồn chuẩn.

Ví dụ kiểm tra export failure:

~~~promql
rate(otelcol_exporter_send_failed_spans[5m]) > 0
~~~

Ví dụ theo dõi queue utilization:

~~~promql
otelcol_exporter_queue_size
/
clamp_min(otelcol_exporter_queue_capacity, 1)
~~~

Queue tăng liên tục kèm send failures là dấu hiệu exporter không theo kịp dữ liệu hoặc backend/network gặp vấn đề. Một lần send failure chưa chắc đồng nghĩa mất dữ liệu vì exporter có thể retry; hãy xem queue, retry, failure duration và Collector logs.

### 6.3. Không so sánh accepted và sent một cách máy móc

Số spans receiver accepted và exporter sent không nhất thiết bằng nhau trong cùng một cửa sổ vì pipeline có thể:

- Sampling hoặc filtering.
- Routing tới nhiều exporter.
- Batching và queue làm chậm egress.
- Processor drop hoặc transform dữ liệu.
- Replication tạo nhiều bản gửi.
- Chỉ gửi một số signal type.
- Có dữ liệu đang nằm trong queue.

Để xác minh data loss, so sánh cùng signal type, cùng trace/path, cùng cửa sổ thời gian và hiểu rõ processors. Chênh lệch count tự nó không chứng minh dữ liệu bị mất.

### 6.4. Kiểm tra backend và dashboard

Ngay cả khi Collector export thành công, backend có thể:

- Từ chối ingest do quota.
- Chậm index hoặc compact.
- Không lưu dữ liệu do retention/configuration.
- Query timeout hoặc giới hạn scan.
- Có dữ liệu nhưng dashboard lọc sai service, environment, time range hoặc labels.

Hãy kiểm tra từng tầng:

1. Dữ liệu có xuất hiện ở source endpoint không?
2. Collector/agent có nhận được không?
3. Exporter có gửi thành công không?
4. Backend có xác nhận ingest không?
5. Query trực tiếp backend có tìm thấy không?
6. Dashboard có dùng đúng query và time range không?

## 7. Alert riêng cho application failure

Alert nên phản ánh tác động tới người dùng hoặc nghiệp vụ. Tránh tạo alert cho mọi exception kỹ thuật nếu chưa có ngưỡng hoặc hành động xử lý rõ.

### 7.1. Application target không scrape được

~~~yaml
groups:
  - name: application-availability
    rules:
      - alert: ApplicationScrapeUnavailable
        expr: up{job="shop-modulith"} == 0
        for: 2m
        labels:
          severity: critical
          category: target-availability
        annotations:
          summary: "Không scrape được shop-modulith"
          description: "Prometheus không lấy được metrics từ {{ $labels.instance }} trong ít nhất 2 phút."
          runbook: "Kiểm tra process, management port, endpoint exposure, auth và network."
~~~

Alert này phát hiện target scrape không khả dụng. Nó **chưa phân biệt** process down với management path/network lỗi. Để phân loại, đối chiếu blackbox probe và application logs.

### 7.2. Tỷ lệ HTTP 5xx cao

~~~yaml
      - alert: ApplicationHigh5xxRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{job="shop-modulith",status=~"5.."}[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count{job="shop-modulith"}[5m])), 1e-9)
          ) > 0.05
        for: 10m
        labels:
          severity: page
          category: application
        annotations:
          summary: "Tỷ lệ HTTP 5xx vượt 5%"
          description: "Tỷ lệ request lỗi 5xx duy trì trên 5% trong 10 phút."
          runbook: "Đối chiếu logs, dependency spans, database và thay đổi triển khai gần đây."
~~~

Ngưỡng 5% và thời gian 10 phút chỉ là ví dụ. Chọn ngưỡng theo SLO và baseline thực tế. Xác nhận metric name/label status trong Prometheus; nếu meter của ứng dụng dùng naming convention khác, điều chỉnh query.

### 7.3. p95 latency vượt SLO

~~~yaml
      - alert: ApplicationHighP95Latency
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(http_server_requests_seconds_bucket{job="shop-modulith"}[5m])
            )
          ) > 1
        for: 10m
        labels:
          severity: warning
          category: application
        annotations:
          summary: "p95 HTTP latency vượt 1 giây"
          description: "p95 latency duy trì trên 1 giây trong 10 phút."
          runbook: "Kiểm tra JVM, thread pools, database và downstream spans."
~~~

Ví dụ này yêu cầu histogram buckets được xuất. Ngưỡng một giây cần được thay bằng SLO thực tế của API.

### 7.4. Publication lỗi trong Spring Modulith

Không nên giả định **module.events.published** đo listener completion. Nếu cần alert theo publication status, có thể:

- Truy vấn Event Publication Registry theo chu kỳ.
- Export gauge/counter riêng cho số publication FAILED, PROCESSING quá lâu hoặc ABANDONED.
- Đặt labels hữu hạn như module và listener type.
- Alert khi số lượng hoặc tuổi publication vượt ngưỡng nghiệp vụ.

Tên metric ví dụ do ứng dụng tự đăng ký:

~~~text
spring_modulith_event_publications_incomplete{module="inventory"} 12
spring_modulith_event_publications_failed{module="inventory"} 3
~~~

Đây là **custom metrics minh họa**, không phải tên metric mặc định của Spring Modulith. Nếu registry lưu publication theo listener, metric cần định nghĩa rõ đang đếm publication hay listener-target pairs để không đếm sai.

## 8. Alert riêng cho observability failure

### 8.1. Collector target không khả dụng

~~~yaml
groups:
  - name: observability-pipeline
    rules:
      - alert: OpenTelemetryCollectorUnavailable
        expr: up{job="otel-collector"} == 0
        for: 2m
        labels:
          severity: critical
          category: observability
        annotations:
          summary: "Không scrape được OpenTelemetry Collector"
          description: "Collector target {{ $labels.instance }} không phản hồi scrape."
          runbook: "Kiểm tra Collector process, internal telemetry endpoint, network và deployment."
~~~

Collector target down không chứng minh ứng dụng down. Nó có thể khiến trace pipeline mất dữ liệu hoặc queue ở SDK tăng lên; kiểm tra logs và các đường metrics độc lập.

### 8.2. Exporter liên tục gửi spans thất bại

~~~yaml
      - alert: OpenTelemetrySpanExportFailures
        expr: rate(otelcol_exporter_send_failed_spans[5m]) > 0
        for: 5m
        labels:
          severity: warning
          category: observability
        annotations:
          summary: "Collector gặp lỗi gửi spans"
          description: "Exporter có send failures kéo dài; kiểm tra queue, retry và backend."
          runbook: "Kiểm tra backend endpoint, TLS, authentication, quota và Collector logs."
~~~

Metric name ở đây là ví dụ theo internal telemetry của Collector. Xác nhận đúng tên và semantics trong phiên bản đang chạy.

### 8.3. Exporter queue gần đầy

~~~yaml
      - alert: OpenTelemetryExporterQueueNearCapacity
        expr: |
          (
            otelcol_exporter_queue_size
            /
            clamp_min(otelcol_exporter_queue_capacity, 1)
          ) > 0.8
        for: 10m
        labels:
          severity: warning
          category: observability
        annotations:
          summary: "Exporter queue gần đầy"
          description: "Queue sử dụng trên 80% capacity trong 10 phút."
          runbook: "Kiểm tra send failures, backend throughput, queue configuration và Collector resources."
~~~

Ngưỡng 80% là ví dụ. Cần xác minh metric queue là gauge, labels có tương thích giữa size/capacity và backend exporter có đang retry hay không.

### 8.4. Dữ liệu telemetry không còn đến

Có thể dùng **absent_over_time()** cho một series được kỳ vọng liên tục:

~~~promql
absent_over_time(up{job="shop-modulith"}[10m])
~~~

Tuy nhiên, up không tồn tại có thể do target bị xóa khỏi service discovery hoặc label selector sai. Với ứng dụng ít traffic, không nên dùng sự vắng mặt của request counter để kết luận lỗi. Hãy alert dựa trên **tín hiệu được kỳ vọng liên tục**, ví dụ scrape target, synthetic probe hoặc heartbeat metric do ứng dụng phát định kỳ.

Không nhầm:
- Metric có giá trị **0**: series tồn tại và giá trị bằng 0.
- Metric không có series: chưa có dữ liệu, series stale hoặc selector không khớp.
- Scrape **up = 0**: target được biết tới nhưng lần scrape thất bại.
- Không có up series: target có thể chưa được discovery hoặc đã bị loại.

## 9. Alerting rules và Alertmanager

Prometheus alerting rules đánh giá PromQL expression. Khi expression trả về một hoặc nhiều series, alert tương ứng chuyển sang trạng thái active. Clause **for** yêu cầu điều kiện tồn tại liên tục trong một khoảng trước khi alert chuyển sang firing; **keep_firing_for** có thể giữ alert firing thêm một thời gian sau khi điều kiện hết để tránh flapping.

Ví dụ file rule:

~~~yaml
groups:
  - name: application
    interval: 30s
    rules:
      - alert: ApplicationHigh5xxRate
        expr: |
          sum(rate(http_server_requests_seconds_count{job="shop-modulith",status=~"5.."}[5m]))
          /
          clamp_min(sum(rate(http_server_requests_seconds_count{job="shop-modulith"}[5m])), 1e-9)
          > 0.05
        for: 10m
        keep_firing_for: 5m
        labels:
          severity: page
          team: shop
        annotations:
          summary: "HTTP 5xx rate cao"
          description: "Tỷ lệ 5xx là {{ $value }}."
          runbook_url: "https://runbooks.example/application-5xx"
~~~

Trong ví dụ:

- **expr** xác định điều kiện.
- **for** lọc các spike ngắn.
- **keep_firing_for** giảm việc alert tắt/bật liên tục khi metric dao động quanh ngưỡng.
- **labels** dùng để phân loại, route và group.
- **annotations** cung cấp nội dung con người đọc được và liên kết runbook.

### 9.1. Alertmanager grouping

Alertmanager nhận alerts từ Prometheus rồi deduplicate, group và route tới receiver như email, PagerDuty hoặc hệ thống thông báo khác.

Ví dụ cấu hình ý tưởng:

~~~yaml
route:
  receiver: default-ops
  group_by: [alertname, cluster, service]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - category="observability"
      receiver: observability-ops
    - matchers:
        - severity="page"
      receiver: on-call

receivers:
  - name: default-ops
  - name: observability-ops
  - name: on-call
~~~

Receiver trên là tên logic minh họa; cấu hình thật cần khai báo integration tương ứng với hệ thống nhận thông báo.

### 9.2. Inhibition và silences

Khi cả cluster hoặc network lớn bị mất kết nối, hàng trăm alert instance có thể cùng firing. Alertmanager inhibition cho phép suppress alert thứ cấp khi alert nguyên nhân gốc đang firing. Ví dụ, khi **ClusterUnreachable** firing, có thể tạm suppress các alert **ApplicationScrapeUnavailable** cùng cluster để tránh spam.

Silence dùng để tạm ngừng notification theo matcher trong khoảng thời gian xác định, chẳng hạn bảo trì có kế hoạch. Silence không sửa trạng thái ứng dụng và không thay thế việc điều tra; ghi rõ người tạo, lý do và thời hạn.

## 10. Thiết kế quan sát độc lập

Nếu cả ứng dụng và pipeline quan sát dùng chung một dependency, sự cố dependency đó có thể làm mất cả dữ liệu lẫn khả năng phát hiện. Nên có ít nhất một số kiểm tra độc lập:

### 10.1. Synthetic probe từ bên ngoài

Một blackbox probe chạy ngoài cluster gọi endpoint thực tế, ví dụ:

- **GET /health** hoặc endpoint readiness đã được bảo vệ phù hợp.
- Một API read-only kiểm tra luồng người dùng.
- Một transaction synthetic nhẹ, có correlation ID riêng.

Probe nên kiểm tra DNS, TLS, routing, authentication và response time từ góc nhìn client. Health endpoint nội bộ một mình không chứng minh public route hoặc gateway đang hoạt động.

### 10.2. Monitoring cho monitoring

Theo dõi:

- Prometheus target health và rule evaluation.
- Alertmanager process/cluster và receiver errors.
- Collector internal metrics, queue và exporter failures.
- Log agent health và backlog.
- Backend ingest/query availability.
- Grafana datasource/query failures.

Các tín hiệu sức khỏe này nên được thu thập qua một đường độc lập hoặc ít nhất có cơ chế kiểm tra ngoài chính pipeline đang được kiểm tra.

### 10.3. Heartbeat có chủ đích

Nếu cần phát hiện telemetry ngừng đến trong thời gian không có traffic, có thể tạo heartbeat metric định kỳ hoặc synthetic event. Alert dựa trên heartbeat chỉ có ý nghĩa khi lịch phát đã được xác định và có nguồn kiểm tra độc lập.

Ví dụ PromQL khái niệm:

~~~promql
time() - max(application_heartbeat_timestamp_seconds{job="shop-modulith"}) > 180
~~~

Metric timestamp là custom gauge do ứng dụng hoặc agent phát. Đây không phải metric mặc định của Spring Boot. Nếu ứng dụng bị pause hoặc không chạy scheduler, heartbeat cũng dừng; cần phân tích cùng **up** và blackbox probe.

### 10.4. Kiểm tra log và trace bằng correlation ID

Khi request metrics cho thấy 5xx tăng:

1. Lấy traceId từ log nếu có.
2. Tìm trace tương ứng trong backend.
3. Đọc span lỗi và module.identifier, module.method, module.invocation-type.
4. Nếu không có trace, kiểm tra sampled decision, parent context, exporter và Collector.
5. Dùng logs và business metrics để tiếp tục điều tra ngay cả khi trace backend không có dữ liệu.

Không dùng việc “không tìm thấy trace” làm bằng chứng duy nhất rằng request không xảy ra.

## 11. Ma trận chẩn đoán theo tình huống

| Tình huống | Dữ liệu kiểm tra | Hướng phân loại |
| --- | --- | --- |
| Blackbox thất bại, up=0, logs app có startup/crash errors | External probe, scrape status, process logs | Application failure có thể kéo theo observability failure |
| Blackbox thành công, request metrics có dữ liệu, trace backend trống | Probe, Prometheus, Collector internal metrics | Tracing pipeline/sampling/propagation |
| Blackbox thành công, /actuator/metrics có data, Prometheus up=0 | Actuator local, target config, auth/network | Prometheus scrape failure |
| Prometheus target UP, Grafana panel No data | Prometheus query trực tiếp, labels, time range | Dashboard/query failure |
| Collector nhận spans, exporter failed và queue tăng | Collector accepted/refused/sent/failed/queue | Observability export failure |
| Request 200, event publication counter tăng, registry có FAILED | Business response, event registry, listener logs | Application/domain processing failure |
| Request 5xx, trace có span ERROR, Collector queue bình thường | Request metrics, trace, logs | Application failure, observability hoạt động |
| Request 5xx, trace mất, Collector exporter failures tăng | Application logs, request metrics, Collector metrics | Cả hai loại lỗi |
| Không có request metrics nhưng service có thể đang idle | Blackbox, up, traffic expectation | Chưa đủ dữ liệu để báo application failure |
| Event publication counter đứng yên, request traffic cũng bằng 0 | Request metrics, synthetic traffic | Có thể là trạng thái idle bình thường |

## 12. Runbook phân loại sự cố

Khi nhận alert hoặc người dùng báo lỗi, thực hiện theo trình tự:

### Bước 1 — Xác nhận tác động tới người dùng

- Gọi synthetic probe từ vị trí độc lập.
- Kiểm tra API nghiệp vụ quan trọng.
- Xem status code và latency.
- Xác định sự cố ảnh hưởng toàn service, một route hay một nhóm user.

Nếu probe thất bại, ưu tiên kiểm tra application path, gateway, DNS, TLS và dependency.

### Bước 2 — Xác nhận Prometheus scrape

- Xem **up{job="shop-modulith"}**.
- Kiểm tra target URL, port, path và authentication.
- Gọi **/actuator/prometheus** trực tiếp từ network của Prometheus.
- Kiểm tra target labels và service discovery.

Nếu app URL thành công nhưng scrape thất bại, xử lý management endpoint hoặc scrape configuration.

### Bước 3 — Xác nhận ứng dụng có thực sự phát tín hiệu

- Gọi **/actuator/metrics** để kiểm tra meter.
- Kiểm tra request counter, JVM, executor và database metrics.
- Kiểm tra domain event publication counter.
- Kiểm tra Event Publication Registry nếu cần listener status.

Nếu source có dữ liệu nhưng backend không có, điều tra từ scrape/collector trở đi.

### Bước 4 — Kiểm tra telemetry pipeline

- Collector receiver accepted/refused counts.
- Processor pipeline và filtering/sampling.
- Exporter sent/failed counters.
- Queue size/capacity, retry và Collector logs.
- Backend ingest errors và query visibility.

Nếu Collector nhận dữ liệu nhưng export thất bại, xử lý network, TLS, auth, quota hoặc backend availability.

### Bước 5 — Kết luận phạm vi và cập nhật incident

Phân loại một trong bốn trạng thái:

1. Application failure.
2. Observability failure.
3. Cả hai cùng xảy ra.
4. Chưa đủ dữ liệu.

Ghi lại bằng chứng, thời điểm bắt đầu, ảnh hưởng, nguyên nhân đã xác nhận và đường telemetry nào vẫn còn sử dụng được.

## 13. Những lỗi suy luận thường gặp

| Suy luận sai | Vì sao sai | Cách suy luận đúng |
| --- | --- | --- |
| “Dashboard trống nghĩa ứng dụng đã chết.” | Dashboard/query/backend có thể lỗi hoặc traffic đang idle | Kiểm tra blackbox, scrape và source metrics |
| “Prometheus up=0 nghĩa process chắc chắn down.” | Network, auth, path và TLS cũng làm scrape thất bại | Kiểm tra endpoint từ đúng network và process logs |
| “Không có trace nghĩa request không chạy.” | Sampling, propagation hoặc exporter có thể loại trace | Đối chiếu request metrics và logs |
| “Collector process chạy nghĩa trace đã được lưu.” | Exporter có thể queue hoặc send failures | Kiểm tra internal telemetry và backend query |
| “Exporter send thành công nghĩa backend query được ngay.” | Ingest/index/query có thể trễ hoặc lỗi | Xác minh ở backend |
| “Event publication counter tăng nghĩa listener thành công.” | Counter đếm publication | Kiểm tra Event Publication Registry |
| “Event metric không tăng nghĩa event publisher hỏng.” | Có thể không có traffic hoặc meter chưa được tạo | Đối chiếu request/business metrics |
| “Liveness DOWN thì restart mọi instance.” | External dependency failure có thể gây restart storm nếu liveness phụ thuộc dependency | Giữ liveness tập trung vào process; dùng readiness cho traffic |
| “Tăng sampling sẽ khôi phục trace đã bị drop.” | SDK/Collector không thể khôi phục dữ liệu chưa được gửi | Điều chỉnh policy cho lần chạy tiếp theo |
| “Accepted spans ít hơn sent spans chắc chắn mất dữ liệu.” | Routing, replication, batching, filtering và sampling thay đổi count | So sánh đúng pipeline và signal type |
| “Alert firing đồng nghĩa phải page ngay.” | Alert có thể warning, pending hoặc bị group/inhibit | Xác định severity, action và receiver |

## 14. Thực hành xây dựng bộ alert hai nhóm

### 14.1. Chuẩn bị metric và labels

Xác nhận ứng dụng xuất:

- HTTP request count/duration.
- JVM memory, GC và process metrics.
- Event publication counter.
- Custom listener outcome metrics nếu cần.
- Collector internal metrics.
- Prometheus up và synthetic probe result.

Không tạo rule dựa trên metric name chưa được kiểm tra. Nếu cần một metric chưa có, hãy instrument có chủ đích và định nghĩa owner.

### 14.2. Viết application alert

Tạo rule cho 5xx rate và latency, dùng **for** để loại spike ngắn. Với event listener, bổ sung metric hoặc health indicator dựa trên publication registry.

### 14.3. Viết observability alert

Tạo rule cho:

- Prometheus scrape target unavailable.
- OpenTelemetry Collector unavailable.
- Exporter send failures kéo dài.
- Exporter queue gần đầy.
- Backend ingest hoặc query failures.
- Heartbeat/synthetic probe mất dữ liệu.

### 14.4. Kiểm thử alert

Trong môi trường staging:

1. Tạo endpoint test trả 500 có kiểm soát.
2. Xác nhận ApplicationHigh5xxRate chuyển pending rồi firing.
3. Tạm làm sai scrape path để kiểm tra ApplicationScrapeUnavailable.
4. Chặn Collector tới backend trong thời gian ngắn để kiểm tra send failures/queue.
5. Khôi phục cấu hình và xác nhận alert resolved.
6. Kiểm tra Alertmanager group, route, silence và receiver.

Không thử làm hỏng production pipeline chỉ để kiểm tra rule.

## 15. Bài thực hành

### Bài 1 — Phân loại bốn tình huống

Phân loại các trường hợp:

- API trả 500, Prometheus và trace vẫn hoạt động.
- API trả 200, Collector không export được trace.
- API trả 500, Collector cũng không gửi được spans.
- Dashboard không có dữ liệu nhưng synthetic probe và API vẫn thành công.

Giải thích bằng ít nhất hai bằng chứng cho mỗi kết luận.

### Bài 2 — Kiểm tra health groups

Cấu hình **/actuator/health/liveness** và **/actuator/health/readiness**. Làm database unavailable trong môi trường lab và quan sát probe nào thay đổi. Giải thích vì sao không nên đưa mọi external dependency vào liveness.

### Bài 3 — Tạo alert HTTP 5xx

Dùng **http_server_requests_seconds_count** hoặc metric tương ứng trong ứng dụng. Viết PromQL tính tỷ lệ 5xx; đặt **for: 5m** và annotations có runbook.

### Bài 4 — Tạo alert Collector

Scrape internal telemetry của Collector. Theo dõi exporter send failures và queue utilization. Tạo tình huống backend không nhận telemetry rồi quan sát alert.

### Bài 5 — Phân biệt publication và listener failure

Publish một domain event với listener thành công, sau đó thử listener thất bại. So sánh publication counter với Event Publication Registry statuses. Giải thích vì sao cần hai tín hiệu.

### Bài 6 — Kiểm tra tình huống mất dashboard

Tạm đổi query label trong Grafana để panel trả No data, trong khi Prometheus có series. Dùng Explore và query trực tiếp để xác định lỗi nằm ở dashboard.

### Bài 7 — Thiết kế Alertmanager routing

Tạo route riêng cho category=application và category=observability. Group theo service/cluster; thiết lập inhibition để một cluster outage không tạo hàng trăm notification thứ cấp.

## 16. Câu hỏi ôn tập

1. Application failure và observability failure khác nhau ở đâu?
2. Vì sao thiếu telemetry không chứng minh ứng dụng đang chết?
3. Prometheus up=0 chưa đủ để kết luận process down vì sao?
4. http.server.requests của Spring Boot giúp phát hiện những dạng lỗi nào?
5. Vì sao business failure có thể không được phản ánh bằng HTTP 5xx?
6. Liveness và readiness khác nhau thế nào?
7. Vì sao liveness không nên phụ thuộc database?
8. Spring Modulith Event Publication Registry cung cấp các trạng thái nào?
9. module.events.published có đo listener completion không?
10. Collector internal telemetry giúp chẩn đoán những vấn đề nào?
11. Vì sao không so sánh accepted spans và sent spans như hai con số luôn phải bằng nhau?
12. Prometheus for và keep_firing_for giải quyết vấn đề gì?
13. Alertmanager grouping, inhibition và silence khác nhau thế nào?
14. Vì sao cần synthetic probe độc lập với monitoring pipeline?
15. Khi Grafana không có data, nên kiểm tra những tầng nào?

## 17. Ghi nhớ

**Application failure là lỗi trong khả năng phục vụ hoặc xử lý nghiệp vụ; observability failure là lỗi trong khả năng thu thập và trình bày tín hiệu về hệ thống.** Chúng có thể xảy ra độc lập hoặc đồng thời. Hãy dùng request metrics, health, business metrics và Event Publication Registry để xác minh nghiệp vụ; dùng Prometheus up, Collector internal telemetry, exporter queue và backend checks để xác minh pipeline quan sát.

Trong Spring Modulith, publication count chỉ cho biết event đã được công bố; registry mới giúp kiểm tra listener đang chờ, xử lý, hoàn tất hay thất bại. Trong tracing, không thấy trace có thể do sampling hoặc export failure, không phải bằng chứng request không chạy.

Thiết kế alert theo hai nhóm, đặt ngưỡng và thời gian duy trì theo SLO, cung cấp runbook và dùng Alertmanager để group/inhibit thông báo. Giữ một đường kiểm tra độc lập như synthetic probe để vẫn phát hiện được sự cố khi chính hệ thống quan sát gặp lỗi.

### Tài liệu tham khảo chính thức

- [Spring Boot — Actuator Health, Liveness và Readiness Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Metrics và HTTP Server Request Instrumentation](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Modulith 2.2 — Production-ready Features và Observability Metrics](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html).
- [Spring Modulith — Working with Application Events: Event Publication Registry và lifecycle](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith — EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html).
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
- [Prometheus — Alertmanager Concepts](https://prometheus.io/docs/alerting/latest/alertmanager/).
- [OpenTelemetry Collector — Internal Telemetry and Monitoring](https://opentelemetry.io/docs/collector/internal-telemetry/).
- [OpenTelemetry Collector — Configuration and Health Check Extension](https://opentelemetry.io/docs/collector/configuration/).
