# Xử lý mất kết nối tới hệ thống quan sát

## 1. Bối cảnh: trace không đến backend có nghĩa là gì?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, một request có thể đi qua module **order**, **payment**, sau đó phát sự kiện để module **notification** xử lý bất đồng bộ. Micrometer Observation và tracing tạo spans mô tả các tương tác đó; exporter chuyển spans tới **Zipkin**, **OpenTelemetry Collector** hoặc nền tảng APM. Khi hệ thống quan sát mất kết nối, trace có thể không xuất hiện trong giao diện dù nghiệp vụ vẫn chạy bình thường.

Bài thuộc chương **Export traces** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Phạm vi module học là dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác khi ứng dụng vận hành, gồm module graph, Actuator, event metrics, tracing và context propagation. Bài này tập trung vào **xử lý mất kết nối tới hệ thống quan sát**: xác định điểm đứt trong pipeline, hiểu retry và queue, giảm nguy cơ mất spans, khôi phục sau outage và kiểm chứng bằng dữ liệu vận hành.

Sau bài học, bạn có thể:

1. Phân biệt lỗi ở ứng dụng/exporter, Collector, mạng và tracing backend.
2. Giải thích sampling, batch processor, queue, timeout và retry ảnh hưởng tới khả năng nhìn thấy trace ra sao.
3. Cấu hình endpoint OTLP/Zipkin đúng protocol, path, TLS và authentication.
4. Bổ sung retry, sending queue và persistent storage cho OpenTelemetry Collector.
5. Theo dõi queue, số lần gửi lỗi, lượng spans bị drop và thời gian phục hồi.
6. Phân biệt **mất telemetry** với **lỗi nghiệp vụ**, đặc biệt khi listener của Spring Modulith xử lý bất đồng bộ.

## 2. Xác định pipeline trước khi sửa lỗi

Một luồng export thường có một hoặc nhiều chặng:

~~~mermaid
flowchart LR
    App["Spring Boot + Micrometer Tracing"] --> SDK["Tracer / Span Processor"]
    SDK -->|OTLP hoặc Zipkin| Agent["Collector Agent / Sidecar"]
    Agent -->|OTLP / message queue| Gateway["Collector Gateway"]
    Gateway -->|OTLP / vendor protocol| Backend["Trace backend"]
    Backend --> UI["Trace search / dashboard"]
~~~

Nếu ứng dụng xuất thẳng đến backend, chặng Agent/Gateway có thể không tồn tại. Nếu dùng Collector, cần kiểm tra cả hai phía: **ứng dụng → Collector** và **Collector → backend**. Một Collector có thể nhận spans thành công nhưng không gửi tiếp được; khi đó lỗi nằm ở exporter downstream, không phải instrumentation trong ứng dụng.

| Lớp | Trách nhiệm | Dấu hiệu lỗi |
| --- | --- | --- |
| **Instrumentation** | Tạo Observation/span từ HTTP, database, module API hoặc event listener. | Không có span ngay từ đầu; thiếu module attributes. |
| **Sampling** | Quyết định trace/span nào được ghi nhận. | Chỉ một tỷ lệ request có trace; không thấy trace của request không được sample. |
| **Span processor** | Gom spans, xếp hàng và chuyển batch cho exporter. | Queue đầy, drop span, shutdown chưa flush. |
| **Exporter trong ứng dụng** | Gửi batch đến Zipkin hoặc OTLP receiver. | Timeout, DNS, connection refused, TLS/auth hoặc lỗi HTTP/gRPC. |
| **Collector receiver** | Nhận telemetry từ ứng dụng/agent. | Receiver không lắng nghe, sai port/protocol, reject payload. |
| **Collector processor/exporter** | Batch, retry, queue và chuyển spans tới backend. | Queue tăng, exporter send failed, queue overflow. |
| **Backend** | Ingest, lưu trữ, index và truy vấn trace. | Nhận dữ liệu nhưng không tìm thấy trong UI, sai service/time range hoặc lỗi ingest. |

**Không bắt đầu bằng việc sửa code nghiệp vụ.** Trước hết xác định spans đã được tạo chưa, có được sample không, đã được đưa vào queue chưa và request export đã đi đến hop nào.

## 3. Phân biệt mất kết nối với sampling hoặc thiếu instrumentation

Không phải mọi trace không xuất hiện đều do network outage. Spring Boot mặc định chỉ sample khoảng **10% request** để hạn chế tải lên trace backend. Nếu đang kiểm tra một request đơn lẻ, request đó có thể không được sample.

Các trường hợp thường gặp:

