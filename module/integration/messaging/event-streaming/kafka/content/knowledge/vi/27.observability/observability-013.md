# Dashboard cho sức khỏe cụm và một luồng nghiệp vụ cụ thể

Dashboard Kafka cần giúp hai nhóm người trả lời hai câu hỏi khác nhau nhưng liên quan chặt chẽ: cluster có đủ sức khỏe để lưu trữ và phục vụ dữ liệu không; và luồng nghiệp vụ có xử lý dữ liệu đúng, đủ, kịp thời không?

Broker có thể vẫn nhận Produce request trong khi consumer group tăng backlog. Consumer có thể đọc record nhanh nhưng xử lý database chậm. Kafka Streams có thể đang RUNNING nhưng một task bị lỗi hoặc record bị drop. Vì vậy, một dashboard chỉ có CPU, RAM và throughput chưa thể phản ánh sức khỏe của hệ thống event streaming.

Bài học này thiết kế hai dashboard liên kết với nhau: dashboard sức khỏe Kafka cluster và dashboard cho một luồng nghiệp vụ cụ thể. Ví dụ xuyên suốt là luồng xử lý đơn hàng: API nhận đơn, Kafka lưu event, Kafka Streams làm giàu dữ liệu, billing service xử lý và database ghi nhận kết quả. Các metric, SLI/SLO, Prometheus query, alert và runbook được xây dựng quanh luồng đó.

## 1. Mục tiêu và phạm vi quan sát

Một dashboard vận hành tốt cần thể hiện được:

- **Availability:** broker, controller, connector, stream application và consumer có đang hoạt động không?
- **Reliability:** partition có offline, replica có mất đồng bộ, request có lỗi, event có bị drop hoặc đưa vào DLQ không?
- **Performance:** throughput, request latency, processing latency và end-to-end latency có nằm trong giới hạn không?
- **Backlog:** producer đang tạo dữ liệu nhanh hơn consumer xử lý bao nhiêu; backlog đang tăng hay giảm?
- **Capacity:** CPU, heap, GC, disk, network, partition và connection còn đủ tài nguyên không?
- **Business outcome:** số đơn hàng được nhận, xử lý thành công, thất bại và hoàn tất có khớp với kỳ vọng nghiệp vụ không?

Dashboard không thay thế log, trace, kiểm thử hoặc quy trình xử lý sự cố. Dashboard giúp phát hiện dấu hiệu và khoanh vùng; log và trace giúp tìm nguyên nhân ở một request/event cụ thể.

## 2. Mô hình quan sát hai tầng

Dashboard nên có một tầng cluster và một tầng business flow.

~~~mermaid
flowchart TB
    subgraph DATA["Luồng nghiệp vụ đơn hàng"]
        A["orders-api"] --> B["orders topic"]
        B --> C["order-enrichment Streams"]
        C --> D["enriched-orders topic"]
        D --> E["billing-service"]
        E --> F["payment database"]
        E --> G["payment-completed event"]
    end

    subgraph SIGNALS["Nguồn tín hiệu"]
        H["Kafka broker / KRaft JMX"]
        I["Producer / Consumer JMX"]
        J["Streams / Connect JMX"]
        K["Node / JVM metrics"]
        L["Micrometer business metrics"]
        M["OpenTelemetry traces and logs"]
    end

    H --> N["Prometheus / Metrics backend"]
    I --> N
    J --> N
    K --> N
    L --> N
    M --> O["Trace and log backend"]
    N --> P["Grafana: Cluster dashboard"]
    N --> Q["Grafana: Business flow dashboard"]
    O --> Q
    N --> R["Alertmanager"]
~~~

**Dashboard sức khỏe cluster** trả lời broker, KRaft quorum, replication, storage, request handler và network có bình thường không.

**Dashboard business flow** trả lời event đi qua từng stage có đầy đủ không, thời gian xử lý có đạt SLO không, backlog nằm ở đâu và stage nào đang tạo lỗi.

Hai dashboard phải dùng chung các nhãn định danh ổn định như `cluster`, `environment`, `service`, `flow`, `topic`, `consumer_group` để người trực vận hành có thể chuyển từ panel business sang panel Kafka tương ứng.

## 3. Metrics, logs và traces bổ sung cho nhau

### 3.1. Metrics

Metrics là số liệu có thể tổng hợp theo thời gian:

- Số record được gửi/nhận mỗi giây.
- Consumer lag theo topic, partition và group.
- Tỷ lệ request lỗi.
- p95/p99 latency.
- Số partition offline hoặc under-replicated.
- Số đơn hàng hoàn tất và số đơn hàng thất bại.

Metrics phù hợp với dashboard, alert và xu hướng dài hạn.

### 3.2. Logs

Logs ghi sự kiện chi tiết của broker, connector, stream processor hoặc ứng dụng:

- Authentication/authorization failure.
- Producer send failure.
- Consumer rebalance.
- Task hoặc connector chuyển sang FAILED.
- Deserialization exception.
- Database timeout.
- Event bị đưa vào dead-letter topic.

Log nên có timestamp, service, environment, trace ID, correlation ID và topic/partition/offset khi phù hợp. Không ghi payload nhạy cảm hoặc secret vào log.

### 3.3. Distributed traces

Trace liên kết một lần xử lý qua nhiều service. Ví dụ một order có thể đi qua:

1. HTTP request tại orders-api.
2. Producer gửi event vào orders.
3. Kafka Streams đọc và làm giàu event.
4. Producer của Streams ghi enriched-orders.
5. billing-service đọc event.
6. Database commit payment.
7. Service phát payment-completed.

Trace context nên được truyền qua Kafka record headers theo chuẩn W3C Trace Context hoặc cơ chế instrumentation tương thích. Trace giúp xác định stage nào làm tăng latency, trong khi metric cho biết vấn đề có xảy ra trên diện rộng hay không.

Không dùng trace ID hoặc order ID làm label metric vì số lượng giá trị gần như không giới hạn.

## 4. Xác định SLI và SLO trước khi thiết kế panel

Không nên bắt đầu bằng việc chọn một danh sách metric dài. Trước hết cần xác định điều gì tạo nên một luồng nghiệp vụ khỏe mạnh.

### 4.1. SLI cho luồng đơn hàng

| SLI | Cách đo | Ý nghĩa |
|---|---|---|
| Ingest success rate | Event được Kafka chấp nhận / event API đã xác nhận nhận | API và producer có đưa được event vào Kafka không? |
| Processing success rate | Event được xử lý thành công / event đã đến stage xử lý | Logic Streams/service có hoàn thành không? |
| End-to-end completion rate | Đơn hàng hoàn tất / đơn hàng đã được chấp nhận | Kết quả cuối cùng có đạt không? |
| End-to-end latency | Thời gian từ event tạo đến business completion | Người dùng phải chờ bao lâu? |
| Backlog age | Tuổi của event cũ nhất chưa hoàn tất | Dữ liệu đang bị chậm bao lâu? |
| Duplicate rate | Event nghiệp vụ trùng / event đã xử lý | Idempotency có hoạt động không? |
| Dead-letter rate | Event vào DLQ / event đã xử lý | Có bao nhiêu record không xử lý được tự động? |

Tỷ lệ hoàn tất cần xác định rõ mẫu số và cửa sổ thời gian. Nếu event vừa được nhận nhưng chưa đến hạn xử lý, không nên lập tức tính nó là lỗi. Với quy trình asynchronous, cần định nghĩa thời gian chờ hợp lệ và trạng thái cuối cùng của event.

### 4.2. Ví dụ SLO

Ví dụ mục tiêu minh họa cho hệ thống orders:

