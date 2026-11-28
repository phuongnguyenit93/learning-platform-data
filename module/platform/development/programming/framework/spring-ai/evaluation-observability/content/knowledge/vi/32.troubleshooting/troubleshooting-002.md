# Metric có trong Actuator nhưng không tới hệ thu thập

> **Chương:** Chẩn đoán sự cố  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt meter có trong process, dữ liệu được Actuator hiển thị, dữ liệu được scrape và dữ liệu đến backend trung tâm.
2. Phân biệt endpoint JSON /actuator/metrics với Prometheus exposition endpoint /actuator/prometheus.
3. Chẩn đoán sai port, path, context path, security, network, service discovery và scrape configuration.
4. Tìm metric bị loại bởi relabeling, metric relabeling, sample limits hoặc bộ lọc của collector.
5. Phân biệt lỗi scrape với lỗi remote_write hoặc lỗi export từ OpenTelemetry Collector.
6. Dùng curl, Prometheus targets, PromQL, promtool và integration tests để xác định chính xác tầng làm mất metric.
7. Thiết kế đường thu thập an toàn, có thể quan sát và có kiểm thử hồi quy cho metrics Spring AI VectorStore.

## 1. Triệu chứng và phạm vi sự cố

Ứng dụng Spring AI đã có meter trong Actuator. Ví dụ, gọi /actuator/metrics cho thấy meter liên quan đến VectorStore, nhưng dashboard của Prometheus hoặc hệ thống giám sát trung tâm không có dữ liệu.

Trường hợp này cho biết ít nhất một phần instrumentation trong process đã hoạt động. Phần cần điều tra nằm ở bước công bố endpoint, scrape, xử lý dữ liệu hoặc chuyển tiếp dữ liệu.

Các nguyên nhân thường gặp:

- Prometheus scrape nhầm port, host, path hoặc scheme.
- Actuator chạy ở management port riêng, nhưng target vẫn trỏ vào application port.
- /actuator/metrics được expose, còn /actuator/prometheus chưa được expose hoặc chưa có Prometheus registry.
- Spring Security, reverse proxy, ingress hoặc network policy trả 401, 403, 404 hay connection refused.
- Prometheus target không được service discovery chọn do sai namespace, labels, selector hoặc annotations.
- relabel_configs loại target hoặc sửa địa chỉ/path sai.
- metric_relabel_configs loại đúng metric cần tìm.
- sample limit, label limit, body size limit hoặc scrape timeout khiến scrape thất bại.
- Prometheus đã scrape nhưng remote_write không chuyển được dữ liệu lên backend.
- OpenTelemetry Collector nhận scrape nhưng filter processor hoặc exporter làm rơi dữ liệu.
- Dashboard truy vấn sai tên metric, label, datasource hoặc time range.

**Cần lần theo dữ liệu từ endpoint đến backend theo từng chặng.** Đừng thay đổi registry trong ứng dụng khi endpoint đã chứng minh meter tồn tại; trước hết xác định chặng nào không nhận được dữ liệu.

### 1.1. Đường đi của metric

~~~mermaid
flowchart TD
  A["Spring AI VectorStore Observation"] --> B["Observation / MeterRegistry"]
  B --> C["Actuator MeterRegistry"]
  C --> D["/actuator/metrics"]
  C --> E["PrometheusMeterRegistry"]
  E --> F["/actuator/prometheus"]
  F --> G["Prometheus scrape target"]
  G --> H["Prometheus TSDB"]
  H --> I["remote_write queue"]
  I --> J["Remote metrics backend"]
  H --> K["Grafana / dashboard"]

  F --> L["OpenTelemetry Collector Prometheus receiver"]
  L --> M["Processors"]
  M --> N["OTLP / Prometheus exporter"]
  N --> J
~~~

Sơ đồ có hai nhánh thu thập phổ biến:

- Prometheus tự scrape ứng dụng rồi lưu vào TSDB; sau đó có thể remote_write tới backend khác.
- OpenTelemetry Collector tự scrape Prometheus endpoint hoặc nhận OTLP metrics, xử lý rồi export tới backend.

Một hệ thống có thể dùng cả hai hoặc chỉ một nhánh. Cần xác định kiến trúc thực tế trước khi kiểm tra.

### 1.2. Các tầng và bằng chứng cần có

| Tầng | Bằng chứng thành công | Khi thất bại |
|---|---|---|
| MeterRegistry | Meter có trong /actuator/metrics | Kiểm tra instrumentation/registry |
| Prometheus exposition | Series xuất hiện trong /actuator/prometheus | Kiểm tra registry exporter và endpoint |
| Scrape target | Target UP và scrape thành công | Kiểm tra URL, auth, TLS, network, timeout |
| Prometheus ingestion | Query trực tiếp thấy series mới | Kiểm tra metric relabel, sample limits, scrape window |
| Remote write | Backend đích nhận sample mới | Kiểm tra queue, auth, network và write relabel |
| Collector pipeline | Receiver nhận, processor giữ, exporter gửi | Kiểm tra pipeline wiring, filter, exporter |
| Dashboard | Query đúng series và time range | Kiểm tra datasource, labels, query và timezone |

## 2. Phân biệt Actuator metrics endpoint và Prometheus endpoint

Đây là lỗi cấu hình phổ biến nhất.

### 2.1. /actuator/metrics là endpoint chẩn đoán JSON

Endpoint này cho phép xem các meter đã đăng ký trong process. Ví dụ:

~~~http
GET /actuator/metrics
~~~

Sau đó có thể truy vấn một meter cụ thể:

~~~http
GET /actuator/metrics/db.vector.client.operation
~~~

