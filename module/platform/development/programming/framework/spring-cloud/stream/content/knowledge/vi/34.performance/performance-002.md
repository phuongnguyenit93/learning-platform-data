# Đo điểm nghẽn tại broker, consumer và dịch vụ phụ thuộc

Một luồng Spring Cloud Stream có thể chậm dù function xử lý rất nhanh. Message có thể phải chờ producer gửi, chờ broker ghi hoặc phân phối, chờ consumer nhận, chờ function xử lý, chờ dịch vụ bên ngoài trả lời rồi mới được acknowledge hoặc commit. Nếu chỉ đo thời gian chạy của function, nhóm vận hành có thể tối ưu nhầm tầng và làm hệ thống phức tạp hơn mà throughput không tăng.

Cách đo hiệu quả bắt đầu bằng một ngân sách độ trễ end-to-end và chia nó thành các khoảng có thể quan sát. Cần đo riêng thời gian xử lý trong ứng dụng, thời gian chờ trong broker, thời gian lấy kết nối đến dependency, thời gian phản hồi của dependency và thời gian xác nhận message. Sau đó đối chiếu metrics của ứng dụng với metrics broker và dịch vụ phụ thuộc để tìm tầng đang giới hạn throughput.

Bài học này xây dựng quy trình đo và chẩn đoán cho Spring Cloud Stream với Kafka, RabbitMQ hoặc Pulsar. Bạn sẽ biết cần đo gì, đọc tín hiệu nào, thiết kế load test ra sao và chọn cách xử lý theo nguyên nhân thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân rã end-to-end latency thành producer, broker, consumer, function, dependency và acknowledgement.
- Phân biệt thời gian xử lý với thời gian chờ trong queue và consumer lag.
- Chọn metrics p50, p95, p99, throughput, backlog và oldest-message age.
- Đo thời gian xử lý function và từng dependency bằng Micrometer Observation.
- Đọc các chỉ số broker đặc trưng của Kafka, RabbitMQ và Pulsar.
- Phân biệt consumer thiếu concurrency với consumer bị chặn bởi I/O hoặc dependency.
- Dùng Little's Law để ước lượng backlog và thời gian chờ.
- Thiết kế load test có thể tái hiện điểm nghẽn.
- Chọn biện pháp tối ưu dựa trên bằng chứng và xác minh lại bằng cùng một workload.

## 1. Nhìn toàn bộ đường đi của một message

Một message thường đi qua các chặng sau:

1. Producer tạo payload, serialize và gửi request.
2. Broker nhận request, xác thực, định tuyến, ghi dữ liệu và replication theo cấu hình.
3. Message nằm trong topic/queue cho đến khi consumer có thể nhận.
4. Consumer fetch hoặc nhận message, deserialize và chuyển vào function.
5. Function chạy logic nghiệp vụ.
6. Function gọi dịch vụ phụ thuộc như HTTP API, database, cache hoặc object storage.
7. Consumer acknowledge hoặc commit tiến độ theo binder.
8. Broker cập nhật trạng thái giao nhận và giải phóng tài nguyên tương ứng.

~~~mermaid
flowchart LR
    A["Producer<br/>serialize + send"] --> B["Broker<br/>accept + persist + route"]
    B --> C["Queue / partition<br/>waiting time"]
    C --> D["Consumer<br/>fetch + deserialize"]
    D --> E["Spring Cloud Stream<br/>function processing"]
    E --> F["Dependency<br/>HTTP / DB / cache"]
    F --> G["Ack / commit"]
    G --> H["Broker progress"]
~~~

Độ trễ end-to-end có thể được biểu diễn gần đúng:

~~~text
T_end_to_end =
    T_producer
  + T_broker_accept
  + T_queue_wait
  + T_consumer_dispatch
  + T_deserialize
  + T_function
  + T_dependency_wait
  + T_dependency_service
  + T_ack_or_commit
~~~

Một số khoảng có thể chồng lấp do batching, asynchronous I/O, prefetch hoặc xử lý song song. Vì vậy, không nên cộng mọi metric độc lập rồi coi kết quả là một phép đo chính xác tuyệt đối. Mô hình này giúp đặt câu hỏi đúng và xác định tầng cần đo sâu hơn.

### Phân biệt ba loại thời gian thường bị nhầm

- **Processing duration:** thời gian function thực thi sau khi đã nhận message.
- **Queue wait / message age:** thời gian message chờ trước khi consumer bắt đầu xử lý.
- **Consumer lag:** chênh lệch tiến độ consumer với dữ liệu mới nhất của broker; thường được đo theo số record hoặc offset, không trực tiếp là thời gian.