- 99,9% đơn hàng được hoàn tất trong 5 giây.
- 99,95% event được chấp nhận bởi Kafka trong giờ hoạt động.
- Tỷ lệ event bị xử lý lỗi dưới 0,1% trong cửa sổ 30 phút.
- Không có partition offline.
- Không có partition nằm dưới min ISR kéo dài.
- Consumer backlog không vượt ngưỡng tuổi event do nghiệp vụ quy định.

Các con số này không phải mặc định của Kafka. Đội sản phẩm và vận hành phải chọn ngưỡng theo traffic, yêu cầu người dùng, capacity và error budget thực tế.

### 4.3. Error budget

Nếu SLO completion là 99,9%, error budget là 0,1% số event trong cửa sổ đánh giá. Khi error budget tiêu thụ nhanh, cần ưu tiên reliability work như xử lý lỗi, tăng capacity hoặc giảm thay đổi rủi ro thay vì chỉ tối ưu throughput.

Một dashboard SLO nên hiển thị:

- SLO hiện tại.
- Tỷ lệ lỗi trong cửa sổ ngắn và dài.
- Error budget còn lại.
- Burn rate.
- Số lượng event lỗi và tổng event trong cùng cửa sổ.

## 5. Kiến trúc thu thập metrics

Kafka và Java clients expose metrics qua JMX. Prometheus có thể scrape metrics được JMX Exporter chuyển thành HTTP endpoint. Ứng dụng Spring Boot có thể expose Micrometer metrics. Node exporter cung cấp số liệu hệ điều hành.

### 5.1. Thành phần chính

| Thành phần | Vai trò |
|---|---|
| Kafka JMX | Expose broker, controller, producer, consumer, Connect và Streams metrics |
| Prometheus JMX Exporter | Đọc JMX MBeans và expose Prometheus metrics |
| Micrometer | Thu thập metric nghiệp vụ trong Spring Boot/Java |
| Node exporter | CPU, RAM, filesystem, network và disk của host |
| Consumer lag exporter | Tính group lag từ committed offsets và log-end offsets |
| Prometheus | Scrape, lưu trữ và query time-series |
| Grafana | Dashboard và khám phá metric |
| Alertmanager | Group, route và gửi cảnh báo |
| OpenTelemetry Collector | Thu nhận, xử lý và chuyển trace/log/metric theo kiến trúc observability |

Kafka 4.4 expose broker và Java client metrics qua JMX. Remote JMX bị tắt mặc định; nếu bật remote JMX, phải bảo vệ authentication, network access và quyền quản trị. Không mở JMX port ra Internet hoặc mạng không tin cậy.

### 5.2. Dùng JMX Exporter Java agent

Java agent chạy trong JVM của broker hoặc ứng dụng. Đây thường là cách triển khai đơn giản hơn remote JMX/RMI.

Ví dụ khởi động một Java process với agent:

~~~bash
java \
  -javaagent:jmx_prometheus_javaagent.jar=127.0.0.1:9404:exporter.yaml \
  -jar application.jar
~~~

Agent mở endpoint metrics trên địa chỉ loopback port 9404. Nếu Prometheus ở host/container khác, cấu hình bind address và network policy phù hợp để Prometheus truy cập được, nhưng endpoint vẫn phải giới hạn trong mạng monitoring.

Với Kafka broker, thêm agent vào JVM options của broker theo cơ chế startup của distribution hoặc container image đang sử dụng. Không nhầm JMX Exporter Java agent với biến `JMX_PORT`: agent scrape MBeans trong JVM và expose HTTP, còn remote JMX mở cổng JMX/RMI.

### 5.3. Prometheus scrape configuration

Ví dụ cấu hình Prometheus:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: kafka-brokers
    static_configs:
      - targets:
          - broker-1:9404
          - broker-2:9404
          - broker-3:9404
        labels:
          cluster: kafka-prod
          environment: production

  - job_name: kafka-connect
    static_configs:
      - targets:
          - connect-1:9404
          - connect-2:9404
        labels:
          cluster: kafka-prod
          environment: production

  - job_name: business-services
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - orders-api:8080
          - billing-service:8080
          - order-streams:8081
        labels:
          environment: production

  - job_name: node-exporter
    static_configs:
      - targets:
          - broker-1:9100
          - broker-2:9100
          - broker-3:9100
        labels:
          cluster: kafka-prod
          environment: production
~~~

Đây là ví dụ cấu trúc scrape. Tên host, port, metrics path và nhãn cần điều chỉnh theo môi trường. Với Spring Boot, cần có Prometheus registry dependency và expose endpoint Actuator tương ứng.

### 5.4. Chọn metric mapping cho JMX Exporter

JMX Exporter có thể ánh xạ MBean object name và attribute thành metric name/label. Nên định nghĩa rule rõ ràng cho các MBean cần dùng thay vì scrape mọi MBean rồi đưa toàn bộ vào dashboard.

Ví dụ metric chuẩn hóa có thể dùng:

| Kafka MBean / Attribute | Metric chuẩn hóa gợi ý |
|---|---|
| ReplicaManager / UnderReplicatedPartitions | `kafka_server_under_replicated_partitions` |
| ReplicaManager / UnderMinIsrPartitionCount | `kafka_server_under_min_isr_partition_count` |
| ReplicaManager / OfflineReplicaCount | `kafka_server_offline_replica_count` |
| KafkaController / OfflinePartitionsCount | `kafka_controller_offline_partitions` |
| KafkaController / ActiveControllerCount | `kafka_controller_active_count` |
| BrokerTopicMetrics / BytesInPerSec | `kafka_server_bytes_in_per_second` |
| BrokerTopicMetrics / BytesOutPerSec | `kafka_server_bytes_out_per_second` |

Tên metric bên trên là quy ước chuẩn hóa minh họa cho exporter rule. Tên thực tế phụ thuộc mapping configuration; phải kiểm tra endpoint `/metrics` trước khi viết PromQL.

## 6. Dashboard sức khỏe Kafka cluster

Dashboard cluster nên có một hàng tổng quan dễ đọc, sau đó là các nhóm chi tiết theo availability, replication, request, capacity và KRaft.

### 6.1. Hàng tổng quan

| Panel | Metric / nguồn dữ liệu | Trạng thái kỳ vọng |
|---|---|---|
| Broker up | Prometheus `up` theo broker target | Tất cả broker mục tiêu đang scrape được |
| Active broker count | KRaft controller metric | Bằng số broker dự kiến |
| Active controller count | `ActiveControllerCount` | Tổng cluster đúng một controller active |
| Offline partitions | `OfflinePartitionsCount` | 0 |
| Under-replicated partitions | `UnderReplicatedPartitions` | 0 khi cluster ổn định |
| Under-min-ISR partitions | `UnderMinIsrPartitionCount` | 0 |
| Unclean leader elections | `UncleanLeaderElectionsPerSec` | 0 trong vận hành bình thường |
| Disk free | Node exporter | Còn đủ headroom theo retention và tốc độ ghi |

Các panel tổng quan nên có giá trị hiện tại, trend trong 1 giờ và link drill-down đến broker/topic/partition liên quan.

### 6.2. Availability và replication

Nhóm metric quan trọng:

| Metric Kafka 4.4 | Ý nghĩa |
|---|---|
| `UnderReplicatedPartitions` | Số partition có ISR nhỏ hơn số replica được cấu hình |
| `UnderMinIsrPartitionCount` | Số partition có ISR thấp hơn `min.insync.replicas` |
| `OfflineReplicaCount` | Số replica offline trên broker |
| `OfflinePartitionsCount` | Số partition offline do controller quan sát |
| `IsrShrinksPerSec` | Tốc độ ISR shrink |
| `IsrExpandsPerSec` | Tốc độ ISR expansion |
| `UncleanLeaderElectionsPerSec` | Leader election không bảo đảm chọn từ ISR |
| `LeaderElectionRateAndTimeMs` | Tần suất và thời gian leader election |
| `PartitionCount` | Số partition trên từng broker |
| `LeaderCount` | Số leader replica trên từng broker |