Tên meter thực tế tùy phiên bản Spring AI/Micrometer. Endpoint thường trả JSON chứa tên meter, measurements và available tags. Đây là giao diện kiểm tra cho người vận hành, **không phải Prometheus text exposition format**.

Prometheus không thể scrape JSON Actuator metrics endpoint như thể đó là Prometheus endpoint. Nếu target cấu hình path /actuator/metrics, scrape có thể thất bại do định dạng không phù hợp hoặc parser không đọc được payload.

### 2.2. /actuator/prometheus là endpoint exposition

Khi ứng dụng có Prometheus registry implementation, endpoint này xuất dữ liệu theo định dạng Prometheus:

~~~http
GET /actuator/prometheus
~~~

Một timer có thể được biểu diễn bằng các series dạng:

~~~text
db_vector_client_operation_seconds_count{...} 12
db_vector_client_operation_seconds_sum{...} 0.42
~~~

Tên chính xác và các series histogram phụ thuộc registry, naming convention, timer configuration và phiên bản. Hãy lấy tên từ response thực tế, không đoán tên.

### 2.3. Cấu hình Spring Boot tham khảo

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - prometheus
~~~

Để có endpoint Prometheus, runtime classpath cần Prometheus registry implementation tương thích với Spring Boot/Micrometer. Chỉ có Actuator chưa chắc đã tạo endpoint Prometheus.

Không expose mọi Actuator endpoint chỉ để sửa lỗi scrape. Chỉ expose endpoint cần thiết và bảo vệ bằng security/network policy.

### 2.4. Management port riêng

Ứng dụng có thể chạy HTTP API ở port 8080 và management endpoint ở port 8081:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - prometheus
          - metrics
~~~

Trong trường hợp này, Prometheus phải scrape đúng port management. Nếu vẫn scrape port 8080, target có thể trả 404 hoặc route sang API server không có Actuator.

Ngoài port, cần kiểm tra:

- management.server.address có giới hạn interface chỉ bind localhost hoặc interface khác không.
- management.endpoints.web.base-path có bị đổi không.
- server.servlet.context-path hoặc reverse proxy có thêm prefix không.
- management.endpoints.web.path-mapping có đổi tên endpoint không.
- TLS termination và scheme HTTP/HTTPS ở giữa proxy với ứng dụng.

Không giả định URL luôn là host:8080/actuator/prometheus.

## 3. Kiểm tra endpoint ngay từ nơi chạy ứng dụng

Trước khi mở dashboard, hãy gọi endpoint trực tiếp từ máy/container có thể tiếp cận ứng dụng.

### 3.1. Kiểm tra HTTP status và content type

~~~bash
curl -i http://localhost:8081/actuator/prometheus
~~~

Kết quả mong đợi là HTTP 200 và body theo Prometheus exposition format. Nếu endpoint yêu cầu HTTPS:

~~~bash
curl -i https://localhost:8443/actuator/prometheus
~~~

Không tắt xác minh TLS trong production để làm cho scrape chạy được. Nếu chứng chỉ không hợp lệ, sửa trust chain/hostname hoặc cấu hình TLS của scraper.

### 3.2. Kiểm tra meter JSON và exposition riêng biệt

~~~bash
curl -i http://localhost:8081/actuator/metrics
curl -i http://localhost:8081/actuator/prometheus
~~~

Đọc kết quả:

| /actuator/metrics | /actuator/prometheus | Hướng điều tra |
|---|---|---|
| Có meter | Có series | Ứng dụng đã công bố; chuyển sang kiểm tra scraper |
| Có meter | 404 | Endpoint chưa expose, registry exporter thiếu hoặc path khác |
| Có meter | 401/403 | Security policy chặn endpoint exposition |
| Có meter | 200 nhưng không có series mong đợi | Kiểm tra meter name, registry, filters, meter có được ghi nhận chưa |
| Không có meter | Không có series | Quay lại instrumentation/registry |
| 404 cả hai | Base path, management port hoặc exposure có thể sai | Kiểm tra effective config và route |

### 3.3. Phân biệt 401, 403, 404 và lỗi kết nối

- **401 Unauthorized:** scraper chưa cung cấp credential hợp lệ hoặc proxy yêu cầu xác thực.
- **403 Forbidden:** đã tới được lớp bảo vệ nhưng principal không có quyền.
- **404 Not Found:** sai path/port/context path, endpoint chưa expose hoặc proxy route sai.
- **301/302 Redirect:** có thể bị chuyển sang HTTPS, login page hoặc route khác; Prometheus scrape cần URL trực tiếp đúng.
- **Connection refused:** không có process listen ở địa chỉ/port hoặc port mapping sai.
- **Timeout:** network, firewall, proxy, server quá tải hoặc scrape timeout quá ngắn.
- **TLS error:** CA, hostname, certificate chain, SNI hoặc protocol không khớp.
- **200 nhưng body HTML/JSON:** đang scrape nhầm endpoint hoặc proxy trả trang khác.

Không gửi token/password vào command history hoặc ticket. Nếu endpoint cần auth, cấu hình secret file hoặc secret manager theo khả năng của scraper.

### 3.4. Gọi từ đúng network namespace

Một endpoint chạy được trên localhost của container ứng dụng chưa chứng minh Prometheus ở namespace khác truy cập được. Hãy kiểm tra từ:

- Pod/container chạy Prometheus hoặc Collector.
- Node/network segment thực sự thực hiện scrape.
- Service DNS hoặc load balancer mà scraper sử dụng.

Kiểm tra DNS, port, route, NetworkPolicy, firewall, ingress và service mesh. Tránh chỉ thử từ laptop rồi kết luận đường truyền nội bộ hoạt động.

