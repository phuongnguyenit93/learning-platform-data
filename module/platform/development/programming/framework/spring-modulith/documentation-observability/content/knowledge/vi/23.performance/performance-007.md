# Giới hạn queue telemetry

> **Chương:** Hiệu năng  
> **Module học tập:** SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Vì sao cần giới hạn queue telemetry?

Spring Modulith có thể instrument lời gọi vào application module và event listener để tạo observations, metrics hoặc spans. Ví dụ, request hoàn tất đơn hàng đi qua module order, inventory, payment và notification. Những spans này được đưa vào tracing pipeline để export tới OpenTelemetry Collector và trace backend.

Khi backend chậm hoặc mất kết nối, dữ liệu telemetry vẫn tiếp tục được tạo. Nếu mọi thành phần giữ dữ liệu vô hạn trong RAM, ứng dụng hoặc Collector có thể hết bộ nhớ. Nếu queue quá nhỏ, telemetry bị drop ngay khi tốc độ tạo dữ liệu vượt tốc độ export. Vì vậy, queue cần có giới hạn và chính sách xử lý overflow rõ ràng.

Một pipeline điển hình:

~~~mermaid
flowchart LR
    App["Spring Boot + Spring Modulith"]
    Obs["Micrometer Observation / Tracing"]
    SDK["OTel SDK BatchSpanProcessor"]
    OTLP["OTLP exporter"]
    Receiver["Collector receiver"]
    Limit["memory_limiter"]
    Batch["batch processor"]
    Queue["Exporter sending queue"]
    Backend["Trace backend"]

    App --> Obs --> SDK --> OTLP --> Receiver
    Receiver --> Limit --> Batch --> Queue --> Backend
~~~

Queue không làm backend nhanh hơn. Nó chỉ hấp thụ chênh lệch tốc độ trong một khoảng thời gian hữu hạn. Nếu tốc độ nhận luôn lớn hơn tốc độ gửi, queue cuối cùng vẫn đầy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt queue trong ứng dụng với sending queue của OpenTelemetry Collector.
2. Giải thích cách BatchSpanProcessor gom và export spans.
3. Cấu hình giới hạn queue cho Spring Boot 4.x và 3.5.
4. Cấu hình queue, retry và persistent storage của Collector.
5. Ước lượng capacity theo ingest rate, export rate và thời gian backend gián đoạn.
6. Hiểu overflow, drop, retry, backpressure và WAL.
7. Theo dõi queue size, queue capacity, enqueue failures và memory limiter.
8. Kiểm thử queue saturation và xác định đúng tầng gây nghẽn.
9. Tránh tăng queue vô hạn hoặc đẩy tải quá mức sang backend.

## 2. Phân biệt các loại queue trong telemetry pipeline

Trong một hệ thống có Spring Modulith, cùng một trace có thể đi qua nhiều bộ đệm. Mỗi queue có đơn vị đo và chính sách overflow khác nhau.

| Thành phần | Dữ liệu được giữ | Đơn vị giới hạn | Khi đầy |
|---|---|---|---|
| OpenTelemetry BatchSpanProcessor trong app | Spans đã kết thúc, đủ điều kiện export | Số spans | Drop spans mới theo chính sách SDK |
| OpenTelemetry BatchLogRecordProcessor | Log records đã được ghi nhận | Số log records | Drop log records khi queue đầy |
| Micrometer metrics registry | Meter state và dữ liệu theo chu kỳ export | Không dùng chung queue BSP | Export theo registry/step; phụ thuộc registry |
| Collector exporter sending queue | Batch traces, metrics hoặc logs chờ gửi backend | Requests, items hoặc bytes tùy sizer | Reject/drop hoặc chờ nếu cấu hình overflow |
| Collector persistent queue | Batch đang chờ gửi được ghi xuống storage | Queue capacity và dung lượng storage | Có thể đầy do capacity hoặc disk |
| Message queue như Kafka | Messages giữa các tầng collector | Bytes, partitions và retention | Phụ thuộc quota, retention và producer policy |

**Queue telemetry khác Event Publication Registry của Spring Modulith.** Event Publication Registry theo dõi trạng thái giao event tới transactional listener. Queue telemetry chỉ giữ dữ liệu quan sát chờ export. Không dùng counter event publication hoặc publication status để suy ra queue OTLP đang đầy.

### 2.1. Queue trong ứng dụng

Với tracing, OpenTelemetry SDK thường dùng BatchSpanProcessor. Khi span kết thúc và được ghi nhận, processor đưa span vào queue. Worker nền lấy spans theo batch và gửi tới exporter.

Queue này nằm trong process Spring Boot. Nó giúp request thread không phải chờ mỗi span được gửi đồng bộ tới backend. Nếu exporter chậm lâu hơn tốc độ tạo span, queue tăng dần.

### 2.2. Sending queue trong Collector

Collector nhận dữ liệu từ ứng dụng qua OTLP. Exporter của Collector có thể dùng sending queue để tách tốc độ nhận khỏi tốc độ gửi tới backend. Khi backend chậm hoặc tạm dừng, Collector giữ batch và retry.

