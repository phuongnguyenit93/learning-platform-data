# Đối chiếu log với broker metric trong Spring Kafka

Khi một ứng dụng Spring Kafka báo producer timeout, consumer lag tăng hoặc listener xử lý chậm, log của ứng dụng thường chỉ cho biết **điều mà client nhìn thấy**. Broker metrics cho biết **Kafka cluster đang xử lý requests, replication và partitions ra sao**. Broker logs bổ sung nguyên nhân ở phía server, ví dụ lỗi leader, ISR, authorization hoặc quota. Muốn chẩn đoán đúng, cần ghép ba nguồn này trên cùng một dòng thời gian và cùng phạm vi: cluster, broker, client, topic, partition và loại request.

Đối chiếu log với broker metric không phải là tìm một dòng log có cùng tên với một metric. Một broker metric thường là số liệu tổng hợp theo chu kỳ; log có thể là một sự kiện riêng lẻ; một ProduceRequest có thể chứa nhiều record và nhiều partition; một record có thể được retry qua nhiều broker. Vì vậy, hai nguồn dữ liệu thường **hỗ trợ giải thích lẫn nhau**, nhưng không phải lúc nào cũng khớp một-một.

Trong module **Spring Kafka Reliability Operations**, mục tiêu là xây dựng cách điều tra có thể trả lời:

- Ứng dụng gửi hoặc nhận Kafka record gặp lỗi gì?
- Broker nào xử lý request tại thời điểm đó?
- Request latency tăng ở queue, local processing, replication hay throttling?
- Lỗi có ảnh hưởng một topic/partition hay toàn cluster?
- Consumer lag tăng do producer gửi nhanh, consumer xử lý chậm, rebalance hay broker fetch bất thường?
- Log và metric có đủ bằng chứng để quyết định retry, pause, failover hoặc mở incident không?

**Nguyên tắc chính:** bắt đầu từ một log cụ thể, xác định thời điểm và phạm vi, sau đó so sánh với metric của đúng broker/request/topic trong cùng cửa sổ. Không kết luận broker lỗi chỉ từ một exception ở ứng dụng, và không kết luận một record thành công chỉ vì broker throughput vẫn cao.

## 1. Ba lớp telemetry cần đối chiếu

Một Kafka pipeline thường có ít nhất ba nguồn telemetry:

| Nguồn | Ai phát ra? | Cho biết điều gì? | Giới hạn chính |
|---|---|---|---|
| Application logs | Spring service | Business event, listener, exception, topic/partition/offset, trace | Chỉ thấy góc nhìn ứng dụng |
| Kafka client metrics/logs | Producer/consumer JVM | Send/fetch/request latency, retries, errors, poll progress | Không thấy toàn bộ trạng thái broker/replication |
| Kafka broker metrics/logs | Kafka brokers/controllers | Request queue, produce/fetch errors, ISR, leaders, quotas, server exceptions | Thường tổng hợp, không phải log từng business record |

Có thể xem mối quan hệ như sau:

~~~mermaid
flowchart TD
    A["Spring application log"] --> D["Incident timeline"]
    B["Kafka producer/consumer metrics"] --> D
    C["Kafka broker metrics"] --> D
    E["Kafka broker/controller logs"] --> D
    D --> F["Khoanh vùng cluster / broker / client / topic / partition"]
    F --> G["Chọn hành động và xác minh kết quả"]
~~~

Mỗi nguồn trả lời một phần khác nhau:

- Application log: “Tôi gọi send cho topic này và nhận TimeoutException.”
- Producer metric: “Client retry tăng, request latency cao và buffer wait tăng.”
- Broker metric: “Produce request queue tăng, request handler idle giảm, broker throttling tăng.”
- Broker log: “Broker áp quota cho client hoặc partition đang thiếu ISR.”

Khi cả bốn tín hiệu cùng xảy ra trong một cửa sổ thời gian, giả thuyết broker overload/throttling mạnh hơn nhiều so với việc chỉ nhìn một exception.

## 2. Định nghĩa đúng phạm vi trước khi so sánh

Trước khi truy vấn log hay metric, xác định chính xác **đối tượng đang được so sánh**.

| Chiều | Ví dụ | Câu hỏi |
|---|---|---|
| Environment | prod, staging | Log và metrics có thuộc cùng môi trường không? |
| Kafka cluster | kafka-primary | Có đang xem đúng cluster mà ứng dụng kết nối không? |
| Service | orders-service | Service nào phát sinh lỗi? |
| Client ID | orders-producer-2 | Producer/consumer instance nào gặp vấn đề? |
| Consumer group | billing-service | Group nào có lag hoặc commit failure? |
| Topic | orders.created | Topic nào bị ảnh hưởng? |
| Partition | 4 | Lỗi tập trung ở một partition hay nhiều partition? |
| Broker ID | 2 | Broker nào là leader/receiver tại thời điểm xảy ra? |
| Request type | Produce, Fetch, OffsetCommit | Loại request nào chậm/lỗi? |
| Time window | 10:05–10:10 UTC | Log và metric có cùng khoảng thời gian không? |

Một lỗi xảy ra trên broker 2 ở phút 10:05 có thể liên quan partition mà leader đã chuyển sang broker 4 ở phút 10:07. Nếu chỉ truy vấn leader hiện tại, có thể bỏ lỡ broker chịu trách nhiệm tại thời điểm incident.

### 2.1. Cluster identity và environment

Không ghép log từ staging với metrics của production chỉ vì topic name giống nhau. Cần có nhãn cluster/environment nhất quán trong log fields và metrics labels.

Nếu một service kết nối nhiều Kafka clusters, ghi rõ producer role hoặc cluster alias. Một dashboard chỉ ghi topic mà không ghi cluster có thể trộn các topic trùng tên ở hai clusters khác nhau.

### 2.2. Broker ID và địa chỉ broker

Broker ID là định danh logic của broker trong cluster; hostname/IP có thể thay đổi theo deployment. Log pipeline nên giữ broker ID, hostname và cluster identity để điều tra được cả trước lẫn sau khi node được thay thế.

Không dùng hostname động làm dimension duy nhất nếu hệ thống có autoscaling hoặc ephemeral pods.

## 3. Bắt đầu từ một log ứng dụng có đủ context

Một log hữu ích cho sự cố Kafka nên ghi **operation, outcome và Kafka coordinates**. Ví dụ producer:

~~~json
{
  "timestamp": "2026-11-15T10:05:21.431Z",
  "level": "ERROR",
  "service": "orders-service",
  "environment": "prod",
  "cluster": "kafka-primary",
  "event": "kafka_publish_failed",
  "producerRole": "business",
  "clientId": "orders-producer-2",
  "topic": "orders.created",
  "keyHash": "a8c2...",
  "eventId": "order-event-42",
  "traceId": "example-trace-id",
  "exceptionClass": "TimeoutException",
  "outcome": "failed"
}
~~~

Đây là cấu trúc log minh họa do ứng dụng định nghĩa; Spring Kafka không tự động xuất mọi field trên theo đúng schema này.

Consumer log có thể ghi:

~~~json
{
  "timestamp": "2026-11-15T10:05:23.008Z",
  "level": "WARN",
  "service": "billing-service",
  "cluster": "kafka-primary",
  "event": "kafka_record_processing_failed",
  "consumerGroup": "billing-service",
  "clientId": "billing-consumer-1",
  "topic": "orders.created",
  "partition": 4,
  "offset": 9812,
  "eventId": "order-event-42",
  "traceId": "example-trace-id",
  "exceptionClass": "DataAccessException"
}
~~~

Các trường hữu ích:

- Timestamp UTC có độ chính xác đủ để ghép với metric scrape window.
- Service, environment và Kafka cluster.
- Producer client ID hoặc consumer group/client ID.
- Topic, partition, offset khi đã có ConsumerRecord.
- Business event ID hoặc correlation ID ổn định, nếu được phép log.
- Operation và outcome: send, receive, commit, retry, recovery.
- Exception class/category đã chuẩn hóa.
- Trace ID/span ID để tìm trace liên quan.