## 4. Kiểm tra Prometheus scrape configuration

Prometheus cần biết target, scheme, path, port, interval và phương thức xác thực.

### 4.1. Cấu hình static target tối thiểu

~~~yaml
scrape_configs:
  - job_name: spring-ai-evaluation
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /actuator/prometheus
    scheme: http
    static_configs:
      - targets:
          - app-host.internal:8081
        labels:
          service: spring-ai-evaluation
          environment: staging
~~~

Đây là ví dụ cho lab/staging. Trong production, target thường được tạo bằng Kubernetes service discovery, cloud service discovery hoặc file-based discovery; credentials và TLS phải được cấu hình theo policy.

### 4.2. Các trường cần đối chiếu

| Trường | Câu hỏi |
|---|---|
| job_name | Target có nằm trong đúng job không? |
| targets | Host/port có thể truy cập từ Prometheus không? |
| metrics_path | Có phải /actuator/prometheus không? |
| scheme | Endpoint dùng HTTP hay HTTPS? |
| scrape_interval | Có đang chờ nhầm cửa sổ thời gian không? |
| scrape_timeout | Có đủ dài nhưng không vượt interval không? |
| tls_config | CA, server_name và certificate có đúng không? |
| authorization/basic_auth | Credential có hợp lệ và được cấp đúng quyền không? |
| proxy_url | Proxy có route tới management port không? |
| params | Có query parameters bắt buộc không? |

Nếu ứng dụng dùng management port riêng, scrape target phải trỏ đúng port đó. Nếu base path hoặc reverse proxy prefix thay đổi, metrics_path phải khớp URL cuối cùng mà Prometheus gọi.

### 4.3. Kiểm tra target trong giao diện Prometheus

Mở trang Targets của Prometheus hoặc endpoint API targets được bảo vệ. Với từng target, kiểm tra:

- Target có xuất hiện không?
- State là UP hay DOWN?
- Last scrape time và last scrape duration.
- Last error.
- Labels sau relabeling.
- Discovered labels và final labels nếu giao diện hỗ trợ.

Nếu target không xuất hiện, điều tra service discovery và relabeling trước. Nếu target xuất hiện nhưng DOWN, đọc lỗi HTTP/TLS/network cụ thể.

### 4.4. Dùng metric tự giám sát của Prometheus

Một số metric hữu ích:

~~~promql
up{job="spring-ai-evaluation"}
~~~

Giá trị 1 nghĩa là scrape target thành công gần nhất; 0 nghĩa là scrape thất bại. Nếu không có series, target có thể chưa được phát hiện hoặc job/label selector sai.

Số sample đọc từ target:

~~~promql
scrape_samples_scraped{job="spring-ai-evaluation"}
~~~

Số sample còn lại sau metric relabeling:

~~~promql
scrape_samples_post_metric_relabeling{job="spring-ai-evaluation"}
~~~

Thời gian scrape:

~~~promql
scrape_duration_seconds{job="spring-ai-evaluation"}
~~~

Series mới được tạo trong lần scrape:

~~~promql
scrape_series_added{job="spring-ai-evaluation"}
~~~

Tên và khả năng có mặt của các self-monitoring metrics phụ thuộc phiên bản Prometheus. Chúng giúp định vị sự khác biệt giữa số sample đọc được và số sample được giữ lại.

### 4.5. Đọc chênh lệch sample count

Ví dụ:

| Chỉ số | Giá trị |
|---|---:|
| scrape_samples_scraped | 1.250 |
| scrape_samples_post_metric_relabeling | 1.020 |

Prometheus đã đọc 1.250 samples nhưng chỉ còn 1.020 sau metric relabeling. Có 230 samples bị loại hoặc không được giữ theo pipeline relabeling của scrape. Kiểm tra metric_relabel_configs và rule drop/keep.

Nếu hai giá trị bằng nhau, chưa chứng minh toàn bộ metric mong muốn có mặt; có thể endpoint vốn không xuất metric đó hoặc target scrape nhầm ứng dụng.

## 5. Relabeling có thể loại metric

Prometheus có nhiều giai đoạn relabel khác nhau. Nhầm chúng dễ khiến target hoặc sample biến mất.

### 5.1. relabel_configs: thay đổi hoặc loại target trước scrape

relabel_configs chạy trên target labels được phát hiện trước khi scrape. Nó có thể:

- Sửa __address__ hoặc __metrics_path__.
- Tạo, đổi tên hoặc xóa target labels.
- Chỉ giữ target phù hợp.
- Loại target bằng action drop.

Ví dụ:

~~~yaml
relabel_configs:
  - source_labels: [__meta_kubernetes_namespace]
    action: keep
    regex: ai-platform
~~~

Rule này chỉ giữ target có namespace ai-platform. Nếu ứng dụng nằm ở namespace khác, target sẽ không xuất hiện trong danh sách scrape cuối cùng.

Một lỗi khác là sửa __address__ sang port API thay vì management port, hoặc đặt __metrics_path__ thành /actuator/metrics.

### 5.2. metric_relabel_configs: loại sample sau khi scrape

metric_relabel_configs áp dụng lên từng sample sau khi Prometheus đọc endpoint và trước khi ingest. Ví dụ rule sau loại metric VectorStore:

~~~yaml
metric_relabel_configs:
  - source_labels: [__name__]
    action: drop
    regex: "db_vector_client_operation_seconds_.*"
~~~

Nếu có rule như vậy, endpoint vẫn trả metric và target vẫn có thể UP, nhưng các series bị loại khỏi TSDB.

