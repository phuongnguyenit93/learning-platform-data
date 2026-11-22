# Xử lý NotEnoughReplicas

## 1. NotEnoughReplicas là lỗi gì?

Trong Kafka, producer có thể nhận `NotEnoughReplicasException` khi số replica đang ở trạng thái in-sync (ISR) thấp hơn mức tối thiểu được cấu hình cho topic. Lỗi thường xuất hiện khi producer gửi với `acks=all` và broker không thể đáp ứng chính sách replication của topic.

Đây là cơ chế bảo vệ durability. Kafka từ chối xác nhận một lần ghi nếu số replica đồng bộ không đạt ngưỡng đã đặt. Vì vậy, lỗi này thường cho biết cluster đang thiếu replica khỏe mạnh, replica chưa bắt kịp leader, hoặc cấu hình `min.insync.replicas` cao hơn số replica hiện đang sẵn sàng.

Trong Spring Kafka, lỗi xuất hiện ở phía producer được `KafkaTemplate` sử dụng. Ứng dụng có thể nhìn thấy exception trực tiếp hoặc một exception bao ngoài trong `CompletableFuture`. Việc cần làm là xác định partition nào thiếu ISR, vì sao replica rời ISR, và liệu producer còn retry trong giới hạn delivery timeout hay đã thất bại cuối cùng.

NotEnoughReplicas không nhất thiết có nghĩa toàn bộ Kafka cluster đã ngừng hoạt động. Một cluster vẫn có thể phục vụ đọc hoặc ghi trên các partition khác trong khi một số partition không đủ ISR để nhận ghi.

## 2. Hiểu ISR và min.insync.replicas

Mỗi partition có một leader và các replica được gán. Producer gửi record tới leader. Tập hợp replica đang theo kịp leader đủ điều kiện được gọi là ISR (in-sync replicas).

Ba khái niệm cần phân biệt:

- **Replication factor:** số replica được gán cho mỗi partition, bao gồm leader.
- **ISR:** các replica hiện đang đồng bộ đủ điều kiện tham gia xác nhận ghi.
- **min.insync.replicas:** số replica tối thiểu phải có trong ISR để broker chấp nhận yêu cầu ghi với `acks=all`.

Ví dụ topic có replication factor bằng 3 và `min.insync.replicas=2`:

| Trạng thái partition | Số replica được gán | Số replica trong ISR | Kết quả ghi với `acks=all` |
|---|---:|---:|---|
| Bình thường | 3 | 3 | Được chấp nhận; leader chờ các replica trong ISR xác nhận |
| Một replica bị chậm hoặc offline | 3 | 2 | Vẫn có thể ghi; ISR đáp ứng ngưỡng tối thiểu |
| Hai replica bị chậm hoặc offline | 3 | 1 | Bị từ chối vì ISR thấp hơn 2 |
| Không có leader khả dụng | 3 | 0 hoặc không có leader | Không thể ghi vào partition |

`acks=all` yêu cầu leader chờ xác nhận từ tất cả replica hiện có trong ISR. `min.insync.replicas` đặt giới hạn thấp nhất cho số thành viên ISR được phép có khi nhận ghi. Hai cấu hình phối hợp với nhau: `acks=all` xác định cách producer chờ xác nhận, còn `min.insync.replicas` đặt mức replication tối thiểu mà broker chấp nhận.

### 2.1. Vì sao Kafka từ chối ghi?

Giả sử partition có ba replica: broker 1 là leader, broker 2 và broker 3 là follower. Topic yêu cầu tối thiểu hai replica trong ISR.

Ban đầu:

```text
Assigned replicas: 1, 2, 3
ISR:               1, 2, 3
min.insync.replicas = 2
```

Broker 3 bị lỗi ổ đĩa hoặc mất kết nối replication. Sau khi follower bị loại khỏi ISR:

```text
Assigned replicas: 1, 2, 3
ISR:               1, 2
min.insync.replicas = 2
```

Partition vẫn có thể nhận ghi. Nếu broker 2 cũng bị loại khỏi ISR:

```text
Assigned replicas: 1, 2, 3
ISR:               1
min.insync.replicas = 2
```

