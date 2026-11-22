# acks=0, acks=1 và acks=all

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này giải thích ba chế độ xác nhận của producer: **acks=0**, **acks=1** và **acks=all**.

Thuộc tính acks quyết định producer chờ broker xác nhận đến mức nào trước khi coi một lần gửi là hoàn tất. Lựa chọn này ảnh hưởng trực tiếp đến độ trễ, khả năng phát hiện lỗi và độ bền dữ liệu. Để hiểu đúng acks, cần xem đồng thời replication factor, In-Sync Replicas (ISR) và min.insync.replicas.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của acks=0, acks=1 và acks=all.
- Mô tả producer, partition leader và follower tương tác như thế nào khi gửi record.
- Phân biệt replication factor với ISR.
- Giải thích vai trò của min.insync.replicas khi producer dùng acks=all.
- Dự đoán kết quả ghi khi số replica trong ISR thay đổi.
- Nhận biết các lỗi NotEnoughReplicas và NotEnoughReplicasAfterAppend.
- Cấu hình acks trong Java Kafka Producer và Spring Kafka.
- Kết hợp acks=all với idempotent producer để tăng độ tin cậy khi retry.
- Đánh giá trade-off giữa latency, throughput, availability và durability.

## 2. Producer gửi record và broker xác nhận

Producer gửi record đến partition leader. Leader append record vào log của partition, sau đó replica follower fetch dữ liệu từ leader theo cơ chế replication.

Một record được gửi thành công qua producer API không đồng nghĩa consumer đã đọc hoặc xử lý record. Acks chỉ điều khiển mức xác nhận từ phía Kafka broker đối với yêu cầu ghi.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Partition Leader
    participant F1 as Follower 1
    participant F2 as Follower 2

    P->>L: Produce request
    L->>L: Append record
    L->>F1: Replication qua follower fetch
    L->>F2: Replication qua follower fetch
    Note over P,F2: Thời điểm trả ACK phụ thuộc cấu hình acks
    L-->>P: Produce response
~~~

Kafka hỗ trợ ba lựa chọn chính:

| Giá trị | Broker xác nhận | Đặc điểm |
|---|---|---|
| acks=0 | Producer không chờ response từ broker | Độ trễ thấp, không biết chắc broker đã append record hay chưa. |
| acks=1 | Partition leader xác nhận sau khi append vào log cục bộ | Nhanh hơn acks=all, nhưng record có thể mất nếu leader hỏng trước khi replica khác sao chép. |
| acks=all hoặc -1 | Leader chờ các replica hiện thuộc ISR xác nhận ghi | Độ bền cao hơn khi kết hợp replication và min.insync.replicas phù hợp. |

Acks được áp dụng cho yêu cầu ghi của producer. Với producer gửi batch, kết quả xác nhận tương ứng với request/batch đó; các record trong batch không có một mức acks riêng biệt.

## 3. acks=0: không chờ broker xác nhận

Với **acks=0**, producer gửi request và không chờ broker trả Produce response. Client không có xác nhận từ broker rằng record đã được append vào log.

### 3.1. Luồng xử lý

1. Producer tạo record và gửi dữ liệu đến broker.
2. Producer không đợi response xác nhận từ partition leader.
3. Client tiếp tục xử lý các record tiếp theo theo cơ chế gửi của producer.
4. Ứng dụng không thể dựa vào response để biết broker đã lưu record hay từ chối request.

Nếu broker không thể nhận dữ liệu, leader không sẵn sàng hoặc kết nối bị lỗi sau khi dữ liệu rời producer, ứng dụng có thể không xác định được record đã được ghi hay chưa.

### 3.2. Ưu điểm và giới hạn

Ưu điểm:

- Không phải chờ broker gửi response.
- Có thể giảm thời gian chờ ở phía producer trong một số workload.
- Hữu ích với dữ liệu có thể mất và có thể được tạo lại, chẳng hạn một số loại telemetry không quan trọng.

Giới hạn:

- Không nhận được xác nhận rằng record đã được append.
- Khó phát hiện lỗi ghi ở phía broker.
- Không có cơ sở đáng tin cậy để retry một record dựa trên kết quả broker.
- Không phù hợp với dữ liệu nghiệp vụ cần bảo đảm như thanh toán, đơn hàng hoặc số dư.

Cấu hình acks=0 không có nghĩa record chắc chắn bị mất. Nó có nghĩa producer không đợi xác nhận nên không thể biết chắc kết quả ghi. Một số lỗi mạng cục bộ vẫn có thể được client phát hiện, nhưng lỗi broker sau khi request đã được gửi không được phản ánh qua Produce response.

### 3.3. Khi nào cân nhắc acks=0?

Chỉ cân nhắc khi:

- Dữ liệu có giá trị thấp hoặc có thể tái tạo.
- Mất một phần record không làm sai lệch nghiệp vụ.
- Hệ thống ưu tiên giảm độ trễ gửi hơn việc xác nhận từng lần ghi.
- Có một nguồn dữ liệu khác để khôi phục nếu cần.

Không nên chọn acks=0 chỉ để tăng throughput khi chưa đo được bottleneck. Batching, compression, partitioning và cấu hình network cũng ảnh hưởng lớn đến throughput.

## 4. acks=1: leader xác nhận sau khi append

Với **acks=1**, producer chờ partition leader xác nhận sau khi record được append vào log cục bộ của leader.

Follower không bắt buộc phải xác nhận record trước khi leader trả response cho producer. Follower tiếp tục sao chép dữ liệu bất đồng bộ.

### 4.1. Luồng xử lý

1. Producer gửi record đến partition leader.
2. Leader append record vào log cục bộ.
3. Leader trả response thành công cho producer.
4. Follower fetch record từ leader sau đó.
5. Khi follower bắt kịp, tiến độ replication và high watermark có thể tiến lên.

### 4.2. Rủi ro khi leader gặp sự cố

Giả sử topic có replication factor 3:

- Broker 1 là leader.
- Broker 2 và broker 3 là follower.
- Producer gửi record với acks=1.
- Broker 1 append record và trả ACK.
- Trước khi follower sao chép record, broker 1 bị dừng.
- Một follower chưa có record được bầu làm leader mới.

Trong tình huống này, record mà producer đã nhận ACK có thể không còn trong log của leader mới. Vì thế, acks=1 có thể chấp nhận rủi ro mất record đã được xác nhận khi leader gặp sự cố trước khi replication hoàn tất.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Broker 1 (leader)
    participant F as Broker 2 (follower)

    P->>L: Gửi record R
    L->>L: Append R vào log
    L-->>P: ACK thành công (acks=1)
    Note over L,F: Follower chưa fetch R
    L-xF: Broker 1 gặp sự cố
    Note over P,F: Broker 2 có thể được bầu làm leader nhưng chưa có R
~~~

Đây là ví dụ rủi ro, không phải điều chắc chắn xảy ra với mọi lần leader failover. Nếu follower đã sao chép record trước khi leader hỏng, record vẫn có thể tồn tại trên leader mới.

### 4.3. Ưu điểm và giới hạn

Ưu điểm:

- Producer có response xác nhận từ leader.
- Không cần chờ toàn bộ ISR xác nhận.
- Độ trễ thường thấp hơn acks=all khi follower replication chậm.

Giới hạn:

- Chỉ xác nhận append tại leader.
- Không bảo đảm record đã được follower sao chép.
- Có thể mất record đã ACK nếu leader gặp sự cố trước khi replica khác bắt kịp.
- Không phải lựa chọn phù hợp nhất khi yêu cầu durability cao.

Acks=1 có thể phù hợp với dữ liệu có thể chấp nhận một mức rủi ro mất record thấp, trong khi vẫn cần xác nhận broker đã nhận và append dữ liệu.

## 5. acks=all: chờ toàn bộ ISR xác nhận

Với **acks=all** (giá trị tương đương là **acks=-1**), leader chỉ trả response thành công sau khi các replica hiện thuộc In-Sync Replicas (ISR) đã xác nhận ghi record theo giao thức replication của Kafka.