- **Không có span:** kiểm tra instrumentation, observation registry, điều kiện module detection và sampling.
- **Có traceId trong log nhưng không thấy trace trong backend:** kiểm tra sampler, span processor, exporter, collector và backend. Correlation ID trong log không tự chứng minh trace đã được export.
- **Có trace HTTP nhưng thiếu module span:** kiểm tra Spring Modulith observability và điểm gọi qua public module API; đây có thể là vấn đề instrumentation chứ không phải mất kết nối.
- **Có một số trace, thiếu trace khác:** kiểm tra sampling, queue overflow, exporter errors và thời gian lưu/index.
- **Trace xuất hiện trễ:** exporter hoặc Collector có thể đang retry và backlog chưa được drain hết.

Trong môi trường lab, có thể tạm tăng sampling lên 100% để loại trừ yếu tố sampling:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Chỉ dùng cấu hình này trong kiểm thử có kiểm soát. Trên production, 100% sampling có thể làm tăng đáng kể lưu lượng, chi phí ingest và dung lượng lưu trữ. Sau khi kiểm tra xong, khôi phục sampling phù hợp với tải và mục tiêu quan sát.

## 4. Chẩn đoán điểm đứt theo thứ tự

~~~mermaid
flowchart TD
    A["Không thấy trace trong UI"] --> B{"Request có được sample và tạo span?"}
    B -->|Không| C["Kiểm tra sampler / instrumentation"]
    B -->|Có| D{"Span processor có nhận span?"}
    D -->|Không| E["Kiểm tra lifecycle Observation và span processor"]
    D -->|Có| F{"Exporter ứng dụng gửi được?"}
    F -->|Không| G["Kiểm tra endpoint, DNS, port, TLS, auth, timeout"]
    F -->|Có| H{"Collector có nhận dữ liệu?"}
    H -->|Không| I["Kiểm tra receiver, protocol, firewall và logs"]
    H -->|Có| J{"Collector gửi đến backend thành công?"}
    J -->|Không| K["Kiểm tra exporter queue, retry, backend và credentials"]
    J -->|Có| L["Kiểm tra ingest, service name, retention, time range và query"]
~~~

Thực hiện từng bước với **một request có mã tương quan xác định**. Ghi lại thời điểm, `traceId`, `spanId`, `eventId` nếu có, service name và phiên bản ứng dụng. Khi có Collector, so sánh log/metrics ở receiver với exporter để biết dữ liệu dừng ở phía nào.

## 5. Kiểm tra cấu hình endpoint, protocol và mạng

### 5.1. OTLP/HTTP và OTLP/gRPC không dùng cùng URL

| Đường truyền | Endpoint ví dụ | Ghi nhớ |
| --- | --- | --- |
| **OTLP/HTTP traces** | `http://otel-collector:4318/v1/traces` | HTTP/protobuf, có path `/v1/traces`. |
| **OTLP/gRPC** | `otel-collector:4317` | gRPC, không gắn path HTTP `/v1/traces`. |
| **Zipkin v2 HTTP API** | `http://zipkin:9411/api/v2/spans` | Giao thức Zipkin, không phải OTLP. |
| **Zipkin UI** | `http://zipkin:9411` | Giao diện truy vấn; không phải endpoint nhận spans. |

Một lỗi phổ biến là gửi OTLP/HTTP vào port gRPC hoặc dùng URL giao diện Zipkin thay cho API `/api/v2/spans`. Khi nhận HTTP 404, 415, lỗi protocol hoặc gRPC status không tương thích, xác minh lại **exporter type, transport, port và path** trước.

### 5.2. localhost trong container không phải host máy phát triển

`localhost` luôn trỏ đến network namespace của process đang chạy. Nếu Spring Boot ở container A và Collector ở container B, cấu hình `http://localhost:4318` trong ứng dụng sẽ gọi lại container A. Trên Docker Compose, dùng service name trên network chung; trong Kubernetes, dùng DNS service nội bộ hoặc địa chỉ đã được cấp.

### 5.3. Kiểm tra DNS, TCP và TLS

Một thứ tự kiểm tra thực tế:

1. Xác nhận hostname resolve đúng từ **môi trường chạy ứng dụng/Collector**, không chỉ từ laptop.
2. Kiểm tra route, firewall, NetworkPolicy, security group và port listener.
3. Xác minh TLS handshake, certificate chain, hostname/SAN, CA trust và thời hạn chứng chỉ.
4. Kiểm tra proxy, service mesh hoặc ingress có rewrite path, chặn gRPC hay áp timeout riêng không.
5. Xác minh server nhận đúng protocol và phiên bản OTLP/Zipkin.

Nếu dùng HTTPS, không hạ kiểm tra certificate để “làm cho chạy” trên production. Sửa CA bundle, SSL bundle hoặc certificate chain đúng môi trường.

### 5.4. Authentication và giới hạn tài nguyên