Queue của Collector thường đo theo request/batch thay vì số span. Nếu đổi sizer sang items hoặc bytes, đơn vị capacity cũng thay đổi. Đọc cấu hình exporter cụ thể và metric của Collector đang chạy trước khi tính toán.

### 2.3. Queue không phải durable storage mặc định

Queue trong RAM mất nội dung khi process crash hoặc restart. Queue có persistent storage ghi batch xuống disk/WAL, giúp khôi phục dữ liệu sau restart trong giới hạn storage và retry policy.

Persistent queue vẫn có capacity hữu hạn. Nó không bảo đảm lưu vô hạn và cũng không thay thế hệ thống message queue chuyên dụng khi cần durability cao qua nhiều network boundary.

## 3. BatchSpanProcessor hoạt động như thế nào?

BatchSpanProcessor nhận spans đã kết thúc, giữ chúng trong queue và export theo một trong các điều kiện:

- Đã đến thời gian chờ export tiếp theo (schedule delay).
- Queue đã có đủ số spans để tạo batch (max batch size).
- Ứng dụng gọi force flush hoặc shutdown.

Các tham số chính:

| Tham số | Ý nghĩa | Giá trị mặc định phổ biến |
|---|---|---:|
| max-queue-size | Số spans tối đa được giữ trong queue | 2048 |
| max-batch-size | Số spans tối đa trong một lần export | 512 |
| schedule-delay | Khoảng chờ tối đa giữa hai lần export | 5 giây |
| timeout | Thời gian tối đa cho một lần export trước khi bị hủy | 30 giây |

Max batch size phải nhỏ hơn hoặc bằng max queue size.

### 3.1. Điều gì xảy ra khi queue đầy?

Khi queue đạt capacity, BatchSpanProcessor không thể giữ thêm spans. Với hành vi chuẩn của processor, span mới bị drop thay vì làm request nghiệp vụ chờ vô thời hạn.

Điều đó có nghĩa:

- Request đặt hàng vẫn có thể thành công.
- Trace có thể thiếu một số spans.
- Backend có thể nhận được trace không đầy đủ.
- Ứng dụng không nhất thiết ghi nhận lỗi nghiệp vụ chỉ vì telemetry queue overflow.

Đây là một lựa chọn bảo vệ ứng dụng. Observability không nên khiến mọi request bị block chỉ vì trace backend tạm thời mất kết nối.

### 3.2. Vai trò của batch size

Batch lớn giảm số lần gọi exporter và có thể cải thiện throughput, nhưng tăng memory footprint của mỗi lần export và độ trễ chờ đủ batch.

Batch nhỏ gửi dữ liệu thường xuyên hơn nhưng có thể tăng overhead mạng, CPU và số request tới Collector.

Không đặt batch size bằng queue size theo thói quen. Hãy giữ một phần capacity cho spans tiếp tục đến trong khi batch hiện tại đang được export.

### 3.3. Vai trò của schedule delay và timeout

Giảm schedule delay có thể làm trace xuất hiện sớm hơn trong backend, nhưng cũng làm tăng tần suất export khi tải thấp. Tăng timeout không làm exporter nhanh hơn; nó chỉ cho một lần export thêm thời gian hoàn thành.

Timeout của BatchSpanProcessor và timeout của OTLP exporter là hai giới hạn ở hai tầng. Nên cấu hình timeout của HTTP/gRPC exporter phù hợp với timeout tổng của processor, để một request mạng không giữ worker lâu hơn thời gian processor cho phép.

## 4. Cấu hình queue trong Spring Boot 4.x

Với Spring Boot 4.x, OpenTelemetry tracing được cấu hình qua namespace management.opentelemetry.tracing.export.*.

Ví dụ:

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 0.1

  opentelemetry:
    tracing:
      export:
        max-queue-size: 4096
        max-batch-size: 512
        schedule-delay: 5s
        timeout: 30s
        otlp:
          endpoint: "http://otel-collector:4318/v1/traces"
          transport: http
          timeout: 10s
~~~

Ý nghĩa:

- max-queue-size: 4096 cho phép giữ tối đa 4096 spans trong BatchSpanProcessor queue.
- max-batch-size: 512 giới hạn mỗi lần export tối đa 512 spans.
- schedule-delay: 5s export theo lịch nếu batch chưa đầy.
- timeout: 30s giới hạn thời gian của một lần export ở processor.
- otlp.timeout: 10s giới hạn call tới Collector ở tầng OTLP exporter.
- sampling.probability: 0.1 chỉ lấy mẫu khoảng 10% trace theo policy hiện hành; queue sẽ nhận số spans đã được sampling, không phải toàn bộ spans được tạo.

Các giá trị trên chỉ là điểm bắt đầu để thử nghiệm. Hãy điều chỉnh theo throughput, độ lớn span và khả năng export của Collector.

### 4.1. Tên property không giống OpenTelemetry SDK trực tiếp

Spring Boot 4.x ánh xạ các biến môi trường OpenTelemetry như OTEL_BSP_MAX_QUEUE_SIZE sang property Spring Boot tương ứng. Khi dùng Spring Boot auto-configuration, ưu tiên property được Spring Boot tài liệu hóa.

