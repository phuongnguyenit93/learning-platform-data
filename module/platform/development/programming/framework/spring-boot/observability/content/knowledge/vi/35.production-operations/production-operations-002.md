# Cấu hình exporter bằng environment

Trong chương **Vận hành production** của module `SPRING_BOOT_OBSERVABILITY`, bài này trình bày cách cấu hình các exporter của Spring Boot bằng biến môi trường. Mục tiêu là triển khai cùng một ứng dụng ở nhiều môi trường mà không phải đóng gói endpoint collector, credential, chu kỳ export hay sampling vào mã nguồn. Cách làm này hỗ trợ thiết lập observability bằng Micrometer Observation, metrics, logs và distributed tracing; đồng thời giúp thay đổi đích nhận telemetry theo từng môi trường vận hành.

Spring Boot bind biến môi trường vào `Environment` thông qua cơ chế relaxed binding. Các property có thể được đặt trong `application.yml`, file cấu hình theo profile, biến môi trường hoặc các nguồn cấu hình khác. Ứng dụng cần có dependency và auto-configuration tương ứng thì exporter mới hoạt động; chỉ đặt biến môi trường không tự cài thêm registry hoặc tracing bridge.

## 1. Phân biệt các loại exporter và cách truyền dữ liệu

Exporter chuyển telemetry từ ứng dụng tới hệ thống thu thập. Trước khi cấu hình, cần xác định loại tín hiệu, giao thức và mô hình truyền dữ liệu:

| Tín hiệu | Cách thường dùng | Đích nhận | Đặc điểm vận hành |
| --- | --- | --- | --- |
| Metrics | Micrometer OTLP registry | OpenTelemetry Collector hoặc OTLP backend | Ứng dụng chủ động gửi dữ liệu theo chu kỳ. |
| Metrics | Micrometer Prometheus registry | Prometheus server scrape endpoint Actuator | Prometheus chủ động lấy dữ liệu từ ứng dụng. |
| Traces | Micrometer Tracing với OTLP exporter | OpenTelemetry Collector hoặc tracing backend | Span được gửi theo cấu hình exporter và sampling. |
| Logs | Logging appender, agent hoặc log collector | OpenTelemetry Collector hoặc log platform | Thường là pipeline logging riêng; không mặc định được xuất bằng metrics exporter. |

Hai mô hình metrics phổ biến có hướng truyền khác nhau. OTLP thường là push: ứng dụng gửi dữ liệu đến collector. Prometheus thường là pull: Prometheus server gọi endpoint `/actuator/prometheus` của ứng dụng. Vì vậy, không cấu hình một URL push cho Prometheus registry theo cách của OTLP.

Với OTLP qua HTTP, OpenTelemetry Collector thường nhận metrics ở `/v1/metrics` và traces ở `/v1/traces`, thường trên cổng HTTP OTLP `4318`. Cổng và path thực tế phụ thuộc cấu hình receiver của collector. Hãy xác nhận ứng dụng và collector thống nhất giao thức, host, port, path, TLS và authentication.

## 2. Cách Spring Boot chuyển tên property thành biến môi trường

Spring Boot áp dụng quy tắc chuyển đổi tên property sang biến môi trường:

1. Thay dấu chấm (`.`) bằng dấu gạch dưới (`_`).
2. Bỏ dấu gạch ngang (`-`).
3. Chuyển toàn bộ tên thành chữ hoa.

Ví dụ:

