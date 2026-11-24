# Xây dựng cảnh báo và bảng theo dõi tình trạng luồng

Một ứng dụng Spring Cloud Stream có thể vẫn chạy và health endpoint vẫn trả về UP trong khi dữ liệu đang ùn ứ, consumer xử lý chậm, message liên tục vào DLQ hoặc một binding đã ngừng nhận event. Vì vậy, quan sát hệ thống cần theo dõi cả ứng dụng, binding và broker. Dashboard phải cho biết luồng đang nhận bao nhiêu dữ liệu, xử lý nhanh đến đâu, lỗi xuất hiện ở đâu và backlog có đang tăng hay không. Cảnh báo cần gắn với tác động nghiệp vụ và hướng xử lý cụ thể.

Bài học này xây dựng cách quan sát pipeline Supplier/Function/Consumer bằng Spring Boot Actuator, Micrometer, Prometheus và Grafana; bổ sung số liệu native từ Kafka, RabbitMQ hoặc Pulsar; rồi dùng SLI/SLO để tạo cảnh báo và runbook.

## 1. Quan sát theo ba lớp

Không có một metric đơn lẻ nào mô tả đầy đủ tình trạng luồng. Nên chia dữ liệu quan sát thành ba lớp:

| Lớp | Cần theo dõi | Câu hỏi vận hành |
|---|---|---|
| Ứng dụng và function | Số event nhận/xử lý/thất bại, thời gian xử lý, exception, JVM, thread, connection | Function có xử lý được event không? |
| Binding và consumer | Throughput theo binding, consumer group/subscription, retry, redelivery, pause, concurrency | Binding nào đang chậm hoặc lỗi? |
| Broker và hạ tầng | Kafka lag/partition, RabbitMQ queue depth/unacked, Pulsar backlog/subscription, broker health, disk/network | Broker có tiếp nhận và phân phối dữ liệu bình thường không? |

Một luồng có thể có throughput đầu vào cao nhưng throughput đầu ra thấp. Một function có thể xử lý nhanh từng message nhưng consumer group thiếu instance nên lag vẫn tăng. Broker có thể khỏe nhưng một queue cụ thể bị dồn message vì consumer lỗi. Dashboard cần đặt các số liệu này cạnh nhau để tìm được nút thắt.

Luồng quan sát tổng quát:

    Producer / Source
        -> Broker
        -> Spring Cloud Stream binding
        -> Function / Consumer
        -> Output binding
        -> Downstream broker / service

    Application metrics ----+
    Broker exporter ---------+--> Prometheus --> Grafana dashboards
    Alert rules -------------+                 --> Alertmanager / on-call

## 2. Chọn SLI và SLO trước khi tạo dashboard

SLI (Service Level Indicator) là chỉ số đo chất lượng thực tế. SLO (Service Level Objective) là mục tiêu chất lượng trong một khoảng thời gian. Nếu chỉ thêm hàng chục biểu đồ mà không xác định mục tiêu, đội vận hành khó biết con số nào cần hành động.

Với event stream, các SLI thường hữu ích:

- **Processing success ratio:** tỷ lệ event hợp lệ được xử lý thành công.
- **End-to-end processing latency:** thời gian từ lúc event được tạo/đưa vào hệ thống đến lúc hoàn tất xử lý.
- **Consumer lag hoặc backlog:** lượng dữ liệu đang chờ consumer.
- **Oldest message age:** tuổi của message cũ nhất chưa xử lý.
- **DLQ rate:** tốc độ message bị chuyển sang dead-letter destination.
- **Availability:** khả năng binding/consumer kết nối và tiếp tục nhận xử lý.
- **Throughput:** số event vào và ra mỗi giây hoặc mỗi phút.

Ví dụ mục tiêu cho một luồng xử lý đơn hàng:

| SLI | SLO minh họa | Cách diễn giải |
|---|---|---|
| Event processing success | 99,9% trong 30 ngày | Event hợp lệ được xử lý thành công, không tính message bị từ chối theo hợp đồng |
| End-to-end latency | 99% dưới 30 giây | 99% event hoàn tất trong 30 giây kể từ mốc bắt đầu đã thống nhất |
| Backlog age | Message cũ nhất dưới 2 phút | Luồng không để event chờ quá lâu |
| DLQ rate | Dưới 0,1% event đầu vào | Lỗi không xử lý được phải hiếm và được điều tra |
| Consumer availability | 99,9% thời gian | Có consumer sẵn sàng nhận và xử lý dữ liệu |

