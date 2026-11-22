# Cân bằng số partition, số client và mức concurrency

Hiệu năng Kafka phụ thuộc vào cách phân phối dữ liệu và công việc giữa partition, broker và client. Tăng partition có thể tăng khả năng ghi/đọc song song; tăng consumer hoặc thread có thể tận dụng thêm partition; thêm producer có thể tăng khả năng tạo tải. Nhưng nếu các con số không cân bằng, hệ thống sẽ tốn tài nguyên cho connection, buffer, rebalance và replica mà throughput không tăng tương ứng.

Thiết kế tốt bắt đầu từ workload và phép đo: cần bao nhiêu record/byte mỗi giây, latency mục tiêu là bao nhiêu, key phân bố ra sao, cần bao nhiêu consumer chạy đồng thời và cluster còn chịu được tải khi một broker hoặc instance lỗi hay không. Không có một công thức cố định như “mỗi broker 100 partition” hoặc “mỗi partition một consumer” phù hợp cho mọi hệ thống.

## 1. Vai trò của partition, client và concurrency

Ba khái niệm liên quan nhưng không thay thế nhau:

| Thành phần | Quyết định điều gì? | Có thể tăng bằng cách |
|---|---|---|
| Partition | Đơn vị lưu trữ, thứ tự và phân phối song song trong một topic | Tạo topic với nhiều partition hoặc tăng partition count |
| Client | Tiến trình ứng dụng kết nối Kafka | Thêm producer/consumer instance |
| Concurrency | Số luồng/task xử lý đồng thời bên trong ứng dụng | Tăng listener concurrency, stream threads hoặc connector tasks |

~~~mermaid
flowchart TB
    subgraph Producers["Producer clients"]
        P1["Producer 1"]
        P2["Producer 2"]
    end
    P1 --> T["Topic: P partitions"]
    P2 --> T
    subgraph Consumers["Consumer group"]
        C1["Consumer 1"]
        C2["Consumer 2"]
        C3["Consumer 3"]
    end
    T --> C1
    T --> C2
    T --> C3
~~~

Partition là đơn vị song song quan trọng nhất của consumer group. Client là tiến trình tạo hoặc xử lý dữ liệu; concurrency là số luồng/task mà tiến trình sử dụng. Một consumer có thể đọc nhiều partition, nhưng một partition trong cùng consumer group chỉ được gán cho tối đa một consumer tại một thời điểm.

## 2. Partition ảnh hưởng đến throughput và ordering

Kafka chia topic thành nhiều partition. Mỗi partition là một log append-only có offset tăng dần. Producer ghi record vào partition; consumer đọc partition theo thứ tự offset.

Lợi ích khi có nhiều partition:

- Nhiều broker có thể giữ leader của các partition khác nhau.
- Producer có thể ghi đồng thời đến nhiều partition.
- Consumer group có thể chia partition cho nhiều consumer.
- Kafka Streams tạo nhiều task hơn khi input partition count tăng.
- Có thể tăng tổng throughput bằng cách phân tán tải.

Đổi lại, partition nhiều hơn làm tăng:

- Metadata, file segment, index và file handle trên broker.
- Số replica phải phục vụ fetch/replication.
- Công việc leader election, reassignment và recovery.
- Số task, state store và changelog cần quản lý trong ứng dụng stateful.
- Chi phí rebalance và thời gian khởi động/khôi phục ở một số workload.

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu các event của cùng order phải theo đúng chuỗi Created -> Paid -> Shipped, hãy dùng order ID làm key để chúng đi vào cùng partition. Nhiều partition cho phép song song giữa các order khác nhau, không tạo thứ tự toàn cục giữa mọi order.

### Key quyết định cách phân phối

Với keyed record, partitioner mặc định thường hash key để chọn partition. Vì vậy:

- Cùng key thường vào cùng partition.
- Key phân bố đều thường tạo tải tương đối cân bằng.
- Một hot key vẫn dồn vào một partition dù topic có nhiều partition.
- Record không có key có thể được phân phối theo sticky partitioning để tăng batching; hành vi cụ thể phụ thuộc partitioner/client version.

Không chọn partition count chỉ dựa trên tổng record mỗi giây. Cần đo phân bố key, kích thước record và tải trên từng partition.