Kiểm tra các action:

- drop: loại sample khớp regex.
- keep: chỉ giữ sample khớp regex.
- labeldrop/labelkeep: xóa hoặc giữ nhãn, có thể làm thay đổi cách truy vấn.
- labelmap: ánh xạ tên nhãn, có thể tạo nhãn ngoài dự kiến.
- replace: thay giá trị nhãn hoặc tên tùy cấu hình.

Regex của Prometheus được neo theo toàn bộ chuỗi trong nhiều thao tác relabel; đọc cấu hình thực tế và kiểm tra bằng promtool/fixture thay vì phỏng đoán.

### 5.3. write_relabel_configs: loại sample khi remote_write

Một metric có thể tồn tại trong Prometheus local TSDB nhưng bị loại trước khi gửi tới remote backend:

~~~yaml
remote_write:
  - url: https://metrics.example.internal/api/v1/write
    write_relabel_configs:
      - source_labels: [__name__]
        action: drop
        regex: "db_vector_client_operation_seconds_.*"
~~~

Rule này không làm metric biến mất khỏi local Prometheus; nó chỉ tác động đến luồng remote_write tương ứng. Nếu dashboard truy vấn remote backend, metric có thể không xuất hiện dù Prometheus local vẫn có.

### 5.4. Cách xác định rule gây mất metric

1. Gọi /actuator/prometheus và xác nhận series có trong body.
2. Kiểm tra target UP và scrape_samples_scraped.
3. So sánh scrape_samples_post_metric_relabeling.
4. Đọc toàn bộ relabel_configs và metric_relabel_configs của job.
5. Query trực tiếp trên Prometheus local.
6. Nếu local có nhưng remote backend không có, kiểm tra write_relabel_configs và remote_write queue.
7. Thử rule trên cấu hình staging hoặc bản sao config có test fixtures trước khi sửa production.

Không xóa hàng loạt relabel rules chỉ để metric xuất hiện; chúng có thể đang bảo vệ cardinality, loại dữ liệu nhạy cảm hoặc giới hạn chi phí.

## 6. Scrape limits và lỗi do payload

Prometheus có các giới hạn nhằm bảo vệ tài nguyên:

- scrape_timeout.
- sample_limit.
- label_limit.
- label_name_length_limit.
- label_value_length_limit.
- body_size_limit trong các phiên bản hỗ trợ.

Nếu endpoint xuất quá nhiều series, nhãn quá dài hoặc body vượt giới hạn, scrape có thể bị từ chối hoặc thất bại theo cấu hình/version.

### 6.1. Dấu hiệu thường gặp

- Target DOWN với last error đề cập sample limit hoặc label limit.
- Scrape duration gần timeout.
- Số series tăng mạnh sau khi thêm tag mới.
- Endpoint response lớn bất thường.
- Cardinality tăng sau khi đưa request ID, tenant ID hoặc document ID vào metric tags.

### 6.2. Hướng xử lý

1. Xác định metric family và label nào tạo cardinality.
2. Bỏ raw query, trace ID, user ID, tenant ID và document ID khỏi metric labels.
3. Chuẩn hóa version/profile thành tập giá trị có kiểm soát.
4. Dùng histogram bucket có chủ đích, không tạo vô hạn bucket động.
5. Giữ scrape limits phù hợp với capacity; không tăng giới hạn trước khi hiểu nguyên nhân payload phình to.
6. Kiểm tra số series sau relabeling và dung lượng TSDB.

Tăng sample_limit có thể giúp scrape hoàn tất nhưng cũng tăng tải và chi phí. Sửa nguồn cardinality thường bền vững hơn.

## 7. Phân biệt scrape với remote_write

Một hệ thống Prometheus có hai giai đoạn riêng:

1. Scrape target và ingest samples vào local TSDB.
2. Gửi samples từ local TSDB tới remote backend bằng remote_write.

### 7.1. Kiểm tra local trước

Trong Prometheus local, query trực tiếp:

~~~promql
db_vector_client_operation_seconds_count
~~~

Hoặc theo job:

~~~promql
{job="spring-ai-evaluation", __name__=~"db_vector_client_operation_seconds_.*"}
~~~

Nếu local Prometheus có series, Actuator và scrape path cơ bản đang hoạt động. Chuyển sang remote_write hoặc dashboard datasource.

Nếu local không có:

- Kiểm tra endpoint exposition.
- Kiểm tra target UP.
- Kiểm tra metric relabeling.
- Kiểm tra scrape interval và thời điểm operation tạo meter.

### 7.2. Remote write queue

Khi local có series nhưng backend trung tâm không có, kiểm tra:

- URL remote_write và route mạng.
- TLS, CA, auth token và tenant header.
- HTTP status từ remote endpoint.
- Queue pending, retries, failed samples và dropped samples nếu phiên bản export các metric này.
- Backend rate limit, payload limits và retention.
- write_relabel_configs.

Các metric nội bộ remote storage có thể có tên dạng prometheus_remote_storage_samples_pending hoặc counters retry/failure; tên cụ thể thay đổi theo Prometheus version. Khám phá metric có sẵn trên chính server.

### 7.3. Phân biệt lỗi ghi và lỗi truy vấn

Nếu remote_write queue đang retry hoặc pending tăng, dashboard ở backend đích có thể chậm hơn local. Nếu queue bình thường nhưng dashboard trống, kiểm tra tenant/project, datasource, metric name và label mapping ở backend.

Không coi remote_write HTTP 2xx là bằng chứng mọi series được hiển thị trên dashboard. Backend có thể nhận sample nhưng query đang dùng sai tenant, namespace, metric name hoặc time range.