Nếu tự tạo OpenTelemetry bean hoặc thay SDK auto-configuration, hành vi mapping và tích hợp observability của Spring Boot có thể thay đổi. Không trộn nhiều cơ chế cấu hình SDK nếu chưa xác định bean nào đang sở hữu TracerProvider.

## 5. Cấu hình queue trong Spring Boot 3.5

Spring Boot 3.5 dùng namespace khác cho BatchSpanProcessor:

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 0.1
    opentelemetry:
      export:
        max-queue-size: 4096
        max-batch-size: 512
        schedule-delay: 5s
        timeout: 30s

  otlp:
    tracing:
      endpoint: "http://otel-collector:4318/v1/traces"
      transport: http
      timeout: 10s
~~~

Bảng đối chiếu:

| Nội dung | Spring Boot 4.x | Spring Boot 3.5 |
|---|---|---|
| Queue spans | management.opentelemetry.tracing.export.max-queue-size | management.tracing.opentelemetry.export.max-queue-size |
| Batch size | management.opentelemetry.tracing.export.max-batch-size | management.tracing.opentelemetry.export.max-batch-size |
| Schedule delay | management.opentelemetry.tracing.export.schedule-delay | management.tracing.opentelemetry.export.schedule-delay |
| Processor timeout | management.opentelemetry.tracing.export.timeout | management.tracing.opentelemetry.export.timeout |
| OTLP endpoint | management.opentelemetry.tracing.export.otlp.endpoint | management.otlp.tracing.endpoint |
| OTLP call timeout | management.opentelemetry.tracing.export.otlp.timeout | management.otlp.tracing.timeout |

Không sao chép nguyên namespace của Boot 3.5 sang Boot 4.x hoặc ngược lại.

### 5.1. Kiểm tra giá trị đã bind

Khi thay đổi queue capacity, cần xác nhận ứng dụng thực sự bind property mong muốn. Có thể kiểm tra configuration metadata, startup configuration report hoặc Actuator config properties trong môi trường nội bộ đã được bảo vệ.

Không expose toàn bộ /actuator/configprops ra public network vì endpoint có thể tiết lộ cấu hình nhạy cảm.

## 6. Logs và metrics có queue riêng

Queue max-queue-size của BatchSpanProcessor chỉ giới hạn spans. Không áp dụng nó cho tất cả telemetry signal.

### 6.1. OpenTelemetry logs trong Boot 4.x

Nếu ứng dụng sử dụng OpenTelemetry logging pipeline trong Spring Boot 4.x, BatchLogRecordProcessor có cấu hình riêng:

~~~yaml
management:
  opentelemetry:
    logging:
      export:
        max-queue-size: 2048
        max-batch-size: 512
        schedule-delay: 1s
        timeout: 30s
~~~

BatchLogRecordProcessor mặc định phổ biến có queue 2048 log records, batch 512 và schedule delay 1 giây. Cần kiểm tra phiên bản Spring Boot và logging integration đang dùng trước khi áp dụng.

### 6.2. Micrometer metrics không dùng BatchSpanProcessor

Spring Boot dùng Micrometer làm API metrics. Khi export Micrometer meters qua OTLP, management.otlp.metrics.export.step là chu kỳ export của registry. Đây không phải max-queue-size của BatchSpanProcessor.

Ví dụ:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        step: 30s
~~~

Metric data sau đó vẫn có thể đi qua sending queue của Collector. Vì vậy cần phân biệt chu kỳ export của registry với queue ở Collector.

## 7. Cấu hình sending queue cho OpenTelemetry Collector

Collector exporter thường có sending queue và retry. Với exporter sử dụng exporter helper mặc định, queue thường có capacity khoảng 1000 requests/batches, nhưng từng exporter hoặc distribution có thể ghi đè mặc định. Luôn kiểm tra tài liệu đúng component và phiên bản đang triển khai.

Ví dụ cấu hình Collector dùng OTLP receiver, memory limiter, batch processor và persistent sending queue:

~~~yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/storage

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 75
    spike_limit_percentage: 15

  batch:
    timeout: 5s
    send_batch_size: 1024
    send_batch_max_size: 2048

exporters:
  otlp/backend:
    endpoint: otel-backend:4317
    sending_queue:
      enabled: true
      storage: file_storage
      queue_size: 5000
      num_consumers: 10
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
      processors: [memory_limiter, batch]
      exporters: [otlp/backend]
~~~

Các điểm cần hiểu:

- file_storage là storage extension ghi queue xuống disk/WAL.
- sending_queue.storage tham chiếu extension để bật persistent queue.
- queue_size giới hạn số đơn vị queue theo sizer; mặc định exporter helper thường dùng request/batch.
- num_consumers điều khiển số worker lấy batch khỏi queue để export.
- retry_on_failure cấu hình exponential backoff và thời gian retry tối đa.
- max_elapsed_time: 10m cho phép retry tối đa 10 phút trong ví dụ.
- memory_limiter nên đứng đầu danh sách processor để giới hạn memory trước khi các processor phía sau giữ thêm dữ liệu.
- batch processor gom dữ liệu trước khi chuyển đến exporter.