**Không log raw payload, access token hoặc dữ liệu cá nhân chỉ để tăng khả năng correlation.** Với key nhạy cảm, có thể log hash hoặc business identifier đã được phê duyệt.

### 3.1. Producer log và consumer log có lượng thông tin khác nhau

Trước khi broker xác nhận produce, application có thể biết topic/key và exception nhưng chưa có partition/offset cuối cùng. Với send success, callback có thể cung cấp RecordMetadata chứa topic, partition và offset.

Consumer nhận ConsumerRecord nên có topic, partition và offset ngay khi record được giao. Dùng các coordinates này để điều tra record cụ thể ở consumer side.

### 3.2. Correlation ID của Kafka protocol

Kafka protocol có correlation ID cho request/response trên connection. Client DEBUG logs có thể ghi thông tin request/correlation ID, tùy version và logger category. Tuy nhiên application business log thường không biết correlation ID đó.

Không nhầm Kafka protocol correlation ID với business event ID hoặc W3C Trace ID. Chúng có phạm vi và vòng đời khác nhau.

## 4. Broker metrics là số liệu tổng hợp, không phải record log

Kafka broker xuất metrics qua JMX và các cơ chế monitoring tích hợp. Một số metric thường được dùng:

| Nhóm | Metric JMX phổ biến | Ý nghĩa vận hành |
|---|---|---|
| Broker traffic | MessagesInPerSec | Số message broker nhận theo thời gian |
| Broker traffic | BytesInPerSec / BytesOutPerSec | Lưu lượng vào/ra |
| Produce/Fetch | FailedProduceRequestsPerSec | Tốc độ Produce requests thất bại |
| Produce/Fetch | FailedFetchRequestsPerSec | Tốc độ Fetch requests thất bại |
| Produce/Fetch | TotalProduceRequestsPerSec | Tốc độ Produce requests |
| Produce/Fetch | TotalFetchRequestsPerSec | Tốc độ Fetch requests |
| Request latency | TotalTimeMs | Tổng thời gian request theo request type |
| Request latency | RequestQueueTimeMs | Thời gian chờ request queue |
| Request latency | LocalTimeMs | Thời gian xử lý local ở broker |
| Request latency | RemoteTimeMs | Thời gian chờ xử lý/replication remote theo request semantics |
| Request latency | ResponseQueueTimeMs | Thời gian chờ response queue |
| Request latency | ThrottleTimeMs | Thời gian request bị throttle |
| Replication | UnderReplicatedPartitions | Số partition có replica chưa theo kịp |
| Replication | UnderMinIsrPartitionCount | Số partition dưới min ISR |
| Replication | IsrShrinksPerSec / IsrExpandsPerSec | ISR shrink/expand activity |
| Availability | OfflinePartitionsCount | Số partition offline |
| Availability | ActiveControllerCount | Trạng thái active controller theo cluster |
| Network | NetworkProcessorAvgIdlePercent | Mức rảnh trung bình của network processors |
| Request handlers | RequestHandlerAvgIdlePercent | Mức rảnh của request handler threads |
| Queues | RequestQueueSize / ResponseQueueSize | Độ dài queue nếu metric/version hỗ trợ |

Tên object, metric, scope, đơn vị và cách xuất phụ thuộc Kafka version, broker distribution và JMX exporter. Đây là **các tên JMX quen thuộc**, không phải cam kết mọi broker version đều expose chính xác cùng tập metrics.

### 4.1. Mẫu JMX object name

Một broker metric thường có object name theo dạng:

~~~text
kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec
kafka.server:type=BrokerTopicMetrics,name=FailedProduceRequestsPerSec
kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce
kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions
~~~

Các object name này chỉ minh họa cấu trúc phổ biến. Topic-specific metrics có thể có thêm dimension/topic name, và Kafka versions khác nhau có thể thay đổi cách group metrics.

### 4.2. Broker-wide và topic-specific metrics

Broker-wide metric trả lời “broker đang nhận tổng cộng bao nhiêu traffic?” Topic-specific metric trả lời “topic nào đang đóng góp traffic hoặc lỗi?”

Nếu chỉ xem broker-wide BytesInPerSec, một topic lớn có thể che mất một topic nhỏ đang lỗi. Ngược lại, topic-specific metrics giúp khoanh vùng nhưng cần tránh tạo dashboard có quá nhiều topic động.

### 4.3. RequestMetrics cần đọc theo request type

Kafka có nhiều request types: Produce, Fetch, Metadata, OffsetCommit, JoinGroup, Heartbeat và các loại khác. Khi request latency tăng, hãy phân biệt request type.

Ví dụ Produce request latency tăng có thể ảnh hưởng producer sends; Fetch request latency tăng có thể ảnh hưởng consumer progress. OffsetCommit request errors là một vấn đề khác với produce errors.

Không cộng latency của Produce và Fetch thành một con số “Kafka latency” duy nhất.

## 5. Client metrics giúp nối log ứng dụng với broker metrics

Producer và consumer client cũng xuất metrics riêng. Chúng thường là cầu nối tốt giữa application exception và broker request metrics.

### 5.1. Producer metrics

| Kafka producer metric | Dấu hiệu cần xem |
|---|---|
| record-send-rate | Producer đang gửi bao nhiêu records |
| record-error-rate | Tốc độ record send error theo client semantics |
| record-retry-rate | Retry nội bộ của producer tăng |
| request-latency-avg/max | Thời gian request tới broker |
| record-queue-time-avg/max | Record chờ trong producer accumulator |
| bufferpool-wait-time | Producer phải chờ buffer |
| produce-throttle-time-avg/max | Broker quota/throttling ảnh hưởng producer |
| connection-count | Số connections tới broker |
| metadata-age | Tuổi metadata producer đang dùng |

Khi application log ghi TimeoutException, hãy xem producer retry rate và request latency cùng thời điểm. Nếu retry tăng trước final error, có thể client đã cố phục hồi transient errors nhưng cuối cùng hết delivery deadline.

### 5.2. Consumer metrics

| Kafka consumer metric | Dấu hiệu cần xem |
|---|---|
| fetch-rate / fetch-latency | Fetch requests có tiến triển không |
| records-consumed-rate | Consumer xử lý/nhận record với tốc độ nào |
| bytes-consumed-rate | Throughput nhận dữ liệu |
| records-lag-max | Lag lớn nhất theo client assignment khi metric có |
| commit-latency-avg/max | Offset commit chậm |
| commit-rate | Tần suất commit |
| heartbeat-rate / heartbeat-response-time | Group membership/heartbeat |
| assigned-partitions | Số partition consumer đang sở hữu |

Tên và availability của client metrics phụ thuộc Kafka client version và metric scope. Consumer group lag cũng có thể được tính bởi exporter/AdminClient bằng log end offset trừ committed offset, không nhất thiết là một broker metric duy nhất.

### 5.3. Client khỏe không đồng nghĩa broker khỏe

Một consumer có thể fetch thành công nhưng listener xử lý chậm ở database. Một producer có thể send thành công nhưng downstream consumer lag tăng vì thiếu capacity.

Đối chiếu client metrics với broker metrics giúp phân biệt:

- Broker/network không đáp ứng requests.
- Client không phát request đủ nhanh.
- Listener/business logic không xử lý kịp.
- Offset commit hoặc transaction có vấn đề.

## 6. Ghép log và metric trên cùng timeline

Đây là bước quan trọng nhất trong incident response.

Giả sử application log có TimeoutException lúc 10:05:21 UTC. Quy trình:

1. Xác định log timestamp và timezone.
2. Xác định cluster, client ID, topic và producer/consumer role.
3. Mở broker metrics với một cửa sổ trước và sau thời điểm lỗi, ví dụ 10:00–10:10 UTC.
4. Xem broker leader/partition assignment ở đúng thời điểm đó.
5. So sánh request latency, failed request rate, retry, queue time, ISR và throttling.
6. Tìm broker logs quanh thời điểm đó theo broker ID và request/topic context.
7. Kiểm tra cùng client có lỗi ở broker khác hay chỉ một node.
8. Xác định thời điểm metric trở lại baseline và application error rate giảm.