Leader hiện chỉ có một replica trong ISR. Với `acks=all`, broker từ chối ghi để không xác nhận record khi mức replication thấp hơn chính sách.

Cách hoạt động này tạo ra một lựa chọn có chủ đích giữa availability và durability. Khi cluster mất quá nhiều replica, Kafka ưu tiên từ chối ghi để bảo vệ mức an toàn dữ liệu đã cấu hình.

## 3. Phân biệt hai loại lỗi trước và sau khi append

Kafka có hai exception thường được nhắc đến trong tình huống thiếu ISR:

| Exception | Thời điểm xảy ra | Ý nghĩa |
|---|---|---|
| `NotEnoughReplicasException` | Trước khi append record vào log của leader cho request đó | ISR đã thấp hơn `min.insync.replicas` khi broker kiểm tra điều kiện ghi |
| `NotEnoughReplicasAfterAppendException` | Sau khi leader đã append record nhưng trước khi hoàn tất acknowledgement | ISR giảm xuống dưới ngưỡng sau khi append; broker không thể xác nhận theo chính sách replication |

Sự khác biệt này quan trọng khi xử lý kết quả gửi.

Với `NotEnoughReplicasException`, broker từ chối request trước khi append do không đủ ISR. Với `NotEnoughReplicasAfterAppendException`, record có thể đã được append ở leader nhưng acknowledgement không được hoàn tất vì số ISR giảm dưới ngưỡng. Ứng dụng không nên suy luận rằng lần gửi sau exception thứ hai chắc chắn chưa ghi gì.

Hai exception thuộc nhóm lỗi có thể retry trong Kafka client. Producer có thể tự thử lại khi ISR phục hồi, trong giới hạn thời gian gửi. Nếu producer cuối cùng báo lỗi cho ứng dụng, trạng thái của một lần ghi có thể cần được xử lý thận trọng, đặc biệt với trường hợp lỗi sau append.

Nếu ứng dụng phát một lời gọi `send()` mới như một lần retry nghiệp vụ, lần gửi mới có thể tạo record khác. Idempotent producer bảo vệ retry nội bộ của cùng batch bằng producer ID và sequence number; nó không tự hợp nhất hai lời gọi gửi mới ở tầng ứng dụng. Với event nghiệp vụ quan trọng, hãy dùng event ID ổn định, transactional outbox hoặc cơ chế deduplication ở consumer.

## 4. Vai trò của acks và cấu hình producer

`NotEnoughReplicasException` thường gắn với producer đặt `acks=all`. Các mức acknowledgement có hành vi khác nhau:

| `acks` | Hành vi | Quan hệ với `min.insync.replicas` |
|---|---|---|
| `0` | Producer không chờ broker xác nhận | Không cung cấp bảo đảm xác nhận replication |
| `1` | Leader xác nhận sau khi append local | Không áp dụng ngưỡng ISR như khi dùng `acks=all` |
| `all` hoặc `-1` | Leader chờ tất cả replica hiện có trong ISR xác nhận | Broker yêu cầu ISR đạt `min.insync.replicas` |

Đổi `acks=all` sang `acks=1` có thể làm lỗi biến mất trong một số tình huống vì broker không còn áp dụng cùng điều kiện minimum ISR cho yêu cầu ghi. Tuy nhiên, đây là thay đổi mức bảo vệ dữ liệu. Nếu leader hỏng trước khi record được replicate, record đã được xác nhận có thể bị mất trong một số kịch bản failover.

Vì vậy, không nên coi `acks=1` là cách sửa lỗi vận hành mặc định. Trước tiên hãy khôi phục replica và đưa ISR trở lại trạng thái đáp ứng chính sách.

### 4.1. Idempotence và retry

Với producer bền vững, cấu hình thường dùng:

- `enable.idempotence=true`
- `acks=all`
- `retries` lớn hơn 0
- `max.in.flight.requests.per.connection` không vượt quá 5