Đường dẫn /var/lib/otelcol/storage phải nằm trên volume bền vững, có dung lượng và quyền ghi phù hợp. Nếu Collector chạy trong Kubernetes, dùng PersistentVolume/PersistentVolumeClaim phù hợp với topology triển khai.

### 7.1. Queue size không nhất thiết là số spans

Với sizer requests, queue_size 5000 có nghĩa tối đa khoảng 5000 request/batch, không phải 5000 spans. Một batch có thể chứa hàng trăm hoặc hàng nghìn spans.

Nếu dùng sizer items, queue tính theo số phần tử nhỏ nhất của signal, ví dụ spans, metric points hoặc log records. Nếu dùng sizer bytes, queue được giới hạn theo kích thước dữ liệu đã serialize/ước lượng theo implementation.

Không so sánh queue_size cấu hình trực tiếp với số spans mà không quy đổi đơn vị.

### 7.2. Cẩn thận khi dùng batch ở nhiều tầng

Ứng dụng đã batch spans trước khi gửi. Collector có thể tiếp tục batch trước khi export. Một số exporter cũng hỗ trợ batching bên trong sending queue.

Nhiều tầng batching có thể tăng latency và memory mà không tăng throughput. Chọn một điểm batching phù hợp với pipeline, đo kích thước batch thực tế và tránh cấu hình batch lồng nhau chỉ để tăng số lượng buffer.

## 8. Memory limiter và backpressure

Queue hữu hạn cần đi cùng giới hạn bộ nhớ. Nếu chỉ tăng queue size, Collector có thể giữ quá nhiều batch khi backend chậm.

Memory limiter sử dụng hard limit và soft limit:

- limit_percentage hoặc limit_mib đặt giới hạn bộ nhớ cứng.
- spike_limit_percentage hoặc spike_limit_mib tạo khoảng an toàn cho memory spike.
- Khi vượt soft limit, processor bắt đầu từ chối dữ liệu để giảm áp lực.
- Khi vượt hard limit, processor có thể buộc garbage collection theo cấu hình.

Memory limiter không bảo đảm không mất dữ liệu. Receiver hoặc upstream phải có khả năng retry khi nhận lỗi; nếu upstream không retry hoặc retry hết hạn, dữ liệu vẫn có thể mất.

### 8.1. Vì sao memory_limiter phải đứng đầu?

Nếu processor biến đổi hoặc batch dữ liệu trước memory limiter, dữ liệu có thể đã chiếm thêm memory trước khi bị giới hạn. Đặt memory limiter đầu tiên giúp Collector trả backpressure sớm hơn cho receiver có hỗ trợ retry.

Thứ tự thường dùng:

1. memory_limiter
2. Sampling/filtering để loại dữ liệu không cần thiết sớm.
3. Processor enrich hoặc transform.
4. batch
5. Exporter sending queue.

Thứ tự thực tế còn phụ thuộc processor cần đọc request context và semantics của pipeline.

### 8.2. block_on_overflow có thể làm tăng latency

Với exporter hỗ trợ, block_on_overflow: true có thể khiến caller chờ khi queue đầy cho tới khi có chỗ trống hoặc request timeout. Đây là một dạng backpressure, nhưng có thể làm tăng latency và gây timeout ngược về receiver hoặc service gửi dữ liệu.

Mặc định thường là không block và trả lỗi enqueue khi queue đầy. Chỉ bật block khi đã kiểm thử tác động lên receiver, network timeout và ứng dụng upstream.

## 9. Persistent queue và retry không phải bảo đảm vô hạn

In-memory queue mất nội dung khi Collector process bị crash hoặc restart. Persistent queue dùng WAL để lưu batch trên disk và phục hồi sau khi Collector khởi động lại.

Persistent queue phù hợp khi:

- Collector Gateway nhận telemetry quan trọng từ nhiều service.
- Backend có thể bảo trì hoặc restart trong thời gian ngắn.
- Restart Collector không nên làm mất ngay toàn bộ dữ liệu đang chờ.
- Có volume bền vững và runbook quản lý dung lượng disk.

Persistent queue vẫn có thể mất dữ liệu khi:

- Disk đầy, lỗi filesystem hoặc volume không truy cập được.
- Queue đạt capacity.
- Retry vượt max_elapsed_time.
- Backend không phục hồi trong thời gian retention cho phép.
- Storage bị xóa hoặc volume bị thay thế không đúng quy trình.

Nếu yêu cầu durability rất cao qua nhiều network boundary, có thể dùng message queue chuyên dụng như Kafka giữa Agent và Gateway. Điều này tăng độ bền nhưng cũng tăng chi phí vận hành, partitioning, retention và quản lý consumer lag.

### 9.1. Retry và queue capacity phải được tính cùng nhau

Tăng max_elapsed_time mà không tăng queue capacity có thể khiến queue đầy trước khi hết thời gian retry. Ngược lại, queue lớn nhưng retry quá ngắn vẫn có thể drop dữ liệu cũ khi backend outage kéo dài.

Cần thiết kế đồng thời:

- Tốc độ ingest.
- Tốc độ export khi backend hoạt động.
- Thời gian outage chấp nhận được.
- Queue capacity và đơn vị queue.
- Retry duration.
- Dung lượng disk nếu dùng persistent queue.
- Khả năng phục hồi và tốc độ drain backlog sau outage.

## 10. Ước lượng queue capacity

Một mô hình đơn giản giúp ước lượng số phần tử cần buffer:

\[
Q \geq (\lambda - \mu) \times T
\]

Trong đó:

- \(\lambda\): tốc độ telemetry đến queue (items/giây).
- \(\mu\): tốc độ queue được export thành công (items/giây).
- \(T\): thời gian cần hấp thụ sự cố (giây).
- \(Q\): số items cần giữ.

Khi backend hoàn toàn không nhận dữ liệu, \(\mu \approx 0\), do đó:

\[
Q \geq \lambda \times T
\]

### 10.1. Ví dụ tính queue cho spans

Giả sử một service tạo 400 sampled spans/giây và muốn giữ telemetry trong 120 giây backend outage:

\[
Q \geq 400 \times 120 = 48\,000\ \text{spans}
\]

Queue mặc định 2048 spans chỉ giữ được khoảng:

\[
2048 / 400 \approx 5.12\ \text{giây}
\]

Nếu muốn giữ 2 phút, cần capacity lớn hơn nhiều. Tuy nhiên, không nên tăng queue lên 48.000 mà chưa đo memory footprint của span, vì queue có thể tiêu thụ đáng kể heap của ứng dụng.

### 10.2. Quy đổi sang queue của Collector

Giả sử Collector nhận trung bình 500 spans mỗi request/batch. Nếu cần giữ 48.000 spans:

\[
Q_{requests} \approx 48\,000 / 500 = 96\ \text{requests}
\]

Thực tế batch size biến động theo traffic, timeout và exporter. Dùng phân phối batch size quan sát được, không lấy một giá trị trung bình duy nhất nếu traffic có burst lớn.

### 10.3. Ước lượng memory

Có thể dùng công thức gần đúng:

\[
M_{queue} \approx Q \times S_{avg} \times H
\]

Trong đó:

- \(Q\): số items.
- \(S_{avg}\): kích thước trung bình mỗi item trong bộ nhớ.
- \(H\): hệ số headroom cho object overhead, batch, retry và biến động tải.

Không lấy kích thước OTLP payload đã nén làm kích thước object trong heap. Đo memory trong load test để hiệu chỉnh \(S_{avg}\) và \(H\).

### 10.4. Chọn headroom

Capacity thực tế nên lớn hơn lượng tính toán lý thuyết để hấp thụ burst và sai số đo. Tuy nhiên, headroom không thể thay thế việc sửa một backend có throughput thấp hơn ingest trong thời gian dài.

Nếu queue luôn tăng sau mỗi đợt tải, vấn đề là mất cân bằng throughput. Tăng capacity chỉ kéo dài thời gian trước khi overflow.

## 11. Sampling và filtering ảnh hưởng tới queue

Queue chỉ nhận dữ liệu được gửi tới tầng đó.

Với head sampling ở ứng dụng, spans bị loại trước khi vào BatchSpanProcessor queue, nên giảm trực tiếp số spans cần buffer. Ví dụ sampling 10% có thể làm giảm đáng kể queue load khi trace phân bố tương đối đồng đều.

Với tail sampling ở Collector, ứng dụng vẫn gửi các spans cần thiết tới Collector để Collector quyết định giữ hay drop cả trace. Queue phía trước tail sampler vẫn phải chịu tải từ dữ liệu đến; không tính queue capacity theo tỷ lệ giữ cuối cùng.

Các cách giảm telemetry load:

- Điều chỉnh sampling probability theo môi trường và lưu lượng.
- Loại spans không có giá trị vận hành bằng filter có kiểm soát.
- Giới hạn số attributes/events trên mỗi span.
- Tránh ghi payload lớn hoặc dữ liệu nhạy cảm vào span.
- Không tạo custom span cho mọi method nhỏ nếu instrumentation hiện tại đã đủ.
- Chọn trace retention và sampling theo nhu cầu điều tra.

Không giảm sampling chỉ để che một backend đang quá tải mà không xem xét tác động tới khả năng điều tra production.

## 12. Theo dõi queue và cảnh báo saturation

Collector cung cấp internal metrics để giám sát queue và luồng dữ liệu.

| Metric | Ý nghĩa |
|---|---|
| otelcol_exporter_queue_size | Số đơn vị hiện đang nằm trong sending queue |
| otelcol_exporter_queue_capacity | Capacity của sending queue |
| otelcol_exporter_enqueue_failed_spans | Số spans không thể đưa vào queue |
| otelcol_exporter_send_failed_spans | Số spans gặp lỗi khi gửi tới backend |
| otelcol_exporter_sent_spans | Số spans export thành công |
| otelcol_receiver_refused_spans | Số spans receiver từ chối |
| otelcol_processor_refused_spans | Số spans bị processor từ chối, ví dụ memory limiter |