Backend/Collector có thể yêu cầu header token, API key, mTLS hoặc OAuth. Kiểm tra secret được mount đúng, header được truyền đến đúng hop và token còn hiệu lực. Không đưa token vào URL, source code hoặc log lỗi.

Ngoài kết nối, kiểm tra response **429/RESOURCE_EXHAUSTED**, rate limit, quota ingest và payload quá lớn. Một endpoint vẫn mở TCP nhưng liên tục từ chối payload do quota cũng khiến trace không xuất hiện.

## 6. Cấu hình Spring Boot xuất trace

Spring Boot hỗ trợ Micrometer Tracing với **OpenTelemetry + OTLP** hoặc **Brave + Zipkin**. Dependency và property khác nhau theo dòng phiên bản; luôn dùng BOM phù hợp với dự án.

### 6.1. Spring Boot 3.5: OpenTelemetry + OTLP

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Trên Spring Boot 3.5, nhóm property là `management.otlp.tracing.*`. Nếu ứng dụng chạy trong container, thay hostname bằng tên service/địa chỉ có thể truy cập từ container đó.

### 6.2. Spring Boot 4.2: OpenTelemetry + OTLP

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
          timeout: 10s
          transport: http
~~~

Ở Spring Boot 4.2, property nằm dưới `management.opentelemetry.tracing.export.otlp.*`. Không copy `management.otlp.tracing.endpoint` của Boot 3.x sang Boot 4.x mà không kiểm tra metadata cấu hình.

### 6.3. Spring Boot 3.5: gửi trực tiếp Zipkin

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

### 6.4. Spring Boot 4.2: gửi trực tiếp Zipkin bằng Brave

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-zipkin'
}
~~~

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
    export:
      zipkin:
        endpoint: http://zipkin:9411/api/v2/spans
        connect-timeout: 1s
        read-timeout: 10s
~~~

Các ví dụ chỉ minh họa cách chọn một tracer/exporter phù hợp. Không cấu hình đồng thời nhiều exporter trùng mục đích nếu chưa có kế hoạch nhân bản telemetry và kiểm soát chi phí. Nếu cần tùy chỉnh exporter OTLP sâu hơn trên Boot 4.x, có thể dùng `OtlpHttpSpanExporterBuilderCustomizer` hoặc `OtlpGrpcSpanExporterBuilderCustomizer` theo tài liệu phiên bản.

### 6.5. Xác minh bằng Actuator và logs

Nếu đã expose các endpoint cần thiết và có quyền truy cập:

~~~bash
curl -fsS http://localhost:8080/actuator/health
curl -fsS http://localhost:8080/actuator/metrics
~~~

Health cho biết tình trạng các health contributors đã cấu hình; nó **không mặc định chứng minh exporter đã gửi trace thành công**. Tìm logs của exporter/Collector để biết lỗi DNS, timeout, TLS hoặc response code. Với Micrometer Tracing, Spring Boot đưa `traceId` và `spanId` vào logging correlation mặc định khi tracing được cấu hình.

## 7. Retry ở OTLP exporter: có giới hạn và có phân loại lỗi

Theo đặc tả OTLP, exporter phải retry **transient errors** bằng chiến lược **exponential backoff có jitter**. Thời gian chờ và từng lần gửi đều phải nằm trong thời hạn export còn lại. Khi hết timeout/deadline, exporter dừng thử lại và trả kết quả thất bại.

Điều này có ba ý nghĩa:

1. Retry không kéo dài vô hạn; một outage đủ lâu vẫn có thể làm mất batch.
2. Không nên retry mọi lỗi như nhau. Lỗi tạm thời (ví dụ backend unavailable hoặc timeout) khác lỗi cấu hình/permanent (ví dụ endpoint sai path, payload không hợp lệ, authentication bị từ chối).
3. Backoff và jitter tránh việc hàng nghìn ứng dụng cùng retry đồng thời, tạo thêm tải đúng lúc backend đang phục hồi.

### Timeout của exporter khác timeout của request nghiệp vụ

Timeout export áp dụng cho việc gửi telemetry, không phải thời gian chờ của HTTP request nghiệp vụ trong mọi cấu hình. Với batch span processor, spans thường được gửi ở luồng nền. Tuy nhiên, việc gọi `forceFlush()`/shutdown hoặc dùng exporter/processor đồng bộ tùy biến có thể tạo thêm thời gian chờ khi kết thúc ứng dụng. Không nên chặn mỗi request nghiệp vụ để đợi trace backend phản hồi.

### Batch processor có queue hữu hạn

OpenTelemetry SDK thường dùng **BatchSpanProcessor** để gom spans trước khi export. Các giá trị mặc định được đặc tả cho SDK phổ biến gồm:

| Tham số | Giá trị mặc định thường gặp | Ý nghĩa |
| --- | ---: | --- |
| `maxQueueSize` | 2048 spans | Số spans có thể chờ trong queue. |
| `maxExportBatchSize` | 512 spans | Số spans tối đa trong một batch. |
| `scheduledDelayMillis` | 5000 ms | Khoảng chờ tối đa trước một lần export tiếp theo. |
| `exportTimeoutMillis` | 30000 ms | Thời gian tối đa cho một lần export. |

Đây là giá trị mặc định trong đặc tả/SDK tham chiếu, không phải cam kết mọi bridge hoặc cấu hình Spring Boot đều có đúng các giá trị ấy. Khi queue đầy, SDK có thể **drop spans mới** để bảo vệ ứng dụng. Kiểm tra cấu hình và telemetry của SDK đang dùng trước khi điều chỉnh.

**Không tăng queue vô hạn.** Queue lớn hơn giúp hấp thụ burst/outage ngắn nhưng tốn heap, làm tăng thời gian drain và không giải quyết được backend không thể phục hồi. Nếu cần giữ dữ liệu qua restart hoặc outage dài, hãy cân nhắc Collector với persistent queue hoặc message broker thay vì chỉ tăng queue trong JVM.

## 8. Làm Collector chịu lỗi tốt hơn

Collector có thể nhận spans từ ứng dụng rồi gửi tiếp đến backend. Exporter của Collector hỗ trợ **sending queue**, **retry_on_failure**, timeout và batch. Queue mặc định thường là in-memory; khi Collector restart/crash, dữ liệu chưa gửi trong RAM có thể mất.

### 8.1. Cấu hình retry và sending queue

Ví dụ cấu hình Collector dùng OTLP exporter:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  otlp:
    endpoint: trace-backend.internal:4317
    tls:
      insecure: false
    sending_queue:
      enabled: true
      queue_size: 5000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp]
~~~

Đây là **khung minh họa**, cần xác nhận exporter component, TLS/auth và schema theo phiên bản Collector đang triển khai. `queue_size` là số đơn vị queue theo cấu hình exporter/implementation, không nên tự đổi thành “số spans” nếu exporter đang queue theo batches/requests. Tăng queue cần tính dung lượng RAM, tốc độ ingest và thời gian outage có thể chấp nhận.

### 8.2. Persistent queue bằng file_storage

Nếu Collector restart trong lúc backend chưa kết nối được, queue chỉ nằm trong RAM sẽ mất khi process dừng. Với Collector quan trọng, có thể dùng `file_storage` để queue ghi dữ liệu ra write-ahead log (WAL):

~~~yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/storage

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  otlp:
    endpoint: trace-backend.internal:4317
    sending_queue:
      enabled: true
      storage: file_storage
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m

service:
  extensions: [file_storage]
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp]
~~~

Đường dẫn WAL phải nằm trên **persistent volume** có dung lượng, quyền truy cập và chính sách backup phù hợp. `file_storage` giúp queue tồn tại qua restart Collector; nó không bảo đảm chống mất dữ liệu khi disk hỏng/đầy hoặc khi retry đã hết thời hạn. Cấu hình thực tế cần kiểm tra đúng storage extension version và lifecycle.

### 8.3. Khi nào cần message queue?

Với các hop quan trọng giữa Agent/Gateway hoặc giữa hạ tầng và vendor backend, một message queue như Kafka có thể tách rời vòng đời producer và consumer. Queue giúp lưu backlog theo retention và cho phép consumer xử lý lại sau khi phục hồi, nhưng thêm vận hành: cluster, topic, replication, retention, consumer offsets và xử lý lỗi của chính message broker. Không cần thêm Kafka chỉ để sửa một lỗi DNS ngắn; chọn mức bền vững theo yêu cầu mất dữ liệu và độ phức tạp chấp nhận được.

### So sánh các mức buffer

| Cơ chế | Giữ dữ liệu khi backend tạm mất kết nối? | Qua restart process? | Giới hạn |
| --- | --- | --- | --- |
| **SDK BatchSpanProcessor queue** | Có thể giữ batch ngắn hạn trong bộ nhớ. | Thường không. | Queue hữu hạn, spans có thể bị drop khi đầy hoặc export thất bại. |
| **Collector in-memory sending queue** | Có, trong thời gian retry và khi còn dung lượng. | Không. | Queue overflow, hết thời hạn retry hoặc Collector restart có thể mất dữ liệu. |
| **Collector file_storage/WAL** | Có. | Có, nếu persistent volume còn nguyên và cấu hình đúng. | Disk failure/overflow và retry expiry vẫn có thể gây mất dữ liệu. |
| **Message queue chuyên dụng** | Có, theo retention/replication của broker. | Thường có. | Thêm thành phần vận hành và vẫn cần xử lý broker outage/retention. |