URP có thể xuất hiện tạm thời trong lúc broker restart hoặc replica catch-up. Cần kết hợp thời gian kéo dài, ISR shrink, broker availability và business impact để chọn severity.

`UnderMinIsrPartitionCount > 0` nghiêm trọng hơn URP thông thường vì producer dùng `acks=all` có thể không đáp ứng điều kiện ghi theo `min.insync.replicas`.

Một số ReplicaManager metrics được expose theo từng broker. Hiển thị giá trị theo broker để tìm node có vấn đề; khi tổng hợp cấp cluster, chỉ dùng phép sum nếu exporter đã tạo series duy nhất theo partition. Nếu đang scrape gauge lặp lại trên nhiều broker, dùng max hoặc deduplicate theo topic/partition để tránh đếm một partition nhiều lần.

### 6.3. Request performance

Theo dõi request type Produce, FetchConsumer và FetchFollower:

- Request rate.
- Error rate theo request type và error code.
- Request total time.
- Request queue time.
- Local processing time.
- Remote wait time.
- Response send time.
- Request queue size.

`TotalTimeMs` được chia thành các thành phần queue, local, remote và response send. Điều này giúp xác định bottleneck:

- Queue time tăng: request đang chờ worker xử lý.
- Local time tăng: broker xử lý request chậm, có thể do CPU, disk hoặc workload.
- Remote time tăng ở Produce với `acks=all`: follower replica có thể chậm.
- Response send time tăng: có thể có vấn đề network hoặc client đọc response chậm.

### 6.4. Network và thread pool

Các metric quan trọng:

- `NetworkProcessorAvgIdlePercent`: tỷ lệ network processor nhàn rỗi.
- `RequestHandlerAvgIdlePercent`: tỷ lệ request handler nhàn rỗi.
- `RequestQueueSize`: số request đang chờ xử lý.
- Bytes in/out theo broker và topic.
- Replication bytes in/out.

Kafka documentation đưa ra giá trị idle ratio lớn hơn khoảng 0,3 như một tham khảo tốt. Đây không phải ngưỡng cứng; phải đối chiếu với traffic, CPU và request latency của cluster.

Nếu idle ratio giảm kéo dài cùng request queue và latency tăng, broker có thể đang bão hòa.

### 6.5. Storage và host capacity

Kafka JMX phản ánh log directory, partition và segment. Node exporter bổ sung số liệu hệ điều hành.

| Nhóm | Metric |
|---|---|
| Disk | Free bytes, utilization, read/write latency, IOPS |
| CPU | CPU usage, load average, throttling trong container |
| Memory | Available memory, JVM heap, direct memory |
| JVM | GC pause, allocation rate, thread count |
| Network | Receive/transmit bytes, errors, drops |
| File descriptors | Open descriptors và giới hạn process |

Kafka thường dùng page cache của hệ điều hành. Không kết luận broker thiếu RAM chỉ dựa vào JVM heap thấp hoặc process RSS cao; cần xem page cache, disk latency và GC cùng lúc.

### 6.6. KRaft quorum và metadata log

Với Kafka chạy KRaft, dashboard cần có một hàng riêng cho quorum:

| Metric | Ý nghĩa |
|---|---|
| Current State | Trạng thái thành viên quorum: leader, follower, candidate... |
| Current Leader | ID của quorum leader |
| Current Epoch | Epoch hiện tại |
| High Watermark | Vị trí đã commit trong metadata log |
| Log End Offset | End offset của metadata log |
| Commit Latency | Thời gian commit record |
| Election Latency | Thời gian bầu leader |
| Active Controller Count | Controller active trên node |
| Fenced Broker Count | Broker bị fence |
| Active Broker Count | Broker active theo controller |
| OfflinePartitionsCount | Partition offline |
| MetadataErrorCount | Lỗi xử lý metadata ở controller |
| Metadata Load/Apply Error Count | Lỗi load hoặc apply metadata trên broker |

Một cluster KRaft ổn định cần quorum có leader, các member theo kịp metadata log và controller không liên tục bầu lại leader. Theo dõi cả commit/election latency và error count, không chỉ nhìn process controller còn sống.

### 6.7. Group coordinator health

Kafka 4.4 có broker-side metrics cho group coordinator. Nhóm này hữu ích khi consumer group hoặc Streams group rebalance thường xuyên, join chậm hoặc coordinator bị quá tải:

- `consumer-group-count` theo state như Empty, Assigning, Reconciling, Stable và Dead.
- `consumer-group-rebalance-rate` và `consumer-group-rebalance-count`.
- `streams-group-count` theo state và `streams-group-rebalance-rate`.
- `event-queue-size` và `event-queue-time-ms-p95/p99`.
- `event-processing-time-ms-p95/p99`.
- `partition-load-time-max/avg` khi coordinator load offsets/group metadata.
- `thread-idle-ratio-avg` của coordinator thread.

Nếu rebalance tăng cùng event queue time hoặc partition load time, kiểm tra coordinator load, số lượng group, số partition của `__consumer_offsets` và broker đang host các offsets partitions. Khi đó nguyên nhân có thể nằm ở group coordination thay vì business processor.

## 7. Dashboard Producer và Consumer

### 7.1. Producer metrics

| Metric | Câu hỏi vận hành |
|---|---|
| `record-send-rate` | Producer đang gửi bao nhiêu record/giây? |
| `record-error-rate` | Có bao nhiêu lần gửi lỗi? |
| `record-retry-rate` | Có bao nhiêu lần retry? |
| `request-latency-avg/max` | Request đến broker mất bao lâu? |
| `record-queue-time-avg/max` | Batch chờ trong send buffer bao lâu? |
| `buffer-available-bytes` | Producer còn bao nhiêu buffer? |
| `bufferpool-wait-ratio` | Thread gửi có phải chờ buffer không? |
| `produce-throttle-time-avg/max` | Broker đang throttle producer bao lâu? |
| `requests-in-flight` | Có bao nhiêu request đang chờ response? |

Nếu retry tăng nhưng error cuối cùng vẫn thấp, producer có thể đang tự phục hồi trước một đợt broker/network instability. Nếu retry, request latency và buffer wait cùng tăng, throughput có thể sớm giảm.

### 7.2. Consumer metrics

| Metric | Ý nghĩa |
|---|---|
| `records-consumed-rate` | Tốc độ đọc record |
| `bytes-consumed-rate` | Tốc độ đọc byte |
| `records-lag` | Lag theo partition dựa trên current position |
| `records-lag-max` | Lag lớn nhất theo partition trong cửa sổ metric |
| `commit-latency-avg/max` | Độ trễ commit offset |
| `assigned-partitions` | Số partition đang được consumer sở hữu |
| `rebalance-total` | Tổng số lần tham gia rebalance |
| `failed-rebalance-total` | Tổng số rebalance thất bại |
| `last-poll-seconds-ago` | Thời gian từ lần poll gần nhất |
| `time-between-poll-max` | Khoảng cách lớn nhất giữa hai lần poll |
| `fetch-throttle-time-avg/max` | Thời gian broker throttle fetch |

Consumer lag và throughput phải được xem cùng nhau. Lag tăng trong khi consume rate bằng 0 có thể là consumer chết, mất assignment, bị block hoặc gặp lỗi processing. Lag cao nhưng consume rate cũng cao có thể là consumer đang xử lý backlog và dần bắt kịp.

## 8. Consumer group lag: đo đúng backlog

### 8.1. Lag theo committed offset