Tên metric Prometheus có thể thay đổi suffix hoặc cách chuẩn hóa theo Collector version và cấu hình Prometheus reader. Hãy kiểm tra endpoint internal metrics thực tế trước khi viết alert.

### 12.1. Tỷ lệ queue utilization

Nếu queue size và capacity có cùng đơn vị:

~~~promql
otelcol_exporter_queue_size
/
clamp_min(otelcol_exporter_queue_capacity, 1)
~~~

OpenTelemetry Collector scaling guide gợi ý xem xét scale khi queue thường xuyên đạt khoảng 60–70% capacity. Đây là tín hiệu vận hành để điều tra, không phải ngưỡng bắt buộc cho mọi hệ thống.

### 12.2. Cảnh báo queue gần đầy

~~~promql
(
  otelcol_exporter_queue_size
  /
  clamp_min(otelcol_exporter_queue_capacity, 1)
) > 0.7
~~~

Có thể yêu cầu điều kiện duy trì vài phút để tránh alert khi có burst ngắn:

~~~yaml
- alert: OTelExporterQueueNearCapacity
  expr: |
    (
      otelcol_exporter_queue_size
      /
      clamp_min(otelcol_exporter_queue_capacity, 1)
    ) > 0.7
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "OpenTelemetry exporter queue đang gần đầy"
    description: "Queue utilization đã vượt 70% trong 5 phút."
~~~

Ví dụ trên cần thêm label phân biệt exporter/service nếu Prometheus scrape nhiều Collector hoặc nhiều exporter. Hãy giữ các label có ích để tìm đúng pipeline.

### 12.3. Cảnh báo enqueue failures

~~~promql
increase(otelcol_exporter_enqueue_failed_spans[5m]) > 0
~~~

Enqueue failure cho thấy dữ liệu không vào được sending queue. Điều tra queue capacity, memory/disk, tốc độ ingest và khả năng export.

### 12.4. Cảnh báo send failures

~~~promql
rate(otelcol_exporter_send_failed_spans[5m]) > 0
~~~

Send failure có thể được retry; nó không tự chứng minh dữ liệu đã mất. Kết hợp với queue size, enqueue failures, retry duration và Collector logs để đánh giá.

### 12.5. Theo dõi queue ở SDK ứng dụng

OpenTelemetry SDK có semantic conventions cho các metric như:

- otel.sdk.processor.span.queue.size
- otel.sdk.processor.span.queue.capacity
- otel.sdk.processor.span.processed

Các metric SDK này có mức ổn định còn đang phát triển và mức hỗ trợ phụ thuộc SDK/version/exporter. Chỉ dùng khi ứng dụng thực sự export các internal metrics đó. Không giả định chúng luôn xuất hiện trong mọi cấu hình Spring Boot.

## 13. Phân biệt queue đầy với backend chậm

Queue tăng là triệu chứng, cần tìm nguyên nhân phía sau:

| Dấu hiệu | Khả năng | Việc cần kiểm tra |
|---|---|---|
| Queue tăng, send failures tăng | Backend hoặc network lỗi | DNS, TLS, auth, endpoint và backend health |
| Queue tăng, send failures thấp, sent rate thấp | Backend xử lý chậm hoặc ít consumer | Export latency, consumer count, backend throughput |
| Queue đầy, enqueue failures tăng | Capacity không đủ hoặc outage kéo dài | Queue size, retry window và storage |
| Memory limiter refused tăng | Collector thiếu memory | Memory limit, batch size, queue footprint và replica |
| Receiver refused tăng | Collector không nhận thêm được dữ liệu | Pipeline pressure, memory limiter, receiver và upstream retry |
| Queue size giảm nhưng backend thiếu trace | Có thể đã drop hoặc filter | Enqueue failures, retry timeout, sampling và backend query |
| Queue luôn gần đầy sau khi tăng capacity | Throughput mất cân bằng lâu dài | Backend capacity, network và ingest rate |

Không scale Collector một cách tự động khi backend đã là bottleneck. Thêm Collector hoặc exporter consumers có thể làm backend nhận tải lớn hơn và khiến sự cố nặng hơn.

## 14. Kiểm thử queue saturation

Một bài kiểm thử hữu ích cần mô phỏng tốc độ ingest, tốc độ export và thời gian gián đoạn.

### Phần A — Baseline

1. Chạy ứng dụng Spring Boot có Spring Modulith observability.
2. Gửi request tạo tương tác qua nhiều application modules.
3. Xác nhận spans xuất hiện trong Collector và backend.
4. Ghi nhận spans/giây, queue size, queue capacity, memory và export latency.
5. Đo baseline trong một khoảng thời gian đủ ổn định.

### Phần B — Tăng tải

1. Tăng request rate theo từng mức có kiểm soát.
2. Theo dõi số spans được tạo sau sampling.
3. Quan sát queue SDK và Collector nếu có metrics.
4. Ghi nhận thời điểm queue vượt 60%, 70%, 90% và thời điểm có enqueue failures.
5. So sánh throughput gửi thành công với throughput nhận vào.

### Phần C — Mô phỏng backend outage