Điểm quan trọng: “all” ở đây là **tất cả replica đang thuộc ISR tại thời điểm ghi**, không nhất thiết là tất cả replica được gán cho partition.

### 5.1. Luồng xử lý

1. Producer gửi record đến leader.
2. Leader append record vào log.
3. Follower trong ISR fetch và append record.
4. Kafka theo dõi tiến độ replica và điều kiện xác nhận.
5. Khi các replica trong ISR đáp ứng yêu cầu, leader trả response thành công cho producer.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Leader
    participant F1 as Follower 1
    participant F2 as Follower 2

    P->>L: Produce request (acks=all)
    L->>L: Append record
    F1->>L: Fetch
    L-->>F1: Record batch
    F1->>F1: Append record
    F2->>L: Fetch
    L-->>F2: Record batch
    F2->>F2: Append record
    Note over L,F2: Các replica trong ISR đã xác nhận
    L-->>P: Produce response thành công
~~~

Acks=all thường có độ trễ cao hơn acks=1 vì producer phải chờ replication. Đổi lại, record được xác nhận có khả năng tồn tại trên nhiều replica đồng bộ hơn, giúp tăng độ bền khi một broker gặp sự cố.

### 5.2. acks=all không có nghĩa mọi replica assignment đều phải xác nhận

Giả sử partition có:

- Replication factor = 3.
- Replica assignment = broker 1, broker 2, broker 3.
- ISR hiện tại = broker 1 và broker 2.
- Broker 3 đang chậm và đã bị loại khỏi ISR.

Với acks=all, producer chờ các replica trong ISR hiện tại, tức broker 1 và broker 2. Broker 3 không nằm trong ISR nên không thuộc tập phải xác nhận cho lần ghi đó.

Điều này cho phép Kafka tiếp tục ghi khi một replica không đồng bộ, nhưng số bản sao đồng bộ đang có đã giảm. Cấu hình min.insync.replicas giúp kiểm soát mức giảm này.

## 6. min.insync.replicas: ngưỡng replica tối thiểu

**min.insync.replicas** (min ISR) là cấu hình broker hoặc topic quy định số replica tối thiểu phải có trong ISR để Kafka chấp nhận ghi với acks=all.

Acks và min ISR giải quyết hai câu hỏi khác nhau:

- **acks**: producer muốn chờ mức xác nhận nào?
- **min.insync.replicas**: với acks=all, Kafka yêu cầu ít nhất bao nhiêu replica đang đồng bộ trước khi chấp nhận ghi?

Nếu ISR có ít replica hơn min ISR, Kafka từ chối yêu cầu ghi với acks=all. Điều này giúp hệ thống dừng ghi khi mức dự phòng không còn đáp ứng chính sách durability.

### 6.1. Ví dụ replication factor 3, min ISR 2

Giả sử:

- Replication factor = 3.
- min.insync.replicas = 2.
- Producer dùng acks=all.

Các trường hợp:

| Trạng thái ISR | Số replica trong ISR | Kết quả ghi |
|---|---:|---|
| Broker 1, 2, 3 đồng bộ | 3 | Chấp nhận, chờ cả 3 replica trong ISR xác nhận. |
| Broker 1, 2 đồng bộ | 2 | Chấp nhận, chờ cả 2 replica trong ISR xác nhận. |
| Chỉ broker 1 đồng bộ | 1 | Từ chối vì thấp hơn min ISR. |
| Không có leader khả dụng | 0 leader | Không thể ghi; producer nhận lỗi hoặc timeout tùy tình huống. |

Min ISR không yêu cầu số replica bằng replication factor. Nó đặt ngưỡng tối thiểu để bảo đảm một lần ghi acks=all không diễn ra khi số replica đồng bộ quá thấp.

### 6.2. Điều gì xảy ra khi ISR thấp hơn min ISR?

Khi ISR giảm xuống dưới ngưỡng:

- Producer dùng acks=all không thể ghi thành công.
- Kafka có thể trả về NotEnoughReplicasException.
- Nếu ISR thay đổi sau khi record đã append nhưng trước khi điều kiện xác nhận hoàn tất, producer có thể nhận NotEnoughReplicasAfterAppendException.
- Producer client có thể retry các lỗi retriable trong giới hạn delivery timeout và cấu hình retry.