Idempotence giúp broker nhận diện retry của cùng batch và tránh append bản sao do producer retry nội bộ. `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng hoàn tất một lần gửi; `retries` lớn không có nghĩa producer sẽ thử mãi.

Khi ISR phục hồi trong thời hạn gửi, producer có thể retry thành công. Nếu ISR tiếp tục thấp hơn ngưỡng đến hết delivery timeout, future của lần gửi hoàn tất với lỗi. Ứng dụng cần quan sát exception và xử lý theo chính sách nghiệp vụ.

### 4.2. Cấu hình trong Spring Boot

Ví dụ cấu hình producer trong `application.yml`:

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
```

Các giá trị thời gian tính bằng milliseconds. Đây là giá trị minh họa; hãy chọn delivery timeout theo latency SLO và thời gian mà nghiệp vụ có thể chờ.

**Lưu ý:** `min.insync.replicas` là cấu hình ở broker hoặc topic, không phải producer property. Không đặt nó trong `spring.kafka.producer.properties` với kỳ vọng thay đổi ngưỡng ISR của broker. Producer chỉ gửi request; broker mới là nơi kiểm tra số replica đồng bộ.

## 5. Cấu hình min.insync.replicas đúng chỗ

Có thể đặt giá trị mặc định ở broker bằng cấu hình `min.insync.replicas`. Topic có thể ghi đè bằng topic-level config. Cần kiểm tra giá trị hiệu lực của topic đang lỗi thay vì chỉ xem một file cấu hình broker.

Ví dụ tạo topic mới với replication factor 3 và minimum ISR 2:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders.created \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

Để xem leader, replicas và ISR của topic:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.created
```

Để xem cấu hình hiện tại của topic:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --describe
```

Nếu cần thay đổi topic-level config sau khi đã đánh giá rủi ro:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --alter \
  --add-config min.insync.replicas=2