Không cơ chế nào biến tracing thành hệ thống lưu trữ giao dịch. Tracing là telemetry có thể sample và drop; nếu cần bảo đảm nghiệp vụ, dùng outbox/event store hoặc cơ chế persistence dành riêng cho nghiệp vụ.

## 9. Theo dõi sức khỏe của pipeline export

Một hệ thống quan sát cần quan sát chính nó. Với Collector, theo dõi các metrics exporter/queue (tên metric có thể thay đổi theo phiên bản và mức telemetry):

| Metric thường gặp | Ý nghĩa | Cảnh báo gợi ý |
| --- | --- | --- |
| `otelcol_exporter_queue_size` | Số phần tử đang chờ gửi. | Tăng liên tục hoặc tiến sát capacity. |
| `otelcol_exporter_queue_capacity` | Sức chứa queue. | Queue thường xuyên gần đầy. |
| `otelcol_exporter_send_failed_spans` | Số spans gửi thất bại ở exporter. | Tăng liên tục trong một khoảng thời gian. |
| `otelcol_exporter_enqueue_failed_spans` | Số spans không được enqueue thành công, nếu metric được phát. | Bất kỳ mức tăng bất thường nào. |
| `otelcol_exporter_in_flight_requests` | Request export đang chạy hoặc chờ retry, tùy phiên bản. | Số lượng lớn kéo dài. |

Không hardcode tên metric mà chưa kiểm tra `/metrics` của Collector hiện tại; một số metric chỉ có ở mức telemetry chi tiết hoặc khác giữa các bản phân phối. Cần theo dõi thêm logs của exporter và receiver.

### Dashboard nên có

- **Export success/failure rate** theo exporter và signal.
- **Queue size / capacity** và xu hướng backlog.
- **Oldest queued batch age** nếu có metric hoặc custom instrumentation.
- **Retry duration**, request latency và timeout.
- **Dropped spans / enqueue failures**.
- **Backend ingest rate** so với app span creation rate.
- **Collector restarts**, disk usage của WAL và lỗi storage.

Đặt cảnh báo theo xu hướng và mức gần đầy, không chỉ theo một lần lỗi đơn lẻ. Một lỗi gửi ngắn có thể tự phục hồi; queue tăng liên tục là dấu hiệu hệ thống đang tích lũy dữ liệu nhanh hơn khả năng drain.

## 10. Quy trình xử lý outage từng bước

### Bước 1 — Xác nhận phạm vi ảnh hưởng

Xác định backend hay Collector đang mất kết nối, bao nhiêu service/instance bị ảnh hưởng, bắt đầu từ thời điểm nào và trace nào bị thiếu. Kiểm tra dashboard health của backend và Collector; đối chiếu deployment, certificate rotation, firewall, DNS hoặc thay đổi secret gần thời điểm xảy ra sự cố.

### Bước 2 — Xác nhận ứng dụng còn tạo spans

Gửi một request thử nghiệm có thể nhận diện. Kiểm tra log có `traceId`/`spanId`, module attributes hoặc Observation phù hợp. Nếu không có, kiểm tra instrumentation và sampling trước khi điều tra exporter. Spring Boot mặc định sample khoảng 10%; trace không được sample sẽ không có batch để export.

### Bước 3 — Kiểm tra hop đầu tiên

Nếu ứng dụng gửi trực tiếp, xác minh exporter endpoint, port, protocol, DNS, TLS, authentication và timeout. Nếu gửi đến Collector, kiểm tra receiver logs/metrics, listener port và request status. Không dùng giao diện UI backend để kết luận Collector không nhận dữ liệu.

### Bước 4 — Kiểm tra queue và retry

Nếu Collector đã nhận spans nhưng backend không nhận, xem `queue_size`, `queue_capacity`, send failures và retry logs. Xác định queue còn chỗ không, retry còn trong thời hạn không, WAL có ghi được không và backend đang rate-limit hay từ chối payload.

### Bước 5 — Giảm áp lực có kiểm soát

Nếu queue tiến sát capacity, xử lý nguyên nhân downstream và cân nhắc giảm tải telemetry tạm thời theo chính sách. Có thể điều chỉnh sampling hoặc lọc spans ít giá trị trong một khoảng ngắn, nhưng phải ghi nhận rõ phạm vi và thời điểm để không tạo khoảng mù khó giải thích. Không tắt toàn bộ tracing lâu dài chỉ để giảm áp lực mà không có phương án thay thế.

### Bước 6 — Khôi phục và theo dõi drain

Sau khi endpoint phục hồi, theo dõi queue giảm, exporter failures ngừng tăng và backend ingest trở lại. Backlog có thể khiến trace xuất hiện trễ so với thời điểm request. Kiểm tra time range theo timestamp của span, không chỉ theo thời điểm dữ liệu được ingest.

### Bước 7 — Đánh giá dữ liệu bị mất

