# Thu thập JMX metrics và xuất số liệu cho Prometheus

## Mục tiêu bài học

Kafka broker, producer, consumer, Kafka Connect và Kafka Streams công bố nhiều chỉ số vận hành qua JMX (Java Management Extensions). Prometheus không đọc JMX trực tiếp; một exporter cần chuyển MBean attributes thành định dạng Prometheus có thể scrape. Với Kafka chạy trên JVM, cách triển khai phổ biến là gắn Prometheus JMX Exporter Java agent vào process để đọc MBeans tại chỗ và mở endpoint `/metrics`.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa JMX, MBean, JMX Exporter và Prometheus.
- Phân biệt Java agent exporter với remote JMX và exporter đọc Kafka qua protocol.
- Gắn JMX Exporter vào Kafka broker, Kafka Connect worker và ứng dụng Kafka client.
- Viết rules để chuyển Kafka MBeans thành metric name/label phù hợp.
- Chọn metric theo broker throughput, replication, request latency, JVM và client.
- Cấu hình Prometheus scrape job, target labels và scrape interval.
- Thiết kế dashboard và alert từ metric có ý nghĩa vận hành.
- Bảo vệ endpoint metrics và kiểm soát cardinality.
- Kiểm tra exporter, chẩn đoán metric thiếu/sai và vận hành khi nâng cấp Kafka.

## 1. Kiến trúc quan sát Kafka bằng JMX và Prometheus

Kafka chạy trên JVM và công bố nhiều MBean trong các domain như `kafka.server`, `kafka.network`, `kafka.controller`, `kafka.log` và `java.lang`. Mỗi MBean có ObjectName định danh và một tập attribute. JMX Exporter đọc các ObjectName/attribute này, áp dụng rule rồi xuất metric dạng text exposition. Prometheus định kỳ gọi HTTP endpoint của exporter để scrape.

```text
+-------------------------- Kafka broker JVM --------------------------+
|                                                                       |
|  Kafka server / network / replica / controller MBeans                 |
|  JVM memory / GC / threads MBeans                                     |
|                         |                                             |
|                         v                                             |
|              Prometheus JMX Exporter Java agent                       |
|                 JMX MBean -> metric rules                             |
|                         |                                             |
|                  HTTP :9404/metrics                                   |
+-------------------------|---------------------------------------------+
                          |
                          | HTTP scrape
                          v
                  +------------------+
                  |    Prometheus    |
                  | scrape / TSDB    |
                  +--------+---------+
                           |
                    PromQL / alert rules
                           |
                    +------+------+
                    |             |
                    v             v
                 Grafana      Alertmanager
```

Mỗi Kafka broker là một JVM process riêng, do đó thường có một exporter endpoint riêng. Kafka Connect worker và Kafka Streams application cũng là JVM process độc lập; muốn quan sát MBeans của chúng phải gắn exporter vào đúng process đó.

### 1.1. Vai trò của từng thành phần

| Thành phần | Vai trò |
|---|---|
| JMX | Giao diện quản lý/quan sát các MBean trong JVM |
| MBean | Đối tượng công bố metric hoặc thuộc tính quản trị |
| JMX Exporter | Chuyển MBean attributes thành Prometheus metrics |
| Prometheus | Scrape, lưu time series và đánh giá PromQL/alert rules |
| Grafana | Trực quan hóa dashboard từ Prometheus |
| Alertmanager | Nhóm, định tuyến và gửi cảnh báo |

JMX Exporter không tự tạo dashboard hay lưu lịch sử. Prometheus không tự phát hiện mọi broker nếu chưa có service discovery hoặc static target configuration.

### 1.2. JMX metrics khác log và trace

- **Metrics:** số liệu tổng hợp theo thời gian như request rate, byte rate, error count, heap usage, replication lag.
- **Logs:** sự kiện chi tiết và stack trace để tìm nguyên nhân cụ thể.
- **Traces:** đường đi của một request/event qua nhiều service.

Metrics giúp phát hiện và khoanh vùng vấn đề; logs/traces giúp điều tra. Một dashboard tốt không thay thế log của broker hoặc ứng dụng.

## 2. JMX, MBean và Kafka metrics

### 2.1. ObjectName và attribute

Một MBean có ObjectName theo dạng:

```text
domain:key=value,key=value
```

Ví dụ:

```text
kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec
```

MBean này công bố các attribute của meter như `Count`, `MeanRate`, `OneMinuteRate`, `FiveMinuteRate` và `FifteenMinuteRate` tùy metric/phiên bản. Một attribute có thể là counter tích lũy, gauge tức thời hoặc percentile.

### 2.2. Các nhóm MBean phổ biến

| Domain/type | Nhóm thông tin | Ví dụ metric cần quan sát |
|---|---|---|
| `kafka.server:type=BrokerTopicMetrics` | Traffic và request error của broker | Messages in, bytes in/out, failed produce/fetch |
| `kafka.server:type=ReplicaManager` | Replication và partition state | Under-replicated, under-min-ISR, offline replicas, ISR changes |
| `kafka.server:type=KafkaRequestHandlerPool` | Request handler thread pool | Average idle percent |
| `kafka.network:type=RequestMetrics` | Latency theo request type | Produce/Fetch request queue, local, remote và total time |
| `kafka.network:type=SocketServer` | Network processor | Network processor idle percent |
| `kafka.controller:*` | Controller metrics, tùy metadata mode/version | Controller state và partition events |
| `kafka.server:type=raft-metrics` | KRaft quorum/raft metrics, tùy version | Leader, epoch, high watermark, commit/election latency |
| `kafka.log:*` | Log/segment metrics | Log flush, segment và log size metrics |
| `java.lang:type=Memory` | JVM memory | Heap/non-heap usage |
| `java.lang:type=GarbageCollector,*` | Garbage collection | Collection count và collection time |
| `java.lang:type=Threading` | JVM threads | Thread count, peak thread count |

Danh sách và tên MBean thay đổi theo Kafka/JDK version, broker role và cấu hình. Luôn kiểm tra MBeans thực tế trên đúng phiên bản thay vì sao chép nguyên bộ rule từ cluster khác.

### 2.3. Counter, gauge, rate và percentile

- **Counter:** giá trị tích lũy chỉ tăng trong vòng đời process, ví dụ tổng số message đã nhận. Khi process restart, counter có thể về 0.
- **Gauge:** giá trị có thể tăng/giảm, ví dụ số under-replicated partition hiện tại hoặc heap đang dùng.
- **Rate:** tốc độ tính theo thời gian, ví dụ byte/giây. JMX meter có thể cung cấp `OneMinuteRate` hoặc `MeanRate`.
- **Histogram/percentile:** phân phối latency, ví dụ p50/p95/p99 nếu MBean có công bố percentile.