Consumer lag bằng 10.000 record không tự nói rằng message chờ 10 giây hay 10 phút. Cần thêm tốc độ ingest, tốc độ xử lý và tuổi của message cũ nhất để diễn giải.

## 2. Thiết lập latency budget và baseline

Trước khi tối ưu, xác định mục tiêu nghiệp vụ. Ví dụ, 95% đơn hàng phải được xử lý trong 2 giây và 99% trong 5 giây. Đây là SLO end-to-end, không phải mục tiêu riêng của function.

Một latency budget minh họa:

| Chặng | Ngân sách p95 |
|---|---:|
| Producer serialize + send | 50 ms |
| Broker accept/persist | 100 ms |
| Queue wait | 300 ms |
| Consumer dispatch + deserialize | 50 ms |
| Function logic | 100 ms |
| Dịch vụ pricing | 250 ms |
| Database | 150 ms |
| Ack/commit và phần còn lại | 100 ms |
| Tổng ngân sách mục tiêu | 1.100 ms |

Đây là ví dụ để phân bổ ngân sách, không phải số mặc định cho mọi hệ thống. Nếu một bước có p95 vượt ngân sách, hãy đo p99 và kiểm tra phân bố thay vì chỉ nhìn average.

### Baseline tối thiểu

Trong cùng một khoảng thời gian, ghi lại:

- Input rate và output/completion rate (message/second).
- Processing duration p50, p95, p99.
- End-to-end message age p50, p95, p99.
- Consumer lag hoặc queue backlog.
- Tuổi message cũ nhất.
- Retry, redelivery, nack, DLQ và lỗi deserialize.
- CPU, memory, garbage collection, thread pool và network.
- Broker request latency, disk/storage latency, replication/flow control.
- Dependency latency, connection-pool wait và lỗi/timeouts.

Không dùng một ảnh chụp tức thời để kết luận. So sánh các chuỗi thời gian trên cùng một cửa sổ, có mốc deploy và thay đổi tải.

## 3. Đo từng chặng bằng timestamp và timer

Để đo end-to-end age, message nên có event timestamp hoặc timestamp publish có ý nghĩa rõ ràng. Ví dụ payload:

~~~java
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt
) {}
~~~

Tại consumer, ghi nhận thời điểm bắt đầu xử lý. Có thể tính tuổi nghiệp vụ:

~~~java
import java.time.Duration;

Duration eventAge = Duration.between(
    event.occurredAt(),
    Instant.now()
);
~~~

eventAge bao gồm cả thời gian từ khi nghiệp vụ phát sinh tới lúc consumer xử lý. Nó không đồng nghĩa với queue wait. Nếu producer tạo event sớm rồi mới publish, phần chờ trước publish cũng nằm trong giá trị này.

Để ước lượng queue wait, cần timestamp publish do broker/client cung cấp hoặc header publish-time được producer ghi ngay trước khi gửi. Kafka record timestamp, Pulsar publish time và timestamp/header của RabbitMQ có semantics riêng. Hãy xác minh timestamp đang dùng là thời điểm tạo event, gửi request hay broker nhận message.

### Clock skew và đồng hồ

So sánh timestamp giữa nhiều máy phụ thuộc đồng hồ hệ thống. Nếu producer nhanh hơn consumer 300 ms, queue wait tính bằng wall clock có thể âm hoặc sai lệch. Đồng bộ NTP/chrony trên các node và theo dõi clock offset. Đối với duration bên trong một process, dùng timer monotonic như Micrometer Timer hoặc System.nanoTime(), không lấy hiệu hai giá trị Instant từ đồng hồ có thể bị điều chỉnh.

### Đo duration trong ứng dụng

Micrometer Observation có thể tạo span và timer cho từng bước nghiệp vụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

@Service
class PricingGateway {

    private final ObservationRegistry registry;
    private final PricingClient client;

    PricingGateway(ObservationRegistry registry, PricingClient client) {
        this.registry = registry;
        this.client = client;
    }

    Price quote(OrderCreated event) {
        return Observation.createNotStarted("orders.dependency.pricing", registry)
            .lowCardinalityKeyValue("dependency", "pricing")
            .lowCardinalityKeyValue("operation", "quote")
            .observe(() -> client.quote(event.orderId()));
    }
}
~~~

Đặt observation quanh lời gọi dependency để trace phân biệt function processing với pricing call. Nếu HTTP client đã được instrument tự động, tránh tạo span trùng lặp; dùng trace waterfall để xác nhận instrumentation đang bao phủ đúng tầng.

Không gắn eventId, orderId, customerId hoặc URL có ID động vào metric tag. Những giá trị này có cardinality cao. Giữ chúng trong trace/log có kiểm soát; metric chỉ dùng các nhãn hữu hạn như function, dependency, operation, outcome và region.