| Property | Environment variable |
| --- | --- |
| `management.otlp.metrics.export.url` | `MANAGEMENT_OTLP_METRICS_EXPORT_URL` |
| `management.otlp.metrics.export.step` | `MANAGEMENT_OTLP_METRICS_EXPORT_STEP` |
| `management.otlp.tracing.endpoint` | `MANAGEMENT_OTLP_TRACING_ENDPOINT` |
| `management.tracing.sampling.probability` | `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |

Giá trị environment variable luôn được truyền dưới dạng chuỗi; Spring Boot sẽ bind sang kiểu đích như boolean, số hoặc duration. Ví dụ `30s` là duration 30 giây, còn `0.1` là số thập phân. Với giá trị chứa dấu phẩy, dấu cách hoặc ký tự đặc biệt, hãy chú ý cách quote của shell, Docker Compose hoặc YAML manifest.

## 3. Cấu hình OTLP metrics exporter

Ứng dụng cần Micrometer OTLP registry tương ứng trên classpath và cấu hình exporter. Trong các phiên bản Spring Boot có hỗ trợ cấu hình OTLP metrics, các property thường dùng gồm:

| Property | Environment variable | Ý nghĩa |
| --- | --- | --- |
| `management.otlp.metrics.export.url` | `MANAGEMENT_OTLP_METRICS_EXPORT_URL` | URL nhận OTLP metrics. Với OTLP/HTTP, thường kết thúc bằng `/v1/metrics`. |
| `management.otlp.metrics.export.step` | `MANAGEMENT_OTLP_METRICS_EXPORT_STEP` | Chu kỳ xuất metrics, ví dụ `30s` hoặc `1m`. |
| `management.otlp.metrics.export.connect-timeout` | `MANAGEMENT_OTLP_METRICS_EXPORT_CONNECT_TIMEOUT` | Giới hạn thời gian thiết lập kết nối. |
| `management.otlp.metrics.export.read-timeout` | `MANAGEMENT_OTLP_METRICS_EXPORT_READ_TIMEOUT` | Giới hạn thời gian chờ phản hồi. |

Ví dụ chạy ứng dụng trên Linux hoặc macOS:

```bash
export SPRING_PROFILES_ACTIVE=prod
export SPRING_APPLICATION_NAME=orders-api
export MANAGEMENT_OTLP_METRICS_EXPORT_URL=http://otel-collector:4318/v1/metrics
export MANAGEMENT_OTLP_METRICS_EXPORT_STEP=30s
export MANAGEMENT_OTLP_METRICS_EXPORT_CONNECT_TIMEOUT=2s
export MANAGEMENT_OTLP_METRICS_EXPORT_READ_TIMEOUT=10s