```

Các lệnh trên minh họa CLI Kafka phổ biến; cần dùng script và quyền quản trị phù hợp với cách triển khai Kafka của môi trường. Nếu topic không có override, broker-level default sẽ quyết định giá trị áp dụng.

Không giảm `min.insync.replicas` chỉ để bỏ lỗi khi chưa xác định được tình trạng replica. Việc hạ ngưỡng có thể khiến producer nhận acknowledgement với ít bản sao hơn mức mà thiết kế ban đầu yêu cầu.

## 6. Xử lý lỗi trong Spring Kafka

`KafkaTemplate.send()` trả về kết quả bất đồng bộ. Với Spring Kafka hiện đại, kết quả là `CompletableFuture<SendResult<K, V>>`. Nếu producer không thể hoàn tất gửi sau các lần retry, future sẽ hoàn tất exceptional.

Ví dụ ghi nhận lỗi:

```java
@Service
public class OrderEventPublisher {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate
            .send("orders.created", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                        "Kafka publish failed, eventId={}, orderId={}",
                        event.eventId(),
                        event.orderId(),
                        exception
                    );
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.debug(
                    "Kafka publish acknowledged, topic={}, partition={}, offset={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
```

Các import cần thiết cho ví dụ:

```java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;
```

Không nên chỉ log một thông báo chung như “Kafka send failed”. Hãy giữ exception làm nguyên nhân, đồng thời ghi nhận topic, partition nếu có, event ID và correlation ID. Tránh ghi payload nhạy cảm vào log.

Nếu cần phân loại lỗi, có thể duyệt cause chain để tìm exception Kafka gốc:

```java
static Throwable rootCause(Throwable error) {
    Throwable current = error;

    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }

    return current;
}
```

Sau đó có thể nhận diện `NotEnoughReplicasException` hoặc `NotEnoughReplicasAfterAppendException` tùy exception thực tế được client trả về. Hãy giữ lại exception gốc để phục vụ điều tra và không giả định mọi lỗi send đều là thiếu ISR.

### 6.1. Retry ở Kafka client và retry ở ứng dụng

Có hai lớp retry cần phân biệt:

- **Kafka client retry:** producer tự gửi lại request retriable trong cùng lần gửi, sử dụng cơ chế sequence nếu idempotence bật.
- **Application retry:** ứng dụng gọi `KafkaTemplate.send()` thêm lần nữa sau khi future thất bại hoặc sau timeout.

Kafka client retry là cơ chế đầu tiên nên được cấu hình phù hợp với delivery timeout. Application retry cần có chính sách giới hạn, backoff và nhận diện event nghiệp vụ. Với lỗi `NotEnoughReplicasAfterAppendException`, kết quả append có thể không rõ ràng đối với ứng dụng. Gửi lại như một record mới có thể tạo duplicate nghiệp vụ.

Nếu cần retry ở tầng ứng dụng:

1. Giữ nguyên event ID hoặc business idempotency key.
2. Dùng exponential backoff có jitter để tránh nhiều producer cùng retry dồn dập.
3. Giới hạn số lần và tổng thời gian retry.
4. Đưa event vào outbox hoặc hàng đợi retry bền vững nếu tiến trình không thể giữ request trong bộ nhớ.
5. Thiết kế consumer có thể phát hiện và bỏ qua event đã xử lý.
6. Ghi nhận trạng thái cuối cùng để đội vận hành có thể xử lý event chưa gửi được.

Không retry vô hạn trong callback của future hoặc chặn thread web bằng vòng lặp sleep. Điều đó có thể làm cạn thread và khuếch đại sự cố broker.

## 7. Quy trình chẩn đoán từng bước

Khi nhận cảnh báo hoặc log `NotEnoughReplicas`, cần xác định phạm vi trước khi thay đổi cấu hình.

### Bước 1: Xác định topic và partition bị ảnh hưởng

Từ exception, log producer và metadata của record, xác định topic, partition, thời điểm và producer client. Nếu chưa có partition trong log ứng dụng, lấy thông tin từ broker log và metric producer.

Chạy:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
```

Quan sát các trường:

- `Leader`: broker đang làm leader của partition.
- `Replicas`: danh sách broker được gán làm replica.
- `Isr`: danh sách replica hiện đang in-sync.

So sánh số phần tử trong ISR với `min.insync.replicas` hiệu lực. Nếu ISR nhỏ hơn ngưỡng, đã xác định được điều kiện trực tiếp gây lỗi.

### Bước 2: Kiểm tra cấu hình hiệu lực

Xem topic-level config và broker default. Kiểm tra thêm replication factor của partition. Một topic có RF=2 và min ISR=2 cần cả hai replica trong ISR mới ghi được với `acks=all`; nó không chịu được một replica rời ISR mà vẫn tiếp tục ghi.

Đừng nhầm replication factor với ISR. RF là số replica được gán trong metadata; ISR là tập replica đang đồng bộ tại thời điểm quan sát.

### Bước 3: Xác định replica rời ISR vì lý do gì

Kiểm tra broker log quanh thời điểm lỗi, đặc biệt các sự kiện ISR shrink/expand và replica fetcher. Tìm các nguyên nhân thường gặp:

- Broker dừng, restart liên tục hoặc không thể đăng ký vào cluster.
- Network giữa leader và follower bị mất gói, timeout hoặc phân đoạn.
- Disk đầy, disk latency cao hoặc log directory offline.
- Replica fetcher không theo kịp do throughput cao hoặc broker quá tải.
- CPU, garbage collection hoặc request queue khiến broker phản hồi chậm.
- Partition mất cân bằng, một broker gánh quá nhiều leader hoặc replica.
- Throttling replication hoặc giới hạn băng thông không phù hợp.

Nếu leader offline hoặc partition không có leader, cần xử lý tình trạng leader/partition riêng. NotEnoughReplicas và offline partition có thể xuất hiện cùng lúc nhưng không phải cùng một trạng thái.

### Bước 4: Kiểm tra sức khỏe cluster và metric

Các metric Kafka broker thường hữu ích:

| Metric | Dùng để phát hiện |
|---|---|
| `UnderReplicatedPartitions` | Partition có replica chưa theo kịp leader |
| `OfflinePartitionsCount` | Partition không có leader khả dụng |
| `IsrShrinksPerSec` | Tần suất replica bị loại khỏi ISR |
| `IsrExpandsPerSec` | Tần suất replica quay lại ISR |
| Request handler idle / request queue | Broker có bị quá tải xử lý request không |
| Disk usage và disk latency | Broker có gặp áp lực lưu trữ không |
| Network throughput và errors | Replica replication có bị nghẽn mạng không |

Ở phía producer, theo dõi:

- Record retry rate và error rate.
- Request latency và record queue time.
- Produce throttle time.
- Số lần gửi thất bại theo topic.
- Tỷ lệ publish thành công và p95/p99 latency.

Một retry rate tăng có thể là tín hiệu ISR đang biến động ngay cả khi producer vẫn hoàn tất được một số lần gửi.

### Bước 5: Khôi phục replica và xác nhận ISR

Sau khi tìm được nguyên nhân, phục hồi broker hoặc đường truyền, xử lý disk/log directory, hoặc điều chỉnh năng lực replication. Theo dõi replica bắt kịp leader và quay lại ISR.

Chỉ kết luận sự cố đã được khắc phục khi:

- Số replica trong ISR đạt hoặc vượt `min.insync.replicas` cho partition liên quan.
- Under-replicated partition giảm về mức bình thường theo mục tiêu vận hành.
- ISR không tiếp tục shrink/expand bất thường.
- Producer publish thành công trở lại và retry/error rate ổn định.
- Không còn backlog hoặc event chưa được gửi cần xử lý theo quy trình nghiệp vụ.

## 8. Cách khôi phục theo nguyên nhân

| Nguyên nhân | Hành động phù hợp | Điều cần xác nhận |
|---|---|---|
| Broker follower bị dừng | Khôi phục broker theo runbook, kiểm tra log directory và replica fetcher | Broker đăng ký lại và replica bắt kịp leader |
| Network giữa broker không ổn định | Kiểm tra route, firewall, packet loss, DNS và kết nối giữa broker | Replication fetch ổn định, ISR không tiếp tục shrink |
| Disk đầy hoặc chậm | Giải phóng dung lượng theo retention/runbook, xử lý storage lỗi hoặc mở rộng capacity | Log directory online, disk latency bình thường |
| Replica lag do tải cao | Kiểm tra throughput, throttling, broker capacity và partition skew | Replica catch up mà không tạo nghẽn mới |
| Partition assignment mất cân bằng | Lập kế hoạch reassignment và kiểm soát tốc độ di chuyển replica | Replica mới đã vào ISR trước khi kết thúc thay đổi |
| min.insync.replicas cao hơn khả năng hiện tại | Đánh giá lại RF, min ISR và yêu cầu durability với owner | Thay đổi có phê duyệt và rủi ro được ghi nhận |

Không xóa log directory, di chuyển partition hoặc ép leader election chỉ để làm lỗi biến mất. Những thao tác đó có thể làm mất dữ liệu hoặc khiến partition không khả dụng lâu hơn. Dùng quy trình recovery và reassignment đã được kiểm soát.

### 8.1. Khi nào được cân nhắc hạ min.insync.replicas?

Có thể có tình huống khẩn cấp mà dịch vụ cần khôi phục ghi trước khi tất cả replica phục hồi. Hạ minimum ISR là một quyết định giảm mức bảo vệ dữ liệu, vì broker có thể chấp nhận ghi với ít replica hơn.

Trước khi cân nhắc:

- Xác định topic và partition bị ảnh hưởng.
- Xác định số replica thực sự khỏe mạnh và liệu leader có ổn định.
- Đánh giá loại dữ liệu, khả năng chấp nhận mất dữ liệu và SLA/RPO.
- Có phê duyệt của owner dịch vụ hoặc người chịu trách nhiệm reliability.
- Giới hạn phạm vi thay đổi vào topic cần thiết và đặt thời hạn khôi phục cấu hình.
- Theo dõi chặt chẽ cho tới khi ISR trở lại bình thường, sau đó phục hồi minimum ISR ban đầu.

Không hạ `min.insync.replicas` hàng loạt cho toàn cluster. Không chuyển sang `acks=1` mà không hiểu rõ tác động. Một thay đổi cấu hình có thể làm producer gửi thành công trở lại nhưng đồng thời làm yếu đi chính sách durability vốn ngăn sự cố mất dữ liệu.

## 9. Các tình huống ví dụ

### 9.1. RF=3, min ISR=2, một broker bị lỗi

Topic có ba replica trên ba broker. Broker 3 bị lỗi, ISR còn hai replica. Producer dùng `acks=all` vẫn có thể ghi vì ISR bằng ngưỡng tối thiểu.

Hành động: khôi phục broker 3 để replica quay lại ISR; theo dõi `IsrExpandsPerSec` và `UnderReplicatedPartitions`. Không cần hạ minimum ISR trong tình huống này.

### 9.2. RF=3, min ISR=2, hai broker không đồng bộ

ISR chỉ còn leader. Producer nhận `NotEnoughReplicasException`. Kafka từ chối ghi để giữ chính sách durability.

Hành động: tìm broker follower bị mất kết nối hoặc lag, kiểm tra disk/network và khôi phục ít nhất một follower để ISR đạt hai. Khi ISR trở lại ngưỡng, producer retry có thể thành công trong delivery timeout.

### 9.3. ISR giảm sau khi leader append

Producer gửi record khi ISR đủ điều kiện. Leader append record, nhưng một follower rời ISR trước khi acknowledgement hoàn tất. Broker có thể trả `NotEnoughReplicasAfterAppendException`.

Hành động: để Kafka client retry theo chính sách producer; không lập tức phát một event mới bằng lời gọi `send()` thứ hai nếu chưa xác định trạng thái lần gửi đầu. Với producer idempotent, retry nội bộ của cùng batch được nhận diện bằng sequence. Nếu kết quả cuối cùng thất bại và ứng dụng phải phát lại, dùng event ID ổn định cùng cơ chế deduplication.

### 9.4. min ISR đặt bằng replication factor

Topic RF=3, min ISR=3. Cấu hình này yêu cầu cả ba replica luôn ở ISR để ghi với `acks=all`. Chỉ cần một follower bị loại khỏi ISR, producer đã không thể ghi.

Cấu hình có thể phù hợp với yêu cầu durability nghiêm ngặt trong một topology đủ khỏe, nhưng availability ghi sẽ thấp hơn so với RF=3/min ISR=2. Cần đánh giá capacity, failure domain và khả năng phục hồi trước khi đặt ngưỡng.

### 9.5. Producer gửi thành công nhưng consumer lag tăng

Nếu producer publish được xác nhận, điều đó chỉ cho biết Kafka chấp nhận ghi theo cấu hình hiện tại. Consumer lag tăng là vấn đề ở chặng xử lý sau đó. Không quy mọi vấn đề Kafka thành NotEnoughReplicas.

Hãy kiểm tra consumer group, throughput xử lý, downstream latency, rebalance và lỗi commit offset. SLI publish và SLI processing cần được theo dõi riêng.

## 10. Cảnh báo và runbook vận hành

Nên cảnh báo sớm trước khi producer bắt đầu nhận lỗi. Một bộ cảnh báo phù hợp có thể gồm:

- `UnderReplicatedPartitions > 0` kéo dài trên topic quan trọng.
- `IsrShrinksPerSec` tăng bất thường.
- ISR của partition thấp hơn `min.insync.replicas`.
- `OfflinePartitionsCount > 0`.
- Producer retry rate hoặc error rate tăng cùng lúc.
- Publish success giảm hoặc p99 latency vượt SLO.
- Disk, network hoặc request queue tiến gần ngưỡng capacity.

Cảnh báo theo ISR cần đối chiếu với minimum ISR hiệu lực của topic. Chỉ nhìn UnderReplicatedPartitions không đủ để biết producer có thể tiếp tục ghi hay không: một partition có thể under-replicated nhưng vẫn có ISR đạt minimum, hoặc chỉ còn một replica và đã thấp hơn ngưỡng.

Một runbook ngắn cho on-call nên ghi:

1. Tên cluster, topic, partition và producer service bị ảnh hưởng.
2. Lệnh kiểm tra leader, replicas và ISR.
3. Giá trị `min.insync.replicas` hiệu lực.
4. Broker log và dashboard cần xem.
5. Owner của broker, network, storage và producer.
6. Quy trình phục hồi replica hoặc reassignment.
7. Điều kiện xác nhận incident đã hết.
8. Quy trình phê duyệt nếu cần thay đổi minimum ISR.
9. Cách xác định và xử lý event publish thất bại hoặc chưa rõ kết quả.

## 11. Những sai lầm thường gặp

**Chuyển ngay sang `acks=1`.** Điều này làm giảm điều kiện xác nhận và có thể che giấu tình trạng replica không khỏe. Trước hết hãy tìm và phục hồi replica.

**Giảm `min.insync.replicas` mà không đánh giá rủi ro.** Ngưỡng thấp hơn có thể làm mất dữ liệu đã được xác nhận nếu leader gặp sự cố trước khi bản sao khác nhận record.

**Nhầm replication factor với ISR.** Ba replica được gán không có nghĩa cả ba đang đồng bộ. Kiểm tra danh sách ISR thực tế.

**Nghĩ rằng tăng retries sẽ sửa được broker.** Retry giúp vượt qua gián đoạn tạm thời. Nếu ISR luôn thấp hơn ngưỡng, producer sẽ tiếp tục retry tới delivery timeout rồi thất bại.

**Retry bằng lời gọi send mới khi kết quả cũ chưa rõ.** Lỗi sau append có thể để lại record ở leader. Lần gửi mới ở tầng ứng dụng có thể tạo duplicate nghiệp vụ.

**Đặt min ISR trong producer properties.** Đây là cấu hình broker/topic. Producer không thể tự thay đổi điều kiện replication của cluster.

**Chỉ kiểm tra log ứng dụng.** Nguyên nhân thường nằm ở broker, replica fetcher, disk, network hoặc partition assignment. Cần đối chiếu producer log với broker log và ISR.

**Coi hết lỗi producer là hết incident.** Cần kiểm tra event chưa gửi, backlog, retry nghiệp vụ và consumer để bảo đảm luồng nghiệp vụ đã phục hồi.

## 12. Checklist xử lý sự cố

- [ ] Xác định topic, partition, producer và thời điểm bắt đầu lỗi.
- [ ] Kiểm tra leader, danh sách replicas và ISR.
- [ ] Lấy giá trị `min.insync.replicas` hiệu lực của topic.
- [ ] Xác nhận producer có dùng `acks=all` hay không.
- [ ] Phân biệt `NotEnoughReplicasException` với `NotEnoughReplicasAfterAppendException`.
- [ ] Kiểm tra broker log, replica fetcher, disk, network và request queue.
- [ ] Theo dõi UnderReplicatedPartitions, OfflinePartitionsCount và ISR shrink/expand.
- [ ] Khôi phục replica và xác nhận ISR đạt ngưỡng.
- [ ] Kiểm tra producer retry/error rate và publish SLO sau phục hồi.
- [ ] Xử lý event thất bại hoặc kết quả chưa rõ bằng event ID/outbox/deduplication.
- [ ] Chỉ thay đổi min ISR khi đã đánh giá durability, có phê duyệt và kế hoạch rollback.
- [ ] Ghi nhận nguyên nhân gốc, thời gian ảnh hưởng và hành động phòng ngừa.

## 13. Kết luận vận hành

`NotEnoughReplicas` cho biết Kafka không có đủ replica đồng bộ để đáp ứng chính sách ghi với `acks=all`. Cách xử lý bền vững là tìm partition bị thiếu ISR, xác định nguyên nhân replica rời ISR, khôi phục broker hoặc replication path, rồi xác nhận ISR đã đạt minimum trước khi kết luận producer hoạt động bình thường.

Trong Spring Kafka, hãy cấu hình producer retry và idempotence phù hợp, quan sát exception từ future của `KafkaTemplate`, và tránh phát một lần gửi nghiệp vụ mới khi kết quả của lần trước còn chưa rõ. `min.insync.replicas` cần được quản lý ở broker/topic với quyết định có chủ đích về cân bằng availability và durability.