## 4. Đo phía producer và broker

Producer send latency chỉ đo một phần đường đi. Nó có thể gồm thời gian serialize, chờ buffer, retry và chờ broker phản hồi theo acknowledgement policy. Một producer gửi nhanh không chứng minh broker đang xử lý backlog tốt: broker có thể nhận message nhanh nhưng consumer đọc chậm.

### Các chỉ số producer

- Messages sent per second.
- Send request latency p50/p95/p99.
- Serialization duration.
- Batch size và batch fill ratio.
- Retry count và send error rate.
- Request timeout, buffer wait và blocked time.
- Bytes in per second và compression ratio.

Nếu send latency tăng cùng broker request latency, nghi ngờ broker hoặc network. Nếu send latency tăng nhưng broker khỏe, kiểm tra serialize, producer buffer, batching, DNS/TLS và client-side throttling.

### Broker cần đo gì?

| Nhóm | Câu hỏi |
|---|---|
| Request latency | Broker mất bao lâu để nhận và xử lý produce/fetch? |
| Queue/request backlog | Request đang chờ xử lý ở broker hay không? |
| Storage | Disk/BookKeeper có đang giới hạn tốc độ ghi/đọc? |
| Replication | Replica/ISR có theo kịp không? |
| Network | Network processor, socket và bandwidth có bão hòa không? |
| Flow control | Broker có throttle hoặc làm chậm producer/consumer? |
| Resource | CPU, memory, page cache, disk IOPS và file descriptor có chạm ngưỡng? |

Đừng chỉ nhìn CPU broker. Broker có thể CPU thấp nhưng bị giới hạn bởi disk fsync, replication acknowledgement, network hoặc request queue.

## 5. Metrics broker theo từng hệ thống

### Apache Kafka

Các nhóm chỉ số thường dùng:

| Nhóm | Metric/tín hiệu | Ý nghĩa |
|---|---|---|
| Traffic | BytesInPerSec, BytesOutPerSec, MessagesInPerSec | Lưu lượng vào/ra |
| Request | RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs, ResponseQueueTimeMs, ResponseSendTimeMs | Thời gian các giai đoạn xử lý request |
| Broker capacity | RequestHandlerAvgIdlePercent, NetworkProcessorAvgIdlePercent | Mức nhàn rỗi của request/network threads |
| Replication | UnderReplicatedPartitions, OfflinePartitionsCount, IsrShrinksPerSec | Sức khỏe replica và ISR |
| Storage | Log flush latency, disk utilization, I/O wait | Khả năng ghi log |
| Client | Produce/Fetch latency, retry, request rate | Trải nghiệm producer/consumer |

Tên JMX metric và nhóm MBean có thể thay đổi theo phiên bản Kafka. Dùng Kafka JMX/metrics docs đúng phiên bản và dashboard broker hiện có của cluster. RequestQueueTimeMs tăng cho thấy request chờ trong queue broker; RemoteTimeMs cao có thể phản ánh thời gian chờ replica hoặc xử lý từ xa tùy request type.

Nếu UnderReplicatedPartitions hoặc OfflinePartitionsCount tăng, đừng chỉ tăng producer throughput. Kiểm tra broker mất kết nối, disk chậm, ISR shrink, network và replication trước.

### RabbitMQ

Các chỉ số quan trọng:

| Nhóm | Metric/tín hiệu | Ý nghĩa |
|---|---|---|
| Ready | messages_ready | Message đang chờ consumer |
| Unacked | messages_unacknowledged | Đã giao nhưng chưa ack |
| Consumer | consumer count, consumer capacity | Năng lực nhận/xử lý của consumer |
| Throughput | publish, deliver, ack rates | Tốc độ vào, giao và xác nhận |
| Flow control | publisher flow, blocked connection | Broker đang làm chậm producer |
| Resource alarm | memory alarm, disk alarm | Broker thiếu tài nguyên |
| Queue | queue length, ingress/egress, leader/replica health | Backlog và tình trạng queue |

messages_ready tăng trong khi messages_unacknowledged thấp thường gợi ý consumer không nhận đủ hoặc không có consumer hoạt động. messages_unacknowledged tăng cao có thể do consumer nhận nhanh nhưng xử lý lâu, prefetch quá lớn hoặc ack bị trì hoãn. Kiểm tra consumer capacity và ack rate cùng queue depth.

Với quorum queue, theo dõi leader, replica, disk và network giữa các node. Queue có nhiều replica có thể tăng độ bền nhưng cũng làm tăng chi phí replication.

### Apache Pulsar

Các nhóm metrics cần quan sát:

| Nhóm | Metric/tín hiệu | Ý nghĩa |
|---|---|---|
| Topic traffic | msgRateIn, msgRateOut, throughput in/out | Tốc độ publish và dispatch |
| Subscription | backlog, unacked messages, redelivery | Tồn đọng và giao lại |
| Broker | Dispatch rate, consumer permits, broker load | Năng lực phân phối |
| Storage | BookKeeper read/write latency, journal latency, ledger errors | Độ trễ lưu trữ |
| Resource | Broker CPU/memory, bookie disk, network | Tài nguyên cụm |
| Namespace | Backlog quota, dispatch/publish throttling | Giới hạn theo namespace |

Tên metric cụ thể có thể là pulsar_rate_in, pulsar_rate_out, pulsar_subscription_back_log, pulsar_subscription_unacked_messages hoặc tên tương ứng theo phiên bản. Hãy dùng metrics endpoint và dashboard của đúng Pulsar release, vì tên và labels có thể thay đổi.

Nếu msgRateIn cao hơn msgRateOut trong thời gian dài và backlog tăng, consumer hoặc dispatch path không theo kịp. Nếu broker dispatch chậm cùng BookKeeper write/read latency cao, kiểm tra storage nodes, journal/disk và network trước khi tăng consumer count.

## 6. Đo consumer: từ fetch đến ack

Consumer có thể là điểm nghẽn dù broker khỏe. Cần đo các bước:

1. Thời gian chờ nhận message.
2. Fetch/poll và thời gian dispatch.
3. Deserialize và message conversion.
4. Thời gian chờ thread/worker.
5. Function processing.
6. Gọi dependency.
7. Ack/commit.
8. Retry hoặc redelivery.

Các metrics nên có:

- Received rate và completed rate.
- Processing duration p50/p95/p99.
- Queue wait trong executor nội bộ.
- Consumer lag theo partition/group.
- In-flight, unacked hoặc pending records.
- Ack/commit latency.
- Deserialization/conversion error rate.
- Retry/redelivery và DLQ rate.
- Concurrency thực tế và số consumer/thread đang hoạt động.

### Consumer lag không phải processing latency

Với Kafka, lag theo partition thường được tính từ latest offset trừ committed offset. Lag có thể tăng do producer tăng tốc, consumer dừng, consumer xử lý chậm hoặc partition assignment không cân bằng. Một partition nóng có thể tạo lag cao dù tổng throughput của các partition còn lại vẫn tốt.

Đọc cả:
- Lag theo từng partition, không chỉ tổng.
- Lag tăng hay giảm theo thời gian.
- Record processing rate và input rate.
- Oldest event age nếu có timestamp.
- Rebalance count và thời gian không xử lý khi rebalance.

Với RabbitMQ và Pulsar, backlog/queue depth là số lượng message chờ, còn unacked là message đã giao nhưng chưa xác nhận. Đừng gọi mọi chỉ số backlog là Kafka consumer lag; mỗi broker có semantics riêng.

### Concurrency và giới hạn partition

Tăng consumer concurrency chỉ giúp nếu có đủ partition/queue delivery capacity và downstream còn năng lực. Với Kafka, số consumer trong cùng group vượt số partition sẽ có consumer rảnh. Với RabbitMQ, nhiều consumer có thể cùng nhận từ queue nhưng prefetch và ack semantics ảnh hưởng phân phối. Với Pulsar, subscription type và consumer permits ảnh hưởng cách broker dispatch.

Nếu chỉ một partition chứa phần lớn traffic do key skew, thêm consumer không chia được partition đó thành nhiều worker độc lập. Cần xem lại key distribution, partition count và nghiệp vụ ordering.

## 7. Đo dịch vụ phụ thuộc

Một function có thể dành 80% thời gian chờ HTTP API, database hoặc cache. Khi đó, tăng consumer concurrency chỉ tạo thêm request đồng thời, làm dependency quá tải và tăng timeout.

Đo ít nhất:

| Tầng dependency | Chỉ số cần đo |
|---|---|
| HTTP/gRPC | Request duration, connect/TLS time, DNS, timeout, retry, status code |
| Connection pool | Active, idle, pending/acquire wait, max connections, connection churn |
| Database | Query duration, pool acquisition wait, lock wait, slow query, transaction time |
| Cache | Command latency, hit/miss, connection wait, timeout |
| Object storage | Request latency, throughput, throttling, retry |
| Thread/executor | Active threads, queue depth, rejected tasks, task wait time |

Phân biệt thời gian chờ lấy connection với thời gian server xử lý request. Ví dụ HTTP call tổng cộng 800 ms có thể gồm 650 ms chờ connection pool và chỉ 150 ms trên mạng/server. Tăng timeout không giải quyết được pool saturation.