java -jar app.jar
```

`otel-collector` trong ví dụ là hostname có thể phân giải từ network của ứng dụng, chẳng hạn tên service trong Docker Compose hoặc Kubernetes. Khi chạy local, có thể thay bằng `localhost` nếu collector thực sự chạy cùng network namespace. Trong container, `localhost` trỏ về chính container ứng dụng; nó không tự trỏ tới container collector khác.

Chu kỳ export là một lựa chọn vận hành. Chu kỳ ngắn giúp dữ liệu đến backend nhanh hơn nhưng tăng số lần gửi và overhead; chu kỳ dài giảm tần suất gửi nhưng làm dữ liệu trễ hơn. Hãy cân nhắc lưu lượng, độ trễ chấp nhận được, giới hạn backend và yêu cầu điều tra. Cấu hình cụ thể có thể khác giữa các phiên bản Spring Boot và Micrometer; hãy dùng property được hỗ trợ bởi phiên bản đang chạy.

## 4. Cấu hình OTLP tracing exporter và sampling

Tracing cần tracing bridge và OTLP exporter tương ứng. Khi dependency và auto-configuration đã sẵn sàng, có thể cấu hình endpoint gửi span và sampling bằng environment variables:

```bash
export MANAGEMENT_OTLP_TRACING_ENDPOINT=http://otel-collector:4318/v1/traces
export MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.10
```

Các property tương ứng:

| Property | Environment variable | Ý nghĩa |
| --- | --- | --- |
| `management.otlp.tracing.endpoint` | `MANAGEMENT_OTLP_TRACING_ENDPOINT` | Endpoint nhận OTLP traces. |
| `management.tracing.sampling.probability` | `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` | Tỷ lệ trace được chọn để ghi nhận, trong khoảng từ `0.0` đến `1.0`. |

Sampling probability `0.10` có nghĩa là sampler chọn khoảng 10% trace theo chính sách sampling đang dùng. Đây là quyết định về trace; nó không làm giảm tỷ lệ thu thập metrics theo cùng cách. Tăng sampling có thể cải thiện khả năng quan sát request hiếm nhưng cũng tăng lưu lượng, chi phí ingest và dung lượng lưu trữ. Với production, hãy chọn tỷ lệ dựa trên traffic, yêu cầu điều tra và ngân sách telemetry; cân nhắc tail sampling ở collector nếu cần quyết định dựa trên kết quả trace hoàn chỉnh.

Để tracing có ích khi điều tra liên service, cần giữ propagation context qua HTTP client, messaging và các ranh giới xử lý bất đồng bộ. Endpoint exporter hoạt động không đồng nghĩa propagation đã đúng hoặc mọi request đều có trace được lưu. Sampling, instrumentation và việc backend nhận span đều ảnh hưởng đến khả năng tìm thấy trace.

## 5. Khai báo resource attributes và headers

Telemetry cần định danh service nhất quán để phân biệt dữ liệu giữa ứng dụng, môi trường và phiên bản triển khai. Các thuộc tính thường dùng gồm `service.name`, `service.namespace`, `service.version` và `deployment.environment`. Giá trị cụ thể và cách bind resource attributes phụ thuộc exporter cùng phiên bản Spring Boot/Micrometer.

Với cấu hình map hoặc cấu trúc lồng nhau, không nên đoán tên biến môi trường cho mọi map key. Có thể dùng `SPRING_APPLICATION_JSON` để truyền cấu trúc property rõ ràng. Ví dụ minh họa cấu hình resource attributes cho OTLP metrics:

```bash
export SPRING_APPLICATION_JSON='{"management":{"otlp":{"metrics":{"export":{"resource-attributes":{"service.name":"orders-api","deployment.environment":"production","service.namespace":"commerce"}}}}}}'
```

Hãy kiểm tra property map này được phiên bản exporter đang dùng hỗ trợ và được bind đúng kiểu. Nếu ứng dụng đã nhận service identity từ một cấu hình chung hoặc OpenTelemetry resource, tránh khai báo các giá trị mâu thuẫn giữa metrics và traces. Một service có nhiều tên khác nhau trong hai tín hiệu sẽ làm dashboard và truy vấn liên kết khó hơn.

Một số collector hoặc backend yêu cầu header để xác thực, ví dụ bearer token. Header là map nên cách truyền bằng biến môi trường phụ thuộc quy tắc bind map key. Có thể khai báo map trong cấu hình Spring và lấy secret qua placeholder:

```yaml
management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${OTLP_EXPORT_TOKEN}"
    tracing:
      headers:
        Authorization: "Bearer ${OTLP_EXPORT_TOKEN}"
```

Sau đó cấp `OTLP_EXPORT_TOKEN` từ secret manager, Kubernetes Secret hoặc cơ chế quản lý secret của nền tảng. Cấu hình header chỉ áp dụng khi exporter và phiên bản Spring Boot hỗ trợ property đó. Không ghi token trực tiếp vào Docker image, Git, manifest công khai, command line hoặc log khởi động. Cũng cần bảo đảm TLS khi gửi credential qua network.

## 6. Cấu hình trong Docker Compose

Trong Docker Compose, có thể khai báo các environment variables tại service ứng dụng:

```yaml
services:
  orders-api:
    image: example/orders-api:1.0.0
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SPRING_APPLICATION_NAME: "orders-api"
      MANAGEMENT_OTLP_METRICS_EXPORT_URL: "http://otel-collector:4318/v1/metrics"
      MANAGEMENT_OTLP_METRICS_EXPORT_STEP: "30s"
      MANAGEMENT_OTLP_TRACING_ENDPOINT: "http://otel-collector:4318/v1/traces"
      MANAGEMENT_TRACING_SAMPLING_PROBABILITY: "0.10"
    depends_on:
      - otel-collector

  otel-collector:
    image: otel/opentelemetry-collector:latest