Trong Prometheus, dùng `rate()`/`increase()` cho counter. Không áp dụng `rate()` cho gauge. Với latency, ưu tiên histogram nếu exporter/ứng dụng cung cấp histogram chuẩn; percentile đã tính sẵn trên từng instance không thể cộng gộp chính xác giữa nhiều broker.

## 3. Hai cách xuất JMX metrics

### 3.1. Java agent gắn vào process

Java agent chạy bên trong JVM của Kafka process. Agent đọc MBeans local rồi mở HTTP endpoint để Prometheus scrape.

Ưu điểm:

- Không cần bật remote JMX/RMI port cho Prometheus.
- Mỗi process có endpoint metrics riêng, dễ ánh xạ với broker ID/instance.
- Dễ triển khai cùng lifecycle của Kafka bằng JVM options.
- Không phải mở một kết nối JMX từ máy exporter đến broker.

Đánh đổi:

- Cần restart process để thêm/thay Java agent nếu không có cơ chế attach động được quản lý riêng.
- Agent sử dụng một phần CPU/memory của JVM.
- Phải bảo đảm mỗi process dùng port riêng và endpoint không bị expose công khai.

### 3.2. Standalone JMX Exporter

Standalone exporter chạy process riêng, kết nối remote JMX của JVM mục tiêu. Cách này đòi hỏi cấu hình remote JMX/RMI, port registry và port RMI có thể truy cập được.

Ưu điểm là tách exporter khỏi JVM Kafka. Đánh đổi là phải quản lý remote JMX endpoint, RMI hostname/port, firewall và credential. Nếu dùng remote JMX, chỉ mở trên network quản trị riêng và cấu hình authentication/TLS theo chính sách môi trường.

### 3.3. Không nhầm với `kafka_exporter`

Một số công cụ có tên `kafka_exporter` đọc metadata/topic/consumer group từ Kafka protocol hoặc Admin API. Công cụ đó không thay thế JMX Exporter cho JVM, request handler, GC hoặc replica manager MBeans.

Một hệ thống quan sát có thể dùng cả hai:

- JMX Exporter cho broker/JVM/client metrics.
- Exporter dùng Kafka protocol cho topic/consumer lag/cluster metadata mà JMX không cung cấp trực tiếp hoặc không đủ thuận tiện.

Chọn exporter theo loại dữ liệu cần thu thập, không chỉ theo tên sản phẩm.

## 4. Chuẩn bị JMX Exporter

### 4.1. Tải và cố định artifact

JMX Exporter được phát hành dưới dạng Java agent JAR và standalone JAR. Với Kafka broker, thường dùng artifact Java agent.

Quy trình triển khai:

1. Chọn release tương thích với JDK và môi trường Kafka.
2. Tải JAR từ nguồn phát hành chính thức.
3. Xác minh checksum/signature theo quy trình supply-chain của tổ chức.
4. Đặt JAR vào thư mục chỉ user vận hành Kafka có quyền đọc.
5. Lưu file YAML cấu hình exporter trong thư mục cấu hình được quản lý version.
6. Cấp quyền đọc config/JAR và quyền bind port cho user Kafka.

Ví dụ đường dẫn:

```text
/opt/monitoring/jmx-exporter/jmx_prometheus_javaagent.jar
/etc/kafka/metrics/jmx-exporter.yml
```

Không tải JAR tùy tiện từ mirror không tin cậy hoặc ghi đè artifact mà không xác minh version/checksum.

### 4.2. Chọn port riêng cho từng process

Ví dụ quy ước:

| Process | Metrics port ví dụ |
|---|---:|
| Broker 1 | 9404 |
| Broker 2 | 9405 |
| Broker 3 | 9406 |
| Kafka Connect worker 1 | 9407 |
| Kafka Connect worker 2 | 9408 |
| Kafka Streams app | 9410 |

Port chỉ là ví dụ. Đảm bảo không trùng port JMX exporter, JMX remote, REST API hoặc ứng dụng khác. Dùng một port ổn định theo process để service discovery không nhầm target.

### 4.3. Gắn Java agent vào Kafka broker

Kafka startup script đọc JVM options từ environment. Có thể cấu hình trong systemd EnvironmentFile hoặc deployment manifest.

Ví dụ trên Linux:

```bash
export KAFKA_OPTS="-javaagent:/opt/monitoring/jmx-exporter/jmx_prometheus_javaagent.jar=127.0.0.1:9404:/etc/kafka/metrics/jmx-exporter.yml"
bin/kafka-server-start.sh -daemon config/server.properties
```

Cú pháp agent có dạng `host:port:config.yml`; kiểm tra đúng cú pháp của release JMX Exporter đang cài. Ví dụ bind `127.0.0.1` chỉ cho phép scrape local. Nếu Prometheus chạy trên máy khác, bind vào private interface hoặc dùng proxy/network path được kiểm soát.

Trên mỗi broker, thay port và host theo node. Nếu chạy trong container, truyền `KAFKA_OPTS` qua environment và mount JAR/config read-only.

### 4.4. Tránh ghi đè JVM options đang có

`KAFKA_OPTS` có thể đã chứa `-D` hoặc `-javaagent` khác. Không thay thế toàn bộ giá trị hiện tại khi thêm exporter. Hãy nối thêm agent vào cấu hình hiện có và xác minh command line thực tế của process sau restart.

Nếu nền tảng dùng `KAFKA_JVM_PERFORMANCE_OPTS`, `JDK_JAVA_OPTIONS`, systemd drop-in hoặc wrapper script, kiểm tra thứ tự và cách môi trường đó truyền options. Không đặt cùng một Java agent hai lần trong cùng process.

### 4.5. Kafka Connect và Kafka Streams

Kafka Connect distributed worker là JVM process riêng. Gắn agent vào command khởi động worker, ví dụ:

```bash
export KAFKA_OPTS="-javaagent:/opt/monitoring/jmx-exporter/jmx_prometheus_javaagent.jar=127.0.0.1:9407:/etc/kafka/metrics/connect-jmx.yml"
bin/connect-distributed.sh config/connect-distributed.properties
```

Kafka Streams application cũng có thể gắn agent bằng JVM options của service/container. Mỗi process cần config rules phù hợp với MBeans thực tế của Kafka Connect/Streams và port riêng.

Gắn agent vào broker không tự thu thập MBeans của Connect worker hoặc ứng dụng Java khác. Mỗi JVM phải được instrument riêng.