## 8. OpenTelemetry Collector: receiver, processor và exporter

Một kiến trúc khác là Collector scrape Prometheus exposition rồi export metrics bằng OTLP hoặc giao thức khác. Lúc này cần kiểm tra ba lớp:

- Receiver có scrape được target không?
- Processor có giữ lại metric không?
- Exporter có gửi thành công tới backend không?

### 8.1. Ví dụ cấu hình Prometheus receiver

~~~yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: spring-ai-evaluation
          scrape_interval: 15s
          metrics_path: /actuator/prometheus
          static_configs:
            - targets: ["app-host.internal:8081"]

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  batch:

exporters:
  otlp:
    endpoint: otel-gateway.internal:4317
    tls:
      insecure: false

service:
  pipelines:
    metrics:
      receivers: [prometheus]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

Đây là cấu hình minh họa; endpoint, TLS, certificate, auth và phiên bản Collector phải được điều chỉnh theo môi trường. Với production, dùng trust bundle/credentials được quản lý an toàn.

### 8.2. Kiểm tra pipeline wiring

Một receiver được khai báo chưa đủ; nó phải được tham chiếu trong service.pipelines.metrics. Tương tự, processor hoặc exporter không được nối vào pipeline thì không xử lý dữ liệu.

Kiểm tra:

- Receiver name có đúng với tên trong pipeline không?
- Pipeline type là metrics hay traces?
- Processor có filter/drop metric nào không?
- Exporter có endpoint, TLS và auth hợp lệ không?
- Exporter đã được liệt kê trong pipeline metrics chưa?
- Collector logs có báo retry, queue full, refused, unauthenticated hoặc throttled không?

### 8.3. Processor có thể làm mất metric

Các processor có khả năng lọc/biến đổi dữ liệu gồm filter, transform, attributes, resource và metricstransform. Kiểm tra điều kiện drop, rename hoặc resource attributes khiến query ở backend không còn khớp.

Nếu Collector có nhiều pipeline, cùng một receiver có thể được dùng ở nhiều pipeline với processors/exporters khác nhau. Kiểm tra đúng pipeline đích mà dashboard đang dùng.

### 8.4. Tách telemetry nội bộ của Collector khỏi telemetry ứng dụng

Collector có metric riêng để quan sát receiver/exporter, ví dụ số datapoints nhận, gửi, bị từ chối hoặc queue. Những metric này không phải metric VectorStore. Chúng giúp biết pipeline Collector có hoạt động hay không, nhưng phải xem cùng log/error và backend exporter.

## 9. Kubernetes và service discovery

Trong Kubernetes, Prometheus Operator hoặc cơ chế discovery có thể chỉ chọn ServiceMonitor/PodMonitor thỏa selector.

Kiểm tra:

- Pod đang Ready và endpoint port có tên/number đúng.
- Service selector khớp Pod labels.
- Service targetPort trỏ đúng management port.
- ServiceMonitor namespaceSelector và selector khớp Service.
- Prometheus resource có serviceMonitorSelector phù hợp.
- PodMonitor selector/namespace đúng nếu scrape trực tiếp Pod.
- Annotation/path/port đúng nếu dùng annotation-based discovery.
- NetworkPolicy/service mesh cho phép Prometheus hoặc Collector truy cập.

### 9.1. Ví dụ Service expose management port

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: spring-ai-evaluation
  labels:
    app: spring-ai-evaluation
spec:
  selector:
    app: spring-ai-evaluation
  ports:
    - name: management
      port: 8081
      targetPort: management
      protocol: TCP
~~~

Đây là ví dụ Service; Pod phải thực sự khai báo container port có tên management và ứng dụng phải listen trên port đó. Service port name/selector cần khớp với ServiceMonitor/PodMonitor.

### 9.2. Ví dụ ServiceMonitor

~~~yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: spring-ai-evaluation
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app: spring-ai-evaluation
  namespaceSelector:
    matchNames:
      - ai-platform
  endpoints:
    - port: management
      path: /actuator/prometheus
      interval: 15s
      scheme: http
~~~

Ví dụ phụ thuộc Prometheus Operator CRD và label selector của Prometheus resource. Nếu ServiceMonitor không được Prometheus chọn, nó sẽ không tạo target dù YAML đã được apply thành công. Kiểm tra operator logs, resource labels và generated scrape config.

## 10. Dashboard có thể làm metric trông như bị mất

Khi Prometheus local đã có series nhưng dashboard không hiển thị, kiểm tra:

1. Dashboard đang dùng đúng datasource/project/tenant không?
2. Time range có bao phủ thời điểm scrape và operation không?
3. Query có lọc sai job, instance, namespace hoặc environment không?
4. Tên series đã được chuẩn hóa hoặc đổi qua recording rule chưa?
5. Label đã bị relabel/rename chưa?
6. Panel đang hiển thị rate nhưng counter chưa có đủ samples trong cửa sổ?
7. Biến dashboard đang rỗng hoặc giá trị cũ?
8. Có timezone offset khiến người xem chọn nhầm khoảng thời gian không?

Ví dụ timer count:

~~~promql
sum by (job) (
  rate(db_vector_client_operation_seconds_count{
    db_operation_name="query"
  }[5m])
)
~~~

Nếu metric thực tế dùng label khác hoặc name khác, query này trả rỗng dù series vẫn tồn tại. Dùng Explore để chạy tên metric thô trước khi sửa panel.

### 10.1. Kiểm tra stale series

Prometheus đánh dấu series stale khi target/series không còn được scrape theo quy tắc. Một metric không xuất hiện ở thời điểm hiện tại có thể do:

- Operation không phát sinh trong thời gian gần đây.
- Meter chỉ được tạo khi code path chạy.
- Target chuyển instance hoặc labels thay đổi.
- Scrape thất bại hoặc series bị relabel/drop.
- Dashboard đang truy vấn instant vector tại thời điểm không có sample phù hợp.

Với counter, dùng rate/increase trên cửa sổ phù hợp; với gauge, xem giá trị và semantics cập nhật. Không coi mọi panel trống là scrape outage.

## 11. Quy trình chẩn đoán theo bằng chứng

Thực hiện theo thứ tự sau để tìm tầng đầu tiên không còn dữ liệu:

1. **Actuator JSON:** xác nhận meter xuất hiện trong /actuator/metrics.
2. **Prometheus exposition:** xác nhận series có trong /actuator/prometheus và HTTP 200.
3. **Đúng network path:** gọi endpoint từ network namespace của Prometheus/Collector.
4. **Target discovery:** xác nhận target xuất hiện trong Targets và có labels đúng.
5. **Scrape health:** kiểm tra up, last error, scrape duration và sample counts.
6. **Local ingestion:** query series trực tiếp trên Prometheus local.
7. **Relabeling:** so sánh samples scraped với samples post metric relabeling; đọc drop/keep rules.
8. **Remote write:** nếu local có nhưng backend không có, kiểm tra queue, auth, TLS, write relabel và backend response.
9. **Collector:** kiểm tra receiver, processors, exporter và logs nếu Collector nằm trên đường đi.
10. **Dashboard:** kiểm tra datasource, query, labels và time range.
11. **Ghi nhận nguyên nhân:** nêu rõ chặng đầu tiên làm mất dữ liệu cùng bằng chứng.
12. **Thêm kiểm thử:** giữ smoke test cho endpoint, scrape và query để ngăn hồi quy.

### 11.1. Ma trận triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Bằng chứng cần xem |
|---|---|---|
| /actuator/metrics có, /actuator/prometheus 404 | Thiếu exporter hoặc chưa expose endpoint | Runtime dependency, HTTP status, effective config |
| Prometheus endpoint trả 401/403 | Security/auth | HTTP response, security rules, credentials scope |
| Prometheus endpoint trả JSON/HTML | Scrape nhầm path hoặc proxy route | Content-Type, body, metrics_path |
| Endpoint 200 nhưng target DOWN | Network, TLS, timeout, parser hoặc limits | Target last error, scrape duration, logs |
| Target không xuất hiện | Service discovery/relabel keep/drop | Discovered labels, selectors, relabel config |
| Target UP nhưng metric không có local | Metric absent, metric_relabel drop hoặc meter chưa có sample | Endpoint body, scrape sample counts, PromQL |
| samples_scraped lớn hơn post_metric_relabeling | Metric relabel drop/keep | metric_relabel_configs |
| Local Prometheus có, remote backend không | remote_write, write relabel hoặc backend | Queue/retry/error, remote endpoint response |
| Collector nhận nhưng backend không có | Processor filter hoặc exporter failure | Collector logs/internal metrics/pipeline config |
| Backend có nhưng Grafana trống | Datasource, tenant, query, label hoặc time range | Explore/raw query và datasource settings |
| Chỉ mất p95, count/sum vẫn có | Histogram buckets không export hoặc bị drop | _bucket series và histogram config |
| Metric mất sau deploy | Port/path/labels/config/service selector thay đổi | Diff deployment, generated scrape config |

## 12. Kiểm thử đường thu thập

Một bài test chỉ kiểm tra MeterRegistry trong process chưa đủ. Cần test ít nhất endpoint exposition và có smoke test ở môi trường triển khai cho scrape target.

### 12.1. Integration test PrometheusMeterRegistry

Ví dụ test trong Spring Boot context có Prometheus registry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class VectorStorePrometheusExportTest {
    @Autowired
    PrometheusMeterRegistry prometheusRegistry;

    @Autowired
    VectorStoreFixtureService fixtureService;

    @Test
    void vectorStoreQueryIsExported() {
        fixtureService.runSafeQuery();

        String exposition = prometheusRegistry.scrape();

        assertThat(exposition)
                .contains("db_vector_client_operation_seconds_count");
    }
}
~~~

Ví dụ này giả định version Micrometer dùng package Prometheus registry tương ứng và fixture service gọi đúng VectorStore adapter. Package/API có thể khác giữa các thế hệ Micrometer; điều chỉnh theo dependency thực tế. Nếu meter name được chuẩn hóa khác, assert theo output thực tế đã xác minh.

Test này chứng minh registry có thể tạo exposition sau operation. Nó chưa chứng minh Prometheus server đã scrape được ứng dụng.

### 12.2. HTTP smoke test

Trong môi trường integration, gọi:

~~~text
GET /actuator/prometheus
~~~

Assert:

- HTTP status 200.
- Content-Type là Prometheus exposition format phù hợp.
- Body có metric fixture sau khi operation chạy.
- Không có raw query, prompt, document content hoặc secret trong labels.

Nếu management port riêng, test cần cấu hình đúng management endpoint. Đừng test nhầm application port.

### 12.3. Kiểm thử scrape config

Trong CI cho repository cấu hình Prometheus:

~~~bash
promtool check config prometheus.yml
~~~

Lệnh này kiểm tra cú pháp/cấu trúc cấu hình mà phiên bản promtool hỗ trợ. Nó không chứng minh target reachable, auth đúng hay metric được ingest. Cần thêm integration/smoke test từ môi trường mạng gần với Prometheus.