```

Đây là đoạn minh họa phần kết nối từ ứng dụng; collector vẫn cần cấu hình receiver, processor và exporter phù hợp với backend. `depends_on` điều khiển thứ tự khởi động container ở mức cơ bản, không bảo đảm collector đã sẵn sàng nhận telemetry. Ứng dụng cần có retry hoặc xử lý lỗi export phù hợp khi collector chưa sẵn sàng.

Không nên sử dụng tag `latest` cố định cho production. Hãy pin phiên bản image đã được kiểm thử và quản lý nâng cấp có chủ đích. Nếu có token, đưa token vào secret của Docker hoặc nền tảng triển khai, không đặt giá trị thật trong file Compose được commit.

## 7. Cấu hình trong Kubernetes

Trong Kubernetes, environment variables thường lấy từ `ConfigMap` cho cấu hình không nhạy cảm và `Secret` cho credential. Ví dụ Deployment rút gọn:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: example/orders-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: SPRING_APPLICATION_NAME
              value: "orders-api"
            - name: MANAGEMENT_OTLP_METRICS_EXPORT_URL
              value: "http://otel-collector.observability.svc:4318/v1/metrics"
            - name: MANAGEMENT_OTLP_METRICS_EXPORT_STEP
              value: "30s"
            - name: MANAGEMENT_OTLP_TRACING_ENDPOINT
              value: "http://otel-collector.observability.svc:4318/v1/traces"
            - name: MANAGEMENT_TRACING_SAMPLING_PROBABILITY
              value: "0.10"
            - name: OTLP_EXPORT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: otel-export-credentials
                  key: token
```

Trong ví dụ, biến `OTLP_EXPORT_TOKEN` được lấy từ Secret; cấu hình header trong `application.yml` có thể tham chiếu biến này như phần trước. Tên DNS `otel-collector.observability.svc` chỉ là ví dụ, cần thay bằng service name và namespace thực tế. NetworkPolicy, service port, TLS và authentication phải cho phép kết nối từ workload ứng dụng đến collector.

Thay đổi environment variables trong Pod template làm Kubernetes tạo Pod mới trong rollout. Sau khi cập nhật, kiểm tra rollout và log của các Pod mới. Nếu Secret được mount dưới dạng volume, ứng dụng có thể cần cơ chế reload hoặc restart tùy cách đọc cấu hình; không giả định mọi thay đổi secret đều tự cập nhật vào cấu hình đang chạy.

## 8. Cấu hình Prometheus exporter theo mô hình scrape

Nếu dùng Prometheus thay vì OTLP cho metrics, thêm Prometheus registry tương ứng vào ứng dụng và expose endpoint `prometheus` qua web. Ví dụ cấu hình bằng environment variables:

```bash
export MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,prometheus
```

Prometheus server sau đó scrape URL dạng:

```text
http://orders-api:8080/actuator/prometheus
```

Endpoint phải được expose, service phải truy cập được từ Prometheus và quyền truy cập phải được bảo vệ theo mô hình mạng của môi trường. Không expose mọi Actuator endpoint chỉ để Prometheus scrape metrics. Nếu cần remote write tới backend tập trung, cấu hình remote write ở Prometheus server; ứng dụng Spring Boot vẫn cung cấp endpoint scrape.

Không nên bật đồng thời nhiều registry hoặc exporter chỉ vì có thể. Mỗi đường xuất làm tăng lưu lượng, số lượng cấu hình và khả năng tạo dữ liệu trùng. Chọn mô hình dựa trên kiến trúc telemetry: Prometheus scrape, OTLP push hoặc một chiến lược có chủ đích kết hợp cả hai.

## 9. Logs là một pipeline riêng

Metrics exporter và tracing exporter không tự động xuất logs. Spring Boot có thể đưa trace ID và span ID vào logging context khi tracing được tích hợp; ứng dụng vẫn cần một pipeline để thu thập và chuyển log tới nơi lưu trữ. Các cách triển khai thường gặp gồm:

- Agent hoặc collector đọc stdout/stderr của container rồi chuyển log đi.
- Logging appender tích hợp OpenTelemetry hoặc backend log tương ứng.
- Nền tảng logging của Kubernetes hoặc hạ tầng gom log tập trung.