1. Dùng môi trường test để tạm dừng hoặc chặn kết nối từ Collector tới backend.
2. Tiếp tục gửi request ở tốc độ đã xác định.
3. Quan sát queue tăng và retry hoạt động.
4. Xác nhận queue đạt capacity có hành vi overflow đúng cấu hình.
5. Kiểm tra Collector memory không vượt resource limit.
6. Khôi phục backend và quan sát tốc độ drain queue.
7. Kiểm tra trace có thể truy vấn ở backend sau khi export hoàn tất.

### Phần D — Kiểm tra restart Collector

1. Bật persistent queue trên volume thử nghiệm.
2. Tạo backlog khi backend không khả dụng.
3. Restart Collector trong môi trường test.
4. Xác nhận queue được phục hồi từ storage.
5. Khôi phục backend và kiểm tra batch được gửi tiếp.
6. Thử disk gần đầy để xác định cảnh báo và hành vi lỗi.

### Bảng kết quả mong đợi

| Tình huống | SDK queue | Collector queue | Kết quả cần xác nhận |
|---|---|---|---|
| Backend hoạt động bình thường | Thấp/ổn định | Thấp/ổn định | Export rate theo kịp ingest |
| Backend chậm | Có thể tăng | Tăng | Queue chưa đầy, latency tăng |
| Backend outage ngắn | Tăng tới giới hạn | Tăng tới giới hạn | Retry và buffer hấp thụ gián đoạn |
| SDK queue đầy | Drop spans mới | Có thể không nhận đủ dữ liệu | Ứng dụng vẫn xử lý request, telemetry thiếu |
| Collector queue đầy | App có thể nhận lỗi export hoặc retry | Enqueue failures tăng | Có nguy cơ mất batch |
| Collector restart với RAM queue | Không liên quan | Queue RAM mất | Dữ liệu đang chờ có thể mất |
| Collector restart với WAL | Không liên quan | Queue được khôi phục nếu storage còn tốt | Batch tiếp tục export |
| Backend phục hồi | Queue giảm | Queue drain dần | Trace mới xuất hiện, backlog trở về bình thường |

Đây là kết quả kỳ vọng của bài thực hành, không phải báo cáo một cluster hoặc backend đã được chạy trong repository.

## 15. Runbook khi queue telemetry tăng cao

Khi queue vượt ngưỡng, xử lý theo thứ tự:

### Bước 1 — Xác định queue nào đang đầy

- Queue của BatchSpanProcessor trong ứng dụng?
- Sending queue của exporter Collector?
- Queue persistent đang đầy disk?
- Queue của log hoặc metrics pipeline?

Không tăng mọi queue cùng lúc.

### Bước 2 — Xác định ingest và drain rate

Đo dữ liệu đến và dữ liệu gửi thành công. Nếu ingest lớn hơn drain trong thời gian dài, queue sẽ tiếp tục tăng.

### Bước 3 — Kiểm tra downstream

Kiểm tra backend latency, error rate, network, TLS, authentication, quota và ingest capacity. Nếu backend đã quá tải, thêm consumers có thể làm tình hình xấu hơn.

### Bước 4 — Giảm lượng telemetry không cần thiết

Xem sampling, filter, span attributes, event count và log volume. Giảm dữ liệu không cần thiết thường hiệu quả hơn việc tăng queue liên tục.

### Bước 5 — Điều chỉnh queue và retry

Nếu outage ngắn và resource còn đủ, tăng capacity có kiểm soát. Nếu cần chịu restart Collector, dùng persistent queue với volume bền vững. Điều chỉnh max_elapsed_time cùng queue capacity để phù hợp thời gian outage chấp nhận được.

### Bước 6 — Kiểm tra backpressure

Nếu bật block_on_overflow, đo latency ở receiver và upstream. Đảm bảo request timeout và retry policy không tạo ra vòng retry kéo dài.

### Bước 7 — Xác nhận khôi phục

Queue phải giảm dần, enqueue failures ngừng tăng, send failures trở về mức bình thường và backend truy vấn được telemetry mới. Ghi lại thời gian backlog được drain và lượng dữ liệu có thể đã bị drop.

## 16. Những lỗi cấu hình thường gặp

### 16.1. Tăng queue mà không đo memory

Queue lớn giữ nhiều object hơn trong RAM. Với SDK, điều này làm tăng heap của ứng dụng; với Collector, nó làm tăng memory footprint của process. Tính capacity cùng kích thước item và headroom.

### 16.2. Nhầm queue capacity với batch size

Queue capacity là tổng lượng dữ liệu đang chờ; batch size là lượng dữ liệu gửi trong một lần. Chúng có đơn vị khác nhau ở các tầng và không thể thay thế cho nhau.

### 16.3. Nhầm schedule delay với retry interval

Schedule delay quyết định thời điểm BSP bắt đầu export batch. Retry interval quyết định khoảng chờ giữa các lần thử lại khi export thất bại. Chúng điều khiển hai giai đoạn khác nhau.

### 16.4. Để retry vô hạn nhưng không có storage

Retry không giới hạn với in-memory queue có thể giữ dữ liệu trong RAM cho đến khi process bị OOM hoặc queue đầy. Cần giới hạn queue và quyết định rõ thời gian retry.