## 3. Tính số partition từ throughput mục tiêu

Một cách thực tế để ước lượng là benchmark throughput bền vững của một partition trong điều kiện gần với production. Gọi:

- \(T_{target}\): throughput mục tiêu của topic, tính bằng byte/s hoặc record/s.
- \(T_{partition}\): throughput bền vững đo được trên một partition ở latency mục tiêu.
- \(H\): hệ số headroom để xử lý peak, skew và tăng trưởng.

Ước lượng ban đầu:

\[
P_{throughput} =
\left\lceil
\frac{T_{target} \times H}{T_{partition}}
\right\rceil
\]

Ví dụ topic cần 120 MB/s, một partition chịu ổn định 8 MB/s ở p99 latency mục tiêu, và chọn headroom 1.5:

\[
P_{throughput} =
\left\lceil
\frac{120 \times 1.5}{8}
\right\rceil = 23
\]

Đây là điểm bắt đầu để thử nghiệm, không phải kết quả sizing cuối. Throughput mỗi partition thay đổi theo record size, compression, acks, replication factor, broker disk/network, key skew, producer batching và consumer fetch pattern.

Sau khi có P_throughput, kiểm tra thêm:

- Consumer cần bao nhiêu partition hoạt động đồng thời?
- Có cần chịu peak khi một broker hoặc một consumer instance dừng?
- Replica có phân bố được trên đủ broker/rack không?
- Số partition có làm tăng state store/task hoặc thời gian rebalance vượt ngân sách?
- Có thể tăng partition sau này mà không phá vỡ yêu cầu ordering theo key không?

### Đừng dùng một con số partition/broker cố định

Sức chứa broker phụ thuộc CPU, RAM, disk IOPS, network, record size, replication factor, retention, số topic, traffic và cấu hình. Hai cluster cùng số broker nhưng khác workload có thể chịu số partition rất khác nhau.

## 4. Replication factor và tải trên broker

Nếu topic có P partition và replication factor RF, tổng số replica là:

\[
R_{total} = P \times RF
\]

Với 36 partition, replication factor 3, cluster quản lý 108 replica. Nếu có 6 broker và phân phối cân bằng, trung bình mỗi broker giữ khoảng 18 replica của topic đó; thực tế cần xét cả replica của topic khác và phân bố leader.

Replication giúp chịu lỗi broker nhưng tạo thêm disk và network traffic. Leader nhận produce request và phục vụ read theo cấu hình; follower fetch dữ liệu để duy trì replica. Khi tăng RF, không chỉ dung lượng lưu trữ tăng mà traffic replication và công việc I/O cũng tăng.

acks=all kết hợp min.insync.replicas kiểm soát mức xác nhận ghi. Ví dụ RF=3 và min ISR=2 có thể tiếp tục ghi khi còn ít nhất hai replica trong ISR; nếu ISR tụt dưới ngưỡng, broker từ chối ghi để giữ mức durability đã chọn. Đây là trade-off độ bền và khả năng ghi khi lỗi, không nên giảm min ISR chỉ để benchmark có throughput cao hơn.

### Phân bố leader và replica

Kiểm tra phân bố:

~~~bash
bin/kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe --topic orders.events
~~~

Đọc Leader, Replicas và Isr của từng partition. Cần quan sát cả:

- Số leader partition trên từng broker.
- Tổng replica và disk footprint trên từng broker.
- Bytes in/out và request latency theo broker.
- Under-replicated partition và offline partition.
- Broker nào trở thành bottleneck về network hoặc disk.

Partition count hợp lý vẫn có thể tạo mất cân bằng nếu leader hoặc replica assignment bị lệch.

## 5. Consumer group: concurrency tối đa bị giới hạn bởi partition

Với một topic có P partition và một consumer group có C consumer instance, số consumer có thể nhận partition đồng thời tối đa là:

\[
C_{active} = \min(P, C)
\]

Ví dụ topic có 12 partition:

| Consumer trong group | Consumer active tối đa | Nhận xét |
|---:|---:|---|
| 3 | 3 | Mỗi consumer có thể nhận khoảng 4 partition |
| 6 | 6 | Mỗi consumer có thể nhận khoảng 2 partition |
| 12 | 12 | Có thể đạt một consumer cho mỗi partition |
| 16 | 12 | Có ít nhất 4 consumer không được gán partition |