Các con số trên chỉ là ví dụ. Mỗi luồng cần xác định loại event, giờ hoạt động, lưu lượng dự kiến, yêu cầu nghiệp vụ và cách tính mẫu số. Ví dụ, nếu producer không phát event vào ban đêm thì không thể cảnh báo chỉ vì throughput bằng 0 trong khoảng đó.

### 2.1. Xác định mẫu số và trạng thái hoàn tất

Success ratio chỉ có ý nghĩa khi định nghĩa rõ một event được xem là thành công ở thời điểm nào. Có thể là function hoàn tất, database transaction commit, output publish được xác nhận hoặc downstream xác nhận nghiệp vụ. Các mốc này khác nhau.

Đối với consumer ghi database rồi publish tiếp, cần phân biệt:
- Đã nhận message.
- Đã bắt đầu xử lý.
- Đã commit side effect nghiệp vụ.
- Đã publish output và nhận xác nhận theo delivery contract.
- Đã commit offset/ack với broker.

Không gộp tất cả thành một counter tên success nếu các bước có thể thất bại độc lập. Dùng metric riêng cho từng mốc quan trọng hoặc định nghĩa một completion boundary rõ ràng cho SLO.

## 3. Thêm Actuator và Prometheus registry

Spring Boot Actuator cung cấp các endpoint quản trị và quan sát. Micrometer là facade để ghi metric; registry chuyển metric tới hệ thống thu thập tương ứng. Với Prometheus, ứng dụng thường cần Actuator và Micrometer Prometheus registry.

Maven dependencies, để Spring Boot BOM quản lý version:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>

Ví dụ cấu hình:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,prometheus
      endpoint:
        health:
          probes:
            enabled: true
      metrics:
        tags:
          application: order-stream-processor

Prometheus thường scrape endpoint /actuator/prometheus. Endpoint health có thể được dùng để kiểm tra trạng thái ứng dụng và readiness/liveness probe. Chỉ expose endpoint cần thiết; đặt authentication, network policy hoặc reverse proxy phù hợp. Không mở rộng toàn bộ Actuator endpoint ra Internet.

Ví dụ cấu hình scrape trong Prometheus:

    scrape_configs:
      - job_name: order-stream-processor
        metrics_path: /actuator/prometheus
        static_configs:
          - targets:
              - order-stream-processor:8080

Trong Kubernetes, thường dùng ServiceMonitor/PodMonitor hoặc cơ chế discovery của nền tảng thay cho static target. Cấu hình scrape phải lấy đúng port và endpoint mà container expose.

## 4. Health endpoint không thay thế stream metrics

Health indicator trả lời một câu hỏi gần với: ứng dụng hoặc dependency có đang ở trạng thái được coi là UP không? Nó không tự cho biết backlog đang tăng, processing latency vượt SLO hay tỷ lệ DLQ cao.

Spring Boot có thể cung cấp health endpoint và readiness/liveness probes. Binder cụ thể có thể bổ sung health indicator, nhưng component hiển thị và semantics phụ thuộc binder/version/cấu hình. Hãy kiểm tra health response thực tế của ứng dụng; không giả định mọi broker hoặc mọi binding đều được kiểm tra tự động.

Một cách phân vai hợp lý:

- **Liveness:** process còn hoạt động và không ở trạng thái cần restart để tự phục hồi. Không nên làm liveness thất bại chỉ vì broker tạm thời mất kết nối, nếu điều đó khiến Kubernetes restart liên tục và làm tình hình tệ hơn.
- **Readiness:** instance có thể nhận traffic/đảm nhiệm công việc hay chưa. Nếu consumer chưa thể kết nối broker hoặc chưa sẵn sàng nhận message, readiness có thể phản ánh trạng thái đó theo chính sách ứng dụng.
- **Stream health metrics:** lag, backlog, error rate, processing duration và DLQ rate.
- **Broker health:** broker exporter/management API cung cấp trạng thái cluster, queue, partition, subscription và tài nguyên.

Nếu cần health indicator tùy chỉnh cho một điều kiện nghiệp vụ, giữ nó nhẹ và có timeout. Không gọi truy vấn broker tốn kém trong mỗi lần health check.

## 5. Ghi metric ứng dụng bằng Micrometer