Đối chiếu thời gian outage với queue capacity, retry expiry, Collector restarts, WAL/disk và SDK dropped spans. Xác định phần nào còn được giữ, phần nào đã drop và liệu cần điều tra thêm từ application logs, event registry hoặc audit logs. Không khẳng định khôi phục được mọi trace nếu buffer đã overflow hoặc SDK đã drop batch.

## 11. Phân loại lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Connection refused` | Không có receiver lắng nghe, sai port hoặc service chưa ready. | Kiểm tra process, service discovery, port 4317/4318/9411 và protocol. |
| `UnknownHostException` / DNS failure | Hostname sai hoặc DNS/network namespace không resolve được. | Resolve từ đúng container/Pod; kiểm tra DNS service và search domain. |
| TLS handshake/certificate error | CA không được trust, cert hết hạn, hostname mismatch hoặc mTLS thiếu client cert. | Cập nhật trust chain/SSL bundle và cấu hình certificate đúng. |
| HTTP 401/403 | Token/API key thiếu, hết hạn hoặc không có quyền ingest. | Kiểm tra secret, auth header, role và policy gateway. |
| HTTP 404 | Sai path hoặc gửi nhầm protocol/receiver. | Kiểm tra `/v1/traces` của OTLP/HTTP hoặc `/api/v2/spans` của Zipkin. |
| HTTP 415 / decode error | Content type/encoding không đúng hoặc server không hỗ trợ payload. | Kiểm tra exporter, transport, protobuf/JSON và phiên bản. |
| HTTP 429 / gRPC resource exhausted | Backend throttling hoặc quota vượt mức. | Giảm tải, điều chỉnh batch/concurrency theo hướng dẫn backend và retry có backoff. |
| HTTP 5xx / gRPC unavailable | Backend tạm lỗi hoặc quá tải. | Retry có giới hạn, queue, kiểm tra backend capacity. |
| Queue tăng liên tục | Exporter không drain nhanh bằng tốc độ nhận. | Kiểm tra downstream latency, retry, consumer count, network và quota. |
| Queue đầy, spans drop | Outage kéo dài hoặc capacity không đủ. | Khôi phục backend, tăng buffer có tính toán, persistent queue nếu cần. |
| Collector restart làm mất backlog | Queue chỉ lưu trong RAM. | Cấu hình file_storage/WAL và persistent volume. |
| Trace chỉ thiếu một tỷ lệ | Sampling hoặc queue drop/export failure. | Kiểm tra sampler và dropped counters trước khi sửa instrumentation. |
| Trace có nhưng thiếu module spans | Module instrumentation hoặc context boundary không đúng. | Kiểm tra Spring Modulith Insight, module API và context propagation. |
| Trace đến muộn | Queue retry/backlog đang drain. | Kiểm tra ingest timestamp và span timestamp; chờ backlog giảm. |
| Backend ingest thành công nhưng UI không thấy | Sai service name/time range, retention, index hoặc query filter. | Tìm theo traceId, mở rộng time range và kiểm tra resource attributes. |

## 12. Phân biệt mất trace với lỗi xử lý event của Spring Modulith

Đây là điểm quan trọng khi module giao tiếp qua domain event. Giả sử **order** commit đơn và phát `OrderPlaced`; module **notification** xử lý bằng `@ApplicationModuleListener`. Nếu trace backend mất kết nối:

- Giao dịch đặt hàng vẫn có thể commit.
- Listener vẫn có thể chạy và ghi dữ liệu thông báo.
- Span của listener có thể nằm trong SDK queue, Collector queue hoặc bị drop.
- Event Publication Registry (nếu được cấu hình) vẫn theo dõi publication lifecycle độc lập với tracing exporter.

**Không dùng “không thấy trace” làm bằng chứng listener không chạy.** Hãy kiểm tra:

1. Trạng thái nghiệp vụ của đơn hàng.
2. Log publisher và consumer có cùng `eventId` hay không.
3. Event Publication Registry có publication đang chờ/FAILED/COMPLETED theo trạng thái của phiên bản đang dùng không.
4. Metrics listener và downstream notification có phản ánh xử lý không.
5. Pipeline trace có queue/drop/export errors trong cùng khoảng thời gian không.

~~~mermaid
flowchart TD
    P["Order transaction commit"] --> E["OrderPlaced published"]
    E --> L["Notification listener"]
    L --> DB["Notification request saved"]
    L --> S["Listener span created"]
    S --> Q["SDK / Collector queue"]
    Q --> X{"Trace backend reachable?"}
    X -->|Có| B["Trace searchable"]
    X -->|Không| R["Retry / buffer / possible drop"]
    DB --> Outcome["Nghiệp vụ có thể hoàn tất dù trace mất"]
    R --> Outcome