Phân bổ thực tế phụ thuộc assignor, số topic được subscribe và partition assignment. Với nhiều topic, một consumer có thể nhận các partition từ nhiều topic.

Thêm consumer khi đã có nhiều consumer hơn partition không tăng parallelism đọc của group. Nó vẫn tạo thêm process, socket, heartbeat, metrics và chi phí vận hành.

### Một consumer đọc nhiều partition có phải vấn đề?

Không nhất thiết. Consumer được thiết kế để đọc nhiều partition. Số consumer hợp lý phụ thuộc throughput mỗi partition, CPU xử lý record, thời gian gọi dịch vụ ngoài và khả năng batch/fetch. Một consumer xử lý được 4 partition có thể hiệu quả hơn 4 consumer rất nhàn rỗi.

Nếu consumer xử lý mỗi record rất nặng, có thể tăng số consumer đến gần partition count. Nếu xử lý nhẹ và broker/network là bottleneck, thêm consumer có thể không tăng throughput.

## 6. Sizing consumer theo throughput và thời gian xử lý

Giả sử:

- Topic có P partition.
- Mỗi partition nhận trung bình r_p record/s.
- Một consumer xử lý bền vững r_c record/s với logic thực tế.
- Cần headroom H.

Số consumer ước lượng:

\[
C_{needed} =
\left\lceil
\frac{P \times r_p \times H}{r_c}
\right\rceil
\]

Sau đó giới hạn theo partition:

\[
C_{effective} = \min(P,\ C_{needed})
\]

Ví dụ 12 partition, mỗi partition 2.000 record/s, một consumer xử lý được 5.000 record/s và headroom 1.25:

\[
C_{needed} =
\left\lceil
\frac{12 \times 2{,}000 \times 1.25}{5{,}000}
\right\rceil = 6
\]

Sáu consumer có thể đáp ứng tải trung bình theo phép ước lượng. Cần benchmark lại với record size, key skew, database latency, commit và retry thật. Nếu một partition nóng gấp nhiều lần phần còn lại, tổng công suất trung bình không đủ để kết luận.

### Concurrency và xử lý bất đồng bộ

Consumer poll records theo partition assignment. Nếu ứng dụng đẩy record sang thread pool để xử lý song song, cần bảo đảm:

- Không commit offset vượt qua record chưa xử lý xong ở offset thấp hơn.
- Không làm đảo thứ tự cập nhật cùng entity nếu nghiệp vụ yêu cầu ordering.
- Giới hạn queue để tránh tăng heap và consumer lag khi downstream chậm.
- Pause/resume partition khi queue đạt ngưỡng.
- Xử lý shutdown/rebalance để chờ hoặc hủy công việc đang chạy an toàn.

Tăng thread pool không đồng nghĩa tăng số partition mà consumer group có thể đọc.

## 7. Producer client count và số partition

Producer không tham gia consumer group. Vì vậy không có công thức “một producer cho mỗi partition”. Một producer instance có thể gửi đến nhiều partition và nhiều broker.

Điều cần cân bằng là:

- Số producer instance tạo tải đồng thời.
- Số partition mà mỗi producer ghi.
- Số connection/request đến broker.
- Buffer memory và batch accumulator của từng producer.
- Khả năng gom batch theo từng partition.
- CPU dùng để serialize/compress.

Nếu có quá nhiều producer nhỏ, mỗi producer gửi ít record đến mỗi partition, batch có thể không đầy và số request tăng. Một số producer instance có tải đều, tái sử dụng lâu dài thường hiệu quả hơn tạo producer mới cho mỗi request.

### Batch và compression

Ví dụ cấu hình Java producer để tăng batching:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringSerializer;

Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka-1:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    ByteArraySerializer.class.getName());

props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
~~~

Các giá trị 64 KiB, 5 ms và 64 MiB là điểm thử nghiệm, không phải mặc định tối ưu. batch.size là mục tiêu kích thước batch cho mỗi partition; linger.ms cho producer thêm thời gian gom record; compression giảm byte trên network/disk nhưng tiêu thụ CPU.