## 5. Viết cấu hình rules cho JMX Exporter

### 5.1. Cấu trúc cấu hình

File YAML có thể giới hạn ObjectName được thu thập và ánh xạ MBean attribute thành metric. Một số thuộc tính phổ biến:

| Thuộc tính | Mục đích |
|---|---|
| `startDelaySeconds` | Thời gian chờ trước khi agent bắt đầu scrape JMX |
| `lowercaseOutputName` | Chuẩn hóa metric name thành chữ thường |
| `lowercaseOutputLabelNames` | Chuẩn hóa label name |
| `includeObjectNames` | Chỉ lấy các ObjectName được chỉ định |
| `excludeObjectNames` | Loại các ObjectName không cần thiết |
| `rules` | Ánh xạ ObjectName/attribute thành metric name, label và type |

Nếu rule không match, exporter có thể không xuất metric hoặc dùng behavior mặc định tùy cấu hình/version. Vì vậy, cần kiểm tra output `/metrics` sau mỗi lần thay rule.

### 5.2. Ví dụ cấu hình tối thiểu

Ví dụ sau minh họa một tập metric cơ bản. MBean pattern và attribute phải được kiểm tra trên đúng Kafka version:

```yaml
startDelaySeconds: 5
lowercaseOutputName: true
lowercaseOutputLabelNames: true

includeObjectNames:
  - "kafka.server:type=BrokerTopicMetrics,name=*"
  - "kafka.server:type=ReplicaManager,*"
  - "kafka.server:type=KafkaRequestHandlerPool,*"
  - "kafka.network:type=RequestMetrics,*"
  - "kafka.network:type=SocketServer,*"
  - "java.lang:type=Memory"
  - "java.lang:type=GarbageCollector,*"
  - "java.lang:type=Threading"

rules:
  - pattern: 'kafka.server<type=BrokerTopicMetrics, name=(.+)PerSec><>Count'
    name: kafka_server_broker_topic_$1_total
    type: COUNTER

  - pattern: 'kafka.server<type=BrokerTopicMetrics, name=(.+)PerSec><>OneMinuteRate'
    name: kafka_server_broker_topic_$1_rate
    type: GAUGE

  - pattern: 'kafka.server<type=ReplicaManager, name=(UnderReplicatedPartitions|UnderMinIsrPartitionCount|OfflineReplicaCount)><>Value'
    name: kafka_server_replica_manager_$1
    type: GAUGE

  - pattern: 'kafka.server<type=ReplicaManager, name=(LeaderCount|PartitionCount)><>Value'
    name: kafka_server_replica_manager_$1
    type: GAUGE

  - pattern: 'kafka.server<type=ReplicaManager, name=(IsrShrinksPerSec|IsrExpandsPerSec)><>Count'
    name: kafka_server_replica_manager_$1_total
    type: COUNTER

  - pattern: 'kafka.server<type=KafkaRequestHandlerPool, name=RequestHandlerAvgIdlePercent><>OneMinuteRate'
    name: kafka_server_request_handler_avg_idle_ratio
    type: GAUGE

  - pattern: 'kafka.network<type=SocketServer, name=NetworkProcessorAvgIdlePercent><>OneMinuteRate'
    name: kafka_network_processor_avg_idle_ratio
    type: GAUGE

  - pattern: 'kafka.network<type=RequestMetrics, name=TotalTimeMs, request=(.+)><>99thPercentile'
    name: kafka_network_request_total_time_ms_p99
    labels:
      request: "$1"
    type: GAUGE

  - pattern: 'kafka.network<type=RequestMetrics, name=RequestQueueTimeMs, request=(.+)><>Mean'
    name: kafka_network_request_queue_time_ms_mean
    labels:
      request: "$1"
    type: GAUGE

  - pattern: 'java.lang<type=Memory><HeapMemoryUsage>used'
    name: jvm_memory_heap_used_bytes
    type: GAUGE

  - pattern: 'java.lang<type=Memory><HeapMemoryUsage>committed'
    name: jvm_memory_heap_committed_bytes
    type: GAUGE

  - pattern: 'java.lang<type=Memory><HeapMemoryUsage>max'
    name: jvm_memory_heap_max_bytes
    type: GAUGE

  - pattern: 'java.lang<type=Memory><NonHeapMemoryUsage>used'
    name: jvm_memory_nonheap_used_bytes
    type: GAUGE

  - pattern: 'java.lang<type=GarbageCollector, name=(.+)><>CollectionCount'
    name: jvm_gc_collection_count_total
    labels:
      collector: "$1"
    type: COUNTER

  - pattern: 'java.lang<type=GarbageCollector, name=(.+)><>CollectionTime'
    name: jvm_gc_collection_time_milliseconds_total
    labels:
      collector: "$1"
    type: COUNTER

  - pattern: 'java.lang<type=Threading><>ThreadCount'
    name: jvm_threads_current
    type: GAUGE

  - pattern: 'java.lang<type=Threading><>PeakThreadCount'
    name: jvm_threads_peak
    type: GAUGE
```

Trong rule đầu, `$1` lấy tên meter trước hậu tố `PerSec`. `Count` là tổng số lần ghi nhận kể từ khi process khởi động; `OneMinuteRate` là tốc độ đã được MBean tính theo cửa sổ một phút. Metric rate được xuất dưới dạng gauge, không dùng `rate()` lên metric đó lần nữa.

Ví dụ rule có thể cần chỉnh nếu exporter version thay đổi cách chuẩn hóa ObjectName, nếu attribute không có ở Kafka build đang chạy hoặc nếu MBean name có thêm property. Kiểm tra thực tế trước khi dùng dashboard/alert.

### 5.3. Quy tắc metric name

Prometheus metric name nên:

- Dùng chữ thường và dấu gạch dưới.
- Có prefix thể hiện domain/service, ví dụ `kafka_server_` hoặc `jvm_`.
- Có suffix đơn vị như `_bytes`, `_seconds`, `_total`.
- Có type nhất quán giữa các instance.
- Không đưa giá trị thay đổi liên tục như request ID, client ID ngẫu nhiên hoặc exception message thành label.

Metric name là contract giữa exporter, dashboard và alert. Đổi rule có thể làm dashboard cũ mất dữ liệu vì series name thay đổi.

### 5.4. Label từ MBean properties

Một MBean có thể có `client-id`, `topic`, `partition`, `request` hoặc `listener`. JMX Exporter có thể map property thành label. Ví dụ metric theo request type nên có label `request="Produce"` hoặc `request="FetchConsumer"` để phân biệt loại request.