Một cách tính phổ biến cho mỗi partition:

~~~text
consumer_group_lag = log_end_offset - committed_offset
~~~

Ví dụ:

| Partition | Log end offset | Committed offset | Lag |
|---|---:|---:|---:|
| 0 | 12.000 | 11.700 | 300 |
| 1 | 18.500 | 18.100 | 400 |
| 2 | 9.200 | 9.150 | 50 |

Tổng lag của group là 750 record. Tuy nhiên, cần xem cả lag lớn nhất của một partition; một partition bị kẹt có thể bị che khuất bởi tổng lag toàn group.

Nếu consumer group chưa từng commit offset, exporter có thể trả về -1 hoặc không có series. Không cộng giá trị -1 vào tổng lag. Cần hiển thị trạng thái chưa có committed offset riêng.

Với topic transactional và consumer dùng `read_committed`, dữ liệu nhìn thấy còn phụ thuộc Last Stable Offset. Phải hiểu semantics của exporter khi đối chiếu LEO và committed offset.

### 8.2. Phân biệt current position và committed offset

Kafka consumer metric `records-lag-max` dựa trên current offset, không phải committed offset. Current position có thể tiến xa hơn committed offset nếu consumer đã fetch record nhưng chưa commit.

Vì vậy, cần thêm exporter hoặc công cụ đọc consumer group offsets để tính lag theo committed offset. Không lấy một metric client `records-lag-max` rồi gọi nó là toàn bộ group backlog.

### 8.3. Lag theo record chưa đủ

Lag 10.000 record có thể tương ứng vài giây trong topic traffic cao, nhưng có thể tương ứng hàng giờ trong topic ít traffic.

Dashboard business cần thêm:

- Age của event cũ nhất chưa hoàn tất.
- Thời gian backlog dự kiến được xử lý hết.
- Tốc độ tạo event mới.
- Tốc độ xử lý event.
- Xu hướng lag trong 5, 15 và 60 phút.

Oldest event age không phải một metric group-lag mặc định. Có thể instrument gauge/histogram từ event timestamp và trạng thái hoàn tất trong ứng dụng, hoặc dùng exporter đọc timestamp của offset chưa xử lý theo từng partition. Cần xác định rõ timestamp nguồn và xử lý clock skew.

Nếu tốc độ xử lý lớn hơn tốc độ sản xuất, backlog có thể giảm. Nếu tốc độ xử lý thấp hơn tốc độ sản xuất trong thời gian dài, backlog sẽ tiếp tục tăng.

### 8.4. Dashboard lag nên có ba cấp

1. **Group overview:** tổng lag, số member, số partition assigned, group state.
2. **Topic overview:** lag tổng và lag max theo topic.
3. **Partition detail:** committed offset, log end offset, lag, leader broker và consumer member đang sở hữu partition.

Tạo link drill-down từ business flow panel đến group/topic/partition tương ứng.

## 9. Kafka Connect metrics

Với Kafka Connect, theo dõi cả connector và task.

| Metric | Ý nghĩa |
|---|---|
| `status` | Task đang running, paused, failed hay restarting |
| `running-ratio` | Tỷ lệ thời gian task ở trạng thái running |
| `source-record-poll-rate` | Tốc độ source poll record |
| `source-record-write-rate` | Tốc độ source ghi record vào Kafka |
| `sink-record-read-rate` | Tốc độ sink đọc record từ Kafka |
| `sink-record-send-rate` | Tốc độ sink gửi record tới hệ thống đích |
| `sink-record-lag-max` | Lag tối đa của sink task |
| `offset-commit-failure-percentage` | Tỷ lệ commit offset thất bại |
| `total-record-errors` | Tổng số record processing errors |
| `total-record-failures` | Tổng số record failures |
| `total-records-skipped` | Tổng record bị skip |
| `total-retries` | Tổng số retry |
| `deadletterqueue-produce-failures` | Số lần ghi DLQ thất bại |

Dashboard Connect cần hiển thị connector status và từng task status. Connector có thể ở trạng thái RUNNING nhưng một task cụ thể FAILED; chỉ nhìn trạng thái connector tổng thể có thể bỏ sót lỗi.

Nếu source poll rate cao nhưng source write rate thấp, kiểm tra transformation, serialization, producer hoặc broker. Nếu sink read rate cao nhưng sink send rate thấp, kiểm tra hệ thống đích, batch put latency và retry.

## 10. Kafka Streams metrics

Kafka Streams có hierarchy metrics gồm client, stream thread, task, processor node và state store.

### 10.1. Client-level

- `state`: trạng thái KafkaStreams client.
- `alive-stream-threads`: số stream thread còn sống.
- `failed-stream-threads`: số stream thread lỗi kể từ lúc khởi động.
- `application-id`: logical application ID.

### 10.2. Thread-level

- `process-rate`: tốc độ record được xử lý.
- `process-latency-avg/max`: thời gian xử lý.
- `poll-rate`: tốc độ consumer poll.
- `commit-rate`: tốc độ commit.
- `task-created-rate` và `task-closed-rate`.
- `blocked-time-ns-total`: thời gian thread bị block bởi broker.
- Rebalance callback latency.

### 10.3. Task và processor node

- `process-rate` và `process-latency`.
- `record-lateness-avg/max`.
- `dropped-records-rate/total`.
- `active-buffer-count`.
- `record-e2e-latency-avg/max` tại processor node hỗ trợ metric.
- `records-consumed-total` và `records-produced-total`.

Metric record E2E của Streams dựa trên record timestamp so với thời điểm xử lý. Ở terminal node, thời gian hoàn tất có thể được ghi theo batch và là upper bound cho latency từng record trong batch. Nếu SLO yêu cầu đo đến lúc database commit hoặc business completion, hãy instrument metric nghiệp vụ ở ứng dụng như phần sau.

### 10.4. State store

- get/put latency.
- iterator/range latency.
- RocksDB metrics.
- Store size, disk usage và cache.
- State restore duration và restore rate.

Kafka 4.4 có ba recording levels `info`, `debug` và `trace`. Dùng `info` làm mức cơ bản. Chỉ bật `debug`/`trace` cho những ứng dụng hoặc khoảng thời gian cần phân tích sâu vì số lượng metric có thể tăng mạnh theo thread, task, processor node và state store.

## 11. Dashboard cho luồng nghiệp vụ đơn hàng

Ví dụ flow:

~~~mermaid
flowchart LR
    A["Orders API"] -->|accepted| B["orders"]
    B -->|consumed| C["Order Enrichment"]
    C -->|produced| D["enriched-orders"]
    D -->|consumed| E["Billing Service"]
    E -->|database commit| F["Payment DB"]
    E -->|completed event| G["payment-completed"]
~~~

Mỗi stage cần có tín hiệu vào, tín hiệu ra, lỗi và latency.

### 11.1. Hàng tổng quan nghiệp vụ

| Panel | Metric |
|---|---|
| Orders accepted | Tổng đơn hàng được API chấp nhận |
| Orders published | Event đã được gửi vào Kafka |
| Orders enriched | Event đã qua Kafka Streams |
| Payments completed | Database đã ghi nhận thanh toán |
| End-to-end p99 | p99 từ thời điểm nhận đơn đến completion |
| Oldest unfinished event age | Tuổi event chưa hoàn tất lâu nhất |
| Processing error rate | Tỷ lệ event xử lý lỗi |
| DLQ rate | Tỷ lệ event đi vào dead-letter topic |

Panel `Payments completed` phải đo trạng thái nghiệp vụ cuối cùng. Không dùng số record Produce thành công làm đại diện cho số đơn hàng hoàn tất.

### 11.2. Stage throughput

Theo dõi các đường:

- Orders API accepted/sec.
- Producer send/sec.
- Streams input processed/sec.
- Streams output produced/sec.
- Billing consumer processed/sec.
- Payment DB commit/sec.
- Payment-completed event/sec.

Nếu input 1.000 event/s nhưng output chỉ 800 event/s trong thời gian kéo dài, cần điều tra chênh lệch 200 event/s. Chênh lệch có thể do filter hợp lệ, retry, DLQ, lỗi hoặc backlog; dashboard cần hiển thị các nhóm này để tránh kết luận sai.

### 11.3. End-to-end latency

Đo từ thời điểm event được tạo/nhận đến thời điểm nghiệp vụ hoàn tất.

~~~text
e2e_latency = completed_at - event_created_at
~~~

Theo dõi p50, p95 và p99. Average có thể che khuất một nhóm event bị chậm rất lâu.

Nếu timestamp được tạo ở nhiều máy, đồng hồ hệ thống cần đồng bộ. Clock skew có thể làm latency âm hoặc sai lệch. Với trace, có thể đo duration theo span; với business event, cần thống nhất timestamp semantics.

### 11.4. Backlog age và time to drain

Backlog age cho biết event cũ nhất đã chờ bao lâu. Time to drain ước lượng thời gian cần để xử lý backlog hiện tại:

~~~text
net_processing_rate = consumer_processing_rate - producer_arrival_rate

time_to_drain = backlog / net_processing_rate
~~~

Công thức chỉ có ý nghĩa khi net processing rate dương. Nếu consumer xử lý không nhanh hơn tốc độ event mới đến, backlog không thể tự giảm. Khi net rate bằng hoặc âm, dashboard nên hiển thị “không thể drain ở throughput hiện tại”.

### 11.5. Error, retry và DLQ

Tách riêng:

- Validation errors ở API.
- Producer errors.
- Deserialization errors.
- Business processing failures.
- Database errors.
- Retry attempts.
- DLQ records.
- Event bị skip có chủ đích.

Retry tăng không nhất thiết là event cuối cùng thất bại. DLQ tăng có thể là dấu hiệu cần can thiệp nghiệp vụ. Nếu event bị skip, cần metric và audit record để biết event nào bị bỏ qua theo policy.

## 12. Instrument metric nghiệp vụ trong Spring Boot

Kafka JMX không biết đơn hàng đã thanh toán thành công hay chưa. Ứng dụng cần tự phát hành metric phản ánh business outcome.

Ví dụ dùng Micrometer:

~~~java
import java.time.Duration;
import java.time.Instant;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class OrderFlowMetrics {

    private final Counter accepted;
    private final Counter published;
    private final Counter enriched;
    private final Counter completed;
    private final Counter failed;
    private final Counter retried;
    private final Counter deadLettered;
    private final Timer endToEnd;

    public OrderFlowMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("business.events.accepted")
            .tag("flow", "orders")
            .register(registry);

        this.published = Counter.builder("business.events.published")
            .tag("flow", "orders")
            .register(registry);

        this.enriched = Counter.builder("business.events.enriched")
            .tag("flow", "orders")
            .register(registry);

        this.completed = Counter.builder("business.events.completed")
            .tag("flow", "orders")
            .register(registry);

        this.failed = Counter.builder("business.events.failed")
            .tag("flow", "orders")
            .register(registry);

        this.retried = Counter.builder("business.events.retried")
            .tag("flow", "orders")
            .register(registry);

        this.deadLettered = Counter.builder("business.events.dead_lettered")
            .tag("flow", "orders")
            .register(registry);

        this.endToEnd = Timer.builder("business.event.e2e")
            .tag("flow", "orders")
            .publishPercentileHistogram()
            .register(registry);
    }

    public void onAccepted() {
        accepted.increment();
    }

    public void onPublished() {
        published.increment();
    }

    public void onEnriched() {
        enriched.increment();
    }

    public void onCompleted(Instant eventCreatedAt) {
        completed.increment();
        Duration duration = Duration.between(
            eventCreatedAt,
            Instant.now()
        );

        if (!duration.isNegative()) {
            endToEnd.record(duration);
        }
    }

    public void onFailed() {
        failed.increment();
    }

    public void onRetried() {
        retried.increment();
    }

    public void onDeadLettered() {
        deadLettered.increment();
    }
}
~~~

Đây là ví dụ instrument metric; cần gọi các method ở đúng điểm nghiệp vụ:

- `onAccepted()` sau khi API chấp nhận yêu cầu theo định nghĩa đã chọn.
- `onPublished()` sau khi producer nhận xác nhận gửi thành công theo delivery semantics của ứng dụng.
- `onEnriched()` sau khi stage enrichment hoàn tất và output được phát ra thành công.
- `onCompleted()` sau khi transaction database commit thành công hoặc business completion được xác nhận.
- `onFailed()` chỉ khi event thất bại cuối cùng và không còn retry theo policy. Không tăng counter này cho mọi lần thử lỗi tạm thời.
- `onRetried()` mỗi lần retry thực sự được thực hiện.
- `onDeadLettered()` khi record được ghi vào DLQ thành công.

Nếu metric completion được tăng trước database commit, dashboard có thể báo thành công dù transaction rollback. Hãy đặt instrumentation ở đúng ranh giới nghiệp vụ.

Nếu cần theo dõi cả lỗi tạm thời, tạo thêm counter riêng như `business.events.attempt_failed`; giữ `business.events.failed` cho terminal failure để tỷ lệ thất bại nghiệp vụ không bị phóng đại bởi retry.

Các metric ví dụ sẽ được export dưới dạng Prometheus counter và histogram theo naming convention của Micrometer. Tên chính xác cần xác nhận trên `/actuator/prometheus`.

### 12.1. Không dùng ID nghiệp vụ làm metric label

Không thêm các label sau:

- `order_id`
- `customer_id`
- `payment_id`
- `trace_id`
- `request_id`
- email hoặc username

Mỗi giá trị mới có thể tạo một time series riêng, làm tăng cardinality và tải Prometheus. Đưa ID vào structured log hoặc trace attribute để điều tra một giao dịch cụ thể.

Label phù hợp thường có số giá trị hữu hạn:

- `environment`
- `service`
- `flow`
- `stage`
- `topic`
- `result`
- `error_type` đã chuẩn hóa

## 13. PromQL cho dashboard

Tên metric Kafka JMX phụ thuộc rule mapping của exporter. Các query cluster bên dưới dùng tên chuẩn hóa trong phần exporter configuration. Query business dùng metric contract của ví dụ Micrometer.

### 13.1. Target availability

~~~promql
up{job="kafka-brokers"}
~~~

Panel theo broker để thấy target nào không scrape được. `up=0` có thể là process chết, endpoint exporter không truy cập được hoặc lỗi mạng monitoring; cần kiểm tra broker health riêng.

### 13.2. Under-replicated partitions

~~~promql
max by (cluster) (
  kafka_server_under_replicated_partitions
)
~~~

Nếu metric được scrape trên từng broker, query này hiển thị giá trị lớn nhất ở một broker. Muốn có tổng partition duy nhất toàn cluster, cần metric đã deduplicate theo topic/partition.

### 13.3. Under-min-ISR partitions

~~~promql
max by (cluster) (
  kafka_server_under_min_isr_partition_count
)
~~~

Query này giả định exporter đang expose gauge theo từng broker. Nếu exporter cung cấp series duy nhất theo partition, hãy tổng hợp theo partition thay vì lấy max.

### 13.4. Offline partitions

~~~promql
max by (cluster) (
  kafka_controller_offline_partitions
)
~~~

### 13.5. Orders accepted throughput

~~~promql
sum by (flow) (
  rate(business_events_accepted_total[5m])
)
~~~