### Connection pool saturation

Dấu hiệu thường gặp:
- Pending/acquire wait tăng.
- Active connection chạm max.
- Dependency service time không tăng tương ứng.
- Function thread chờ connection.
- Consumer lag tăng theo sau.

Hướng xử lý:
- Kiểm tra connection leak và thời gian giữ connection.
- Xem pool max có phù hợp giới hạn server không.
- Giảm thời gian transaction/connection hold.
- Dùng bulkhead để giới hạn concurrency.
- Tăng pool chỉ khi dependency có khả năng xử lý thêm request.

### Retry khuếch đại tải

Nếu mỗi message retry nhiều lần trong lúc dependency đang lỗi, tổng request tới dependency có thể tăng vượt input rate. Đây là retry amplification. Đo retry attempt, backoff time, timeout và số request thực tế tới dependency. Dùng exponential backoff có jitter, giới hạn số lần retry và circuit breaker/bulkhead khi phù hợp.

Retry không thay thế DLQ hoặc quy trình xử lý lỗi vĩnh viễn. Một lỗi validation không nên được retry vô hạn như lỗi mạng tạm thời.

## 8. Dùng trace để dựng waterfall

Trace giúp xem một lần xử lý đã dành thời gian ở đâu. Một waterfall tốt nên phân biệt:

- Consumer receive/dispatch.
- Function invocation.
- Deserialize/conversion nếu có instrumentation.
- Dependency HTTP/DB spans.
- Publish output.
- Ack/commit nếu có thể instrument.

Ví dụ một trace:

~~~text
orders.consume                         1,240 ms
  ├─ deserialize                          12 ms
  ├─ orders.process                      1,190 ms
  │   ├─ inventory.lookup                  35 ms
  │   ├─ pricing.http                     910 ms
  │   │   ├─ connection.acquire            680 ms
  │   │   └─ remote request                230 ms
  │   └─ orders.persist                   170 ms
  └─ ack/commit                            38 ms
~~~

Trong ví dụ, dependency pricing chiếm phần lớn thời gian và phần lớn là chờ connection. Tối ưu function Java hoặc tăng consumer concurrency sẽ không giải quyết nguyên nhân.

Không phải binder nào cũng tạo span riêng cho broker enqueue, queue wait và ack. Khi thiếu span, kết hợp event timestamp, broker metrics và application timer để suy ra khoảng chờ. Không tự đặt tên span rồi coi đó là thời gian broker nếu instrumentation chỉ đo thời gian client API.

### Correlation ID và event ID

Giữ eventId ổn định qua retry và chuyển tiếp. Trace ID thay đổi tùy propagation và sampling; eventId dùng để tìm cùng một sự kiện qua log/DLQ/replay. Không dùng eventId làm metric label. Ghi binding, destination, consumer group, attempt và outcome trong structured logs.

## 9. Queueing theory và Little's Law

Little's Law mô tả quan hệ trong một hệ thống ổn định:

~~~text
L = λ × W
~~~

Trong đó:
- L: số phần tử trung bình đang nằm trong hệ thống/queue.
- λ: throughput trung bình (message/second).
- W: thời gian trung bình một phần tử ở trong hệ thống (second).

Ví dụ, nếu luồng nhận 150 message/second và thời gian chờ trung bình trong queue là 4 giây:

~~~text
L = 150 × 4 = 600 messages
~~~

Nếu backlog tăng lên 6.000 message trong khi input rate vẫn 150 message/second, queue wait gần đúng có thể lên khoảng 40 giây trong điều kiện ổn định và service rate không đổi. Đây chỉ là ước lượng; burst, retry, nhiều partition và processing song song làm hệ thống phức tạp hơn.

### Ước lượng năng lực consumer

Nếu một consumer xử lý ổn định 40 message/second và có 5 worker thực sự hoạt động, năng lực lý thuyết là 200 message/second. Nhưng nếu dependency chỉ chịu được 120 request/second, tăng worker lên 10 có thể làm tăng pending requests và timeout thay vì tăng throughput.

Luôn đo cả:
- Offered rate: tốc độ producer đưa vào.
- Accepted rate: tốc độ broker nhận.
- Delivered rate: tốc độ broker giao cho consumer.
- Completed rate: tốc độ xử lý thành công.
- Acknowledged/committed rate: tốc độ xác nhận tiến độ.

Nếu accepted rate cao hơn completed rate trong thời gian dài, backlog sẽ tăng. Nếu completed rate cao nhưng ack rate thấp, cần điều tra ack/commit và transaction boundary.

## 10. Chẩn đoán theo dấu hiệu