Chỉ xuất label cần cho truy vấn. Topic và client ID có thể tạo cardinality lớn khi cluster có hàng nghìn topic/client. Tránh dùng label chứa user ID, event ID, exception text hoặc dữ liệu nghiệp vụ.

## 6. Các metric Kafka broker nên thu thập

Không cần export mọi MBean. Chọn nhóm metric trả lời các câu hỏi vận hành: broker có nhận/gửi dữ liệu không, replication có khỏe không, request có bị chậm không và JVM có đang quá tải không.

### 6.1. Traffic và throughput

Các MBean thường gặp trong `BrokerTopicMetrics`:

| MBean `name` | Ý nghĩa | Dùng để |
|---|---|---|
| `MessagesInPerSec` | Số message broker nhận vào | Theo dõi ingress rate |
| `BytesInPerSec` | Byte broker nhận vào | Theo dõi ingress throughput |
| `BytesOutPerSec` | Byte broker gửi ra | Theo dõi egress throughput |
| `BytesRejectedPerSec` | Byte bị từ chối theo giới hạn/quy tắc broker | Phát hiện quota/limit |
| `FailedProduceRequestsPerSec` | Produce request lỗi | Phát hiện lỗi producer/broker |
| `FailedFetchRequestsPerSec` | Fetch request lỗi | Phát hiện vấn đề fetch/replica/consumer |

Các meter thường có `Count`, `OneMinuteRate`, `FiveMinuteRate` hoặc `MeanRate`. Chọn rate để dashboard tức thời; dùng Count để tính rate bằng PromQL khi muốn cửa sổ tùy ý.

Ví dụ PromQL nếu exporter xuất `kafka_server_broker_topic_messagesin_total`:

```promql
sum by (cluster) (
  rate(kafka_server_broker_topic_messagesin_total[5m])
)
```

Tên metric phải khớp rule thực tế. Query ví dụ chỉ minh họa cách tính tốc độ từ counter.

### 6.2. Replication và partition health

| MBean | Metric/attribute thường quan tâm | Diễn giải |
|---|---|---|
| `ReplicaManager` | `UnderReplicatedPartitions` | Partition chưa có đủ replica đồng bộ |
| `ReplicaManager` | `UnderMinIsrPartitionCount` | Partition có ISR thấp hơn min ISR |
| `ReplicaManager` | `OfflineReplicaCount` | Replica offline |
| `ReplicaManager` | `IsrShrinksPerSec` | Tần suất ISR shrink |
| `ReplicaManager` | `IsrExpandsPerSec` | Tần suất ISR expand |
| `ReplicaManager` | `PartitionCount` | Tổng partition trên broker |
| `ReplicaManager` | `LeaderCount` | Số partition leader broker đang nắm |

`UnderReplicatedPartitions > 0` kéo dài có thể báo hiệu replica fetcher chậm, broker mất kết nối, disk/network quá tải hoặc broker vừa restart. `UnderMinIsrPartitionCount > 0` nghiêm trọng hơn vì partition có thể không đáp ứng write policy `acks=all`/min ISR.

Metric `IsrShrinksPerSec` tăng liên tục là dấu hiệu cần điều tra ngay cả khi under-replicated hiện tại bằng 0. Nó có thể chỉ ra replica liên tục rời/nhập ISR.

### 6.3. Request latency và queueing

`kafka.network:type=RequestMetrics,...` cung cấp metric theo request type như Produce, FetchConsumer, FetchFollower, Metadata, ApiVersions và các request khác tùy version.

Các attribute có thể gồm:

- `RequestQueueTimeMs`: thời gian request chờ trong queue.
- `LocalTimeMs`: thời gian xử lý local broker.
- `RemoteTimeMs`: thời gian chờ/trao đổi với broker khác tùy request.
- `ResponseQueueTimeMs`: thời gian response chờ gửi.
- `ResponseSendTimeMs`: thời gian gửi response.
- `TotalTimeMs`: tổng thời gian xử lý request.
- `ThrottleTimeMs`: thời gian request bị throttle.

Metric latency có thể xuất percentile như 50th/95th/99th percentile hoặc histogram tùy MBean/version. Nếu chỉ có p99 theo từng broker, không lấy trung bình p99 của các broker để ra p99 toàn cluster.

### 6.4. Thread pool và network processor

`RequestHandlerAvgIdlePercent` cho biết mức nhàn rỗi trung bình của request handler pool. `NetworkProcessorAvgIdlePercent` phản ánh mức nhàn rỗi của network processor.

Idle ratio giảm lâu dài có thể báo hiệu broker thiếu CPU/thread capacity hoặc request volume tăng. Cần đối chiếu request queue time, CPU, network, disk và latency trước khi tăng thread count.

## 7. JVM metrics cần theo dõi

Kafka broker là Java process nên sức khỏe JVM ảnh hưởng trực tiếp đến request latency và replication.

### 7.1. Heap và non-heap

Theo dõi:

- Heap used, committed và max.
- Non-heap used/committed.
- Metaspace usage.
- Direct buffer/native memory nếu có exporter phù hợp.
- Process RSS/container memory.

Heap used luôn gần max có thể dẫn đến GC pause dài hoặc OOM. Tuy nhiên, Kafka còn dùng page cache của OS và native/direct memory; không đánh giá memory chỉ bằng heap.

### 7.2. Garbage collection

MBean `java.lang:type=GarbageCollector,name=*` thường cung cấp collection count và collection time. Dùng delta/rate để quan sát tần suất và thời gian GC.

Alert không nên chỉ dựa trên GC count lớn. Điều quan trọng là thời gian pause, tần suất, xu hướng heap sau GC và tác động đến request/replication latency. Kết hợp GC log để xem pause chi tiết.

### 7.3. Thread và file descriptor

Threading MBean cung cấp current thread count và peak thread count. Một số OS/JVM MBean cung cấp open file descriptor count và limit. Theo dõi để phát hiện thread leak hoặc tiến gần giới hạn file descriptor.

### 7.4. CPU và process metrics

CPU usage, process RSS, disk I/O và network throughput không phải lúc nào cũng được công bố đầy đủ qua Kafka MBeans. Thu thập thêm bằng node exporter, cAdvisor hoặc hệ thống metrics của nền tảng. Ghép các metric này với JMX theo label `instance`/`broker_id`.

## 8. Consumer và producer metrics

Kafka Java producer/consumer cũng công bố JMX MBeans. Để scrape được các metric này, JMX Exporter phải gắn vào JVM của ứng dụng client hoặc ứng dụng phải expose metrics qua Micrometer/Prometheus client.