Đây là tốc độ API chấp nhận đơn hàng. Để đo producer send rate, dùng Kafka producer `record-send-rate` hoặc metric producer đã chuẩn hóa theo client/topic.

### 13.6. Business completion throughput

~~~promql
sum by (flow) (
  rate(business_events_completed_total[5m])
)
~~~

### 13.7. Processing failure ratio

~~~promql
sum by (flow) (
  rate(business_events_failed_total[5m])
)
/
clamp_min(
  sum by (flow) (
    rate(business_events_completed_total[5m])
    + rate(business_events_failed_total[5m])
  ),
  1e-9
)
~~~

Đây là tỷ lệ terminal failure trên các event đã có kết quả cuối cùng trong cửa sổ đo. Nếu cần tỷ lệ trên event đã được chấp nhận, phải tính mẫu số theo event cohort và trạng thái hoàn tất trong cửa sổ phù hợp; không lấy accepted trong 5 phút chia failed trong 5 phút nếu event có thể mất nhiều phút mới hoàn tất.

### 13.8. End-to-end p99

~~~promql
histogram_quantile(
  0.99,
  sum by (le, flow) (
    rate(business_event_e2e_seconds_bucket[5m])
  )
)
~~~

Histogram phải được bật ở ứng dụng. Nếu chỉ xuất client-side percentile mà không xuất histogram buckets, query `histogram_quantile` sẽ không hoạt động.

### 13.9. Consumer group lag

~~~promql
sum by (cluster, consumer_group, topic) (
  kafka_consumergroup_lag
)
~~~

Metric `kafka_consumergroup_lag` là ví dụ từ group lag exporter, không phải metric built-in của Kafka broker. Xác nhận label và cách exporter tính offset trước khi sử dụng.

### 13.10. Lag lớn nhất theo partition

~~~promql
max by (cluster, consumer_group, topic) (
  kafka_consumergroup_lag
)
~~~

Panel này giúp phát hiện một partition bị kẹt dù tổng lag toàn topic vẫn nhỏ.

## 14. Thiết kế layout Grafana

### 14.1. Dashboard 1: Kafka Cluster Overview

| Vị trí | Panel | Visualization |
|---|---|---|
| Hàng 1 | Broker up, active controller, offline partitions, URP, under-min-ISR | Stat |
| Hàng 2 | Produce/Fetch request rate và bytes in/out | Time series |
| Hàng 3 | Request p95/p99, request queue, network/request-handler idle | Time series |
| Hàng 4 | ISR shrink/expand, leader election, replica lag | Time series |
| Hàng 5 | Partition/leader distribution theo broker | Bar chart |
| Hàng 6 | Disk free, CPU, heap, GC pause, network | Time series |
| Hàng 7 | KRaft quorum state, leader, commit/election latency | Stat + time series |
| Hàng 8 | Offline log directories, retention, reassignment | Table + time series |

Biến dashboard cần có:

- `cluster`
- `environment`
- `broker_id`
- `topic`
- `request_type`
- `time_range`

Mặc định chọn toàn cluster; khi có sự cố, người trực chọn broker hoặc topic để drill-down.

### 14.2. Dashboard 2: Orders Business Flow

| Vị trí | Panel | Visualization |
|---|---|---|
| Hàng 1 | Accepted, completed, failure rate, DLQ, E2E p99 | Stat |
| Hàng 2 | Throughput từng stage | Time series |
| Hàng 3 | E2E latency p50/p95/p99 | Time series |
| Hàng 4 | Consumer lag tổng và max theo topic/group | Time series |
| Hàng 5 | Oldest event age và time to drain | Stat + time series |
| Hàng 6 | Retry, processing error, DLQ theo stage | Time series |
| Hàng 7 | Streams state/thread health và Connect task status | Table |
| Hàng 8 | Trace exemplars và log links | Links / trace view |

Biến dashboard cần có:

- `flow`
- `environment`
- `cluster`
- `topic`
- `consumer_group`
- `service`
- `stage`

Nên thêm link từ panel E2E latency đến trace backend và link từ panel lag đến consumer group detail.

### 14.3. Drill-down từ business sang cluster

Ví dụ người trực thấy Orders E2E p99 tăng:

1. Mở panel throughput để xem stage nào bị giảm.
2. Mở consumer lag để xác định topic/group bị backlog.
3. Mở cluster dashboard với topic và broker liên quan.
4. Kiểm tra request latency, ISR, disk, network và broker saturation.
5. Mở trace của event chậm để xác định thời gian nằm ở Kafka, Streams hay database.
6. Mở log theo trace ID hoặc topic/partition/offset để tìm lỗi cụ thể.

Dashboard tốt giúp giảm số bước cần thiết để chuyển từ triệu chứng đến nguyên nhân.

## 15. Alerting: cảnh báo theo tác động

Không tạo alert cho mọi metric khác 0. Alert nên có severity, thời gian kéo dài, điều kiện và hướng xử lý.

### 15.1. Cluster alerts

| Alert | Điều kiện tham khảo | Severity |
|---|---|---|
| BrokerDown | Broker target down kéo dài | Critical |
| OfflinePartitions | Offline partition > 0 | Critical |
| UnderMinISR | Partition dưới min ISR > 0 | Critical |
| UnderReplicatedPartitions | URP > 0 kéo dài | Warning/Critical tùy phạm vi |
| UncleanLeaderElection | Có unclean election | Critical |
| ControllerElectionChurn | Controller election tăng bất thường | Critical |
| DiskLow | Disk free thấp hơn ngưỡng an toàn | Warning/Critical |
| BrokerRequestSaturation | Idle ratio thấp cùng queue/latency tăng | Warning |
| KRaftQuorumDegraded | Không có quorum leader hoặc commit latency tăng mạnh | Critical |

### 15.2. Business alerts

| Alert | Điều kiện tham khảo | Severity |
|---|---|---|
| OrdersCompletionSLOBurn | Burn rate vượt ngưỡng | Critical |
| OrdersE2ELatencyHigh | p99 vượt SLO liên tục | Warning/Critical |
| ConsumerLagGrowing | Lag cao và tiếp tục tăng | Warning |
| OldestEventTooOld | Event chưa hoàn tất vượt tuổi cho phép | Critical |
| ProcessingErrorRateHigh | Error ratio vượt SLO | Warning/Critical |
| DeadLetterRateHigh | DLQ tăng ngoài mức bình thường | Warning |
| NoBusinessProgress | Có input nhưng completion không tăng | Critical |
| ConnectTaskFailed | Task quan trọng chuyển FAILED | Warning/Critical |
| StreamsThreadFailed | Stream thread failed hoặc app ERROR | Critical |

### 15.3. Prometheus alert rule ví dụ