| Dấu hiệu quan sát | Tầng nghi ngờ | Kiểm tra tiếp theo |
|---|---|---|
| Producer send latency tăng, broker request queue tăng | Broker hoặc network | Request queue, network idle, disk, replication |
| Producer chậm nhưng broker metrics bình thường | Producer client | Serialize, buffer, DNS/TLS, retry, batching |
| Broker khỏe, queue/backlog tăng, consumer CPU cao | Consumer compute | Function duration, GC, serialization, concurrency |
| Broker khỏe, consumer CPU thấp, function duration cao | Consumer đang chờ I/O | Trace dependency, pool wait, network |
| Function duration thấp nhưng message age cao | Queue wait/dispatch | Lag, backlog, partition assignment, consumer capacity |
| RabbitMQ ready cao, unacked thấp | Consumer không nhận đủ | Consumer count, capacity, prefetch, connection |
| RabbitMQ unacked cao | Consumer xử lý/ack chậm | Processing time, prefetch, ack timeout, blocked worker |
| Pulsar backlog tăng, dispatch rate thấp | Subscription/consumer dispatch | Consumer permits, subscription type, broker load |
| Pulsar backlog tăng và BookKeeper latency cao | Storage layer | Bookie disk, journal, network, ledger errors |
| Dependency p95 cao và pool pending tăng | Dependency client/server | Pool sizing, connection hold, service latency |
| Retry và redelivery tăng cùng dependency errors | Retry amplification | Backoff, timeout, circuit breaker, DLQ |
| Một partition lag cao hơn nhiều partition khác | Key skew/hot partition | Key distribution, partition count, event size |
| CPU thấp nhưng latency cao | I/O hoặc queue wait | Pool wait, broker, network, locks |
| CPU/GC cao và latency tăng | Compute/allocation pressure | Serialization, compression, object churn, heap/GC |

Dùng các dấu hiệu như giả thuyết để kiểm tra, không phải kết luận tự động. Một metric đơn lẻ hiếm khi đủ để chỉ ra nguyên nhân.

## 11. Quy trình điều tra điểm nghẽn

Thực hiện theo thứ tự để tránh thay nhiều biến cùng lúc:

1. Xác nhận SLO đang vi phạm: end-to-end age, p95/p99, throughput hoặc backlog.
2. Chọn một trace/message mẫu và dựng waterfall.
3. So sánh input rate, broker accepted/delivered rate, consumer completed rate và ack rate.
4. Kiểm tra backlog/lag theo topic, partition, queue hoặc subscription.
5. Đối chiếu broker metrics: request latency, disk, replication, flow control và resource alarms.
6. Kiểm tra consumer concurrency, worker queue, processing duration, deserialize và ack/commit.
7. Kiểm tra dependency spans, connection pool, server latency, timeout và retry.
8. Tạo giả thuyết một tầng đang giới hạn throughput.
9. Thay đổi một biến, chạy lại cùng workload và so sánh kết quả.
10. Xác minh không làm tăng duplicate, message loss, DLQ hoặc độ trễ ở downstream.

### Chọn cửa sổ và percentile

- p50 thể hiện trải nghiệm điển hình.
- p95 thể hiện phần lớn request chậm.
- p99 giúp phát hiện tail latency và sự kiện hiếm.
- Max dễ bị một outlier chi phối; không dùng làm chỉ số duy nhất.
- Average có thể che khuất tail latency.

Dùng histogram để backend tính percentile theo cửa sổ truy vấn. Client-side percentile không thể tổng hợp chính xác giữa nhiều instance như histogram buckets. Chọn bucket quanh SLO, ví dụ 50 ms, 100 ms, 250 ms, 500 ms, 1 s và 2 s.

## 12. Thiết kế load test để tìm giới hạn

Load test cần tái hiện workload thật, không chỉ gửi một payload nhỏ trong vài giây.

### Chuẩn bị

- Dùng payload có kích thước và schema giống production.
- Tạo key distribution giống thực tế, gồm cả hot key nếu có.
- Dùng số partition, queue và subscription tương đương.
- Cấu hình TLS, compression, batching, replication và retention như môi trường mục tiêu.
- Dùng dependency thật hoặc mock có latency/error profile rõ ràng.
- Đảm bảo broker và consumer có tài nguyên tương đương production.

### Các giai đoạn

1. **Warm-up:** khởi tạo connection, cache, JIT và consumer assignment.
2. **Ramp-up:** tăng offered rate theo từng bậc.
3. **Steady state:** giữ tải đủ lâu để backlog và GC thể hiện xu hướng.
4. **Burst:** tăng tải ngắn để quan sát queue absorption và recovery.
5. **Soak:** giữ tải dài để phát hiện leak, disk growth và retry accumulation.
6. **Failure test:** làm chậm dependency, restart consumer hoặc gây broker/network interruption.
7. **Recovery:** khôi phục dịch vụ và đo thời gian drain backlog.