Đo p50/p95/p99 produce latency và throughput trước/sau thay đổi. Tăng linger có thể tăng throughput nhưng cũng làm tăng latency chờ gửi. Với workload latency rất thấp, cần chọn trade-off khác với workload bulk ingestion.

### Producer concurrency không thay thế partition

Thêm producer có thể tăng khả năng tạo tải nếu client CPU hoặc một producer instance là bottleneck. Nhưng nhiều producer vẫn có thể dồn vào một partition nếu mọi record có cùng key. Khi đó leader của partition đó vẫn là điểm nóng.

Không tạo một producer object cho mỗi record hoặc mỗi HTTP request. Tái sử dụng producer, dùng async send và quản lý lifecycle/close rõ ràng.

## 8. Spring Kafka: cân bằng listener concurrency

Spring Kafka cho phép cấu hình concurrency của listener container:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "orders-reporting",
    concurrency = "6"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Hoặc cấu hình concurrency qua application.yml:

~~~yaml
app:
  kafka:
    listener-concurrency: 6
~~~

concurrency=6 tạo tối đa sáu consumer thread/container child cho listener đó trong cùng group. Nếu topic có 4 partition, tối đa bốn consumer được gán partition; hai consumer còn lại không có partition. Nếu topic có 12 partition, sáu consumer có thể chia nhau các partition.

Một vài điểm cần kiểm tra:

- Concurrency có thể được cấu hình theo listener, không nhất thiết bằng số core CPU.
- Nhiều @KafkaListener cùng group/topic sẽ cùng tham gia assignment theo group semantics.
- Khi số consumer hoặc partition thay đổi, group có thể rebalance.
- Nếu listener gọi database/API chậm, đo thời gian xử lý và pool connection trước khi tăng concurrency.
- Không đặt concurrency cao hơn khả năng connection pool hoặc giới hạn downstream.

Ví dụ nếu listener concurrency là 12 nhưng datasource chỉ cho 5 connection, nhiều thread có thể chờ connection và làm tăng latency thay vì tăng throughput.

## 9. Kafka Streams: partition tạo task, stream thread chạy task

Kafka Streams chia topology thành task dựa trên partition của source/repartition topics. Stream thread thực thi các task được gán. Số thread không tự tạo thêm task vượt quá parallelism mà partition cung cấp.

Ví dụ:

~~~java
import java.util.Properties;

import org.apache.kafka.streams.StreamsConfig;

Properties props = new Properties();
props.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-enricher");
props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka-1:9092");
props.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, 6);
~~~

Nếu subtopology có 4 task mà cấu hình 8 stream threads, một số thread sẽ không có task để chạy. Nếu có 12 task và 3 stream threads, mỗi thread có thể thực thi nhiều task.

Khi cần tăng parallelism:

1. Kiểm tra partition count của source topic.
2. Kiểm tra repartition topics trong topology.
3. Kiểm tra số task theo Topology.describe().
4. Đảm bảo key distribution đủ đều.
5. Tăng stream threads hoặc instance khi còn task cần được phân phối.

Với stateful topology, tăng partition có thể tạo thêm task/state store và làm tăng changelog, restore traffic. Cần đo thời gian restore và dung lượng local state trước khi tăng partition.

## 10. Kafka Connect: tasks.max không phải số task được bảo đảm

Kafka Connect dùng connector để tạo task. tasks.max là giới hạn tối đa mà người vận hành yêu cầu:

~~~json
{
  "name": "orders-sink",
  "config": {
    "connector.class": "com.example.OrdersSinkConnector",
    "topics": "orders.events",
    "tasks.max": "8"
  }
}
~~~

Nếu sink connector đọc topic có 4 partition, thông thường không thể có hơn 4 task đọc độc lập các partition đó trong cùng consumer group. Nếu plugin chỉ chia source thành 2 phần, đặt tasks.max=16 vẫn có thể chỉ tạo 2 task.

Số task thực tế phụ thuộc:

- Khả năng chia nhỏ của connector plugin.
- Số partition/topic hoặc shard nguồn.
- Cấu hình connector.
- Số worker và tài nguyên mỗi worker.
- Giới hạn concurrency của hệ thống đích.

Distributed mode phân phối task trên worker. Thêm worker giúp khi có đủ task chưa được chạy hoặc worker hiện tại thiếu CPU/RAM/network; thêm worker không tự tạo thêm task.