Việc ghi bị từ chối là hành vi bảo vệ dữ liệu. Nếu ứng dụng tiếp tục chấp nhận đơn hàng trong khi Kafka không thể ghi event, cần có chiến lược xử lý nghiệp vụ riêng như trả lỗi tạm thời, lưu outbox hoặc retry ở tầng ứng dụng.

### 6.3. Vì sao không nên đặt min ISR bằng 1 một cách tùy tiện?

Nếu replication factor bằng 3 nhưng min ISR bằng 1, producer dùng acks=all vẫn có thể ghi khi chỉ còn leader trong ISR. Lúc đó acks=all chỉ chờ replica duy nhất còn trong ISR xác nhận.

Cấu hình này làm giảm khả năng bảo vệ khi broker gặp sự cố tiếp theo. Với workload cần độ bền cao, mô hình thường gặp là:

- Replication factor = 3.
- min.insync.replicas = 2.
- Producer acks = all.

Mức cấu hình cụ thể vẫn phải dựa trên yêu cầu availability, durability, số broker và failure domain của cluster.

## 7. So sánh ba chế độ acks

| Tiêu chí | acks=0 | acks=1 | acks=all |
|---|---|---|---|
| Chờ response broker | Không | Có, từ leader | Có, sau khi ISR đáp ứng |
| Xác nhận append tại leader | Không có xác nhận | Có | Có |
| Chờ follower trong ISR | Không | Không | Có |
| Phát hiện broker từ chối ghi qua response | Không | Có | Có |
| Rủi ro mất record khi leader hỏng trước replication | Cao | Có | Thấp hơn khi ISR và min ISR được cấu hình phù hợp |
| Độ trễ xác nhận | Thường thấp nhất | Thường thấp | Thường cao hơn |
| Phù hợp dữ liệu nghiệp vụ quan trọng | Không | Tùy mức rủi ro chấp nhận | Thường là lựa chọn khuyến nghị |

Bảng so sánh là định hướng. Độ trễ và throughput thực tế còn phụ thuộc batch size, linger.ms, compression, network, disk, kích thước record, số partition và tình trạng broker.

### 7.1. Chọn acks theo yêu cầu nghiệp vụ

| Loại dữ liệu | Gợi ý ban đầu | Lý do |
|---|---|---|
| Telemetry có thể tái tạo, mất một phần không nghiêm trọng | acks=0 hoặc acks=1 | Có thể ưu tiên chi phí gửi và độ trễ. |
| Log ứng dụng cần broker xác nhận nhưng có thể chấp nhận rủi ro nhất định | acks=1 | Có xác nhận từ leader, không phải chờ ISR. |
| Đơn hàng, thanh toán, tồn kho, sự kiện nghiệp vụ quan trọng | acks=all kết hợp min ISR phù hợp | Tăng khả năng giữ record khi một broker gặp sự cố. |
| Luồng consume-transform-produce cần atomicity trong Kafka | acks=all và transactional producer | Kết hợp xác nhận replication với giao dịch Kafka. |

Không nên áp dụng một cấu hình acks cho mọi topic nếu các luồng có yêu cầu khác nhau. Hãy xác định hậu quả khi mất record, thời gian chấp nhận ghi gián đoạn và khả năng phục hồi của từng nghiệp vụ.

## 8. acks, retry và idempotent producer

Producer có thể gặp lỗi tạm thời như leader election, network timeout hoặc broker quá tải. Thuộc tính retries cho phép client gửi lại request khi lỗi được phân loại là có thể retry.

Tuy nhiên, retry có thể tạo duplicate nếu producer không có cơ chế idempotence.

Ví dụ:

1. Producer gửi record R.
2. Broker append R và trả response.
3. Response bị mất trên mạng.
4. Producer timeout và gửi lại R.
5. Nếu không có idempotence, broker có thể append thêm một bản R nữa.