Metric ứng dụng giúp trả lời function đã nhận và xử lý message ra sao. Một bộ metric cơ bản có thể gồm:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| stream.events.received | Counter | Số event đã vào ranh giới xử lý |
| stream.events.processed | Counter | Số event hoàn tất theo completion boundary |
| stream.events.failed | Counter | Số lần xử lý thất bại |
| stream.processing | Timer | Thời gian xử lý mỗi event |
| stream.events.retried | Counter | Số lần retry được ứng dụng quan sát |
| stream.dlq.published | Counter | Số event được chuyển sang DLQ |
| stream.inflight | Gauge | Số event đang được xử lý đồng thời |

Counter tăng đơn điệu và được tính rate trong Prometheus. Timer ghi số lần và phân bố thời gian, thích hợp cho p50/p95/p99. Gauge biểu diễn giá trị hiện tại, ví dụ số công việc đang in-flight; không dùng Gauge để giả lập broker lag nếu metric nguồn có thể lấy trực tiếp từ broker.

Ví dụ service ghi nhận thời gian và kết quả:

    @Component
    public class StreamMetrics {
        private final MeterRegistry registry;

        public StreamMetrics(MeterRegistry registry) {
            this.registry = registry;
        }

        public void processed(String binding, Duration duration) {
            registry.counter(
                    "stream.events.processed",
                    "binding", binding
            ).increment();

            registry.timer(
                    "stream.processing",
                    "binding", binding
            ).record(duration);
        }

        public void failed(String binding, String category) {
            registry.counter(
                    "stream.events.failed",
                    "binding", binding,
                    "category", category
            ).increment();
        }
    }

Gọi metric ở ranh giới đã định nghĩa, ví dụ sau khi nghiệp vụ commit thành công. Nếu function có nhiều bước, có thể ghi metric riêng cho validation, database commit và output publish để phân biệt lỗi.

Ví dụ bao quanh một service:

    public void handle(OrderCreated event) {
        Timer.Sample sample = Timer.start(registry);
        try {
            orderService.apply(event);
            sample.stop(registry.timer(
                    "stream.processing",
                    "binding", "orders-in"
            ));
            registry.counter(
                    "stream.events.processed",
                    "binding", "orders-in"
            ).increment();
        } catch (RuntimeException ex) {
            registry.counter(
                    "stream.events.failed",
                    "binding", "orders-in",
                    "category", classify(ex)
            ).increment();
            throw ex;
        }
    }

Đoạn code là mẫu instrumentation ở tầng ứng dụng. Nếu framework/binder đã tự instrument một phần operation, tránh đếm trùng cùng một sự kiện. Exception được ném lại để retry/error handler của Spring Cloud Stream xử lý theo cấu hình; không nuốt exception chỉ để counter success/failure trông đẹp.

## 6. Đặt tên và tag metric có kiểm soát

Tên metric nên ổn định, có đơn vị và diễn tả một sự kiện đo được. Tag dùng để lọc và nhóm theo chiều có số giá trị hữu hạn.

Tag thường phù hợp:
- application hoặc service.
- environment và region.
- binding name.
- broker type.
- topic/queue cố định.
- consumer group hoặc subscription đã biết.
- error category thuộc một tập enum nhỏ.

Không đưa các giá trị có cardinality cao vào tag:
- eventId, orderId, customerId.
- traceId, spanId.
- message payload hoặc exception message.
- timestamp chính xác.
- URL chứa ID hoặc query string.

Mỗi tổ hợp tag có thể tạo một time series riêng. Nếu gắn eventId vào metric, số series có thể tăng theo số event và làm Prometheus tốn RAM, CPU và dung lượng lưu trữ. Dùng log hoặc trace để tìm event cụ thể; dùng metric để tổng hợp.

Lỗi nên được phân nhóm ổn định, ví dụ validation, timeout, dependency, serialization và unknown. Không dùng exception message làm tag vì nội dung thường thay đổi theo request và có cardinality không giới hạn.

## 7. Histogram và latency percentiles

Average latency có thể che giấu một nhóm nhỏ message rất chậm. Timer histogram cho phép tính percentile và phân bố. Với Micrometer, cấu hình histogram trên timer phù hợp với phiên bản registry:

    management:
      metrics:
        distribution:
          percentiles-histogram:
            stream.processing: true

Prometheus có thể thu các bucket của timer để tính p95/p99. Một truy vấn p95 theo binding:

    histogram_quantile(
      0.95,
      sum by (le, binding) (
        rate(stream_processing_seconds_bucket[5m])
      )
    )