~~~yaml
groups:
  - name: kafka-cluster
    rules:
      - alert: KafkaBrokerTargetDown
        expr: up{job="kafka-brokers"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Kafka broker metrics target is unavailable"
          description: "Kiểm tra broker process, exporter endpoint và network."

      - alert: KafkaOfflinePartitions
        expr: kafka_controller_offline_partitions > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Kafka has offline partitions"
          description: "Kiểm tra broker, leader election và replica availability."

      - alert: KafkaUnderMinISR
        expr: kafka_server_under_min_isr_partition_count > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Kafka partitions are below min ISR"
          description: "Kiểm tra ISR, broker health và replication lag."

  - name: orders-business
    rules:
      - alert: OrdersE2ELatencyHigh
        expr: |
          histogram_quantile(
            0.99,
            sum by (le, flow) (
              rate(business_event_e2e_seconds_bucket[5m])
            )
          ) > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Orders end-to-end p99 latency exceeds example SLO"
          description: "Điều tra stage có latency tăng và backlog tương ứng."
~~~

Các metric name trong rule cluster phụ thuộc exporter mapping. Ngưỡng 5 giây là ví dụ theo SLO minh họa của bài; hãy thay bằng SLO thực tế.

### 15.4. Alert cần có hành động

Một alert hữu ích nên có:

- Severity và owner.
- Cluster, broker, topic, group hoặc service liên quan.
- Giá trị hiện tại và ngưỡng.
- Link dashboard.
- Link runbook.
- Hướng xử lý đầu tiên.
- Điều kiện resolve.

Không page đội vận hành chỉ vì một spike ngắn. Dùng `for`, moving window và kết hợp nhiều tín hiệu để giảm false positive.

## 16. Phân tích một số tình huống thường gặp

### 16.1. Broker khỏe nhưng business completion giảm

Dấu hiệu:

- Broker up bình thường.
- Offline partitions bằng 0.
- Producer throughput ổn định.
- Consumer lag tăng.
- Business completion rate giảm.

Điều tra:

1. Kiểm tra consumer group có member hay không.
2. Kiểm tra assigned partitions.
3. Kiểm tra `last-poll-seconds-ago`, poll interval và rebalance.
4. Kiểm tra consumer processing latency.
5. Kiểm tra database connection pool và query latency.
6. Kiểm tra lỗi retry/DLQ.

Khả năng cao vấn đề nằm ở consumer hoặc downstream database, không phải broker.

### 16.2. Under-replicated partitions tăng

Dấu hiệu:

- URP tăng.
- ISR shrink tăng.
- Replica lag tăng.
- Replication bytes có thể giảm hoặc mất cân bằng.
- Produce request latency tăng nếu dùng `acks=all`.

Điều tra:

1. Xác định broker replica đang offline hoặc chậm.
2. Kiểm tra disk latency và network.
3. Kiểm tra broker CPU/GC.
4. Kiểm tra reassignment hoặc maintenance đang diễn ra.
5. Xác nhận ISR đã phục hồi.

Không tự động tăng replication factor hoặc thay `min.insync.replicas` để che sự cố.

### 16.3. Consumer lag tăng nhưng consume rate vẫn cao

Dấu hiệu:

- Producer rate cao hơn consumer processing rate.
- Consumer vẫn hoạt động.
- Lag tăng liên tục.
- E2E latency xấu đi.

Điều tra:

1. Tính net processing rate.
2. Xác định partition có traffic skew.
3. Kiểm tra số partition và số consumer.
4. Kiểm tra downstream processing latency.
5. Đánh giá scale consumer hoặc tối ưu xử lý.
6. Xác định backlog có thể drain trong SLO hay không.

Tăng số consumer chỉ có ích nếu có đủ partition và downstream có capacity.

### 16.4. Consumer lag thấp nhưng event age cao

Có thể group đang đọc được record mới trong một số partition nhưng một partition cũ bị kẹt; hoặc event ít traffic nên lag theo số record nhỏ nhưng tuổi event lớn.

Kiểm tra lag từng partition, timestamp event cũ nhất chưa hoàn tất và business completion state. Không chỉ dựa vào tổng lag.

### 16.5. Kafka Streams RUNNING nhưng output giảm

Kiểm tra:

- `alive-stream-threads` và `failed-stream-threads`.
- `process-rate` và `process-latency`.
- `dropped-records-rate`.
- `active-buffer-count`.
- State store latency và disk.
- Rebalance/task assignment.
- Producer error/retry của Streams client.
- Exception handler logs.

Một process RUNNING không chứng minh mọi task đang xử lý đúng.

### 16.6. Connect connector RUNNING nhưng dữ liệu sink bị chậm

Kiểm tra task status, `sink-record-lag-max`, `sink-record-active-count`, `sink-record-read-rate`, `sink-record-send-rate`, put-batch latency, retries và DLQ. Connector RUNNING không có nghĩa mọi record đã được ghi thành công vào hệ thống đích.

## 17. Cardinality, retention và chi phí monitoring

Một hệ thống monitoring cũng có thể quá tải nếu thiết kế metric sai.

### 17.1. Giới hạn cardinality

Không dùng các giá trị thay đổi liên tục làm label:

- Order ID.
- Customer ID.
- User ID.
- Trace ID.
- Request ID.
- Email.
- Raw exception message.

Các label này tạo ra số lượng time series lớn, tăng RAM, CPU và disk của Prometheus.

Dùng label có tập giá trị giới hạn như `service`, `flow`, `stage`, `topic`, `consumer_group`, `result` và `error_type` đã chuẩn hóa.

### 17.2. Chọn recording level phù hợp

- Kafka broker: chỉ scrape MBean thực sự dùng cho dashboard/alert.
- Kafka clients: thu thập producer/consumer metrics của workload quan trọng.
- Kafka Streams: dùng `info` làm baseline; bật `debug`/`trace` khi cần chẩn đoán sâu.
- Kafka Connect: giữ metric theo connector/task quan trọng, nhưng theo dõi số lượng task.
- JVM/OS: chọn chu kỳ scrape phù hợp với nhu cầu và số lượng node.

### 17.3. Retention

Chọn retention theo mục đích:

- 7–15 ngày cho debug ngắn hạn nếu cần chi phí thấp.
- 30–90 ngày cho xu hướng vận hành phổ biến.
- Lâu hơn cho SLO, capacity planning hoặc yêu cầu audit nếu nền tảng lưu trữ đáp ứng.

Đây là các khoảng tham khảo, không phải yêu cầu bắt buộc. Có thể dùng remote storage hoặc downsampling để giữ xu hướng dài hạn mà không lưu mọi chuỗi chi tiết ở độ phân giải cao.

## 18. Runbook từ dashboard

Khi có alert, quy trình nên đi từ tác động đến nguyên nhân.

### Bước 1: Xác nhận business impact

- Completion rate có giảm không?
- E2E p99 có vượt SLO không?
- Có event quá tuổi chưa hoàn tất không?
- Có DLQ hoặc duplicate tăng không?

### Bước 2: Xác định stage bị nghẽn

So sánh input/output throughput ở từng stage. Tìm điểm đầu tiên mà output thấp hơn input kéo dài.

### Bước 3: Kiểm tra consumer group

- Member count.
- Assigned partitions.
- Lag tổng và lag max.
- Lag trend.
- Oldest event age.
- Rebalance count.
- Commit latency.
- Consumer processing rate.

### Bước 4: Kiểm tra cluster

- Broker up.
- Offline partitions.
- URP và under-min-ISR.
- Leader election.
- Request latency và queue size.
- KRaft quorum state.
- Disk, CPU, network và GC.

### Bước 5: Kiểm tra ứng dụng

- Streams state/thread/task.
- Connect task status.
- Producer retries/errors.
- Processing errors.
- Database latency và connection pool.
- External API errors.

### Bước 6: Mở trace/log

Dùng trace ID hoặc correlation ID từ business flow để theo dõi event qua service. Dùng topic/partition/offset để đối chiếu record với Kafka logs và consumer logs.

### Bước 7: Khôi phục và xác nhận

Sau khi sửa, xác nhận:

- Alert đã resolve.
- Lag đang giảm.
- Oldest event age giảm.
- Completion throughput phục hồi.
- E2E p99 trở lại SLO.
- Không có DLQ/duplicate bất thường.
- Không còn broker/replica degraded.

## 19. Lab: xây dựng hai dashboard cho luồng đơn hàng

Mục tiêu: thu thập Kafka metrics và business metrics, sau đó tạo hai dashboard có thể drill-down từ business flow đến cluster.

### Bước 1: Chuẩn bị Kafka cluster

Dùng cluster lab với ít nhất 3 broker nếu muốn thử replication và KRaft controller metrics. Tạo các topic:

- `orders`
- `enriched-orders`
- `payment-completed`
- `orders-dlq`

Dùng partition và replication factor phù hợp với cluster lab.

### Bước 2: Bật JMX Exporter

Cài JMX Exporter Java agent cho broker JVM. Tạo exporter YAML chỉ map các MBean cần thiết như ReplicaManager, KafkaController, BrokerTopicMetrics và RequestMetrics.

Kiểm tra endpoint `/metrics` có metric đúng và không expose private data.

### Bước 3: Thu thập host metrics

Cài Node exporter trên broker host. Thu thập CPU, memory, disk free, disk latency và network.

### Bước 4: Cấu hình Prometheus

Tạo scrape jobs cho broker, Connect, business services và Node exporter. Xác nhận target đều `UP`.

### Bước 5: Instrument business flow

Thêm Micrometer counters và timers vào orders-api, order-streams và billing-service. Ghi nhận accepted, completed, failed, retry, DLQ và E2E latency.

### Bước 6: Thu thập consumer group lag

Cài hoặc cấu hình exporter đọc committed offsets và log-end offsets. Export metric theo cluster, consumer group, topic và partition.

Đối chiếu metric exporter với kết quả `kafka-consumer-groups.sh --describe` trong lab.

### Bước 7: Tạo dashboard Cluster Overview

Thêm panel broker up, controller, offline partitions, URP, under-min-ISR, request latency, ISR, disk và KRaft quorum.

### Bước 8: Tạo dashboard Orders Flow

Thêm accepted/completed throughput, E2E p99, error ratio, DLQ, consumer lag, oldest event age và time to drain.

### Bước 9: Tạo alert

Tạo alert cho broker down, offline partition, under-min-ISR, lag cao kéo dài, E2E latency vượt SLO và DLQ tăng.

### Bước 10: Tạo tình huống lỗi

Thử lần lượt:

- Dừng một consumer.
- Tăng thời gian xử lý trong billing-service.
- Tạo database timeout.
- Dừng một broker lab.
- Tăng traffic producer vượt consumer capacity.
- Gửi record lỗi serialization vào input topic.

Quan sát panel nào phát hiện sớm nhất và panel nào giúp khoanh vùng nguyên nhân.

### Bước 11: Drill-down

Từ alert business flow, chuyển sang topic/group, sau đó sang broker/partition và trace/log tương ứng.

### Bước 12: Ghi kết quả

Ghi lại:

- Thời gian phát hiện.
- Thời gian xác định stage lỗi.
- Metric giúp tìm nguyên nhân.
- Alert false positive.
- Ngưỡng cần điều chỉnh.
- SLI/SLO có phản ánh đúng business impact không.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ monitor CPU/RAM | Không biết Kafka hoặc business flow có đang xử lý đúng không | Thêm replication, request, lag và business metrics |
| Chỉ nhìn broker up | Broker sống nhưng consumer có thể bị kẹt | Theo dõi group lag và completion |
| Dùng `records-lag-max` làm group committed lag | Có thể đánh giá thiếu backlog chưa commit | Dùng exporter tính committed offset so với log end |
| Chỉ xem tổng lag | Một partition bị kẹt có thể bị che khuất | Xem lag max và per-partition |
| Chỉ xem message lag | Không biết event đã chờ bao lâu | Thêm oldest event age và E2E latency |
| Dùng Produce success làm business completion | Event đã vào Kafka nhưng chưa hoàn tất nghiệp vụ | Instrument metric tại điểm business commit |
| Chỉ dùng average latency | Che khuất tail latency | Dùng histogram và p95/p99 |
| Chỉ xem connector RUNNING | Task có thể FAILED hoặc sink không ghi được | Theo dõi task status và sink metrics |
| Chỉ xem Streams process RUNNING | Thread/task có thể lỗi hoặc drop record | Theo dõi failed threads, dropped records và task metrics |
| Bật toàn bộ debug/trace metrics | Cardinality và chi phí monitoring tăng | Chọn recording level theo nhu cầu |
| Dùng order ID làm label | Tạo hàng triệu time series | Đưa ID vào logs/traces |
| Alert cho mọi spike | Nhiều false positive và alert fatigue | Dùng duration, SLO và nhiều tín hiệu |
| Không kiểm tra scrape health | Dashboard có thể hiển thị dữ liệu cũ hoặc thiếu | Theo dõi Prometheus `up` và scrape errors |
| Mở remote JMX không bảo vệ | Rủi ro lộ thông tin và quyền quản trị JVM | Giới hạn network và bật authentication |

## 21. Checklist production

- [ ] Xác định cluster dashboard và business flow dashboard riêng.
- [ ] Định nghĩa SLI/SLO cho business completion và E2E latency.
- [ ] Thu thập Kafka broker/client metrics qua JMX.
- [ ] Dùng JMX Exporter hoặc metrics reporter phù hợp.
- [ ] Bảo vệ JMX/exporter endpoint trong network nội bộ.
- [ ] Thu thập node/JVM metrics.
- [ ] Thu thập KRaft quorum/controller metrics.
- [ ] Theo dõi URP, under-min-ISR, offline partitions và unclean elections.
- [ ] Theo dõi request rate/error/latency/queue.
- [ ] Theo dõi disk free, disk latency, CPU, memory và GC.
- [ ] Theo dõi producer retries/errors/buffer/throttle.
- [ ] Theo dõi consumer rate, rebalance, commit latency và poll interval.
- [ ] Có exporter tính consumer group lag theo committed offset.
- [ ] Theo dõi lag max theo partition và oldest event age.
- [ ] Theo dõi Kafka Connect connector/task status và DLQ.
- [ ] Theo dõi Kafka Streams state/thread/task/drop/latency.
- [ ] Instrument business accepted/completed/failed/retry/DLQ.
- [ ] Đo E2E latency bằng histogram.
- [ ] Truyền trace context qua Kafka headers.
- [ ] Không dùng ID có cardinality cao làm metric label.
- [ ] Có alert severity, owner, dashboard link và runbook.
- [ ] Kiểm thử alert bằng các tình huống lỗi thật trong lab/staging.
- [ ] Định kỳ rà soát retention, scrape interval và cardinality.
- [ ] Kiểm tra Prometheus target health để phát hiện missing metrics.
- [ ] Có dashboard drill-down từ business flow đến topic/group/broker/trace.

## 22. Tài liệu tham khảo

- [Apache Kafka 4.4 – Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 – Broker Metrics](https://kafka.apache.org/44/operations/monitoring/#broker-metrics)
- [Apache Kafka 4.4 – KRaft Monitoring Metrics](https://kafka.apache.org/44/operations/monitoring/#kraft-monitoring-metrics)
- [Apache Kafka 4.4 – Producer and Consumer Metrics](https://kafka.apache.org/44/operations/monitoring/#producer-monitoring)
- [Apache Kafka 4.4 – Kafka Streams Metrics](https://kafka.apache.org/44/operations/monitoring/#streams-monitoring)
- [Prometheus JMX Exporter – Java Agent](https://prometheus.github.io/jmx_exporter/deployment/java-agent/)
- [Prometheus JMX Exporter – Configuration](https://prometheus.github.io/jmx_exporter/reference/configuration/)
- [Prometheus – Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus – Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana – Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)

Dashboard cluster cho biết Kafka có khỏe và đủ capacity không. Dashboard business flow cho biết event có đi đến kết quả cuối cùng đúng thời gian không. Khi kết hợp broker, KRaft, producer, consumer, Connect, Streams và metric nghiệp vụ, đội vận hành có thể phát hiện sự cố theo tác động thực tế, xác định stage bị nghẽn và drill-down đến broker, partition, task hoặc trace gây ra vấn đề.