### 8.1. Producer metrics

Các nhóm metric đáng quan tâm:

- Record send rate và byte rate.
- Request rate, request latency và batch size.
- Record retry rate và error rate.
- Buffer available bytes và bufferpool wait ratio/time.
- Compression rate.
- Metadata refresh và connection state.

Nếu producer buffer cạn hoặc broker chậm, `bufferpool-wait-time`, request latency và retry có thể tăng. Producer có thể vẫn gửi thành công nhưng latency end-to-end đã vượt SLA.

### 8.2. Consumer metrics

Các nhóm metric:

- Records consumed rate và bytes consumed rate.
- Fetch latency, fetch rate và fetch size.
- Records lag max/partition lag nếu client cung cấp.
- Commit rate/latency và rebalance count.
- Assigned partition count.
- Poll interval và time between poll.

Consumer client metrics là tín hiệu từ ứng dụng consumer. Broker JMX không thể thay thế hoàn toàn metric này. Để có consumer lag đáng tin cậy, có thể kết hợp client metrics, Admin API/exporter hoặc monitoring tool chuyên consumer group.

### 8.3. Không gắn exporter vào mọi ứng dụng một cách máy móc

Mỗi Java application có thể tạo nhiều MBean theo `client-id`, `topic`, `partition` và request type. Nếu có hàng trăm pod/instance và client ID động, số time series có thể tăng mạnh. Chỉ expose nhóm metric phục vụ vận hành và dùng client ID ổn định, có kiểm soát.

## 9. Kafka Connect và Kafka Streams metrics

### 9.1. Kafka Connect

Connect worker công bố JMX metrics cho:

- Worker state và connector/task count.
- Connector/task running/failed state.
- Source record poll/write rate.
- Sink record read/send rate.
- Batch size và put/poll latency.
- Error count, retry và dead-letter queue behavior tùy connector/version.

Metric cụ thể phụ thuộc Kafka Connect runtime và connector plugin. Gắn exporter vào mỗi worker JVM; REST API `/connectors/{name}/status` vẫn hữu ích để biết trạng thái task chi tiết.

### 9.2. Kafka Streams

Kafka Streams có metric theo application, thread, task, processor node, state store và record processing. Theo dõi:

- Process/thread/task state.
- Input/output record rate.
- Process latency và punctuate latency.
- Commit latency và poll latency.
- Restore rate, restore latency và standby lag.
- State store put/get latency, cache hit hoặc RocksDB metrics nếu được expose.
- Rebalance và task migration.

Gắn JMX Exporter vào JVM của Streams application. Nếu dùng Micrometer, có thể publish cùng metric qua registry Prometheus; tránh xuất hai series trùng semantics với tên khác nhau mà không có quy ước.

## 10. Khởi động exporter và kiểm tra endpoint

Sau khi thêm Java agent, restart process theo rolling plan. Kiểm tra port đang listen và endpoint:

```bash
curl http://127.0.0.1:9404/metrics
```

Kiểm tra một số metric mong đợi:

```bash
curl -s http://127.0.0.1:9404/metrics | grep -E 'kafka_server|jvm_memory'
```

Kiểm tra exporter process/port:

```bash
ss -lntp | grep 9404
```

Trong Windows hoặc môi trường không có `ss`, dùng công cụ kiểm tra port tương ứng. Không chỉ xác nhận port mở; cần xác nhận nội dung `/metrics` có metric và giá trị hợp lý.

### 10.1. Kiểm tra metric name và sample

Ví dụ output rút gọn:

```text
# HELP kafka_server_broker_topic_messagesin_total Total messages received.
# TYPE kafka_server_broker_topic_messagesin_total counter
kafka_server_broker_topic_messagesin_total 183920

# HELP kafka_server_replica_manager_underreplicatedpartitions Under replicated partitions.
# TYPE kafka_server_replica_manager_underreplicatedpartitions gauge
kafka_server_replica_manager_underreplicatedpartitions 0

# HELP jvm_memory_heap_used_bytes Heap memory currently used.
# TYPE jvm_memory_heap_used_bytes gauge
jvm_memory_heap_used_bytes 5.24288e+08
```

Đây là output minh họa theo custom rule ở trên, không phải metric name cố định của mọi cấu hình exporter.

### 10.2. Xác minh MBean gốc

Nếu metric không xuất hiện:

1. Xác minh Kafka process đã khởi động với đúng `-javaagent`.
2. Xác minh exporter đọc đúng config YAML.
3. Kiểm tra log startup của Java agent.
4. Xác minh MBean ObjectName tồn tại trên JVM.
5. Xác minh attribute name và type.
6. Kiểm tra regex pattern, thứ tự rule và include/exclude.
7. Kiểm tra endpoint trả về metric hay chỉ có `jmx_scrape_error`.

Có thể dùng JConsole/JMX client trên môi trường test để duyệt MBeans. Không mở JMX remote port rộng chỉ để kiểm tra production.

## 11. Cấu hình Prometheus scrape

### 11.1. Static targets

Ví dụ `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: kafka-brokers
    metrics_path: /metrics
    scrape_interval: 15s
    static_configs:
      - targets:
          - broker-1.internal:9404
          - broker-2.internal:9405
          - broker-3.internal:9406
        labels:
          cluster: kafka-prod
          environment: production
```

Prometheus tự thêm `job` và `instance` labels. Dùng labels bổ sung như `cluster`, `environment`, `role`, `broker_id` hoặc `rack` khi cần lọc/so sánh.

### 11.2. Service discovery

Trong Kubernetes, dùng `kubernetes_sd_configs`/ServiceMonitor/PodMonitor tùy Prometheus Operator và cách triển khai. Trong VM/cloud, có thể dùng file_sd, DNS SD hoặc service discovery của nền tảng.

Không duy trì danh sách IP thủ công nếu broker thường xuyên thay thế node. Dùng label/annotation ổn định để Prometheus tìm đúng exporter port.

### 11.3. Scrape interval và timeout

Chọn `scrape_interval` theo nhu cầu phát hiện sự cố và chi phí ingest. 15s là ví dụ phổ biến; không phải yêu cầu bắt buộc. Với metric ít biến động có thể scrape chậm hơn. Scrape quá nhanh làm tăng tải JMX, exporter, Prometheus và TSDB mà không chắc tăng chất lượng cảnh báo.

`scrape_timeout` phải nhỏ hơn hoặc bằng `scrape_interval`. Nếu endpoint chậm, điều tra exporter/JVM trước khi chỉ tăng timeout.

### 11.4. Kiểm tra target

Trong Prometheus UI, mở trang `/targets` và xác minh:

- Target có trạng thái `UP`.
- `last scrape` cập nhật theo interval.
- `scrape duration` không tăng bất thường.
- `last error` rỗng.
- Labels xác định đúng cluster/broker/process.

`UP` chỉ xác nhận HTTP scrape thành công. Nó không bảo đảm rules đã export đủ metric hoặc giá trị metric có ý nghĩa.

## 12. PromQL cơ bản cho Kafka

Các truy vấn dưới đây giả định custom metric names từ ví dụ rules. Điều chỉnh theo metric name thực tế của exporter.

### 12.1. Throughput vào cluster

```promql
sum by (cluster) (
  rate(kafka_server_broker_topic_bytesin_total[5m])
)
```

Đơn vị là byte/giây nếu counter gốc đếm byte. Có thể chia cho `1024^2` để hiển thị MiB/s.

### 12.2. Message rate theo broker

```promql
sum by (cluster, instance) (
  rate(kafka_server_broker_topic_messagesin_total[5m])
)
```

So sánh giữa broker giúp phát hiện phân phối traffic lệch, nhưng cần xét leader/partition assignment và traffic replication.

### 12.3. Under-replicated partitions

```promql
max by (cluster) (
  kafka_server_replica_manager_underreplicatedpartitions
)
```

Không cộng cùng một partition qua các broker nếu metric phản ánh partition count trên mỗi broker và có thể đếm trùng. Chọn `max`, kiểm tra theo instance hoặc dùng metric cluster-wide phù hợp.

### 12.4. Heap utilization

```promql
100 *
  jvm_memory_heap_used_bytes
  /
  jvm_memory_heap_max_bytes
```

Heap utilization cao liên tục cần đối chiếu GC pause, RSS và memory limit.

### 12.5. Request failure rate

```promql
sum by (cluster, instance) (
  rate(kafka_server_broker_topic_failedproducerequests_total[5m])
)
```

Theo dõi riêng Produce và Fetch. Một giá trị lớn cần phân loại error code qua log/client metrics; MBean rate không luôn cung cấp nguyên nhân lỗi cụ thể.

### 12.6. Request p99 latency

```promql
max by (cluster, request) (
  kafka_network_request_total_time_ms_p99
)
```

Giá trị là millisecond theo rule mẫu. Dùng `max` để xem broker/request type chậm nhất; truy vấn từng `instance` khi cần tìm node gây latency. Đây là percentile riêng từng broker, không phải percentile chính xác của toàn cluster.

### 12.7. Scrape health

```promql
up{job="kafka-brokers"}
```

Kiểm tra exporter có phản hồi. Dùng `absent()` hoặc alert cho target mất hẳn khỏi service discovery nếu cần phát hiện broker biến mất.

## 13. Dashboard Kafka nên có

Một dashboard tổng quan nên trả lời nhanh bốn câu hỏi: traffic ra sao, broker có khỏe không, replication có an toàn không và JVM có đang bị áp lực không.

### 13.1. Cluster overview

- Tổng messages in/s.
- Tổng bytes in/out per second.
- Số broker target UP.
- Số under-replicated và under-min-ISR partition.
- Produce/fetch failure rate.
- Consumer lag từ nguồn metric phù hợp.

### 13.2. Broker detail

- Bytes/messages in/out theo broker.
- Leader/partition count.
- Request handler/network processor idle percent.
- Request latency theo Produce/Fetch/Metadata.
- ISR shrink/expand rate.
- Disk throughput/space và network throughput từ node exporter.

### 13.3. JVM detail

- Heap used/committed/max.
- Non-heap usage.
- GC count/time/pause.
- Thread count.
- Process RSS và container memory.
- CPU usage.

### 13.4. Connect/Streams detail

- Connector/task failed count và trạng thái worker.
- Source poll/write rate, sink read/send rate.
- Task error/retry/DLQ rate.
- Streams process/thread/task state.
- State restore latency và standby lag.

### 13.5. Dashboard phải có link sang logs

Panel chỉ ra thời điểm lỗi nên cho phép người vận hành mở log của broker/worker cùng instance và khoảng thời gian. Metric xác định “cái gì đang xấu”; log thường giải thích “vì sao”.

## 14. Alerting từ JMX metrics

Alert nên dựa trên symptom kéo dài và có ngưỡng theo SLA, không chỉ báo mọi biến động nhỏ.

### 14.1. Under-replicated partition

```yaml
groups:
  - name: kafka-replication
    rules:
      - alert: KafkaUnderReplicatedPartitions
        expr: kafka_server_replica_manager_underreplicatedpartitions > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Kafka broker có partition chưa đủ replica đồng bộ
```

Với môi trường yêu cầu availability cao, có thể có alert nghiêm trọng hơn khi under-min-ISR lớn hơn 0 hoặc kéo dài.

### 14.2. Exporter scrape failure

```yaml
      - alert: KafkaJmxExporterDown
        expr: up{job="kafka-brokers"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: Prometheus không scrape được JMX exporter của Kafka
```

Alert này có thể do broker dừng, exporter dừng, network/firewall hoặc scrape config sai. Cần phân biệt process down với endpoint metrics down.

### 14.3. Heap pressure

```yaml
      - alert: KafkaJvmHeapHigh
        expr: >-
          100 * jvm_memory_heap_used_bytes
          / jvm_memory_heap_max_bytes > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Heap Kafka duy trì ở mức cao
```

Ngưỡng 85% chỉ là ví dụ. Điều chỉnh theo GC, heap sizing, workload và container memory.

### 14.4. Request handler bận

Nếu metric idle ratio thấp liên tục, cảnh báo khi thấp hơn ngưỡng vận hành đã kiểm chứng. Ví dụ:

```promql
kafka_server_request_handler_avg_idle_ratio < 0.1
```

Đừng cảnh báo chỉ theo một sample; dùng `for` để loại bỏ spike ngắn và đối chiếu queue/latency.

### 14.5. Alert không nên tạo noise

- Dùng `for` cho symptom kéo dài.
- Group alert theo cluster và broker.
- Phân biệt warning/critical theo tác động.
- Gắn runbook URL và dashboard link.
- Không dùng label động như exception message.
- Có inhibit rule để tránh gửi hàng chục alert phụ khi cả broker down.

## 15. Cardinality và chi phí Prometheus

Mỗi tổ hợp metric name + label values là một time series. Kafka có thể có nhiều topic, partition, client ID và request type. Nếu export mọi MBean/attribute cùng mọi label, số series có thể tăng rất nhanh.

### 15.1. Nguồn cardinality cao