Tên metric Prometheus được chuyển đổi từ tên Micrometer và base unit của Timer; ví dụ trên giả định timer tên stream.processing được export thành stream_processing_seconds. Xác nhận tên thực tế ở /actuator/prometheus trước khi viết dashboard.

Percentile histogram có chi phí storage. Chỉ bật cho timer quan trọng, chọn bucket hợp lý và tránh tạo quá nhiều chiều tag.

## 8. Theo dõi từng broker bằng metric native

Metric ứng dụng không thể thay thế metric broker. Cần cài exporter hoặc tích hợp hệ thống monitoring mà nền tảng broker cung cấp.

| Broker | Số liệu quan trọng | Câu hỏi |
|---|---|---|
| Kafka | Consumer group lag, offset, partition, under-replicated partition, ISR, request latency, broker disk | Consumer có theo kịp topic? Partition/broker có sự cố? |
| RabbitMQ | Ready messages, unacknowledged messages, consumer count, publish/deliver/ack rate, connection/channel, memory/disk alarm | Queue nào đang dồn? Consumer có ack message? |
| Pulsar | Subscription backlog, unacked messages, connected consumers, backlog age, topic/partition stats, broker/bookie health | Subscription có xử lý backlog? Consumer có kết nối? |

Không dùng một metric tên chung cho cả ba broker. Kafka lag thường được exporter tính từ log end offset và committed offset; RabbitMQ queue depth chia thành ready và unacked; Pulsar backlog có semantics theo subscription và acknowledgement. Chọn exporter/metric chính thức phù hợp với broker version và cách triển khai.

### 8.1. Kafka

Với Kafka, dashboard nên nhóm theo topic, partition và consumer group. Các panel thường gồm:
- Lag hiện tại của từng partition và tổng lag của group.
- Tốc độ lag tăng/giảm.
- Record input rate và consumer processing rate.
- Số partition không có consumer assignment hoặc consumer đang rebalance.
- Under-replicated partitions và offline partitions.
- Request latency, broker disk và network.

Lag cao nhưng đang giảm có thể chỉ là backlog tạm thời sau một đợt tăng tải. Lag thấp nhưng liên tục tăng cũng là dấu hiệu consumer không đủ năng lực. Hãy xem cả độ lớn và xu hướng lag.

### 8.2. RabbitMQ

Với RabbitMQ, phân biệt:
- **Ready:** message đang chờ consumer nhận.
- **Unacked:** message đã giao cho consumer nhưng chưa ack.
- **Consumers:** số consumer đang đăng ký.
- **Publish/deliver/ack rate:** tốc độ vào, giao và xác nhận.
- **Redelivery:** message được giao lại.
- **Queue age/depth:** độ dài và tuổi message chờ.
- **Broker alarms:** memory/disk watermark, connection/channel pressure.

Ready tăng cho thấy consumer có thể thiếu năng lực hoặc không hoạt động. Unacked tăng kéo dài có thể do consumer xử lý chậm, treo hoặc prefetch lớn. Nếu ack rate thấp trong khi deliver rate cao, cần kiểm tra xử lý và acknowledgement.

### 8.3. Pulsar

Với Pulsar, quan sát theo topic và subscription:
- Backlog của subscription.
- Oldest unacked message hoặc backlog age nếu broker/exporter cung cấp.
- Consumer count và connection state.
- Message rate in/out.
- Redelivery và acknowledgement timeout.
- Partition distribution, broker và BookKeeper/bookie health.
- Storage usage và ledger/managed-ledger metrics.

Backlog có thể tồn tại có chủ đích khi subscription nhận dữ liệu theo lịch. Cảnh báo cần dựa trên tuổi backlog, xu hướng tăng và SLO xử lý, không chỉ một con số tuyệt đối.

## 9. Dashboard tổng quan cho toàn bộ luồng

Dashboard cấp hệ thống nên giúp on-call xác định trong vài giây luồng nào cần chú ý. Bố cục gợi ý:

| Hàng | Panel | Hiển thị |
|---|---|---|
| 1 | Overall status | Health, số binding đang hoạt động, số cảnh báo critical |
| 1 | Input vs processed rate | Event vào và event hoàn tất theo thời gian |
| 1 | Success/error ratio | Tỷ lệ lỗi theo service/binding |
| 2 | Processing latency | p50, p95, p99 |
| 2 | Consumer lag/backlog | Tổng và top binding/group/queue có backlog |
| 2 | Oldest message age | Tuổi message đang chờ lâu nhất |
| 3 | Retry and DLQ | Retry rate, DLQ rate và số message mới vào DLQ |
| 3 | Broker health | Kafka/RabbitMQ/Pulsar status và tài nguyên |
| 4 | JVM/runtime | Heap, GC pause, CPU, thread, connection pool |
| 4 | Deployments | Annotation thời điểm release, restart và config change |

Bảng tổng quan nên có biến lọc environment, service, binder, binding và consumer group. Không đưa từng event ID thành một dòng trong dashboard; dùng log/trace khi cần điều tra một event.

## 10. Dashboard chi tiết theo binding

Mỗi binding có thể có dashboard hoặc hàng panel riêng với các số liệu:
- Destination và binder type.
- Input rate và output rate.
- Processed/failed/retried count.
- p95/p99 processing time.
- Lag/backlog và oldest message age.
- Consumer instances/concurrency.
- DLQ destination và DLQ rate.
- Last successful processing timestamp.
- Deployment version.

Khi function có nhiều input/output, không gộp toàn bộ throughput thành một đường duy nhất. Ví dụ function join hai input cần theo dõi rate từng input; một input ngừng phát có thể khiến output ngừng dù input còn lại vẫn tăng.

Với pipeline nhiều chặng, dùng cùng một event correlation ID trong log/trace để theo dấu một event qua các binding. Dashboard vẫn tổng hợp theo binding; correlation ID chỉ dùng để truy vấn log/trace.

## 11. Xây dựng cảnh báo từ SLI

Cảnh báo nên kích hoạt khi có dấu hiệu ảnh hưởng người dùng hoặc nguy cơ vi phạm SLO. Không cảnh báo cho mọi metric thay đổi. Một quy tắc tốt gồm:
- Điều kiện đo rõ ràng.
- Ngưỡng và thời gian duy trì (for).
- Phạm vi binding/consumer group.
- Mức độ severity.
- Người nhận hoặc hệ thống nhận cảnh báo.
- Runbook chỉ ra bước điều tra đầu tiên.

Ví dụ ngưỡng ban đầu:

| Alert | Điều kiện minh họa | Severity |
|---|---|---|
| Processing error ratio high | Tỷ lệ lỗi trên 2% liên tục 10 phút, có đủ traffic mẫu | warning |
| Processing error critical | Tỷ lệ lỗi trên 10% trong 5 phút | critical |
| Consumer lag rising | Lag tăng liên tục và thời gian bắt kịp vượt SLO | warning/critical |
| Oldest message too old | Message cũ nhất vượt 2 phút | warning |
| DLQ receives messages | Có message mới vào DLQ trong luồng quan trọng | warning |
| No successful processing | Có input nhưng không có event hoàn tất trong khoảng dự kiến | critical |
| Broker unavailable | Broker/connection không sẵn sàng kéo dài | critical |
| State restore too long | Kafka Streams task restore vượt startup/recovery objective | warning |

Các ngưỡng cần hiệu chỉnh theo traffic, batch size, thời gian xử lý và SLO. Luồng ít traffic có thể dùng cửa sổ dài hơn hoặc kiểm tra heartbeat/source activity; luồng realtime có thể cần cửa sổ ngắn hơn.

## 12. PromQL cho metric ứng dụng

Giả sử ứng dụng export các metric custom đã nêu ở trên. Tỷ lệ lỗi trong 5 phút:

    sum(rate(stream_events_failed_total[5m]))
    /
    clamp_min(
      sum(rate(stream_events_processed_total[5m])) +
      sum(rate(stream_events_failed_total[5m])),
      1
    )

Truy vấn này chỉ là ví dụ nếu processed và failed là hai nhóm loại trừ nhau và cùng đếm theo một completion boundary. Nếu failed được retry rồi cuối cùng thành công, hãy quyết định liệu SLI đo lần thử hay event cuối cùng; có thể cần metric riêng cho attempts và unique events.

Tốc độ event hoàn tất:

    sum by (binding) (
      rate(stream_events_processed_total[5m])
    )

Tỷ lệ lỗi theo binding:

    sum by (binding) (
      rate(stream_events_failed_total[5m])
    )