Ghi offered rate và completed rate song song. Closed-loop load generator có thể tự giảm tốc khi hệ thống chậm, khiến bạn không thấy backlog tăng như trong thực tế. Với hệ thống event-driven, cần một kịch bản giữ offered rate cố định hoặc mô phỏng burst độc lập với response time.

### Chỉ thay đổi một biến

Ví dụ thử consumer concurrency 2, 4, 8 và 12 trong khi giữ nguyên payload, broker, partition, dependency và offered rate. So sánh:
- Throughput hoàn tất.
- p95/p99 processing và end-to-end age.
- Lag/backlog và thời gian drain.
- CPU/GC, network và dependency pool wait.
- Retry, redelivery và lỗi.

Nếu concurrency tăng nhưng throughput không tăng, đồng thời pool pending tăng, dependency có thể là giới hạn. Nếu consumer rảnh nhưng số partition ít, broker assignment có thể là giới hạn.

## 13. Tối ưu theo nguyên nhân

### Khi broker là điểm nghẽn

- Kiểm tra disk IOPS/latency, network và replication trước.
- Kiểm tra request queue và flow control.
- Xem partition/queue count, leader placement và hot partition.
- Đánh giá batching và compression bằng load test.
- Kiểm tra message size, retention và storage growth.
- Chỉ tăng broker/partition khi có bằng chứng resource hoặc parallelism đang giới hạn.

### Khi consumer là điểm nghẽn

- Tách deserialize, function và ack duration.
- Tối ưu thuật toán, allocation và batch size.
- Điều chỉnh concurrency theo partition/queue capacity.
- Với Kafka, kiểm tra partition assignment và poll/commit behavior.
- Với RabbitMQ, điều chỉnh prefetch để cân bằng throughput với unacked memory.
- Với Pulsar, kiểm tra subscription type, receiver queue/permits và dispatch.
- Tránh tăng concurrency nếu worker đang chờ cùng một dependency.

### Khi dependency là điểm nghẽn

- Tách pool acquisition time khỏi remote service time.
- Kiểm tra connection reuse, DNS, TLS handshake và keep-alive.
- Đặt timeout theo latency budget.
- Dùng bulkhead để giới hạn số request đồng thời.
- Dùng circuit breaker và retry có backoff/jitter.
- Batch hoặc cache nếu semantics cho phép.
- Giảm số lần gọi dependency bằng cách gom request hoặc enrich dữ liệu trước.
- Xác nhận dependency có capacity trước khi tăng pool size.

### Khi queue wait là điểm nghẽn

- So sánh offered rate với completed rate.
- Kiểm tra consumer có đủ instance và partition/queue assignment không.
- Tìm hot key hoặc một queue/partition đang lệch tải.
- Xác minh consumer không bị pause bởi rebalance, flow control hoặc dependency timeout.
- Scale consumer chỉ khi có capacity và backlog được phân phối được.

## 14. Ví dụ đọc kết quả đo

Giả sử một thử nghiệm có kết quả:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| Input rate | 180 msg/s | 180 msg/s |
| Completed rate | 115 msg/s | 176 msg/s |
| Consumer p95 processing | 920 ms | 310 ms |
| Pricing pool wait p95 | 610 ms | 45 ms |
| Pricing service p95 | 180 ms | 175 ms |
| Queue oldest age | 42 s | 3 s |
| Error rate | 0,2% | 0,2% |

Trace cho thấy pricing pool wait chiếm phần lớn thời gian. Nhóm kỹ thuật giảm thời gian giữ connection và giới hạn concurrency ở mức dependency chịu được. Sau đó completed rate gần bằng input rate, queue age giảm và thời gian xử lý cải thiện. Việc tăng consumer thread trước khi xử lý pool wait có thể làm tình trạng nặng hơn.

Một ví dụ khác: consumer p95 thấp, CPU thấp nhưng oldest message age tăng; broker metrics bình thường và consumer chỉ nhận được một partition nóng. Khi đó, cần phân tích key distribution và partition strategy thay vì tối ưu function code.