~~~

Nếu listener thật sự thất bại, hãy xử lý bằng Event Publication Registry, retry policy và idempotency theo thiết kế Spring Modulith. Không phát lại nghiệp vụ chỉ để tạo lại trace; điều đó có thể gây side effect trùng.

## 13. Graceful degradation và chính sách mất dữ liệu

Tracing hỗ trợ chẩn đoán và đo lường, không phải nguồn dữ liệu giao dịch chính. Một ứng dụng nên tiếp tục xử lý nghiệp vụ khi trace backend tạm thời không sẵn sàng, trong giới hạn queue/timeout hợp lý.

Các nguyên tắc:

- Ưu tiên **batch/asynchronous export** thay vì gọi network đồng bộ trên mỗi request.
- Giữ queue có giới hạn để tránh memory growth vô hạn.
- Retry transient errors với exponential backoff và jitter; không retry lỗi cấu hình/permanent vô hạn.
- Không để lỗi exporter làm rollback transaction nghiệp vụ đã commit.
- Đặt timeout export có giới hạn, quan sát force-flush/shutdown và thời gian graceful termination.
- Với Collector gateway quan trọng, dùng persistent queue/WAL nếu yêu cầu phục hồi qua restart đủ cao.
- Nếu yêu cầu durability cao qua nhiều network hops, cân nhắc message queue chuyên dụng và chấp nhận độ phức tạp vận hành.
- Ghi nhận rõ telemetry đã bị drop trong outage; không tạo dữ liệu giả để lấp khoảng trống.

### Rủi ro khi dùng queue lớn

Queue lớn giúp hấp thụ burst nhưng:

- Tốn RAM hoặc disk và có thể gây áp lực lên node.
- Tăng thời gian từ span xảy ra đến lúc xuất hiện trong backend.
- Làm backlog drain lâu sau khi phục hồi.
- Không giải quyết được backend có throughput thấp hơn tốc độ tạo spans trong thời gian dài.

Ước lượng capacity bằng **tốc độ spans/batches × thời gian outage dự kiến × kích thước trung bình**, cộng headroom và giới hạn tài nguyên. Đo kích thước thực tế thay vì chỉ dựa vào số lượng span.

## 14. Kiểm thử outage có kiểm soát

Không đợi production mất kết nối mới biết queue hoạt động ra sao. Trong môi trường staging/lab, có thể mô phỏng từng loại lỗi:

### Thử nghiệm A — Collector không truy cập được

1. Khởi chạy ứng dụng với sampling cao trong lab và cấu hình OTLP tới Collector.
2. Chặn kết nối từ ứng dụng tới Collector trong một khoảng ngắn.
3. Gửi request mẫu, kiểm tra logs/exporter errors và xem queue/drop metrics nếu có.
4. Mở lại kết nối, quan sát việc export phục hồi.

Kết quả mong đợi phụ thuộc span processor và exporter: có thể giữ một lượng spans ngắn hạn trong queue; nếu queue đầy hoặc timeout hết hạn, dữ liệu có thể bị drop.

### Thử nghiệm B — Backend tắt, Collector vẫn chạy

1. Ứng dụng tiếp tục gửi đến Collector.
2. Tạm dừng backend trace.
3. Quan sát Collector `sending_queue`, retry và send-failed metrics.
4. Khởi động lại backend, kiểm tra queue drain và trace xuất hiện trễ.

### Thử nghiệm C — Restart Collector

So sánh hai cấu hình:

- Queue in-memory: restart Collector khi backlog tồn tại; dữ liệu chưa gửi trong RAM có thể mất.
- Queue dùng file_storage: restart Collector; dữ liệu trong WAL có thể được đọc lại nếu persistent volume còn nguyên và cấu hình đúng.

### Thử nghiệm D — Lỗi xác thực hoặc endpoint

Dùng token sai hoặc path sai trong lab. Xác nhận logs phân biệt lỗi auth/path với lỗi mạng, và không retry vô hạn các lỗi cấu hình không thể tự phục hồi. Sau khi sửa secret/endpoint, xác nhận export hoạt động.

### Thử nghiệm E — Kiểm tra nghiệp vụ độc lập

Trong lúc trace backend không truy cập được, tạo một đơn và để notification listener xử lý. Xác nhận dữ liệu nghiệp vụ/event registry/logs, rồi khôi phục trace backend. Bài test phải chứng minh **mất telemetry không đồng nghĩa mất event hoặc rollback nghiệp vụ**.

## 15. Checklist vận hành sau sự cố