~~~text
10:04:50  Producer retry rate bắt đầu tăng
10:05:05  Produce request latency tăng trên broker 2
10:05:12  Broker log ghi nhận quota throttle
10:05:21  Spring service ghi TimeoutException
10:05:30  FailedProduceRequestsPerSec tăng
10:07:00  Throttle giảm sau điều chỉnh traffic/quota
10:07:20  Producer retries trở lại baseline
10:08:00  Application send failures giảm
~~~

Timeline là ví dụ giả định để minh họa cách correlation. Trong incident thực tế, hãy dùng timestamps và metrics từ hệ thống của bạn.

### 6.1. Dùng time window đủ rộng

Không chỉ xem đúng một phút có log lỗi. Cần xem:

- **Trước lỗi:** metric nào thay đổi trước?
- **Trong lỗi:** request/replication/queue metrics nào cùng tăng?
- **Sau lỗi:** metric nào hồi phục trước và ứng dụng hồi phục sau bao lâu?

Đặt cửa sổ theo scrape interval và aggregation window. Nếu Prometheus scrape mỗi 30 giây, một truy vấn 10 giây có thể thiếu samples hoặc không phản ánh diễn biến.

### 6.2. Đồng bộ clock

Application pods, brokers, controllers, Prometheus và log collector cần đồng bộ thời gian (ví dụ NTP/chrony). Clock skew làm cho log và metrics tưởng như lệch nhau.

Lưu timestamp theo UTC, giữ timezone rõ ràng và hiểu metric timestamp là thời điểm scrape/recording rule chứ không phải thời điểm từng Kafka record được append.

### 6.3. Scrape interval và rate window

Một metric rate được tính trên nhiều samples. Nếu cửa sổ query quá ngắn so với scrape interval, kết quả có thể rỗng hoặc nhiễu.

Dùng range phù hợp, ví dụ 5m hoặc 10m trong incident overview, sau đó zoom vào cửa sổ nhỏ hơn khi có đủ dữ liệu.

## 7. Broker logs: tìm đúng logger category

Kafka broker sử dụng logging framework và logger categories khác nhau tùy version/distribution. Các nhóm thường đáng xem gồm:

| Logger/category (tham khảo) | Nội dung thường liên quan |
|---|---|
| kafka.server.KafkaApis | Xử lý API requests như Produce/Fetch |
| kafka.network.Processor | Network request/response processing |
| kafka.network.RequestChannel | Request queue/response flow |
| kafka.server.ReplicaManager | Replication, ISR và replica state |
| kafka.cluster.Partition | Leader/partition state |
| kafka.controller | Controller, leadership và metadata changes |
| kafka.coordinator.group | Consumer group coordination |
| kafka.log.LogManager | Log segments, retention và storage |
| kafka.authorizer.logger hoặc authorizer implementation logger | Authorization decisions, tùy cấu hình/version |

Tên category cụ thể và mức log phụ thuộc Kafka version, security plugin và logging configuration. Không bật DEBUG cho toàn bộ broker một cách lâu dài chỉ để tìm một lỗi; lượng log có thể tăng mạnh và làm ảnh hưởng hiệu năng/chi phí lưu trữ.

### 7.1. Broker log không ghi từng record thành công

Kafka broker thường không ghi một dòng INFO cho mỗi record được append thành công. Produce requests có batching và có thể chứa nhiều records. Vì vậy:

- Không tìm thấy log cho event ID không chứng minh broker không nhận record.
- Broker metrics có thể tăng dù không có log success tương ứng.
- Một broker log error có thể áp dụng cho cả request/batch, không phải một business event duy nhất.
- Để xác định record, kết hợp producer RecordMetadata, topic/partition/offset và consumer evidence.

### 7.2. Tăng log level có mục tiêu

Khi cần DEBUG, xác định logger category, broker và thời gian ngắn. Có runbook để khôi phục log level sau điều tra. Không để DEBUG request logging lâu trong production nếu chưa đánh giá payload exposure, throughput và disk pressure.

### 7.3. Authorization logs

Nếu producer log TopicAuthorizationException, broker authorization logs có thể cho biết principal, resource và operation bị từ chối tùy authorizer/configuration. Đây là bằng chứng tốt hơn việc suy luận từ error ratio chung.

Không log secret, credential hoặc token trong application/broker logs. Kiểm soát quyền truy cập vào security audit logs.

## 8. Correlation không phải lúc nào cũng một-một

Một application send có thể không tương ứng một broker request:

- Producer gom nhiều records vào một batch.
- Một ProduceRequest có thể gửi data cho nhiều partitions/leader brokers.
- Producer retry request sau lỗi tạm thời.
- Một record có thể được chuyển tới broker leader mới sau metadata refresh.
- Broker metrics thường aggregate nhiều clients và topics.
- Log có thể ghi ở mức request, partition hoặc controller event.

Ví dụ:

~~~text
KafkaTemplate.send(event A)
KafkaTemplate.send(event B)
KafkaTemplate.send(event C)

Producer accumulator:
  batch topic-X partition-0 -> broker-1
  batch topic-X partition-2 -> broker-3

Broker metrics:
  broker-1 Produce request rate +1
  broker-3 Produce request rate +1
~~~

Không mong đợi ba logical sends tạo ba broker request logs. Tương tự, một request failure có thể ảnh hưởng nhiều records.

### 8.1. Batching và compression

Producer batching/compression làm cho request-level bytes, request count và record count khác nhau. Khi đối chiếu BytesInPerSec với application send count, nhớ rằng metric bytes còn phụ thuộc serialized/compressed size, protocol overhead và request aggregation.

Một metric throughput tăng không thể được chuyển trực tiếp thành số business events nếu không có size distribution và batching context.

### 8.2. Retries và leader changes

Một producer có thể gửi record tới broker leader cũ, nhận lỗi, refresh metadata rồi retry tới leader mới. Broker cũ có thể ghi log lỗi, broker mới ghi nhận request thành công.

Khi điều tra, cần xem leader assignment và controller logs theo thời gian; không chỉ nhìn leader hiện tại.

## 9. Mapping: application error nào nên so với broker metric nào?

Bảng sau là điểm bắt đầu. Đây là **mối liên hệ để điều tra**, không phải ánh xạ một exception sang đúng một metric.

| Application/client symptom | Broker metrics nên xem | Broker logs nên tìm |
|---|---|---|
| Producer TimeoutException | Produce TotalTimeMs, RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs, FailedProduceRequestsPerSec, throttle | Request timeout, replication/ISR, quota, network |
| Producer retry tăng | Produce request latency, FailedProduceRequestsPerSec, throttle, network idle | Leader change, broker overload, request errors |
| NotEnoughReplicas / NotEnoughReplicasAfterAppend | UnderReplicatedPartitions, UnderMinIsrPartitionCount, ISR shrink | ReplicaManager/Partition ISR events |
| NotLeaderOrFollower | LeaderCount, OfflinePartitionsCount, controller changes | Leader/partition transition, metadata/controller logs |
| UnknownTopicOrPartition | Topic/partition metadata, OfflinePartitionsCount, controller logs | Topic creation/deletion, metadata/partition errors |
| TopicAuthorizationException | Authorization-related audit/logs, request failures | Authorizer deny, principal/resource/operation |
| RecordTooLargeException | Request size/produce failure; broker request logs nếu có | Request rejected/record size validation |
| Producer throttling | ThrottleTimeMs, produce-throttle-time, request latency | Quota enforcement/throttle messages |
| Consumer Fetch timeout | Fetch TotalTimeMs, FailedFetchRequestsPerSec, RequestQueueTimeMs, network metrics | Fetch errors, leader/replica availability |
| Consumer lag tăng | Fetch request rate/latency, BytesOutPerSec, group membership, broker load | Group coordinator/rebalance/leader logs |
| OffsetCommit failure | OffsetCommit request metrics/latency, group coordinator health | Group coordinator errors, generation/member changes |
| Under-replicated partitions | UnderReplicatedPartitions, ISR shrink/expand, OfflinePartitionsCount | ReplicaManager/Partition/controller logs |