**Idempotent producer** sử dụng producer ID, epoch và sequence number để broker nhận diện request gửi lại, giúp tránh duplicate do retry trong phạm vi bảo đảm của Kafka producer.

Khi bật idempotence, cấu hình producer cần thỏa mãn các điều kiện tương thích, trong đó có:

- acks=all.
- retries lớn hơn 0.
- max.in.flight.requests.per.connection không vượt quá giới hạn được hỗ trợ (tối đa 5 trong các client hiện đại có idempotence).

Kafka client hiện đại có thể bật idempotence mặc định tùy phiên bản. Hãy kiểm tra cấu hình và phiên bản client thực tế thay vì dựa vào mặc định của môi trường khác.

### 8.1. acks=all không đồng nghĩa exactly-once

Acks=all tăng độ tin cậy của việc ghi record vào Kafka. Nó không tự bảo đảm:

- Consumer chỉ xử lý record đúng một lần.
- Một transaction nhiều partition luôn được commit nguyên tử.
- Database và Kafka cùng commit hoặc rollback.
- HTTP API bên ngoài không bị gọi lặp.

Để xử lý các yêu cầu đó, cần kết hợp idempotent producer, Kafka transaction, consumer isolation phù hợp, idempotent consumer hoặc transactional outbox tùy phạm vi nghiệp vụ.

## 9. Cấu hình producer bằng Java Kafka Client

Ví dụ cấu hình producer ưu tiên độ bền dữ liệu:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class ReliableOrderProducer {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
        properties.put(
            ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
            5
        );
        properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120000);

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {

            ProducerRecord<String, String> record =
                new ProducerRecord<>(
                    "orders",
                    "ORD-1001",
                    "OrderCreated"
                );

            producer.send(record, (metadata, exception) -> {
                if (exception != null) {
                    System.err.println(
                        "Send failed: " + exception.getMessage()
                    );
                    return;
                }

                System.out.printf(
                    "topic=%s partition=%d offset=%d%n",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });

            producer.flush();
        }
    }
}
~~~

Các thuộc tính đáng chú ý:

| Thuộc tính | Giá trị ví dụ | Vai trò |
|---|---|---|
| acks | all | Chờ ISR xác nhận. |
| enable.idempotence | true | Hạn chế duplicate do retry của producer. |
| retries | Integer.MAX_VALUE | Cho phép retry lỗi có thể phục hồi trong giới hạn thời gian gửi. |
| max.in.flight.requests.per.connection | 5 | Giữ mức request đồng thời tương thích với idempotence. |
| delivery.timeout.ms | 120000 | Giới hạn tổng thời gian producer cố gắng giao record. |

Ví dụ trên dùng callback để xử lý kết quả bất đồng bộ và flush trước khi kết thúc. Ứng dụng production cần quản lý callback, shutdown, exception và metric đầy đủ; không nên chỉ in lỗi rồi bỏ qua nếu record là dữ liệu nghiệp vụ bắt buộc.

Nếu ứng dụng cần xác nhận kết quả ngay tại luồng gọi, có thể chờ Future của send, nhưng cần cân nhắc ảnh hưởng đến throughput khi gửi đồng bộ từng record.

## 10. Cấu hình Spring Kafka

Với Spring Boot, có thể cấu hình producer trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
~~~

Spring Kafka sử dụng các thuộc tính này để tạo producer thông qua ProducerFactory và KafkaTemplate.