- [ ] Xác định request/trace mẫu, thời điểm, service/version và các hop của pipeline.
- [ ] Kiểm tra sampling và xác nhận instrumentation có tạo spans.
- [ ] Xác minh đúng OTLP/HTTP, OTLP/gRPC hoặc Zipkin API, đúng port và path.
- [ ] Kiểm tra DNS, network policy, TLS, authentication, proxy và quota.
- [ ] Đối chiếu SDK/exporter logs với Collector receiver/exporter logs.
- [ ] Kiểm tra queue size, capacity, retry expiry, enqueue failures và dropped spans.
- [ ] Xác định queue là in-memory hay persistent; kiểm tra WAL volume/disk.
- [ ] Sau phục hồi, theo dõi backlog drain và backend ingest.
- [ ] Đối chiếu eventId, Event Publication Registry và dữ liệu nghiệp vụ nếu liên quan listener async.
- [ ] Ghi rõ khoảng thời gian telemetry bị mất và phần dữ liệu không thể phục hồi.
- [ ] Cập nhật alert/runbook để phát hiện queue growth trước khi overflow.

## 16. Nguyên tắc thiết kế để giảm tác động của outage

**Tách nghiệp vụ khỏi exporter.** Không gọi trace backend trực tiếp từ service nghiệp vụ; để Observation/tracer và batch exporter quản lý vòng đời telemetry.

**Đặt Collector gần nguồn nếu phù hợp.** Agent/sidecar có thể giảm số network hops từ ứng dụng, còn Gateway tập trung batch/retry/export. Chọn topology theo yêu cầu vận hành, tài nguyên và phạm vi outage.

**Quan sát pipeline độc lập.** Metrics/logs của Collector nên được gửi tới hệ thống giám sát có đường vận hành riêng hoặc có cảnh báo ngoài trace backend đang gặp sự cố. Nếu chỉ dùng chính trace backend để phát hiện nó không nhận trace, nhóm vận hành có thể không biết outage đã xảy ra.

**Thiết kế retry có giới hạn.** Retry nhanh vô hạn có thể khuếch đại outage và làm đầy queue. Dùng backoff, jitter, timeout và queue capacity theo tải thực tế.

**Giữ khả năng điều tra khi trace thiếu.** Dùng structured logs có `traceId` khi có, `eventId` cho luồng event, module name và mã lỗi. Logs và audit/event records có retention riêng, không phụ thuộc hoàn toàn vào tracing backend.

**Không kỳ vọng exactly-once từ trace export.** Batch có thể được retry, bị drop hoặc được ingest trễ. Trace là dữ liệu quan sát; nếu cần kiểm soát giao dịch và phát lại, dùng cơ chế nghiệp vụ như outbox, event store hoặc publication registry.

## 17. Tài liệu tham khảo chính thức

- **Spring Boot 3.5 — Tracing:** https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html — dependency, sampling, Zipkin/OTLP exporter và property của Boot 3.5.
- **Spring Boot 4.2 — Tracing:** https://docs.spring.io/spring-boot/reference/actuator/tracing.html — starter OpenTelemetry/Zipkin, property export, sampling và customizer exporter.
- **OpenTelemetry — OTLP Exporter Specification:** https://opentelemetry.io/docs/specs/otel/protocol/exporter/ — endpoint, timeout và retry transient errors.
- **OpenTelemetry Collector — Resiliency:** https://opentelemetry.io/docs/collector/resiliency/ — sending queue, retry, file_storage/WAL, message queue và tình huống mất dữ liệu.
- **OpenTelemetry Collector — Exporter Helper:** https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper — cấu hình queue, retry, batching và timeout của exporter.
- **OpenTelemetry — Trace SDK Specification:** https://opentelemetry.io/docs/specs/otel/trace/sdk/ — BatchSpanProcessor, queue, batch size và export scheduling.
- **Spring Modulith — Events:** https://docs.spring.io/spring-modulith/reference/events.html — Event Publication Registry và xử lý sự kiện trong module.

## 18. Tổng kết

Khi mất kết nối tới hệ thống quan sát, hãy tìm **hop đầu tiên bị đứt**: instrumentation/sampling, span processor, exporter trong ứng dụng, Collector receiver, Collector exporter hay backend ingest. OTLP exporter retry lỗi tạm thời bằng backoff có jitter nhưng có timeout; queue trong SDK và Collector đều có giới hạn. Collector có thể dùng sending queue, file_storage/WAL hoặc message broker để tăng khả năng chịu outage, nhưng vẫn phải tính đến queue overflow, disk failure và retry expiry.

Trong Spring Modulith, trace mất không có nghĩa event listener thất bại. Đối chiếu `eventId`, logs, event metrics, Event Publication Registry và trạng thái nghiệp vụ để phân biệt **mất telemetry** với **mất xử lý**. Một pipeline quan sát tốt cần có retry và buffer hợp lý, dashboard cho chính exporter/Collector, quy trình phục hồi và bằng chứng rõ ràng về khoảng dữ liệu đã bị mất.