### 9.1. Producer TimeoutException

Không dừng ở dòng exception. So sánh:

- Kafka producer request latency và retry rate.
- Broker Produce request queue/local/remote time.
- Produce failure rate.
- Throttle time.
- ISR/under-replicated partitions.
- Network processor và request handler idle.

Nếu chỉ broker 2 có request queue/latency cao trong khi các broker khác bình thường, có thể là hotspot hoặc node-specific issue. Nếu toàn cluster cùng tăng, xem load/replication/network chung.

### 9.2. NotEnoughReplicas

Đây là lỗi liên quan điều kiện replication/ISR khi producer yêu cầu acknowledgement phù hợp. Xem ISR shrink, under-replicated partitions và broker/controller logs quanh thời điểm lỗi.

Không giải quyết bằng cách đổi producer sang acks yếu hơn mà chưa đánh giá durability requirement.

### 9.3. NotLeaderOrFollower

Thường liên quan metadata/leadership không còn khớp với broker nhận request, hoặc broker không phải leader/replica hợp lệ cho operation. Xem controller logs, partition leader changes và client metadata refresh/retry.

Một số lỗi transient trong leader election có thể tự hồi phục; nếu kéo dài, điều tra offline partitions, controller và broker health.

### 9.4. Consumer lag

Lag tăng không nhất thiết broker fetch hỏng. Có thể consumer listener xử lý chậm, consumer paused, group rebalance liên tục, hoặc input rate vượt processing capacity.

Đối chiếu consumer-side records-consumed-rate và listener latency với broker Fetch metrics/BytesOutPerSec, group coordinator logs và committed offsets.

## 10. Đọc RequestMetrics theo từng thành phần thời gian

Kafka RequestMetrics thường tách request time thành các thành phần, ví dụ:

- RequestQueueTimeMs
- LocalTimeMs
- RemoteTimeMs
- ResponseQueueTimeMs
- TotalTimeMs
- ThrottleTimeMs

Tên và semantics chi tiết cần xác minh theo Kafka version/request type.

Một cách đọc khái niệm:

~~~text
Request đến broker
    |
    v
RequestQueueTimeMs
    |
    v
LocalTimeMs
    |
    +--> RemoteTimeMs (nếu request cần chờ replication/remote work)
    |
    v
ResponseQueueTimeMs
    |
    v
Response gửi về client

ThrottleTimeMs: thời gian bị áp quota theo request semantics
TotalTimeMs: tổng thời gian theo định nghĩa metric của version
~~~

### 10.1. Queue time tăng

Nếu RequestQueueTimeMs tăng, request đang phải chờ trước khi được xử lý. Xem:

- RequestHandlerAvgIdlePercent giảm?
- RequestQueueSize tăng?
- CPU/GC broker có bất thường?
- Có burst traffic hoặc quá nhiều connections?
- Một broker có hotspot do partition leadership?

Đừng chỉ tăng số request handler threads; cần xác định bottleneck CPU, disk, network hoặc lock trước.

### 10.2. Local time tăng

LocalTimeMs cao có thể chỉ ra broker tốn thời gian xử lý request tại node: disk/log append, metadata, authorization, CPU hoặc các thao tác nội bộ tùy request.

Ghép với broker CPU, disk latency, page cache, log flush behavior và broker logs.

### 10.3. Remote time tăng

Với request cần replication/ack từ replicas, remote time có thể tăng khi follower chậm, network giữa brokers có vấn đề hoặc ISR/replication không khỏe.

Xem UnderReplicatedPartitions, ISR shrink, replication lag, network throughput và broker-to-broker connectivity. Không giả định mọi Produce request đều có cùng remote-time semantics; nó phụ thuộc acks/request/version.

### 10.4. Throttle time tăng

Quota throttling có thể là policy được áp dụng có chủ đích. Nếu throttle tăng, kiểm tra quota entity (user/client-id), broker quota configuration và producer traffic.

Một client có thể bị throttle trong khi broker tổng thể vẫn có CPU/network idle tốt. Đừng kết luận cluster overload chỉ từ throttle time.

## 11. Replication metrics giúp giải thích produce failures

Khi producer dùng acks=all, trạng thái replication có ảnh hưởng đến khả năng broker xác nhận request.

Những tín hiệu cần xem:

| Metric | Cách diễn giải |
|---|---|
| UnderReplicatedPartitions | Có partition có replica chưa theo kịp leader |
| UnderMinIsrPartitionCount | Partition có ISR thấp hơn cấu hình min ISR |
| IsrShrinksPerSec | ISR đang thu hẹp |
| IsrExpandsPerSec | ISR đang mở rộng trở lại |
| OfflinePartitionsCount | Partition không có leader/không online theo metric semantics |
| LeaderCount | Số partition broker đang làm leader |

Ví dụ:

~~~text
10:00 Producer sends thành công
10:02 IsrShrinksPerSec tăng
10:03 UnderReplicatedPartitions tăng
10:04 Produce request latency tăng
10:05 Application bắt đầu nhận NotEnoughReplicas
10:07 Replica hồi phục, ISR mở rộng
10:08 Producer errors giảm
~~~

Đây là timeline giả định. Nó cho thấy broker metrics có thể cung cấp bối cảnh nguyên nhân cho application exceptions.

### 11.1. min.insync.replicas và acks=all

Nếu producer dùng acks=all, broker chỉ xác nhận theo điều kiện ISR và cấu hình min ISR. Khi ISR không đủ, produce có thể bị từ chối thay vì xác nhận với durability thấp hơn.

Không hạ min.insync.replicas hoặc đổi acks để làm metric errors giảm mà không có quyết định durability được phê duyệt. Error rate thấp hơn không tự có nghĩa hệ thống an toàn hơn.

### 11.2. Một broker down có thể ảnh hưởng nhiều partition

Nếu broker chứa nhiều replicas hoặc là leader của nhiều partitions, một sự cố node có thể làm nhiều topic đồng thời tăng lỗi. Tìm pattern theo broker ID và partition leadership để phân biệt một node hotspot với một topic có payload lỗi.

## 12. Controller và consumer group logs

Một số sự cố không nằm ở Produce/Fetch data path mà ở metadata hoặc consumer group coordination.

### 12.1. Controller logs

Khi leader election, broker registration, topic partition changes hoặc controller failover xảy ra, controller logs là nguồn bằng chứng quan trọng.

So sánh với:

- LeaderCount thay đổi.
- OfflinePartitionsCount.
- UnderReplicatedPartitions.
- Producer NotLeaderOrFollower/metadata errors.
- Consumer rebalance rate.

Một đợt leader election có thể gây một số lỗi transient trong lúc client cập nhật metadata; nếu kéo dài, cần điều tra controller stability và broker connectivity.

### 12.2. Group coordinator logs

Khi consumer logs ghi rebalance, heartbeat failure hoặc OffsetCommit error, xem group coordinator logs cùng:

- JoinGroup/SyncGroup/Heartbeat/OffsetCommit request metrics.
- Consumer group membership và generation changes.
- Client max.poll.interval.ms và session timeout.
- Consumer processing duration và poll progress.
- Coordinator broker load/network.

Không nhầm một rebalance bình thường do deployment với coordinator outage. Đối chiếu deployment events và member changes cùng thời gian.

### 12.3. Consumer lag không phải một broker log line

Lag thường được tính bằng chênh lệch giữa log end offset và committed offset (hoặc vị trí đọc phù hợp theo công cụ). Nó cần dữ liệu từ topic partition và consumer group offset.

Một broker không nhất thiết ghi log “group X lag = 5000” cho từng group. Dùng exporter/AdminClient/group monitoring để tính lag và dùng broker logs để giải thích các thay đổi coordination/replication.

## 13. Prometheus: ví dụ truy vấn broker metrics

Tên metric Prometheus phụ thuộc JMX exporter rules, Kafka exporter hoặc hệ thống monitoring. Ví dụ sau giả định exporter chuẩn hóa các JMX metrics thành những tên series minh họa; **không copy query mà chưa kiểm tra /metrics thực tế**.