p95 processing time:

    histogram_quantile(
      0.95,
      sum by (le, binding) (
        rate(stream_processing_seconds_bucket[5m])
      )
    )

Tốc độ đưa message vào DLQ:

    sum by (binding) (
      rate(stream_dlq_published_total[5m])
    )

Các tên metric là ví dụ theo quy tắc export của Micrometer Prometheus. Kiểm tra tên thực tế, label và đơn vị trước khi dùng trong production. Metric lag/backlog của exporter broker có tên khác nhau giữa các exporter; thay bằng metric thật mà nền tảng cung cấp.

## 13. Ví dụ Prometheus alert rules

Một rule có thể được định nghĩa như sau:

    groups:
      - name: spring-cloud-stream
        rules:
          - alert: StreamProcessingErrorRatioHigh
            expr: |
              (
                sum(rate(stream_events_failed_total[5m]))
                /
                clamp_min(
                  sum(rate(stream_events_processed_total[5m])) +
                  sum(rate(stream_events_failed_total[5m])),
                  1
                )
              ) > 0.02
            for: 10m
            labels:
              severity: warning
            annotations:
              summary: Stream processing error ratio is high
              runbook: /runbooks/stream-processing-errors

          - alert: StreamDlqTrafficDetected
            expr: sum(rate(stream_dlq_published_total[5m])) > 0
            for: 2m
            labels:
              severity: warning
            annotations:
              summary: Messages are being sent to a dead-letter destination
              runbook: /runbooks/stream-dlq

Đây là rule mẫu cho custom metrics. Trong production, thêm label lọc service/environment phù hợp và kiểm tra mẫu số traffic. Không áp dụng một ngưỡng lỗi chung cho mọi binding nếu độ quan trọng và volume khác nhau.

### 13.1. Cảnh báo không có traffic

Không cảnh báo chỉ vì processed rate bằng 0. Có thể không có event mới. Cần có bằng chứng rằng source đáng lẽ phải phát dữ liệu, ví dụ:
- Producer heartbeat hoặc source event rate lớn hơn 0.
- Lịch phát dữ liệu có giờ hoạt động rõ ràng.
- Broker nhận message nhưng consumer không xử lý.
- Last successful processing vượt quá khoảng thời gian kỳ vọng.

Ví dụ logic cảnh báo là input rate lớn hơn 0 trong khi processed rate bằng 0 liên tục 5 phút. Điều kiện này có ý nghĩa hơn việc chỉ kiểm tra processed rate bằng 0.

## 14. Cảnh báo lag và thời gian bắt kịp

Lag là số message/record còn chưa xử lý. Một con số lag cao không cho biết chính xác thời gian chờ; cần kết hợp tốc độ xử lý và tốc độ đầu vào.

Nếu lag là L, tốc độ xử lý là P và tốc độ đầu vào là I:
- Nếu P <= I, consumer không bắt kịp; backlog có xu hướng tiếp tục tăng.
- Nếu P > I, thời gian bắt kịp xấp xỉ L / (P - I), giả sử tốc độ tương đối ổn định.
- Nếu traffic theo burst, hãy quan sát xu hướng và percentile age thay vì tin một phép chia tức thời.

Với Kafka, dùng lag theo consumer group và partition. Với RabbitMQ, dùng ready/unacked và message age. Với Pulsar, dùng subscription backlog và backlog age. Không so sánh trực tiếp các số này nếu semantics khác nhau.

Alert lag nên cân nhắc:
- Lag vượt ngưỡng trong một khoảng thời gian.
- Lag tăng liên tục thay vì đang giảm.
- Oldest message age vi phạm SLO.
- Processing rate thấp hơn input rate kéo dài.
- Consumer count bằng 0 hoặc rebalance lặp lại.

## 15. Alertmanager và quy tắc gửi cảnh báo

Prometheus đánh giá alert rule; Alertmanager gom nhóm, khử trùng lặp, định tuyến và gửi cảnh báo tới kênh trực ca. Một cấu hình tốt cần:
- Group theo alert name, environment, service và binding.
- Inhibit alert phụ khi có cảnh báo broker/cluster lớn hơn đã bao phủ nguyên nhân.
- Thời gian repeat phù hợp để không gửi lặp quá nhiều.
- Route critical tới on-call, warning tới kênh vận hành.
- Silence có thời hạn cho maintenance đã lên lịch.
- Annotation có dashboard link và runbook.