Hãy chuẩn hóa timestamp, service identity và trace correlation fields trong log. Không ghi access token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm. Khi tìm một request, có thể dùng trace ID trong log để mở trace tương ứng; metrics cung cấp xu hướng tổng thể còn log cung cấp sự kiện cụ thể.

## 10. Thứ tự ưu tiên cấu hình và quản lý theo môi trường

Spring Boot kết hợp nhiều property source. Trong vận hành thông thường, environment variables có thể ghi đè giá trị trong file cấu hình; `SPRING_APPLICATION_JSON`, system properties và command-line arguments có thể có độ ưu tiên cao hơn tùy nguồn. Vì vậy, khi giá trị thực tế khác file `application.yml`, hãy kiểm tra toàn bộ nguồn cấu hình được nạp.

Một cách tổ chức dễ quản lý là:

- Đặt giá trị mặc định không nhạy cảm trong `application.yml`.
- Dùng profile như `prod` để chọn nhóm cấu hình phù hợp với môi trường.
- Cấp endpoint, chu kỳ export và sampling qua environment variables của workload.
- Cấp token và credential qua secret manager hoặc Secret, rồi tham chiếu bằng placeholder hoặc config tree.
- Giữ cùng service identity giữa metrics, traces và logs; chỉ thay thuộc tính môi trường khi triển khai sang môi trường khác.

Ví dụ, cùng một image có thể chạy ở staging và production với endpoint collector và sampling khác nhau. Không cần build lại image chỉ để thay địa chỉ exporter. Tuy vậy, hãy quản lý thay đổi cấu hình như một phần của release: review, triển khai, quan sát lỗi export và có phương án rollback.

## 11. Kiểm tra exporter sau khi triển khai

Không nên kết luận exporter hoạt động chỉ vì ứng dụng khởi động thành công. Hãy xác minh theo từng lớp.

**Bước 1 — Kiểm tra cấu hình runtime.** Xác nhận profile, endpoint, chu kỳ metrics và sampling đang được cấp đúng cho Pod hoặc container. Tránh công khai endpoint quản trị như `/actuator/env` chỉ để kiểm tra; nếu dùng endpoint này trong môi trường được bảo vệ, phải giới hạn quyền và không chia sẻ giá trị secret.

**Bước 2 — Kiểm tra kết nối tới collector.** Từ network của workload, xác nhận hostname phân giải được, port mở và TLS handshake thành công. Kiểm tra NetworkPolicy, service selector, port mapping, proxy và chứng thư nếu dùng HTTPS.

**Bước 3 — Kiểm tra lỗi exporter.** Đọc log ứng dụng và collector quanh thời điểm export. Tìm lỗi timeout, connection refused, DNS failure, HTTP 401/403, payload không hợp lệ hoặc receiver chưa được bật. Không ghi token hoặc header xác thực vào output chẩn đoán.

**Bước 4 — Kiểm tra metrics tại nguồn.** Nếu dùng Prometheus registry, gọi endpoint scrape:

```bash
curl -i http://localhost:8080/actuator/prometheus
```

Nếu dùng OTLP, endpoint `/actuator/prometheus` chỉ hữu ích khi ứng dụng cũng có Prometheus registry. OTLP exporter thường gửi dữ liệu theo chu kỳ đến collector; kiểm tra receiver/exporter log hoặc metrics của collector để xác nhận dữ liệu đến nơi.

**Bước 5 — Kiểm tra traces.** Tạo một request thử có trace context hoặc để ứng dụng sinh trace theo cấu hình. Tìm trace trong backend theo service name và khoảng thời gian. Nếu không thấy trace, kiểm tra sampling probability, tracing bridge, OTLP endpoint, propagation và collector pipeline.

**Bước 6 — Kiểm tra liên kết tín hiệu.** Chọn một request và xác nhận service name, environment, timestamp và trace ID có thể đối chiếu giữa log và trace. So sánh metrics theo route/status với thời điểm request. Chú ý rằng sampling có thể khiến một request không có trace trong backend dù metrics và logs vẫn có dữ liệu.