Ví dụ publisher:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
        KafkaTemplate<String, String> kafkaTemplate
    ) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String event) {
        kafkaTemplate.send(
            "orders",
            orderId,
            event
        ).whenComplete((result, exception) -> {
            if (exception != null) {
                // Ghi log, metric hoặc chuyển sang cơ chế xử lý lỗi phù hợp.
                return;
            }

            var metadata = result.getRecordMetadata();

            System.out.printf(
                "topic=%s partition=%d offset=%d%n",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
    }
}
~~~

Việc cấu hình acks=all ở producer chỉ có ý nghĩa đầy đủ khi topic và broker được cấu hình replication phù hợp. Nếu topic chỉ có một replica hoặc min ISR quá thấp, mức bảo vệ thực tế vẫn thấp.

## 11. Cấu hình topic và kiểm tra min ISR bằng Kafka CLI

Tạo topic có 6 partition và replication factor 3:

Linux hoặc macOS:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --create --topic orders --partitions 6 --replication-factor 3
~~~

Đặt min.insync.replicas bằng 2 cho topic:

Linux hoặc macOS:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config min.insync.replicas=2
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-configs.bat --bootstrap-server localhost:9092 --entity-type topics --entity-name orders --alter --add-config min.insync.replicas=2
~~~

Kiểm tra cấu hình topic:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 --entity-type topics --entity-name orders --describe
~~~

Kiểm tra leader, replicas và ISR:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Trong kết quả describe:

- Replicas cho biết danh sách broker được gán replica.
- Isr cho biết các replica hiện được xem là đồng bộ.
- Leader cho biết broker đang giữ vai trò leader.

Hãy kiểm tra ISR trước khi đánh giá một lần ghi acks=all có thể thành công hay không.

## 12. Thử nghiệm acks bằng console producer

Console producer cho phép truyền thuộc tính producer qua command line. Ví dụ gửi record với acks=all:

Linux hoặc macOS:

~~~bash
bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --producer-property acks=all \
  --producer-property enable.idempotence=true
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-console-producer.bat --bootstrap-server localhost:9092 --topic orders --producer-property acks=all --producer-property enable.idempotence=true
~~~

Nhập một số record và quan sát producer. Console producer là công cụ kiểm tra đơn giản; để đánh giá durability và latency cần có consumer, metric broker và thử nghiệm lỗi trong cluster lab.

Bạn có thể thử các giá trị acks=0 và acks=1 bằng cách thay thuộc tính producer tương ứng. Hãy ghi lại thời gian gửi và các lỗi quan sát được, nhưng không kết luận độ bền chỉ dựa trên tốc độ gửi.

## 13. Thí nghiệm replication và min ISR

Thí nghiệm này cần cluster lab có ít nhất ba broker và topic có replication factor 3. Không thực hiện dừng broker trên môi trường production hoặc cluster dùng chung.

Cấu hình:

- Topic: orders-lab.
- Replication factor: 3.
- min.insync.replicas: 2.
- Producer: acks=all và idempotence bật.

Các bước:

1. Tạo topic với replication factor 3.
2. Đặt min.insync.replicas=2.
3. Kiểm tra replica assignment, leader và ISR.
4. Gửi record khi cả ba replica đang trong ISR; xác nhận producer gửi thành công.
5. Dừng một follower trong môi trường lab, chờ ISR giảm còn 2.
6. Gửi thêm record; producer vẫn có thể thành công vì ISR bằng min ISR.
7. Dừng follower còn lại nhưng giữ leader hoạt động, chờ ISR giảm còn 1.
8. Gửi record với acks=all; producer sẽ nhận lỗi thiếu ISR thay vì ghi thành công theo chính sách min ISR.
9. Khởi động follower, chờ replica bắt kịp và trở lại ISR.
10. Gửi lại record và xác nhận producer hoạt động bình thường.

Kết quả cần ghi:

| Trạng thái | Số replica trong ISR | Kỳ vọng với acks=all, min ISR=2 |
|---|---:|---|
| Cluster bình thường | 3 | Ghi thành công sau khi ISR xác nhận. |
| Một follower dừng | 2 | Ghi vẫn có thể thành công. |
| Hai follower dừng, leader còn hoạt động | 1 | Ghi bị từ chối do thiếu min ISR. |
| Follower phục hồi | 2 hoặc 3 | Ghi thành công khi ISR đạt ngưỡng và leader sẵn sàng. |

Khi thực hành, cần chờ ISR thực sự thay đổi trước mỗi lần gửi. Dừng broker không đồng nghĩa replica bị loại khỏi ISR ngay tức thì; Kafka cần thời gian phát hiện và cập nhật metadata.

## 14. Lỗi thường gặp và cách xử lý

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| NotEnoughReplicasException | Số replica trong ISR thấp hơn min.insync.replicas khi ghi với acks=all. | Kiểm tra ISR, broker availability và min ISR; chờ replica bắt kịp hoặc khôi phục broker. |
| NotEnoughReplicasAfterAppendException | Record đã append nhưng không đủ replica xác nhận theo điều kiện ghi. | Kiểm tra broker/follower vừa rời ISR, replication lag và retry policy. |
| TimeoutException | Broker chậm, network lỗi, leader election hoặc không đủ điều kiện xác nhận trước delivery timeout. | Kiểm tra broker metrics, request latency, ISR và delivery.timeout.ms. |
| Producer gửi được với acks=1 nhưng có thể mất record sau failover | Leader đã ACK trước khi follower sao chép. | Dùng acks=all và min ISR phù hợp nếu yêu cầu durability cao. |
| Producer không biết record có được ghi hay không khi acks=0 | Không có Produce response từ broker. | Chọn acks=1 hoặc acks=all nếu cần xác nhận kết quả. |
| ISR liên tục giảm | Follower không bắt kịp do network, CPU hoặc disk. | Kiểm tra broker logs, fetch lag, disk I/O, network và tài nguyên. |
| Idempotence cấu hình không hợp lệ | acks, retries hoặc max.in.flight không thỏa điều kiện của client. | Dùng acks=all, retries lớn hơn 0 và max.in.flight trong giới hạn hỗ trợ. |

Khi producer nhận lỗi, không nên tự động tăng timeout hoặc retry vô hạn mà không tìm nguyên nhân. Nếu ISR không đủ, retry chỉ thành công khi replica phục hồi hoặc trạng thái cluster thay đổi.

## 15. Các lưu ý về durability

Acks=all kết hợp min ISR phù hợp giúp giảm rủi ro mất dữ liệu khi broker gặp sự cố đơn lẻ. Tuy nhiên, không có cấu hình acks nào bảo vệ khỏi mọi tình huống.

Cần lưu ý:

- **Replication factor:** số replica được phân công cho partition.
- **ISR:** tập replica hiện đang theo kịp leader theo điều kiện Kafka.
- **min.insync.replicas:** ngưỡng tối thiểu để chấp nhận ghi acks=all.
- **Unclean leader election:** nếu bật, Kafka có thể bầu replica ngoài ISR khi không còn replica ISR khả dụng; việc này có thể làm mất dữ liệu đã được xác nhận trước đó.
- **Failure domain:** replica nên được phân bố qua các broker, rack hoặc zone phù hợp để giảm rủi ro sự cố đồng thời.
- **Disk durability:** ACK replication không đồng nghĩa mọi record đã được fsync đồng thời xuống thiết bị lưu trữ vật lý. Kafka dựa vào log, hệ điều hành và replication; cần thiết kế storage và vận hành phù hợp.
- **Consumer processing:** producer nhận ACK không có nghĩa consumer đã xử lý nghiệp vụ thành công.

Một cấu hình thường dùng cho dữ liệu quan trọng là replication factor 3, min.insync.replicas=2, producer acks=all và idempotence bật. Cần kiểm tra thêm chính sách leader election và phân bố replica để hiểu mức bảo vệ thực tế.

## 16. Checklist chọn acks cho production

Trước khi đưa producer vào production, hãy trả lời:

1. Nếu một record bị mất, nghiệp vụ có thể phục hồi từ nguồn khác không?
2. Topic có replication factor phù hợp không?
3. Replica được phân bố qua các broker và failure domain ra sao?
4. min.insync.replicas được đặt ở mức nào?
5. Producer có dùng acks=all cho dữ liệu quan trọng không?
6. Idempotent producer có được bật và cấu hình hợp lệ không?
7. Retry và delivery timeout có phù hợp với SLA không?
8. Ứng dụng xử lý NotEnoughReplicas và timeout thế nào?
9. Có theo dõi ISR, under-replicated partitions, producer error rate và request latency không?
10. Có quy trình khôi phục khi cluster không đủ ISR để ghi không?

Đừng coi việc producer gửi thành công trong một lần thử bình thường là bằng chứng cấu hình đã chịu lỗi đúng. Cần kiểm tra cả tình huống broker hoặc replica mất kết nối trong môi trường lab.

## 17. Bài tập củng cố

1. Tạo topic có replication factor 3.
2. Đặt min.insync.replicas=2.
3. Gửi cùng một tập record với acks=0, acks=1 và acks=all.
4. Ghi lại response, lỗi và thời gian gửi ở từng chế độ.
5. Dừng một follower, xác nhận ISR còn 2 và gửi lại với acks=all.
6. Dừng follower thứ hai nhưng giữ leader hoạt động, xác nhận ghi bị từ chối.
7. Bật idempotence và cấu hình retry, sau đó thử lỗi mạng ngắn trong cluster lab.
8. So sánh kết quả khi idempotence bật và tắt, chú ý khả năng xuất hiện duplicate khi retry.
9. Giải thích vì sao acks=all không tự tạo exactly-once processing cho database hoặc HTTP API.

Câu hỏi tự kiểm tra:

1. acks=0 khác acks=1 ở điểm nào?
2. Vì sao acks=1 có thể mất record đã ACK khi leader gặp sự cố?
3. acks=all chờ những replica nào xác nhận?
4. Replication factor 3 có đồng nghĩa ISR luôn bằng 3 không?
5. min.insync.replicas có tác dụng gì khi ISR giảm?
6. Với RF=3 và min ISR=2, producer acks=all có thể ghi khi ISR còn 2 không?
7. Vì sao acks=all có thể bị từ chối khi ISR chỉ còn 1?
8. NotEnoughReplicasException khác NotEnoughReplicasAfterAppendException ở tình huống nào?
9. Idempotent producer giải quyết vấn đề gì khi retry?
10. Vì sao acks=all không đồng nghĩa mọi broker trong cluster đã fsync record?
11. Vì sao cần kết hợp acks, min ISR và replication factor?
12. Nếu producer nhận ACK, consumer đã xử lý event chưa?

## Kết luận

Acks quyết định mức producer chờ broker xác nhận một lần ghi. Acks=0 không chờ response; acks=1 chờ leader append record; acks=all chờ các replica hiện thuộc ISR xác nhận. Acks càng chặt thường tăng độ trễ xác nhận, nhưng cung cấp thông tin và khả năng bảo vệ dữ liệu tốt hơn khi cluster được cấu hình đúng.

Để dùng acks=all hiệu quả, cần kết hợp replication factor, ISR và min.insync.replicas. Với dữ liệu quan trọng, cấu hình phổ biến là replication factor 3, min ISR 2, acks=all và idempotent producer bật. Khi ISR xuống dưới ngưỡng, Kafka từ chối ghi để tránh chấp nhận dữ liệu trong trạng thái không đủ dự phòng.

Hãy xem acks như một phần của thiết kế độ bền dữ liệu. Nó cần đi cùng retry, idempotence, transaction, consumer processing và quy trình phục hồi để đáp ứng yêu cầu thực tế của hệ thống event streaming.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| acks | Cấu hình mức producer chờ broker xác nhận yêu cầu ghi. |
| acks=0 | Không chờ Produce response từ broker. |
| acks=1 | Chờ partition leader append record và xác nhận. |
| acks=all | Chờ tất cả replica hiện thuộc ISR xác nhận ghi. |
| Replication factor | Số replica được gán cho mỗi partition. |
| ISR | Tập replica đang đồng bộ với leader theo điều kiện Kafka. |
| min.insync.replicas | Số replica tối thiểu trong ISR để chấp nhận ghi acks=all. |
| Idempotent producer | Producer dùng sequence và producer identity để hạn chế duplicate do retry. |
| NotEnoughReplicasException | Lỗi khi không đủ ISR để đáp ứng min ISR trước khi ghi. |
| NotEnoughReplicasAfterAppendException | Lỗi khi điều kiện replica không còn đáp ứng sau khi record đã append. |
| Durability | Khả năng dữ liệu đã xác nhận vẫn tồn tại khi xảy ra sự cố. |