## 11. Broker cũng có giới hạn concurrency

Partition và client chỉ có ích khi broker còn khả năng phục vụ. Broker xử lý request qua network thread, request handler, disk I/O, replication và page cache.

Các tài nguyên cần đo:

- CPU: request handling, compression/decompression, TLS, replication.
- Network: ingress, egress, replication traffic và số connection.
- Disk: throughput, IOPS, fsync/flush, page cache và retention cleanup.
- RAM: page cache, network buffers, request buffers và JVM heap.
- Request queue: thời gian chờ xử lý và mức bão hòa.
- Partition/leader distribution: broker nào giữ nhiều leader hoặc replica hơn.

Tăng client concurrency khi broker đã bão hòa có thể làm queue và latency tăng. Trước khi thêm client, xác định bottleneck nằm ở producer, consumer, broker, network, disk hay downstream.

## 12. Mô hình sizing tổng thể

Một quy trình sizing nên xét đồng thời:

| Bước | Câu hỏi | Đầu ra |
|---|---|---|
| Workload | Peak records/s, bytes/s, record size, retention và latency SLO? | Tải mục tiêu |
| Partition | Một partition chịu được bao nhiêu tải ở SLO? Key có skew không? | Partition count ban đầu |
| Replication | RF, min ISR và broker/rack capacity? | Replica count và durability |
| Producer | Bao nhiêu producer instance, batch, linger, compression? | Producer count/config |
| Consumer | Một consumer xử lý được bao nhiêu tải? Có bao nhiêu partition? | Consumer count/concurrency |
| Processing | Listener/Streams/Connect có bao nhiêu thread/task thực tế? | Mức concurrency |
| Headroom | Khi peak hoặc một instance/broker lỗi, hệ thống còn đạt SLO? | Dự phòng |

Ví dụ topic orders.events:

- Peak 60.000 record/s, record trung bình 1 KiB.
- Benchmark một partition chịu 5.000 record/s ở p99 latency mục tiêu.
- Chọn headroom 1.4.
- Consumer xử lý 8.000 record/s mỗi instance.
- Cần tối thiểu 17 partition để đạt mục tiêu throughput theo benchmark.

Tính sơ bộ:

\[
P = \left\lceil \frac{60{,}000 \times 1.4}{5{,}000} \right\rceil = 17
\]

Với 17 partition, tổng tải mục tiêu có headroom khoảng 84.000 record/s. Consumer ước lượng:

\[
C = \left\lceil \frac{84{,}000}{8{,}000} \right\rceil = 11
\]

Chọn 11 consumer active, nhưng số consumer tối đa có partition là 17. Đây chỉ là phép tính minh họa; benchmark phải chạy với cùng record size, compression, replication, key distribution và logic xử lý thực tế.

Nếu RF=3, topic có 17 partition sẽ có 51 replica. Với 3 broker, trung bình khoảng 17 replica/broker cho topic này, nhưng cần kiểm tra leader balance và tải của các topic khác.

## 13. Benchmark producer và consumer

Benchmark phải tách rõ producer throughput, consumer throughput và end-to-end latency. Không dùng một con số records/s duy nhất để kết luận cluster đủ tải.

### Producer performance test

Ví dụ dùng Kafka CLI:

~~~bash
bin/kafka-producer-perf-test.sh \
  --topic orders.perf \
  --num-records 10000000 \
  --record-size 1024 \
  --throughput -1 \
  --producer-props \
    bootstrap.servers=kafka-1:9092 \
    acks=all \
    compression.type=lz4 \
    batch.size=65536 \
    linger.ms=5
~~~

Lệnh tạo tải với record kích thước 1 KiB. Chạy nhiều lần với các batch size, linger, compression và producer instance khác nhau. Đảm bảo topic có partition count và replication factor giống môi trường dự kiến.

### Consumer performance test

~~~bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server kafka-1:9092 \
  --topic orders.perf \
  --messages 10000000 \
  --group orders-perf-readers
~~~

Kiểm tra option chính xác theo phiên bản Kafka đang cài. Consumer perf test không bao gồm logic nghiệp vụ như gọi database, validate schema hoặc ghi dịch vụ ngoài; cần thêm benchmark ứng dụng thực tế.