## 12. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Metrics hoặc traces không xuất hiện | Thiếu registry, tracing bridge hoặc exporter dependency; auto-configuration không được kích hoạt. | Kiểm tra dependency và điều kiện auto-configuration của đúng phiên bản Spring Boot. |
| `Connection refused` | Collector chưa chạy, sai port hoặc receiver chưa listen trên interface phù hợp. | Kiểm tra trạng thái collector, receiver và service port. |
| `UnknownHostException` hoặc DNS failure | Hostname sai hoặc workload không cùng network/service discovery. | Kiểm tra DNS từ trong container/Pod và tên service. |
| HTTP `401` hoặc `403` | Token thiếu, hết hạn hoặc không có quyền ingest. | Kiểm tra secret, header, audience/scope và chính sách backend. |
| HTTP `404` | Sai path, ví dụ thiếu `/v1/metrics` hoặc `/v1/traces`, hoặc receiver route khác. | Đối chiếu endpoint OTLP/HTTP và cấu hình receiver của collector. |
| Timeout khi export | Network chậm, collector quá tải, timeout thấp hoặc backend không phản hồi. | Kiểm tra latency, queue, retry, resource của collector và timeout. |
| Metrics đến nhưng traces không đến | Tracing bridge/exporter chưa cấu hình, sampling thấp hoặc pipeline traces của collector thiếu. | Kiểm tra sampling, tracing endpoint và receiver/processor/exporter traces. |
| Traces đến nhưng thiếu liên kết log | Logging pattern chưa đưa trace/span ID vào MDC hoặc log pipeline làm mất field. | Kiểm tra logging integration, format và parser của log collector. |
| Dữ liệu bị chia thành nhiều service | `service.name` hoặc resource attributes không nhất quán. | Chuẩn hóa service identity giữa các tín hiệu và môi trường. |
| Cardinality metrics tăng nhanh | Tag chứa ID hoặc giá trị biến thiên cao. | Dùng route template và tag có tập giá trị giới hạn; chuyển định danh request sang logs/traces. |

Một HTTP GET tới endpoint OTLP không phải phép thử hợp lệ cho export vì receiver thường chờ request POST theo giao thức OTLP. Hãy kiểm tra từ log exporter, log/metrics của collector hoặc backend nhận telemetry. Tương tự, việc endpoint Actuator trả 200 chỉ chứng minh endpoint đó phản hồi, không chứng minh collector đã nhận dữ liệu.

## 13. Checklist vận hành

- [ ] Đã xác nhận dependency exporter và phiên bản Spring Boot/Micrometer tương thích.
- [ ] Đã dùng đúng tên environment variable theo relaxed binding.
- [ ] Đã kiểm tra URL OTLP, protocol, port và path `/v1/metrics` hoặc `/v1/traces`.
- [ ] Đã chọn chu kỳ metrics và sampling phù hợp với lưu lượng cùng chi phí.
- [ ] Đã giữ service identity nhất quán giữa metrics, traces và logs.
- [ ] Đã cấp credential qua secret manager hoặc cơ chế secret của nền tảng.
- [ ] Đã xác nhận workload có thể phân giải DNS và kết nối tới collector.
- [ ] Đã kiểm tra log exporter và collector sau khi triển khai.
- [ ] Đã xác nhận dữ liệu thực sự xuất hiện ở backend nhận telemetry.
- [ ] Đã giới hạn Actuator endpoint được expose và bảo vệ endpoint quản trị.

Khi cấu hình exporter bằng environment, một image ứng dụng có thể được triển khai ở nhiều môi trường với endpoint, chu kỳ export, sampling và credential riêng. Việc kiểm tra cần đi xuyên suốt từ property đã bind, kết nối mạng, exporter, collector đến backend. Khi metrics, traces và logs dùng cùng service identity và có thể liên kết bằng timestamp cùng trace context, đội vận hành có thể điều tra độ trễ và lỗi production dựa trên các tín hiệu nhất quán.