- `topic` khi cluster có hàng nghìn topic.
- `partition` khi topic có hàng chục nghìn partition.
- `client-id` được tạo ngẫu nhiên theo request/process.
- `client-id`/`group` có chứa tenant hoặc user ID.
- Label chứa exception message hoặc request ID.
- Mỗi task/processor node trong Kafka Streams.

### 15.2. Kiểm soát cardinality

- Dùng `includeObjectNames` để giới hạn MBean.
- Chỉ map attribute cần cho dashboard/alert.
- Không export label có giá trị không giới hạn.
- Chuẩn hóa client ID và tên application.
- Dùng metric aggregate theo broker/cluster khi đủ cho mục tiêu.
- Tách dashboard drill-down khỏi metric có cardinality quá cao.
- Theo dõi số series và ingestion rate của Prometheus.

Không bỏ toàn bộ label `topic` nếu cần điều tra topic nóng; hãy giới hạn bằng whitelist/allowlist hoặc scrape/recording strategy phù hợp.

### 15.3. Recording rules

Với query thường dùng và tốn tài nguyên, tạo recording rule để lưu kết quả tổng hợp, ví dụ bytes in/s theo cluster hoặc under-replicated partitions. Đặt tên recording rule có quy ước và giữ nguyên đơn vị.

## 16. Bảo mật endpoint metrics

Metrics có thể tiết lộ broker hostname, topic names, client IDs, throughput và trạng thái hạ tầng. Không coi `/metrics` là endpoint công khai vô hại.

### 16.1. Network boundary

- Bind exporter vào loopback nếu Prometheus agent chạy cùng host.
- Nếu Prometheus ở host khác, bind vào private interface.
- Chỉ cho phép Prometheus server/agent truy cập port metrics qua firewall/security group.
- Không publish port metrics qua Internet hoặc ingress công khai.
- Tách port metrics khỏi Kafka client listener và Connect REST API.

### 16.2. TLS và authentication

Nếu exporter endpoint cần đi qua network không hoàn toàn tin cậy, dùng TLS/authentication tại exporter nếu release hỗ trợ hoặc đặt reverse proxy/service mesh có TLS và access control phía trước. Xác minh Prometheus scrape config tương ứng.

Không giả định JMX Exporter Java agent có authentication giống Kafka broker. Cấu hình bảo mật HTTP của exporter phụ thuộc version và mode triển khai.

### 16.3. Remote JMX

Nếu dùng standalone exporter/remote JMX:

- Cố định RMI registry port và RMI server port.
- Cấu hình hostname mà exporter có thể resolve.
- Bật authentication và TLS theo JMX implementation.
- Giới hạn firewall chỉ cho exporter host.
- Không expose RMI port trên public interface.

Remote JMX/RMI có nhiều chi tiết mạng hơn HTTP scrape của Java agent; ưu tiên agent nếu không có lý do vận hành để tách process.

### 16.4. Secrets và config file

Không ghi password/truststore secret trực tiếp vào Git. Dùng secret manager, file permission chặt hoặc injection từ deployment platform. Không đưa credential vào metric label, annotation hay log của exporter.

## 17. Triển khai rolling và vận hành exporter

### 17.1. Quy trình rollout broker

1. Chọn một broker ít rủi ro để thử trước.
2. Kiểm tra cluster replication/ISR khỏe và controller ổn định.
3. Cài JMX Exporter JAR/config trên node.
4. Thêm Java agent option nhưng giữ nguyên JVM options hiện tại.
5. Restart broker theo quy trình rolling restart Kafka.
6. Xác minh broker trở lại cluster và replica bắt kịp.
7. Kiểm tra `/metrics`, Prometheus target và metric names.
8. Lặp lại với broker tiếp theo.
9. Sau cùng, xác minh mọi broker có cùng rule version và label convention.

Không restart đồng thời toàn bộ broker chỉ để bật exporter. Việc gắn agent thường yêu cầu restart process; phải tuân theo maintenance procedure của cluster.

### 17.2. Cập nhật rule

Một số mode/version exporter có thể reload config, nhưng không giả định mọi cấu hình đều reload nóng. Kiểm tra tài liệu release; nếu cần restart, rollout theo từng broker.

Khi đổi metric name/label:

- Kiểm tra dashboard và alert phụ thuộc series cũ.
- Cập nhật recording rules.
- Tránh để hai rule cùng export metric name với type khác nhau.
- Có giai đoạn chuyển tiếp nếu dashboard cần đọc cả series cũ và mới.

### 17.3. Rollback

Giữ JAR và YAML config phiên bản trước. Nếu exporter làm JVM startup lỗi hoặc tăng overhead bất thường:

1. Rollback JVM option/agent theo node.
2. Restart broker theo rolling plan.
3. Xác minh cluster health và replication.
4. Kiểm tra log startup để xác định agent/config gây lỗi.
5. Sửa config trên staging trước khi thử lại.

Không xóa log hoặc bỏ qua JVM startup exception; exporter lỗi có thể làm broker process không khởi động nếu Java agent không load được.

## 18. Kiểm tra chất lượng metric

Metric chỉ hữu ích khi có semantics đúng và ổn định.

### 18.1. Kiểm tra type

- Counter phải tăng đơn điệu trong vòng đời process.
- Gauge phải phản ánh trạng thái hiện tại và có thể giảm.
- Rate MBean phải được xuất như gauge.
- Percentile phải có đơn vị và label mô tả request type.

Nếu một metric counter giảm mà không có restart, có thể rule đang map nhầm attribute hoặc MBean reset theo window.

### 18.2. Kiểm tra đơn vị

Đặt suffix đúng:

- `_bytes` cho byte.
- `_seconds` cho giây.
- `_milliseconds` chỉ khi giữ nguyên millisecond; ưu tiên convert về seconds nếu rule hỗ trợ.
- `_total` cho counter.
- `_ratio` cho tỷ lệ từ 0 đến 1.

Không cộng byte với MiB hoặc millisecond với second trong cùng query.

### 18.3. Kiểm tra label consistency

Mọi broker cùng loại metric phải dùng cùng label keys. Nếu một broker export `broker_id` còn broker khác thiếu, query aggregate có thể tạo series không đồng nhất.

Gắn labels hạ tầng như `cluster`, `environment`, `broker_id`, `role` từ Prometheus service discovery hoặc relabel config, thay vì cố nhúng mọi thông tin vào JMX rule.

### 18.4. Kiểm tra metric khi restart

Counter của JVM/process reset khi broker restart. Prometheus `rate()` xử lý counter reset nếu metric được khai báo đúng type và có đủ sample. Dashboard cần phân biệt khoảng thời gian process restart với traffic giảm thực sự.