Trên Windows, dùng các script .bat tương ứng trong thư mục bin\windows của Kafka distribution.

### Ma trận benchmark

Thay đổi từng biến một:

| Lần chạy | Partitions | Producers | Consumers | Mục tiêu |
|---|---:|---:|---:|---|
| A | 6 | 1 | 3 | Baseline |
| B | 12 | 1 | 6 | Tăng partition/consumer parallelism |
| C | 12 | 2 | 6 | Kiểm tra producer scaling |
| D | 12 | 2 | 12 | Kiểm tra consumer scaling |
| E | 24 | 2 | 12 | Kiểm tra lợi ích partition thêm |
| F | 24 | 4 | 24 | Kiểm tra giới hạn broker/client |

Không thay đồng thời tất cả biến rồi suy ra nguyên nhân. Giữ record size, key distribution, replication factor, acks, compression và phần cứng giống nhau để so sánh có ý nghĩa.

## 14. Metrics cần theo dõi

### Broker

- BytesInPerSec và BytesOutPerSec.
- MessagesInPerSec.
- RequestHandlerAvgIdlePercent.
- NetworkProcessorAvgIdlePercent.
- Request queue time và request local/remote time.
- UnderReplicatedPartitions và OfflinePartitionsCount.
- LeaderCount, PartitionCount và replica distribution.
- Disk utilization, disk latency và network saturation.

### Producer

- record-send-rate.
- record-error-rate.
- request-latency-avg và request-latency-max.
- batch-size-avg.
- record-queue-time-avg.
- buffer-available-bytes.
- compression-rate.

### Consumer

- records-consumed-rate.
- fetch-latency-avg.
- records-lag-max hoặc lag theo partition.
- commit latency/failure.
- time-between-poll và poll idle ratio.
- processing latency và downstream queue depth.

Tên metric JMX cụ thể phụ thuộc client/broker version và metric reporter. Dùng JMX/metrics catalog của phiên bản đang chạy để xác nhận tên và scope; so sánh theo client ID, broker, topic, partition và task thay vì chỉ nhìn cluster average.

### Consumer lag

Consumer lag là khoảng cách giữa log end offset và offset consumer group đã commit/đang xử lý. Lag tăng liên tục có thể do:

- Consumer concurrency thấp.
- Một partition nóng.
- Consumer xử lý chậm hoặc downstream bị nghẽn.
- Rebalance liên tục.
- Fetch/batch config không phù hợp.
- Lỗi retry khiến record bị xử lý lặp.

Kiểm tra:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --describe --group orders-reporting
~~~

Quan sát lag theo từng partition. Một partition có lag cao hơn nhiều partition khác là dấu hiệu key skew hoặc consumer assignment không cân bằng.

## 15. Những thay đổi cần thận trọng

### Tăng partition count

Tăng partition count không tự phân phối lại record cũ. Với keyed record, partitioner hash key theo số partition hiện tại; sau khi tăng partition, record mới của cùng key có thể vào partition khác record cũ. Điều này có thể phá vỡ ordering theo entity khi consumer xử lý hai partition song song.

Nếu ordering theo key là yêu cầu cứng:

- Lập kế hoạch migration sang topic mới với partition count mới.
- Dùng partitioning strategy ổn định có kiểm soát.
- Có cơ chế cutover/dual-read/dual-write phù hợp.
- Kiểm tra downstream state, offset và replay.

Không tăng partition trong production chỉ vì CPU còn rảnh mà chưa đánh giá key mapping và ordering.

### Tăng consumer concurrency

Consumer mới tham gia group sẽ gây rebalance và thay đổi assignment. Trong thời gian rebalance, một phần consumer có thể tạm ngừng nhận partition. Tăng/giảm liên tục theo autoscaling threshold quá nhạy có thể làm hệ thống rebalance thường xuyên.

Đặt cooldown, scale theo lag có thời gian duy trì và quan sát thời gian rebalance. Với workload cần latency ổn định, tránh scale up/down liên tục chỉ theo một mẫu lag ngắn.

### Tăng producer count