Với Kubernetes, test discovery cần xác minh Service/ServiceMonitor/Prometheus selectors sau khi deploy vào môi trường kiểm thử; YAML lint đơn thuần không chứng minh target được chọn.

### 12.4. Kiểm thử remote write/Collector

Nếu có remote_write hoặc Collector:

- Dùng backend test hoặc receiver giả để xác minh sample tới đích.
- Tạo metric canary có tên/tag không nhạy cảm.
- Xác nhận processor không drop metric được phép.
- Xác nhận write_relabel không loại metric canary.
- Kiểm tra exporter retry/error và queue không tăng liên tục.
- Kiểm tra tenant/resource attributes ở backend đích.

Không dùng raw query hoặc customer identifier làm canary label; canary phải là dữ liệu tổng hợp không nhạy cảm.

## 13. Bảo mật khi mở endpoint metrics

Metrics endpoint có thể tiết lộ tên service, backend, database, index/collection, môi trường, trạng thái lỗi và tải hệ thống. Không nên public endpoint chỉ để Prometheus scrape.

Áp dụng:

- Chỉ cho phép scraper/collector được duyệt truy cập management port.
- Dùng network policy, firewall hoặc private service.
- Bảo vệ bằng authentication/TLS khi endpoint đi qua mạng không tin cậy.
- Không expose env, configprops, heapdump hoặc mappings rộng rãi nếu không cần.
- Không đưa raw query, document ID, tenant ID hoặc prompt vào metric labels.
- Giới hạn cardinality và số series.
- Theo dõi ai có thể truy cập Actuator và dashboard.
- Dùng secret manager hoặc mounted secret file cho scrape credentials.

Nếu endpoint bị 403, không tắt toàn bộ Spring Security để giải quyết. Cấp quyền tối thiểu cho principal scraper trên đúng endpoint.

## 14. Runbook theo từng kết quả kiểm tra

### Trường hợp A: Actuator JSON có meter, Prometheus endpoint không có

1. Xác nhận Prometheus registry implementation có trong runtime classpath.
2. Kiểm tra endpoint prometheus có được expose không.
3. Kiểm tra management port/base path/path mapping.
4. Kiểm tra security response và content type.
5. Nếu endpoint trả 200 nhưng thiếu meter, so sánh registry, meter filters và output naming.

### Trường hợp B: Prometheus endpoint có metric, target DOWN

1. Mở Targets và đọc last error.
2. Kiểm tra port/path/scheme từ Prometheus network.
3. Kiểm tra DNS, route, firewall, NetworkPolicy và service mesh.
4. Kiểm tra TLS/auth/redirect.
5. So sánh scrape timeout với response duration và server load.

### Trường hợp C: Target UP nhưng metric không có trong local Prometheus

1. Query metric name thô trong endpoint response.
2. Kiểm tra scrape_samples_scraped và scrape_samples_post_metric_relabeling.
3. Kiểm tra metric_relabel_configs, sample/label limits.
4. Kiểm tra đúng job/instance/labels và scrape time.
5. Xác minh operation fixture đã chạy trước khi mong đợi timer series.

### Trường hợp D: Local Prometheus có, remote backend không có

1. Kiểm tra remote_write queue, retry, failure và dropped samples.
2. Kiểm tra write_relabel_configs.
3. Kiểm tra endpoint URL, tenant header, TLS/auth và rate limit.
4. Kiểm tra backend nhận sample vào đúng tenant/project.
5. Kiểm tra dashboard truy vấn đúng remote datasource.

### Trường hợp E: Collector nằm giữa ứng dụng và backend

1. Kiểm tra Prometheus receiver target và scrape error.
2. Kiểm tra pipeline metrics có receiver, processor, exporter đúng.
3. Kiểm tra filter/transform/metricstransform processors.
4. Kiểm tra exporter queue, retry, auth và TLS.
5. Kiểm tra Collector internal telemetry và backend ingestion.

## 15. Những sai lầm thường gặp

1. **Cấu hình Prometheus scrape /actuator/metrics.** Đây là endpoint JSON, không phải Prometheus exposition.
2. **Scrape nhầm application port.** Management endpoint có thể chạy ở port riêng.
3. **Chỉ expose metrics mà quên prometheus.** Actuator metrics JSON không thay registry exporter.
4. **Kiểm tra localhost rồi kết luận Prometheus truy cập được.** Network namespace và NetworkPolicy có thể khác.
5. **Tắt security toàn bộ để sửa 401/403.** Cần quyền tối thiểu trên management endpoint.
6. **Bỏ qua relabel_configs.** Target có thể bị loại trước khi scrape.
7. **Bỏ qua metric_relabel_configs.** Target UP nhưng sample vẫn có thể bị drop.
8. **Bỏ qua write_relabel_configs.** Local có metric nhưng remote backend không nhận.
9. **Tăng sample_limit ngay khi scrape thất bại.** Có thể che vấn đề cardinality.
10. **Coi target UP là mọi metric đều có.** UP chỉ nói scrape thành công, không xác nhận một metric cụ thể.
11. **Coi scrape_samples_scraped là số series lưu cuối cùng.** Metric relabeling có thể làm số sample giảm.
12. **Coi remote_write 2xx là dashboard chắc chắn có dữ liệu.** Backend tenant/query/time range vẫn có thể sai.
13. **Khai receiver nhưng quên nối vào Collector pipeline.** Component không được tham chiếu sẽ không chạy.
14. **Đọc metric Collector như metric ứng dụng.** Hai nhóm metric có scope khác nhau.
15. **Không kiểm thử sau thay đổi port, path hoặc service labels.** Scrape target có thể mất sau deploy.

## 16. Bài thực hành tự luyện