### 16.5. Dùng persistent queue nhưng không cấp persistent volume

Nếu storage nằm trên filesystem tạm thời của container, restart hoặc reschedule có thể làm mất WAL. Persistent queue chỉ có tác dụng khi storage thật sự bền vững.

### 16.6. Đặt memory_limiter sau batch

Batch processor có thể giữ dữ liệu trước khi memory limiter kiểm tra. Đặt memory limiter đầu tiên trong pipeline để giảm áp lực sớm.

### 16.7. Thêm exporter consumers mà không kiểm tra backend

Nhiều consumers hơn có thể tăng tốc export nếu Collector thiếu worker. Nhưng nếu backend đã quá tải, thêm consumers chỉ tăng áp lực. Theo dõi latency và send failures trước khi điều chỉnh.

### 16.8. Không giám sát enqueue failures

Queue size có thể dao động hoặc giảm sau khi drop dữ liệu. Chỉ nhìn queue size có thể bỏ lỡ sự cố. Theo dõi enqueue failures và refused metrics song song.

### 16.9. Dùng queue telemetry thay cho event durability

Trace và metrics exporter có thể sampling, drop hoặc hết retry. Nếu event nghiệp vụ cần bảo đảm giao nhận, dùng Event Publication Registry, transactional outbox hoặc message broker phù hợp. Không coi telemetry queue là hàng đợi nghiệp vụ.

## 17. Checklist triển khai production

- [ ] Đã phân biệt queue của SDK, Collector và metrics registry.
- [ ] Queue size và batch size có đơn vị rõ ràng.
- [ ] Max batch size không lớn hơn max queue size.
- [ ] Đã cấu hình đúng namespace theo Spring Boot version.
- [ ] Export timeout và OTLP request timeout được phối hợp hợp lý.
- [ ] Đã đo sampled spans/giây và export throughput thực tế.
- [ ] Queue capacity đủ cho outage window đã chọn và có headroom.
- [ ] Memory budget tính cả queue, batch và retry.
- [ ] Collector exporter có sending queue và retry policy phù hợp.
- [ ] Persistent queue dùng volume bền vững và có disk alert.
- [ ] memory_limiter đứng đầu pipeline.
- [ ] Đã quyết định có bật block_on_overflow sau khi kiểm thử backpressure.
- [ ] Có dashboard queue size/capacity, enqueue failures, send failures và memory.
- [ ] Có cảnh báo queue utilization và enqueue failures.
- [ ] Đã kiểm thử backend outage, Collector restart và queue saturation.
- [ ] Có runbook xác định queue nào đầy và cách drain backlog.
- [ ] Không dùng telemetry queue thay thế event delivery hoặc audit durability.

## 18. Ghi nhớ

- Queue chỉ hấp thụ chênh lệch tốc độ trong một khoảng thời gian hữu hạn; nó không làm backend nhanh hơn.
- BatchSpanProcessor giữ spans trong app process; queue đầy có thể làm drop spans mà không chặn request nghiệp vụ.
- Spring Boot 4.x và 3.5 dùng namespace cấu hình queue tracing khác nhau.
- Collector exporter sending queue có thể giữ batch trong RAM hoặc persistent storage; capacity phụ thuộc sizer và exporter component.
- Retry duration, queue capacity, memory limit và backend throughput phải được thiết kế cùng nhau.
- memory_limiter nên đứng đầu Collector pipeline; queue saturation cần được theo dõi bằng queue size, capacity và enqueue failures.
- Persistent queue giúp phục hồi sau Collector restart nhưng vẫn bị giới hạn bởi disk, capacity và retry policy.
- Khi queue liên tục tăng, phải xử lý mất cân bằng ingest/drain hoặc backend bottleneck thay vì chỉ tăng buffer.

## Tài liệu tham khảo

1. [Spring Boot 4.x — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Mapping OpenTelemetry SDK batch processor settings sang Spring Boot properties.
2. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html) — Queue, batch size, schedule delay và timeout của Micrometer Tracing OpenTelemetry.
3. [Spring Boot 4.x — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — OpenTelemetry/OTLP tracing auto-configuration.
4. [OpenTelemetry — BatchSpanProcessor Specification](https://opentelemetry.io/docs/specs/otel/trace/sdk/) — Queue size, batch size, schedule delay và export timeout.
5. [OpenTelemetry Java — Configure the SDK](https://opentelemetry.io/docs/languages/java/configuration/) — BatchSpanProcessor settings và giá trị mặc định.
6. [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/) — Sending queue, retry, persistent storage/WAL và tình huống mất dữ liệu.
7. [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/) — Queue size/capacity, enqueue failures, send failures và receive metrics.
8. [OpenTelemetry Collector — Scaling](https://opentelemetry.io/docs/collector/scaling/) — Queue utilization, memory limiter và hướng dẫn scale Collector.
9. [OpenTelemetry Collector — Memory Limiter Processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor) — Soft/hard memory limit và thứ tự processor.
10. [OpenTelemetry — SDK Metrics Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/otel/sdk-metrics/) — Metrics theo dõi queue của SDK span processor.