Producer mới tăng connection và buffer. Nếu mỗi producer có nhiều partition, memory cho accumulator/buffer có thể tăng đáng kể. Theo dõi buffer available, request rate và batch size; tái sử dụng producer thay vì tạo producer ngắn hạn.

## 16. Quy trình tối ưu theo từng bước

1. Ghi lại SLO: peak throughput, p95/p99 latency, lag tối đa và thời gian phục hồi.
2. Đo baseline trên đúng record size, key distribution, replication và retention.
3. Kiểm tra leader/replica balance và bottleneck broker.
4. Tính partition count sơ bộ từ throughput/partition đã benchmark.
5. Chọn consumer count/concurrency không vượt parallelism partition cần thiết.
6. Chọn producer count vừa đủ, tối ưu batching và compression.
7. Kiểm tra concurrency của Spring Kafka, Kafka Streams và Connect task.
8. Chạy benchmark thay đổi từng biến một.
9. Kiểm tra cả cluster average lẫn từng partition/task/client.
10. Thử peak và một tình huống lỗi broker/consumer để xác nhận headroom.
11. Ghi lại cấu hình, kết quả, trade-off và điều kiện cần benchmark lại.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thêm consumer nhưng throughput không tăng | Consumer nhiều hơn partition hoặc broker đã bão hòa | Kiểm tra assignment và broker metrics |
| Một partition lag cao | Hot key hoặc tải phân bố lệch | Kiểm tra key histogram, salting nếu semantics cho phép |
| Producer tăng nhưng batch size giảm | Nhiều producer nhỏ gửi ít record mỗi partition | Tái sử dụng producer, điều chỉnh batching |
| Tăng partition nhưng ordering sai | Key remap sang partition khác | Migration có kế hoạch và giữ partitioning strategy |
| Kafka Streams có thread nhàn rỗi | Số task nhỏ hơn số stream threads | Kiểm tra task count/topology và partition source |
| Connect tasks không tăng theo tasks.max | Plugin không thể chia source hoặc thiếu partition | Kiểm tra connector task configs và source parallelism |
| Consumer lag tăng sau scale | Rebalance hoặc downstream không đủ capacity | Kiểm tra rebalance time, pool và processing latency |
| Broker network bão hòa | Quá nhiều client/request hoặc replication traffic | Giảm request overhead, cân bằng replica/broker |
| Disk tăng mạnh sau tăng partition/RF | Nhiều replica, segment và state/changelog hơn | Tính lại storage, retention và RF |

## 18. Bài tập tự kiểm tra

1. Vì sao partition là đơn vị song song chính của consumer group?
2. Một topic có 10 partition và group có 14 consumer thì tối đa bao nhiêu consumer được gán partition?
3. Vì sao producer không cần một instance riêng cho mỗi partition?
4. Số partition ảnh hưởng đến replica count và broker storage như thế nào?
5. Vì sao một hot key không được giải quyết chỉ bằng cách tăng partition count?
6. Kafka Streams phân biệt task và stream thread ra sao?
7. Vì sao tasks.max=16 không đảm bảo Connect chạy 16 task?
8. batch.size, linger.ms và compression ảnh hưởng throughput/latency như thế nào?
9. Vì sao tăng partition count có thể làm thay đổi ordering theo key?
10. Cần theo dõi metric nào để biết consumer lag do một partition nóng hay do toàn bộ consumer group thiếu capacity?

## Kết luận

Cân bằng Kafka cần sizing đồng thời partition, replica, producer/consumer client và concurrency bên trong ứng dụng. Partition quyết định mức song song có thể khai thác; consumer group không thể có nhiều consumer active hơn số partition được gán; Kafka Streams và Connect còn bị giới hạn bởi task thực tế mà topology/plugin tạo ra. Producer có thể ghi nhiều partition từ một instance, nhưng quá nhiều producer nhỏ có thể làm giảm batching và tăng connection/buffer overhead.

Hãy dùng throughput/partition đo được, key distribution, latency SLO, replication factor và headroom để chọn cấu hình ban đầu. Sau đó benchmark từng biến, quan sát lag/latency theo partition và kiểm thử tình huống lỗi. Tăng partition, client hoặc thread chỉ tạo lợi ích khi bottleneck tương ứng được xác định và ordering, durability cùng khả năng phục hồi vẫn được bảo toàn.