### 13.1. Failed produce request rate

~~~promql
sum by (cluster, broker) (
  rate(kafka_server_broker_topic_metrics_failed_produce_requests_total[5m])
)
~~~

Dùng để xem tốc độ failed produce requests theo broker. Nếu exporter dùng một metric name khác hoặc labels khác, điều chỉnh theo schema thực tế.

### 13.2. Produce request latency

Nếu exporter tạo histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, cluster, broker) (
    rate(kafka_network_requestmetrics_totaltimems_bucket{
      request="Produce"
    }[5m])
  )
)
~~~

Đây là ví dụ histogram query. Một số JMX exporters expose gauge/summary hoặc quantile khác chứ không tạo histogram buckets. Không thể áp dụng histogram_quantile nếu không có bucket series.

### 13.3. Under-replicated partitions

~~~promql
max by (cluster) (
  kafka_server_replicamanager_under_replicated_partitions
)
~~~

Gauge thường được tổng hợp theo broker; cách aggregate cluster cần tránh đếm trùng partition nếu mỗi broker expose thông tin tương tự. Với một số metric, `max` phù hợp hơn `sum`; hãy hiểu scope trước khi chọn aggregation.

### 13.4. Request handler idle

~~~promql
avg by (cluster, broker) (
  kafka_server_kafkarequesthandlerpool_requesthandleravgidlepercent
)
~~~

Giá trị thấp kéo dài có thể cho thấy request handlers bận. Cần đối chiếu CPU, request queue, request latency và broker workload; không coi một ngưỡng chung là kết luận overload.

### 13.5. So sánh producer retries và broker errors

Nếu client metrics được export riêng:

~~~promql
sum by (service, client_id) (
  rate(kafka_producer_record_retry_total[5m])
)
~~~

~~~promql
sum by (cluster, broker) (
  rate(kafka_server_broker_topic_metrics_failed_produce_requests_total[5m])
)
~~~

Hai query có labels/scope khác nhau. Chúng không thể ghép trực tiếp bằng một phép join tùy tiện. Dùng dashboard cùng time axis, sau đó lọc theo client ID, broker và topic bằng logs/metadata.

### 13.6. Không ép ratio khi thiếu mẫu số

Nếu failed request count tăng nhưng total request count bằng 0 do exporter restart hoặc metric missing, ratio có thể không xác định. Phân biệt:

- Zero errors với có traffic.
- Không có traffic.
- Metric bị missing.
- Broker/exporter không scrape được.

Alert nên có điều kiện telemetry availability và traffic volume phù hợp.

## 14. Từ JMX đến Prometheus: hiểu labels và exporter

Kafka broker thường expose JMX metrics. Một JMX exporter có thể map MBean/object name thành Prometheus metric name và labels.

Ví dụ concept:

~~~text
JMX:
kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce

Prometheus exporter:
kafka_network_requestmetrics_totaltimems{request="Produce",broker="2",cluster="primary"}
~~~

Mapping trên chỉ là minh họa. Rule file có thể đổi tên metric, bỏ dimension, đổi units hoặc thêm labels. Nếu rule làm mất request type hoặc broker ID, khả năng đối chiếu sẽ giảm.

### 14.1. Kiểm tra metric endpoint trước khi viết alert

Một quy trình:

1. Mở metrics endpoint của đúng broker/exporter.
2. Tìm metric name gốc hoặc MBean pattern.
3. Kiểm tra TYPE (counter, gauge, histogram/summary).
4. Xem labels: cluster, broker, topic, request, client.
5. Kiểm tra units và cách reset khi broker restart.
6. So sánh với Kafka JMX documentation đúng version.
7. Viết query và test trên time range có dữ liệu.
8. Kiểm tra query khi broker down hoặc exporter missing.

Không giả định một metric JMX có tên chứa “PerSec” luôn là Prometheus counter. Exporter có thể expose nó như gauge/rate đã tính sẵn. Dùng `rate()` trên một gauge rate có thể cho kết quả sai.

### 14.2. Counter, gauge và rate

- **Counter**: tăng đơn điệu cho đến khi process restart; dùng rate/increase.
- **Gauge**: giá trị hiện tại như số partition under-replicated; không dùng rate.
- **Histogram**: buckets/count/sum; dùng histogram_quantile khi có buckets.
- **Rate gauge**: đã là tốc độ theo thời gian; không áp rate thêm.

Xác định TYPE trước khi xây query.

## 15. Đối chiếu một incident producer timeout

Tình huống: Spring service ghi log TimeoutException khi gửi topic orders.created.

### Bước 1 — Tìm application log

Lấy timestamp, cluster, client ID, topic, exception category và trace ID. Nếu có send callback success trước đó, ghi lại broker/partition/offset; nếu không, outcome có thể chưa chắc chắn.

### Bước 2 — Xem producer client metrics

Kiểm tra:

- record-error-rate và record-retry-rate.
- request-latency-avg/max.
- record-queue-time.
- bufferpool-wait-time.
- produce-throttle-time.
- Connection count/metadata age.

Nếu retry và queue time tăng trước timeout, producer có thể đang chờ broker hoặc buffer.

### Bước 3 — Xác định broker leader

Dùng topic metadata/partition leadership ở thời điểm xảy ra. Tìm broker leader của partition, broker nhận ProduceRequest và các broker liên quan replication.

Không chỉ xem leader hiện tại nếu leadership đã đổi.

### Bước 4 — Xem broker metrics

Trên broker liên quan, so sánh:

- FailedProduceRequestsPerSec.
- Produce TotalTimeMs và các thành phần queue/local/remote.
- RequestQueueSize.
- RequestHandlerAvgIdlePercent.
- NetworkProcessorAvgIdlePercent.
- UnderReplicatedPartitions và ISR changes.
- ThrottleTimeMs.

### Bước 5 — Tìm broker logs

Tìm theo thời điểm và broker ID, rồi lọc logger category/request errors. Kiểm tra quota, authorization, leader, ISR và network.

### Bước 6 — Kết luận có bằng chứng

Ví dụ kết luận có thể là:

“Producer retries tăng trên client orders-producer-2; broker 3 có Produce request queue và throttle time tăng trong cùng cửa sổ; broker logs ghi quota throttle cho client identity tương ứng. Đây là bằng chứng phù hợp với throttling, cần xử lý quota/traffic.”

Nếu không có broker evidence, không bịa nguyên nhân. Có thể log broker không ghi chi tiết do log level hoặc metrics scope không đủ; ghi rõ phần chưa xác minh.

## 16. Đối chiếu consumer lag và fetch latency

Tình huống: billing-service lag tăng nhưng listener không ghi nhiều exceptions.

Đối chiếu:

1. Consumer logs: rebalance, assigned partitions, pause/resume, poll loop, commit errors.
2. Consumer metrics: records-consumed-rate, fetch latency, fetch rate, commit latency, assigned partitions.
3. Broker metrics: Fetch request latency/failures, BytesOutPerSec, request queue/handler idle, network processor idle.
4. Broker logs: group coordinator, leader changes, fetch errors, broker network issues.
5. Application metrics: listener processing duration, DB latency, worker queue depth.

### 16.1. Fetch latency cao và listener duration thấp

Có thể broker/replica/network làm fetch chậm trước khi listener nhận record. Xem broker Fetch request metrics, network, leader/replica health.

### 16.2. Fetch khỏe nhưng lag vẫn tăng

Có thể listener xử lý chậm, consumer concurrency thấp, batch lớn, dependency chậm hoặc consumer đang pause. Broker BytesOutPerSec có thể bình thường nhưng application records-consumed-rate thấp.

### 16.3. Rebalance liên tục

Xem group coordinator logs, Heartbeat/JoinGroup/SyncGroup metrics, consumer max.poll.interval.ms, session timeout, deployment events và listener processing duration. Không quy mọi rebalance cho broker load.

## 17. Đối chiếu ISR và under-replicated partitions

Một broker có thể tiếp tục nhận request nhưng replication không còn khỏe. Khi đó producer acks=all có thể timeout hoặc nhận NotEnoughReplicas.