**Bối cảnh:** Ứng dụng Spring AI có meter VectorStore trong /actuator/metrics. Prometheus target hiển thị UP nhưng dashboard không thấy db.vector.client.operation.

Yêu cầu:

1. Gọi /actuator/metrics và ghi lại meter name thực tế.
2. Gọi /actuator/prometheus, xác nhận HTTP status, content type và series.
3. Kiểm tra management port, base path, path mapping và security.
4. Từ Prometheus network, gọi endpoint bằng cùng scheme/port/path.
5. Mở Targets, xác nhận labels, last scrape và scrape error.
6. Query up, scrape_samples_scraped và scrape_samples_post_metric_relabeling.
7. Đọc relabel_configs và metric_relabel_configs; xác định rule drop nếu có.
8. Query metric thô trong Prometheus local.
9. Nếu local có nhưng backend không có, kiểm tra write_relabel_configs và remote_write queue.
10. Nếu dùng Collector, kiểm tra receiver, processor, exporter và pipeline metrics.
11. Kiểm tra datasource, labels, query và time range của dashboard.
12. Thêm HTTP smoke test và promtool check config vào quy trình CI.

**Câu hỏi tự kiểm tra:**

- /actuator/metrics và /actuator/prometheus khác nhau thế nào?
- Vì sao target có thể UP nhưng metric cụ thể vẫn không tồn tại?
- relabel_configs khác metric_relabel_configs ở thời điểm áp dụng nào?
- write_relabel_configs tác động đến local TSDB hay remote_write?
- Khi samples_scraped lớn hơn samples_post_metric_relabeling, nên kiểm tra gì?
- Vì sao management port riêng dễ làm scrape nhầm target?
- Khi Prometheus local có series nhưng backend trung tâm không có, chặng nào cần kiểm tra?
- Một Collector receiver có chạy nếu không được khai báo trong pipeline không?
- Vì sao scrape endpoint thành công từ laptop chưa đủ chứng minh Prometheus truy cập được?
- Khi scrape timeout, có nên tăng timeout ngay không? Cần đo gì trước?

## 17. Checklist triển khai

- [ ] Meter xuất hiện trong Actuator và tên meter thực tế đã được xác minh.
- [ ] Prometheus registry implementation có trong runtime khi cần Prometheus exposition.
- [ ] Prometheus scrape đúng /actuator/prometheus, không dùng /actuator/metrics.
- [ ] Management port, base path, context path, scheme và path mapping đã khớp.
- [ ] Endpoint được expose và bảo vệ bằng quyền tối thiểu.
- [ ] Endpoint được kiểm tra từ đúng network namespace của scraper.
- [ ] Prometheus target được discovery và trạng thái UP.
- [ ] Scrape errors, duration và sample counts được theo dõi.
- [ ] relabel_configs không vô tình loại target hoặc sửa sai address/path.
- [ ] metric_relabel_configs không drop metric cần thiết.
- [ ] Sample/label/body limits phù hợp với cardinality và payload thực tế.
- [ ] Prometheus local query thấy series trước khi điều tra remote backend.
- [ ] write_relabel_configs, remote_write queue, auth, TLS và backend response được kiểm tra.
- [ ] Nếu dùng Collector, receiver/processors/exporters được nối đúng pipeline metrics.
- [ ] Dashboard dùng đúng datasource, metric name, labels và time range.
- [ ] Có HTTP smoke test cho exposition endpoint.
- [ ] Có promtool check config và test discovery sau thay đổi cấu hình.
- [ ] Không đưa query, document, tenant ID hoặc secret vào metric labels.

## Tổng kết

Khi meter đã có trong Actuator nhưng không tới hệ thu thập, hãy tách đường truyền thành các chặng: **MeterRegistry → Prometheus exposition → target discovery → scrape → local ingestion → remote_write/Collector → backend → dashboard**. /actuator/metrics là endpoint JSON để chẩn đoán meter trong process; Prometheus cần endpoint exposition phù hợp như /actuator/prometheus. Sai port, path, security, network hoặc service discovery có thể khiến target không scrape được. Ngược lại, target UP vẫn có thể không lưu metric do metric relabeling hoặc sample limits.

Nếu Prometheus local đã có series nhưng backend trung tâm không có, chuyển hướng điều tra sang remote_write, write relabeling, Collector processor/exporter và tenant/backend. Nếu backend có dữ liệu nhưng dashboard trống, kiểm tra datasource, label selector, metric name và time range. Dùng bằng chứng của từng chặng, canary metrics và integration smoke tests để xác định nơi dữ liệu bị mất, thay vì thay đổi registry hoặc nới lỏng bảo mật một cách thiếu căn cứ.

## Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): management endpoints, exposure và path.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry và metrics endpoint.
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): PrometheusMeterRegistry và exposition.
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/): scrape_configs, relabeling và remote_write.
- [Prometheus — Targets](https://prometheus.io/docs/concepts/jobs_instances/): jobs, instances và scrape target.
- [Prometheus — Jobs and Instances](https://prometheus.io/docs/concepts/jobs_instances/): mô hình scrape target.
- [Prometheus — Relabeling](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#relabel_config): target, metric và write relabeling.
- [Prometheus — Remote Write](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write): cấu hình gửi samples tới remote storage.
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/): receivers, processors, exporters và pipelines.
- [Prometheus Operator — API](https://prometheus-operator.dev/docs/api-reference/api/): Prometheus, ServiceMonitor và PodMonitor.
- [Prometheus — promtool](https://prometheus.io/docs/prometheus/latest/command-line/promtool/): kiểm tra cấu hình và công cụ chẩn đoán.