Không gửi một notification cho từng partition nếu sự cố ảnh hưởng toàn consumer group. Group theo consumer group/topic và chỉ giữ partition label trong chi tiết để điều tra.

## 16. Kết hợp metrics, logs và traces

Ba tín hiệu bổ sung cho nhau:
- **Metrics** cho xu hướng, tỷ lệ, độ trễ và cảnh báo.
- **Logs** giải thích một lần xử lý cụ thể, exception và metadata.
- **Traces** theo dấu đường đi của một event qua nhiều service/binding.

Nên ghi các trường có ích vào structured log:
- service, environment, binding.
- event type và event ID (trong log, không làm metric tag).
- correlation ID/trace ID.
- destination hoặc consumer group cố định.
- processing result và error category.
- retry attempt nếu có.

Không log payload nhạy cảm, token, credential hoặc toàn bộ message nếu không có chính sách bảo vệ. Trace context có thể được truyền qua header theo instrumentation/binder hỗ trợ; xác nhận propagation thực tế khi event đi qua Kafka, RabbitMQ và Pulsar. Không giả định trace context luôn được giữ nguyên qua mọi converter hoặc broker.

## 17. Runbook khi cảnh báo kích hoạt

Runbook phải giúp người trực ca tìm nguyên nhân trước khi thay đổi hệ thống.

### 17.1. Processing error ratio tăng

1. Xác định service, environment và binding bị ảnh hưởng.
2. So sánh input rate, processed rate, failed rate và retry rate.
3. Xem error category và log/trace mẫu để tìm exception gốc.
4. Kiểm tra deployment gần nhất, schema change và dependency bên ngoài.
5. Xác định lỗi là dữ liệu poison, schema mismatch, timeout hay broker connectivity.
6. Nếu message lỗi được retry, kiểm tra retry budget và DLQ policy; tránh tăng retry vô hạn.
7. Sau khi sửa nguyên nhân, xác nhận error rate giảm và backlog bắt đầu xử lý lại.

### 17.2. Consumer lag hoặc backlog tăng

1. Xác định topic/queue/subscription và consumer group.
2. So sánh input rate với processing/ack rate.
3. Kiểm tra consumer count, instance restart, rebalance và connection.
4. Kiểm tra latency của database/API downstream và thread/connection pool.
5. Kiểm tra broker resource: disk, memory, network, partition health.
6. Chỉ scale consumer khi partition/queue semantics và downstream capacity cho phép.
7. Theo dõi backlog age và thời gian bắt kịp sau khi thay đổi.

### 17.3. DLQ có message mới

1. Xác định source binding, DLQ destination và error category.
2. Kiểm tra event schema, payload version và exception.
3. Xác định message có thể sửa dữ liệu hay cần sửa code/config.
4. Lưu event ID và metadata để đối soát.
5. Không replay hàng loạt trước khi consumer đã idempotent và nguyên nhân đã được sửa.
6. Replay theo batch có kiểm soát, theo dõi duplicate và backlog.
7. Xác nhận message được xử lý hoặc tiếp tục được cách ly có lý do.

## 18. Kiểm thử dashboard và alert

Dashboard và alert cũng là cấu hình cần kiểm thử. Một số cách:
- Kiểm tra Prometheus scrape target đang UP và metric xuất hiện sau khi ứng dụng khởi động.
- Gửi event thành công, event lỗi và event retry để xác nhận counter/timer tăng đúng.
- Tạo backlog trong môi trường test để xác nhận panel lag và backlog age.
- Phát message vào DLQ để xác nhận alert có kích hoạt.
- Dùng promtool check rules để kiểm tra cú pháp rule.
- Dùng promtool test rules với fixture để xác nhận ngưỡng và thời gian for.
- Kiểm tra Alertmanager route, grouping, inhibition và runbook link.
- Tạo một cảnh báo thử trong môi trường staging để xác nhận notification tới đúng nhóm.

Không thử tạo backlog hoặc làm broker mất kết nối trong production chỉ để xác nhận alert. Dùng staging hoặc failure test có phạm vi và thời gian kiểm soát.

## 19. Những lỗi thiết kế quan sát thường gặp