## 19. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Port metrics không mở | Agent không được truyền vào JVM, port trùng hoặc bind host sai | Kiểm tra command line, startup log và socket |
| Broker không khởi động sau khi thêm agent | Sai path JAR/config, Java version hoặc agent option syntax | Đọc JVM startup error, xác minh artifact và cú pháp |
| Endpoint trả 404 | Sai path hoặc reverse proxy route sai | Kiểm tra `/metrics`, proxy mapping và exporter mode |
| Endpoint trả 200 nhưng không có metric Kafka | Rule không match hoặc MBean chưa tồn tại | Kiểm tra ObjectName/attribute và exporter logs |
| Có `jmx_scrape_error` | Lỗi truy cập MBean hoặc rule/attribute | Xem log agent và rule pattern |
| Metric name khác dashboard | Rule đổi capture group/casing hoặc exporter version | Kiểm tra raw `/metrics` và config version |
| Metric xuất hiện trùng | Nhiều rule match cùng MBean/attribute hoặc agent chạy hai lần | Rà soát rule order và JVM options |
| Prometheus target DOWN | Firewall, DNS, bind address, process hoặc TLS | Kiểm tra `/targets`, curl từ Prometheus host và network policy |
| Scrape duration cao | Quá nhiều MBean/attribute hoặc exporter JVM bị quá tải | Thu hẹp include list, rule và scrape interval |
| Prometheus cardinality tăng đột biến | Label topic/client/partition quá rộng | Phân tích series count, whitelist và relabel/drop |
| Broker CPU tăng sau rollout | Exporter scrape quá thường xuyên hoặc rule quá rộng | So sánh CPU trước/sau, giảm MBean và scrape frequency |
| Heap ổn nhưng container OOM | Native memory/RocksDB/direct buffer/RSS tăng | Kiểm tra process RSS, cgroup memory và native allocations |
| Metric mất sau broker upgrade | MBean name/attribute thay đổi | So sánh MBeans của version mới và cập nhật rules |
| Chỉ một broker thiếu metric | Config/agent version hoặc role khác nhau | So sánh JVM options, JAR checksum, YAML và broker role |

## 20. Checklist triển khai production

- Đã chọn Java agent hay standalone exporter theo kiến trúc mạng.
- JMX Exporter JAR có version/checksum được quản lý.
- Mỗi JVM process có exporter port riêng.
- Agent option được thêm mà không ghi đè JVM options hiện tại.
- YAML rules chỉ lấy MBeans/attributes cần thiết.
- Metric names có prefix, type và unit nhất quán.
- Broker metrics bao gồm traffic, replication, request latency và thread pool.
- JVM metrics bao gồm heap, GC, thread và process/container memory.
- Client/Connect/Streams JVM được instrument riêng khi cần.
- Prometheus target có labels cluster/environment/instance/broker role.
- Scrape interval/timeout phù hợp với chi phí và nhu cầu phát hiện.
- Dashboard hiển thị throughput, replication, request latency, JVM và client health.
- Alert có `for`, severity, runbook và dashboard link.
- Cardinality được kiểm soát, không dùng ID động làm label.
- Endpoint metrics chỉ truy cập từ network được phép.
- Remote JMX/RMI không mở public interface.
- Có quy trình rolling restart, config update và rollback.
- Có kiểm tra `/metrics`, Prometheus `/targets` và metric semantics sau rollout.
- Đã thử restart broker và xác minh counter reset/rate behavior.
- Có kế hoạch cập nhật rules khi nâng Kafka/JDK/exporter.

## 21. Câu hỏi tự kiểm tra

1. JMX, MBean, JMX Exporter và Prometheus có vai trò khác nhau thế nào?
2. Vì sao Prometheus không scrape trực tiếp JMX MBean?
3. Java agent khác standalone JMX Exporter ở cách kết nối và bảo mật ra sao?
4. Vì sao gắn exporter vào broker không thu thập được metrics của Kafka Connect worker?
5. `BrokerTopicMetrics` và `ReplicaManager` cung cấp nhóm thông tin nào?
6. Counter, gauge, rate và percentile khác nhau như thế nào?
7. Vì sao dùng `rate()` cho counter nhưng không dùng cho gauge?
8. `UnderReplicatedPartitions` và `UnderMinIsrPartitionCount` phản ánh rủi ro gì?
9. Request queue time và total request time giúp phân biệt vấn đề nào?
10. Vì sao heap usage không phản ánh toàn bộ memory của Kafka process?
11. Khi nào cần instrument producer/consumer JVM riêng?
12. `includeObjectNames` giúp kiểm soát điều gì?
13. Vì sao label `client-id` hoặc `topic` có thể làm tăng cardinality?
14. `UP` trong Prometheus có đủ chứng minh metric đúng không?
15. Vì sao phải kiểm tra MBean name sau khi nâng Kafka/JDK?
16. Tại sao cần rolling restart khi thêm Java agent vào broker?
17. Làm thế nào bảo vệ endpoint `/metrics`?
18. Những dashboard panel nào giúp phát hiện broker quá tải hoặc replication không khỏe?

## 22. Tài liệu tham khảo

- Prometheus JMX Exporter — [Configuration and Java agent](https://github.com/prometheus/jmx_exporter)
- Prometheus — [Exposition formats](https://prometheus.io/docs/instrumenting/exposition_formats/)
- Prometheus — [Configuration and scrape jobs](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- Prometheus — [Query functions: rate and increase](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- Apache Kafka — [Monitoring](https://kafka.apache.org/documentation/#monitoring)
- Apache Kafka — [Broker metrics](https://kafka.apache.org/documentation/#broker_monitoring)
- Apache Kafka — [Producer and consumer monitoring](https://kafka.apache.org/documentation/#monitoring)

## Kết luận

JMX cung cấp các MBean metrics bên trong Kafka và JVM; JMX Exporter chuyển chúng thành HTTP metrics để Prometheus scrape. Java agent là lựa chọn thuận tiện cho broker, Connect worker và Streams application vì mỗi JVM có endpoint riêng mà không cần mở remote JMX/RMI. Bộ metric nên tập trung vào throughput, replication, request latency, thread pool, JVM và client behavior. Rules cần đặt tên/type/unit nhất quán, kiểm soát label cardinality và được kiểm chứng trên đúng Kafka/JDK version. Bảo vệ endpoint metrics, triển khai rolling, kiểm tra `/metrics`/Prometheus targets và duy trì dashboard/alert/runbook giúp hệ thống quan sát có giá trị trong vận hành production.