Điều tra:

- UnderReplicatedPartitions tăng ở broker nào?
- UnderMinIsrPartitionCount có tăng không?
- ISR shrink/expand events xảy ra lúc nào?
- Replica fetcher/network có chậm không?
- Disk latency hoặc broker GC có bất thường không?
- Broker logs có partition/replica state transition nào?
- Producer acks và min.insync.replicas đang cấu hình ra sao?

### 17.1. Không chỉ nhìn cluster average

Một cluster có thể có nhiều brokers khỏe và một broker bị disk/network fault. Average CPU hoặc average latency có thể che mất node đó.

Dùng per-broker metrics và phân bố latency. So sánh leader partitions và replicas trên node bị ảnh hưởng.

### 17.2. ISR recovery cũng cần được quan sát

Sau khi lỗi được sửa, ISR expands và under-replicated count giảm có thể là dấu hiệu phục hồi. Nhưng cần xác nhận producer failures và latency cũng trở lại baseline.

Không đóng incident chỉ vì UnderReplicatedPartitions về 0 nếu application vẫn đang gặp timeout hoặc consumer backlog chưa catch up.

## 18. Throttling và quota: client log gặp broker metric nào?

Quota có thể áp dụng theo user, client ID hoặc entity khác tùy Kafka configuration. Producer có thể thấy send latency tăng hoặc throttle behavior, trong khi broker metrics ghi throttle time.

Đối chiếu:

- Client ID thực tế, principal và quota entity.
- Producer produce-throttle-time.
- Broker RequestMetrics ThrottleTimeMs.
- Produce request latency.
- BytesInPerSec và request rate.
- Broker logs/authorizer/quota logs nếu có.
- Quota configuration và thay đổi gần đây.

Một client bị throttle không nhất thiết làm toàn cluster overload. Nếu chỉ một client ID bị ảnh hưởng, điều tra quota/traffic profile của client đó.

### 18.1. Quota có thể là behavior mong đợi

Nếu quota đang bảo vệ cluster, throttle time tăng có thể phản ánh policy hoạt động đúng. Câu hỏi là traffic có được giới hạn theo SLO không, không phải mọi throttle đều là lỗi broker.

Nếu cần tăng quota, đánh giá tác động đến tổng capacity và fairness với clients khác.

## 19. Authorization và topic metadata errors

### 19.1. Authorization

Application log có thể ghi TopicAuthorizationException hoặc ClusterAuthorizationException. Đối chiếu broker authorizer logs theo principal, topic/resource và operation.

Xác nhận producer có quyền WRITE/DESCRIBE phù hợp và consumer có quyền READ/DESCRIBE/GROUP theo cấu hình security. Đừng giải quyết bằng cách cấp quyền rộng cho mọi principal.

### 19.2. UnknownTopicOrPartition

Nếu application ghi UnknownTopicOrPartitionException, kiểm tra:

- Topic có tồn tại trong cluster đúng không?
- Producer/consumer có đang dùng cluster bootstrap đúng không?
- Partition count có đúng không?
- Metadata cache có stale không?
- Topic vừa bị delete/recreate hay chưa?
- Controller logs có topic/partition state errors không?

Broker metrics throughput có thể bình thường dù một topic bị thiếu hoặc partition mapping sai. Đây là ví dụ metric aggregate không đủ thay broker/controller logs.

### 19.3. Metadata và leader changes

Producer/consumer metadata refresh có thể tạo transient errors trong lúc leader thay đổi. So sánh client metadata age, retries, broker LeaderCount và controller logs. Nếu lỗi chỉ xuất hiện ngắn rồi hồi phục, phân biệt transient failover với cluster instability kéo dài.

## 20. Network và broker resource pressure

Khi nhiều clients cùng chậm, tìm dấu hiệu ở broker/node:

| Tín hiệu | Ý nghĩa cần điều tra |
|---|---|
| NetworkProcessorAvgIdlePercent thấp | Network processors bận |
| RequestHandlerAvgIdlePercent thấp | Request handlers bận |
| RequestQueueSize tăng | Request backlog |
| ResponseQueueSize tăng | Response processing/network có thể nghẽn |
| Produce/Fetch latency tăng | Request path chậm |
| BytesIn/BytesOut cao | Traffic hoặc network capacity |
| Broker CPU/GC tăng | Tài nguyên JVM |
| Disk latency cao | Log append/replication có thể chậm |
| Network retransmits/drops | Đường truyền có vấn đề |
| Connection count tăng bất thường | Client churn/connection pressure |

Không một metric đơn lẻ chứng minh node quá tải. Ví dụ network processor idle thấp có thể do workload cao nhưng vẫn trong capacity; cần ghép throughput, latency và error rate.

### 20.1. Request queue tăng nhưng CPU thấp

Có thể request handler pool, lock, IO hoặc network dependency là bottleneck thay vì CPU. Kiểm tra thread dumps broker, disk, network và request type.

### 20.2. CPU cao nhưng request latency bình thường

Có thể traffic tăng nhưng broker vẫn xử lý tốt. Đừng alert chỉ theo CPU mà không xem latency, failed requests, queue và replication.

## 21. Structured logging cho broker và application

Để log search có ích, chuẩn hóa fields ở application side và parse broker logs theo cấu trúc nếu log format hỗ trợ.

Các field nên giữ:

- Timestamp UTC.
- Cluster, environment, broker ID, hostname.
- Logger/category, severity, exception class.
- Request type hoặc operation.
- Client ID/principal nếu có và được phép.
- Topic/partition nếu log chứa.
- Trace ID/span ID ở application logs.
- Deployment/version/config revision.
- Message/request correlation ID nếu có.

Broker logs không phải lúc nào cũng có event ID hoặc trace ID vì broker không nhất thiết giải mã business payload hay propagation context. Không mong đợi tìm thấy Trace ID trong broker log nếu broker logging chưa được instrument để trích header.

### 21.1. Log level và volume

Một quy trình debug nên:

1. Chọn broker cụ thể.
2. Chọn logger category liên quan.
3. Tăng log level trong khoảng thời gian ngắn nếu được hỗ trợ an toàn.
4. Thu thập đúng time window.
5. Khôi phục log level.
6. Đánh giá disk/log ingestion impact.

Không bật DEBUG toàn cluster vô thời hạn. Broker logs có thể chứa principal, topic names, network metadata hoặc thông tin vận hành nhạy cảm.

### 21.2. Log retention và sampling

Log pipeline có thể drop, sample hoặc delay logs. Metric scrape cũng có thể miss samples khi exporter/broker restart. Khi bằng chứng không có, ghi nhận giới hạn telemetry; không kết luận sự kiện không xảy ra chỉ vì không thấy log.

## 22. Những truy vấn log minh họa

Các ví dụ dưới đây dùng cú pháp tìm kiếm tổng quát; điều chỉnh theo Elasticsearch, Loki, Splunk hoặc hệ thống log của tổ chức.

Tìm application producer timeout:

~~~text
service="orders-service"
event="kafka_publish_failed"
exceptionClass="TimeoutException"
timestamp within incident window
~~~

Tìm broker Produce errors:

~~~text
cluster="kafka-primary"
brokerId=2
logger contains "KafkaApis" or "ReplicaManager"
timestamp within incident window
~~~

Tìm ISR changes:

~~~text
cluster="kafka-primary"
logger contains "ReplicaManager" or "Partition"
message contains "ISR" or "replica"
timestamp within incident window
~~~

Tìm consumer group coordination:

~~~text
cluster="kafka-primary"
logger contains "GroupCoordinator"
message contains group ID or generation
timestamp within incident window
~~~

Các câu truy vấn là pseudo-query, không phải syntax dùng được nguyên trạng trên mọi log platform. Hãy chuẩn hóa parser và field names trong hệ thống thực tế.

## 23. Dùng trace để bổ sung correlation

Distributed tracing giúp liên kết application spans giữa producer và consumer qua Kafka headers. Trace ID hữu ích để tìm:

- HTTP request tạo event.
- Producer send span.
- Consumer receive/listener span.
- Database hoặc HTTP dependency spans.
- Retry/DLT operations nếu được instrument.

Tuy nhiên broker metrics/logs thường không có Trace ID mặc định. Vì vậy trace không thể thay thế broker telemetry. Dùng trace để hiểu **một business execution**, dùng broker metrics để hiểu **cluster behavior**.

Không dùng Trace ID làm business event ID. Một record có thể được replay bằng trace mới; business event ID mới là định danh phù hợp cho deduplication/reconciliation.

## 24. Các lỗi correlation thường gặp

**Dùng sai timezone.** Application logs UTC nhưng dashboard hiển thị local time hoặc ngược lại. Chốt UTC và xác nhận clock sync.

**Chỉ xem broker leader hiện tại.** Leadership có thể đã thay đổi trong incident. Cần historical controller/metadata evidence.

**So sánh broker-wide metric với một client log rồi kết luận trực tiếp.** Metric tổng hợp nhiều clients/topics; cần scope và dimension phù hợp.

**Coi một ProduceRequest là một record.** Producer batching có thể gom nhiều records/partitions.

**Tìm event ID trong broker log rồi kết luận không có log là không có record.** Broker không ghi từng record thành công theo mặc định.

**Dùng rate() trên gauge.** Kiểm tra metric TYPE và exporter mapping trước khi viết PromQL.

**Coi JMX PerSec luôn là counter.** Một số metrics đã là rate gauge; áp rate lần nữa tạo kết quả sai.

**Gộp Produce và Fetch latency.** Hai request paths khác nhau, ảnh hưởng producer/consumer khác nhau.

**Coi consumer lag là broker error.** Lag có thể do listener, database, pause, concurrency hoặc input throughput.

**Bỏ qua retry.** Client có thể retry thành công trước khi ứng dụng thấy final failure; retry rate là tín hiệu sớm.

**Không xem request queue/local/remote/throttle components.** Chỉ nhìn TotalTimeMs có thể bỏ lỡ bottleneck.

**Metric thiếu samples bị hiểu là zero.** Exporter down hoặc broker restart có thể tạo gap; alert cần telemetry availability.

**Bật DEBUG toàn cluster.** Có thể làm tăng log volume, disk pressure và lộ metadata.

**Dùng client ID động làm label không giới hạn.** Cardinality cao làm monitoring backend tốn tài nguyên.

**Không giữ deployment context.** Một lần rollout có thể gây rebalance/connection churn cùng thời điểm metric biến động.

**Kết luận từ correlation thành causation.** Hai metric cùng tăng chưa đủ chứng minh một metric gây ra lỗi; cần log/error details và kiểm tra giả thuyết.

## 25. Runbook: đối chiếu log với broker metric khi có incident

### Giai đoạn A — Xác định symptom

1. Phân loại symptom: producer send error, consumer fetch/lag, offset commit, transaction abort hay DLT failure.
2. Thu log ứng dụng và chọn timestamp đầu tiên.
3. Xác định environment, cluster, service, client ID/group, topic và partition.
4. Xác định severity và phạm vi ảnh hưởng: một client, một broker, một topic hay nhiều clusters.

### Giai đoạn B — Xây timeline

1. Chuẩn hóa timestamps về UTC.
2. Chọn time window trước/trong/sau incident.
3. Đặt application logs, client metrics, broker metrics và broker logs trên cùng timeline.
4. Xem scrape interval, aggregation và missing samples.
5. Xác định metric nào thay đổi trước application exception.

### Giai đoạn C — Khoanh vùng broker/request

1. Xác định broker leader/receiver ở thời điểm incident.
2. Chọn đúng request type: Produce, Fetch, OffsetCommit, Metadata hoặc group coordination.
3. Xem request queue, local, remote, response queue, total và throttle time.
4. Xem FailedProduce/FailedFetch, replication, ISR và offline partitions.
5. Tìm broker/controller/group coordinator logs quanh cùng thời điểm.
6. So sánh per-broker và cluster-wide signals.

### Giai đoạn D — Kết luận và hành động

1. Ghi bằng chứng ủng hộ giả thuyết.
2. Ghi dữ liệu còn thiếu hoặc chưa xác minh.
3. Chọn hành động theo nguyên nhân: ACL, quota, topic, broker resource, replication, network hoặc application backpressure.
4. Không hạ durability hoặc skip offset chỉ để metric trở về bình thường.
5. Theo dõi metric/log sau thay đổi.
6. Xác nhận application errors, consumer lag và business outcome cùng hồi phục.

### 25.1. Mẫu ghi nhận incident

~~~text
Incident:
  Start time (UTC):
  Environment / Kafka cluster:
  Affected service / client ID / consumer group:
  Topic / partition:
  Broker(s) involved:
  Application symptom:
  Client metric evidence:
  Broker metric evidence:
  Broker log evidence:
  Controller/group coordinator evidence:
  Root cause confidence:
  Action taken:
  Recovery evidence:
  Remaining uncertainty:
~~~

Mẫu này giúp phân biệt bằng chứng quan sát được với giả thuyết. Nếu broker logs không có đủ detail hoặc metrics không có dimension theo client/topic, hãy ghi rõ giới hạn đó.

## 26. Kiểm thử và xác minh khả năng correlation

Không cần tạo một integration test cho mọi metric broker trong mỗi service, nhưng cần kiểm chứng telemetry pipeline và runbook bằng một môi trường Kafka test/staging có broker metrics/logs.

### 26.1. Baseline produce/consume

1. Gửi một lượng records đã biết vào topic test.
2. Ghi application send logs và producer outcomes.
3. Xác nhận broker MessagesIn/BytesIn và Produce request metrics thay đổi.
4. Consume records và xác nhận client fetch/records-consumed metrics.
5. So sánh log timeline với broker metrics trong cùng time window.
6. Xác nhận không suy ra số record chính xác từ request count khi batching bật.

### 26.2. Produce failure có kiểm soát

Dùng test principal thiếu ACL write hoặc cấu hình topic/partition sai trong cluster cô lập.

Xác nhận:

- Application log có exception/category phù hợp.
- Producer client error/retry metrics phản ánh behavior.
- Broker authorization/request logs có bằng chứng nếu cấu hình logging cung cấp.
- Không kỳ vọng broker MessagesIn tăng cho record bị từ chối trước append.
- Sau khi sửa ACL/topic, send outcome phục hồi.

### 26.3. Broker throttling

Trong môi trường test có quota, tạo traffic vượt quota có kiểm soát.

Xác nhận:

- Producer throttle time tăng.
- Broker ThrottleTimeMs hoặc quota metrics thay đổi nếu có.
- Send latency tăng tương ứng.
- Broker-wide CPU có thể vẫn thấp.
- Khi traffic giảm hoặc quota thay đổi hợp lệ, latency/throttle hồi phục.

### 26.4. Replication degradation

Trong cluster test nhiều brokers, tạo tình huống replica unavailable có kiểm soát.

Xác nhận:

- ISR shrink/under-replicated metrics thay đổi.
- Broker/replica logs ghi nhận state transitions.
- Producer acks=all có thể gặp lỗi tương ứng khi min ISR không được đáp ứng.
- Sau khi replica phục hồi, ISR expands và producer outcomes trở lại bình thường.

Không thực hiện test làm mất replica hoặc thay đổi durability trên production chỉ để xác minh dashboard.

### 26.5. Consumer lag và rebalance

Tạo listener xử lý chậm hoặc dừng consumer có kiểm soát.

Xác nhận:

- Application logs có processing latency/rebalance context.
- Consumer lag tăng.
- Fetch/OffsetCommit/group coordinator metrics/logs phản ánh tình huống phù hợp.
- Broker Fetch path vẫn có thể khỏe mạnh dù listener xử lý chậm.
- Sau phục hồi, lag catch-up và offset progress được xác nhận.

### 26.6. Exporter/telemetry failure

Dừng JMX exporter hoặc làm collector mất kết nối trong môi trường test.

Xác nhận:

- Dashboard hiển thị missing telemetry, không hiển thị nhầm zero.
- Alert báo exporter/broker scrape failure.
- Application Kafka processing không bị thay đổi chỉ vì monitoring pipeline lỗi.
- Log retention/collection vẫn có cơ chế phục hồi nếu yêu cầu.

## 27. Thiết kế dashboard correlation

Một dashboard tốt nên có các hàng liên kết cùng time axis:

### Hàng 1 — Application

- Producer logical send errors/successes.
- Listener errors và processing duration.
- Retry/DLT recovery outcomes.
- Offset commit failures.
- Business event completion latency.

### Hàng 2 — Kafka clients

- Producer record error/retry/send rates.
- Producer request latency và queue time.
- Consumer fetch latency/records-consumed-rate.
- Consumer commit latency.
- Assigned partitions và rebalance activity.

### Hàng 3 — Broker requests

- Produce/Fetch request rate và failures.
- Request queue/local/remote/response/total time.
- Throttle time.
- Request queue size và handler/network idle.

### Hàng 4 — Replication/controller

- Under-replicated partitions.
- Under-min-ISR count.
- ISR shrink/expand.
- Offline partitions và leader count.
- Controller changes/availability.

### Hàng 5 — Infrastructure

- Broker CPU, heap, GC.
- Disk latency/space.
- Network throughput/retransmits.
- JVM threads/connections.
- Exporter scrape health.

Tất cả panel phải dùng cùng cluster/environment filters và time zone. Drilldown từ application log sang client ID, topic/partition, broker ID rồi đến broker logs cần được tài liệu hóa.

## 28. Alerting: cảnh báo từ kết hợp tín hiệu

Một alert producer timeout có ý nghĩa hơn khi kết hợp:

- Application send failures tăng.
- Producer retry rate hoặc request latency tăng.
- Broker Produce failures/queue/throttle tăng.
- Metric exporter đang healthy.

Một alert replication nên kết hợp:

- UnderReplicatedPartitions tăng kéo dài.
- ISR shrink activity.
- Producer errors hoặc acks latency tăng.
- Offline partitions/under-min-ISR nếu có.

Một alert consumer lag nên kết hợp:

- Lag tăng liên tục.
- Records-consumed-rate thấp hơn input.
- Listener processing latency hoặc poll gaps.
- Fetch path và group coordinator health.

Không dùng một ngưỡng toàn cục cho mọi topic. Topic critical, DLT và audit streams có thể cần SLO/alert riêng.

### 28.1. Alert cho telemetry missing

Nếu broker exporter down, dashboard có thể không có dữ liệu FailedProduceRequests. Alert chỉ nhìn metric đó sẽ không kích hoạt vì series biến mất.

Tạo alert riêng cho target scrape failure, missing expected brokers hoặc stale samples. **Không có metric không có nghĩa metric bằng 0.**

### 28.2. Alert không nên chỉ dựa vào log count

Log sampling, rate limiting và logger level có thể làm số log thay đổi mà không phản ánh chính xác số failures. Dùng metrics có semantics rõ cho rate/ratio, logs để giải thích từng event.

## 29. Các giới hạn khi đối chiếu

Một số khác biệt không thể loại bỏ hoàn toàn:

1. **Aggregation:** broker metrics gom nhiều clients/records/requests.
2. **Batching:** một request có thể chứa nhiều records.
3. **Retry:** một logical send có thể tạo nhiều requests.
4. **Sampling:** logs/traces có thể bị sample hoặc drop.
5. **Scrape interval:** metric có thể không ghi đúng thời điểm một log xuất hiện.
6. **Clock skew:** timestamp giữa application, broker và monitoring system có thể lệch.
7. **Leadership changes:** broker chịu request có thể thay đổi trong incident.
8. **Version differences:** Kafka JMX names, labels và request metric semantics có thể thay đổi.
9. **Exporter mapping:** JMX-to-Prometheus rules có thể đổi tên/units hoặc bỏ dimensions.
10. **Broker log policy:** broker không ghi từng record success mặc định.
11. **Client-side errors:** serialization hoặc local buffer failure có thể xảy ra trước khi broker thấy request.
12. **Outcome uncertainty:** timeout ở client không luôn chứng minh broker không append record.

Khi kết quả giữa log và metric không khớp, đừng cố ép chúng phải bằng nhau. Hãy kiểm tra xem chúng đang đo cùng operation, cùng request type, cùng broker, cùng time window và cùng semantics hay không.

## 30. Checklist code review và vận hành

Trước khi đưa một Kafka service vào production, xác nhận:

1. Application logs ghi timestamp UTC, service, cluster và operation.
2. Producer logs có client ID/topic/event correlation khi có thể.
3. Consumer logs có group/topic/partition/offset.
4. Exception được phân loại theo type/category thay vì chỉ message text.
5. Kafka client metrics được thu thập theo producer/consumer.
6. Broker JMX metrics được export từ mọi broker và controller cần thiết.
7. Broker logs có retention, parsing và access controls.
8. Metrics labels có cluster/broker/request/topic dimensions phù hợp.
9. Metric TYPE và units được xác minh trước khi dùng PromQL.
10. Dashboard phân biệt Produce, Fetch, OffsetCommit và group coordination.
11. Request queue/local/remote/throttle được xem riêng khi latency tăng.
12. Replication/ISR/offline partition metrics có cảnh báo.
13. Time synchronization và scrape interval được biết rõ.
14. Historical leader changes có thể tra cứu trong incident window.
15. Không giả định broker logs có một dòng cho mỗi record thành công.
16. Không dùng Trace ID thay business event ID.
17. Exporter failure được cảnh báo riêng với zero traffic/errors.
18. Runbook có cách nối application log → client metrics → broker metrics/logs.
19. Integration/staging tests đã xác minh các mẫu produce failure, quota, replication và consumer lag.
20. Kết luận incident ghi rõ evidence, giả thuyết và phần chưa xác minh.

## 31. Tài liệu tham chiếu theo phiên bản

Khi xây dashboard và runbook, đối chiếu tài liệu đúng Kafka version, broker distribution và exporter đang sử dụng:

- **Apache Kafka Monitoring documentation**: broker, producer, consumer và request metrics.
- **Apache Kafka JMX MBean reference**: BrokerTopicMetrics, RequestMetrics, ReplicaManager, controller và network metrics.
- **Apache Kafka Broker Configs**: replication, min ISR, request handlers, quotas và logging.
- **Apache Kafka Producer Configs**: acks, retries, delivery timeout, request timeout và client ID.
- **Apache Kafka Consumer Configs**: max poll interval, session timeout, fetch và group settings.
- **Spring for Apache Kafka Reference — Logging / Monitoring**: listener container, KafkaTemplate, Micrometer và application events.
- **Spring Kafka Javadoc — KafkaTemplate / listener containers**: send results, consumer metadata, lifecycle và error handling.
- **Micrometer Documentation**: Kafka client metrics, meters, counters, gauges, timers và cardinality.
- **Prometheus Documentation**: scrape health, rate/increase, histogram queries và alerting.
- **Kafka JMX Exporter documentation**: cách map MBeans thành Prometheus metrics và labels.

Tên metrics, JMX object names, logger categories, request breakdown và units có thể thay đổi theo Kafka version/distribution. Prometheus metric names còn phụ thuộc exporter rules. Trước khi dùng một query hoặc alert trong production, hãy xác nhận series thật trên endpoint metrics và so với Javadoc/MBean của dependency đang chạy.

**Kết luận:** đối chiếu log với broker metric là quá trình ghép **một symptom cụ thể của ứng dụng** với **tín hiệu tổng hợp của client và broker** trên cùng cluster, broker, request type và thời gian. Application logs cho biết operation và exception; Kafka client metrics cho thấy retry/send/fetch behavior; broker metrics cho thấy request queues, latency, throttling và replication; broker logs giải thích các sự kiện server-side. Khi giữ đúng phạm vi và semantics của từng nguồn, đội vận hành có thể tìm nguyên nhân gốc mà không suy diễn sai từ một metric hoặc một dòng log đơn lẻ.