| Vấn đề | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ theo dõi CPU và memory | Không phát hiện lag hoặc message bị kẹt | Thêm input/output rate, backlog age, error và DLQ |
| Chỉ dùng health UP | Process khỏe nhưng luồng không tiến triển | Theo dõi tiến độ xử lý và broker metrics |
| Cảnh báo khi throughput bằng 0 ở mọi thời điểm | Alert giả khi source không phát dữ liệu | Kết hợp source activity, lịch và input rate |
| Chỉ nhìn tổng lag | Một partition/queue có thể bị nghẽn riêng | Drill-down theo partition, queue hoặc subscription |
| Dùng event ID làm metric label | Cardinality tăng rất nhanh | Đưa event ID vào log/trace |
| Chỉ nhìn average latency | Tail latency bị che khuất | Theo dõi p95/p99 bằng histogram |
| Alert không có runbook | On-call mất thời gian tìm bước đầu tiên | Thêm dashboard, owner và hướng điều tra |
| Scale consumer ngay khi lag cao | Có thể làm quá tải database/downstream | Kiểm tra bottleneck và capacity trước |
| Replay DLQ không kiểm soát | Duplicate hoặc gây backlog mới | Idempotency, batch replay và giám sát |
| Expose Actuator không bảo vệ | Lộ thông tin vận hành hoặc endpoint nhạy cảm | Giới hạn endpoint và kiểm soát truy cập |

## 20. Lộ trình triển khai observability

Có thể triển khai theo từng giai đoạn:

1. **Định nghĩa SLI/SLO:** thống nhất completion boundary, latency objective và backlog age.
2. **Bật Actuator/Micrometer:** expose health và Prometheus endpoint có kiểm soát.
3. **Thêm application metrics:** received, processed, failed, retry, DLQ và processing timer.
4. **Thu broker metrics:** Kafka lag, RabbitMQ queue metrics hoặc Pulsar subscription backlog.
5. **Tạo dashboard tổng quan:** input/output, errors, latency, backlog, DLQ và broker health.
6. **Tạo dashboard chi tiết:** drill-down theo service, binding, topic/queue/group.
7. **Tạo alert:** error ratio, lag/age, DLQ, broker availability và no-progress khi có input.
8. **Viết runbook:** mỗi alert có owner, bước điều tra và cách xác nhận phục hồi.
9. **Kiểm thử alert:** promtool, staging traffic và notification route.
10. **Rà soát định kỳ:** điều chỉnh threshold, histogram bucket, retention và cardinality theo tải thật.

## 21. Checklist trước khi đưa vào production

- [ ] Mỗi luồng có SLI/SLO và completion boundary rõ ràng.
- [ ] Có metric received, processed, failed, retry và DLQ theo binding.
- [ ] Có Timer histogram để quan sát p95/p99 processing latency.
- [ ] Metric tag chỉ dùng chiều cardinality thấp.
- [ ] Actuator chỉ expose endpoint cần thiết và được bảo vệ.
- [ ] Prometheus scrape target hoạt động và metric names đã được xác nhận.
- [ ] Có broker exporter/native metrics tương ứng với Kafka, RabbitMQ hoặc Pulsar.
- [ ] Dashboard hiển thị input/output rate, error, latency, lag/backlog, oldest age và DLQ.
- [ ] Có drill-down theo binding, consumer group, queue hoặc subscription.
- [ ] Alert dựa trên SLO, có for duration và tránh alert giả khi source không phát dữ liệu.
- [ ] Alert có severity, owner, dashboard link và runbook.
- [ ] Alertmanager grouping/inhibition/silence được cấu hình.
- [ ] Log có correlation/event ID nhưng không lộ payload hoặc secret.
- [ ] Trace propagation được kiểm tra qua broker và service boundary.
- [ ] Dashboard và alert được kiểm thử trong staging.
- [ ] Có quy trình scale consumer, xử lý DLQ và replay an toàn.

Một hệ thống Spring Cloud Stream được quan sát tốt phải cho biết dữ liệu đang đi qua từng binding như thế nào, consumer có theo kịp hay không và lỗi có ảnh hưởng tới SLO không. Kết hợp metric ứng dụng với lag/backlog native của broker, dashboard theo từng luồng và alert có runbook sẽ giúp đội vận hành phát hiện sớm tình trạng tắc nghẽn, xử lý lỗi có kiểm soát và xác nhận hệ thống đã phục hồi.

## Tài liệu tham khảo

- [Spring Boot Actuator — Metrics and Endpoints](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Concepts and Instrumentation](https://docs.micrometer.io/micrometer/reference/concepts.html)
- [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Grafana — Dashboards and Alerting](https://grafana.com/docs/grafana/latest/alerting/)
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/)