## 15. Lỗi thường gặp khi đo hiệu năng

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ đo function duration | Bỏ sót queue wait và broker delay | Đo end-to-end age, lag và broker metrics |
| Dùng average thay p95/p99 | Che khuất tail latency | Dùng histogram và percentile |
| Gọi lag là thời gian chờ | Ước lượng sai độ trễ | Theo dõi record lag và oldest-message age riêng |
| Dùng wall clock để đo duration | Bị ảnh hưởng clock adjustment | Dùng Timer/monotonic clock |
| Không đồng bộ clock giữa producer/consumer | Queue wait âm hoặc sai | NTP/chrony và xác minh timestamp semantics |
| Tăng consumer concurrency ngay | Làm dependency quá tải | Đo dependency pool và throughput trước |
| Tăng prefetch quá lớn | Unacked memory tăng và phân phối tải lệch | Đo processing time và điều chỉnh prefetch |
| Retry không giới hạn | Retry amplification và backlog | Backoff, giới hạn attempt, DLQ |
| Chạy load test quá ngắn | Không thấy backlog/GC/soak issues | Warm-up, steady-state và soak test |
| Thay nhiều cấu hình cùng lúc | Không biết thay đổi nào tạo kết quả | Thay từng biến và lưu baseline |
| Gắn ID vào metric tag | Cardinality bùng nổ | ID chỉ nằm trong trace/log |
| Không đo ack/commit | Nhầm xử lý xong với giao nhận hoàn tất | Theo dõi ack/commit rate và latency |

## 16. Bài thực hành: tìm điểm nghẽn của function processOrder

Xây dựng luồng nhận OrderCreated, gọi Pricing API, ghi database và phát OrderAccepted.

1. Tạo một event có eventId và occurredAt.
2. Đo producer send duration và publish rate.
3. Đo consumer processing duration bằng Observation/Micrometer.
4. Tạo observation con cho Pricing API và database.
5. Ghi nhận pool acquisition wait, HTTP/DB service time và timeout.
6. Theo dõi broker backlog/lag và oldest message age.
7. Nếu dùng Kafka, thu thập lag theo partition và request/replication metrics.
8. Nếu dùng RabbitMQ, thu thập ready, unacked, consumer capacity và ack rate.
9. Nếu dùng Pulsar, thu thập backlog, dispatch rate, unacked và storage latency.
10. Chạy baseline với tải thấp, sau đó tăng offered rate theo bậc.
11. Làm chậm Pricing API để quan sát pool wait, retry và queue growth.
12. Tăng consumer concurrency một mức và kiểm tra dependency có bị bão hòa không.
13. Giảm thời gian giữ connection hoặc giới hạn concurrency rồi chạy lại cùng workload.
14. So sánh p50/p95/p99, completed rate, backlog và error/redelivery.
15. Viết báo cáo xác định tầng nghẽn, bằng chứng và thay đổi có hiệu quả.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| End-to-end budget | Có SLO và latency budget cho từng chặng |
| Timestamp | Phân biệt occurredAt, publish time và processing start |
| Application timing | Có function/dependency duration p50/p95/p99 |
| Broker metrics | Có request/storage/replication hoặc queue/backlog metrics phù hợp |
| Consumer | Có received/completed/ack rate và concurrency |
| Lag/backlog | Theo dõi record lag, queue depth và oldest age riêng |
| Dependency | Có pool wait, remote latency, timeout và retry |
| Trace | Waterfall chỉ ra span chậm nhất |
| Load test | Có warm-up, ramp, steady-state, burst, soak và failure |
| Capacity | Offered rate và completed rate được so sánh |
| Cardinality | Không dùng event ID làm metric label |
| Recovery | Backlog drain và redelivery được kiểm tra sau sự cố |
| Kết luận | Mỗi thay đổi có baseline và kết quả đo lại |

## Kết luận

Đo điểm nghẽn trong Spring Cloud Stream cần quan sát toàn bộ đường đi của message. Producer send latency, broker request/storage/replication, queue wait, consumer dispatch, function duration, dependency pool wait/service time và ack/commit đều là những khoảng khác nhau. Consumer lag theo record không thay thế được oldest-message age; function duration thấp cũng không chứng minh luồng đang đáp ứng SLO.

Hãy ghép metrics broker với Micrometer Observation, trace waterfall và load test có offered rate được kiểm soát. Chẩn đoán broker, consumer hay dependency bằng nhiều tín hiệu cùng lúc, thay một biến mỗi lần và chạy lại cùng workload. Chỉ tăng concurrency hoặc tài nguyên khi đã xác định tầng đó thực sự giới hạn throughput; nếu dependency hoặc queue wait là nguyên nhân, scale consumer có thể làm hệ thống chậm hơn.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.4 – Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream – Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/metrics.html)
- [Apache Kafka – Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [RabbitMQ – Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [RabbitMQ – Consumers and Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)
- [Apache Pulsar – Monitoring](https://pulsar.apache.org/docs/4.0.x/administration-metrics/)
- [Apache Pulsar – Concepts: Messaging](https://pulsar.apache.org/docs/4.0.x/concepts-messaging/)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry – Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)

