# Xử lý RecordTooLarge

`RecordTooLarge` xuất hiện khi một record hoặc record batch Kafka vượt quá giới hạn kích thước mà một thành phần trên đường đi chấp nhận. Trong vận hành producer, lỗi thường xuất hiện khi ứng dụng gửi event lớn hơn giới hạn của Kafka producer hoặc broker/topic. Có trường hợp producer gửi thành công nhưng consumer không thể fetch batch vì cấu hình fetch không đủ lớn.

Cách xử lý đúng là xác định thành phần từ chối record, đo kích thước sau serialization và đối chiếu giới hạn trên toàn bộ đường đi: producer, broker/topic, replication và consumer. Tăng một thuộc tính đơn lẻ có thể chỉ chuyển lỗi sang thành phần tiếp theo.

## 1. RecordTooLarge có nghĩa gì?

Kafka truyền dữ liệu theo record batch. Một record có thể chứa key, value, headers và metadata; producer có thể gom nhiều record vào batch và nén batch trước khi gửi. Vì vậy, kích thước JSON hoặc object ban đầu không phải lúc nào cũng bằng kích thước request hoặc batch mà Kafka kiểm tra.

Trong một luồng producer điển hình:

```text
Ứng dụng
  |
  v
Serializer + headers
  |
  v
Kafka producer: max.request.size
  |
  v
Broker / topic: message.max.bytes / max.message.bytes
  |
  v
Replication: replica.fetch.max.bytes
  |
  v
Consumer: max.partition.fetch.bytes / fetch.max.bytes
```

Các giới hạn có vai trò khác nhau:

| Thuộc tính | Thành phần | Vai trò |
|---|---|---|
| `max.request.size` | Kafka producer client | Giới hạn kích thước request producer; đồng thời giới hạn hiệu dụng kích thước record batch chưa nén mà producer có thể gửi |
| `message.max.bytes` | Kafka broker | Giới hạn mặc định kích thước record batch broker chấp nhận |
| `max.message.bytes` | Kafka topic | Giới hạn kích thước record batch cho topic; có thể ghi đè giá trị mặc định broker |
| `replica.fetch.max.bytes` | Broker replication | Giới hạn dữ liệu replica fetch từ mỗi partition trong một lần fetch |
| `max.partition.fetch.bytes` | Kafka consumer client | Giới hạn dữ liệu fetch tối đa từ một partition trong một lần fetch |
| `fetch.max.bytes` | Kafka consumer client | Giới hạn tổng dữ liệu trả về cho một fetch request |

Các thuộc tính fetch có ngoại lệ để bảo đảm tiến trình: Kafka có thể trả về batch đầu tiên của partition không rỗng dù batch đó lớn hơn giới hạn fetch đã cấu hình. Vì vậy, không nên dựa vào ngoại lệ này để thay thế việc cấu hình kích thước fetch phù hợp.

### Những thuộc tính dễ nhầm

- `batch.size` là kích thước mục tiêu của batch producer cho mỗi partition. Nó không phải giới hạn kích thước tối đa của một record.
- `buffer.memory` là dung lượng buffer producer dùng để đệm record đang chờ gửi. Nó không làm một record quá lớn trở nên hợp lệ.
- `compression.type` chọn cách nén batch. Nén có thể giảm dữ liệu truyền qua mạng và kích thước batch sau nén, nhưng không nên xem đây là cách sửa chắc chắn cho record vượt giới hạn producer. `max.request.size` cũng là giới hạn hiệu dụng đối với batch chưa nén.
- Tăng giới hạn consumer không giúp broker chấp nhận một batch bị từ chối ở bước produce.
- Tăng giới hạn broker/topic không giúp producer gửi được record đã vượt `max.request.size`.

## 2. Xác định lỗi xảy ra ở đâu

Trước khi thay đổi cấu hình, hãy xác định chính xác thành phần ném exception và kích thước record thực tế.

### 2.1. Đọc exception gốc

Trong ứng dụng Spring Kafka, lỗi gửi có thể được bọc bởi exception của Spring hoặc các lớp future. Hãy xem toàn bộ cause chain để tìm exception gốc, ví dụ `org.apache.kafka.common.errors.RecordTooLargeException`.

Ghi lại các thông tin vận hành:

- Topic đích và partition nếu đã biết.
- Producer client ID và phiên bản ứng dụng.
- Event type hoặc schema version.
- Kích thước key, value và tổng headers sau serialization.
- Tên cấu hình giới hạn có hiệu lực.
- Thời điểm xảy ra, số lần lỗi và broker liên quan nếu exception cung cấp thông tin đó.

Không ghi toàn bộ payload vào log để chẩn đoán. Payload có thể chứa dữ liệu cá nhân hoặc bí mật, đồng thời log một payload lớn có thể làm tăng tải và chi phí lưu trữ.

### 2.2. Đo dữ liệu sau serialization

Đo kích thước byte sau khi serializer đã chuyển object thành dữ liệu gửi đi. Với JSON, kích thước chuỗi ký tự trước khi encode không nhất thiết bằng số byte UTF-8. Key và headers cũng góp phần vào kích thước record.

Ví dụ, nếu producer dùng `KafkaTemplate<String, byte[]>`:

```java
byte[] payload = objectMapper.writeValueAsBytes(event);

log.info(
    "Preparing Kafka event: topic={}, eventType={}, payloadBytes={}",
    topic,
    event.getClass().getSimpleName(),
    payload.length
);

kafkaTemplate.send(topic, event.id(), payload);
```

Đây là phép đo value. Khi cần xác định chính xác kích thước record, hãy đo cả key, headers và overhead của encoding/batch. Dùng số đo này để so sánh với cấu hình, không coi `payload.length` là kích thước request hoàn chỉnh.

### 2.3. Phân biệt một record quá lớn và batch/request quá lớn

Có hai tình huống cần xem xét:

- **Một record quá lớn:** một event riêng lẻ đã vượt giới hạn producer hoặc giới hạn broker/topic. Giảm `batch.size` thường không giải quyết được vấn đề này.
- **Nhiều record được gom vào batch/request:** từng record có thể hợp lệ nhưng batch hoặc request tổng thể vẫn vượt giới hạn. Khi đó cần xem số partition, tốc độ gửi, batching, compression và `max.request.size`.

Nếu chỉ một loại event gây lỗi, hãy kiểm tra schema, trường dữ liệu bất thường, danh sách phần tử tăng đột biến hoặc nội dung được nhúng trực tiếp vào payload.

### 2.4. Đối chiếu cấu hình thực tế

Kiểm tra cấu hình producer mà ứng dụng đang chạy, cấu hình topic trên cluster và cấu hình broker. Đừng chỉ đọc file YAML hoặc `server.properties`: cấu hình môi trường, biến môi trường, profile Spring và topic override có thể làm giá trị hiệu lực khác với giá trị bạn đang xem.

| Dấu hiệu | Nơi cần kiểm tra đầu tiên |
|---|---|
| Producer báo record vượt giới hạn trước khi gửi được | `max.request.size` và kích thước sau serialization |
| Broker trả lỗi khi nhận batch | `message.max.bytes` và topic `max.message.bytes` |
| Producer gửi được nhưng consumer lỗi khi đọc | `max.partition.fetch.bytes`, `fetch.max.bytes` và giới hạn batch của broker |
| Lỗi xuất hiện sau khi tăng kích thước topic | Replica fetch, consumer fetch và khả năng tương thích của toàn bộ consumer |
| Chỉ một event type bị lỗi | Serializer, headers, schema và kích thước event đó |
| Lỗi chỉ xuất hiện khi tải tăng | Batching, request size, số partition và cấu hình producer |

## 3. Bắt lỗi gửi trong Spring Kafka

Với Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`. Producer gửi bất đồng bộ, vì vậy lời gọi `send()` trả về không đồng nghĩa broker đã xác nhận ghi thành công. Ứng dụng cần quan sát kết quả future.

Ví dụ dưới đây minh họa cách nhận diện lỗi gửi và ghi log metadata có ích:

```java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.common.errors.RecordTooLargeException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, byte[]>> publish(
            String topic,
            String eventId,
            byte[] payload) {

        CompletableFuture<SendResult<String, byte[]>> future =
            kafkaTemplate.send(topic, eventId, payload);

        future.whenComplete((result, error) -> {
            if (error == null) {
                return;
            }

            Throwable cause = rootCause(error);

            if (cause instanceof RecordTooLargeException) {
                // Ghi metadata và chuyển sang luồng xử lý oversize đã thiết kế.
                // Không retry vô hạn cùng một payload.
                System.err.printf(
                    "Kafka record too large: topic=%s, eventId=%s, bytes=%d%n",
                    topic,
                    eventId,
                    payload.length
                );
                return;
            }

            // Xử lý các lỗi gửi khác theo chính sách tương ứng.
            System.err.printf(
                "Kafka send failed: topic=%s, eventId=%s, cause=%s%n",
                topic,
                eventId,
                cause.getClass().getSimpleName()
            );
        });

        return future;
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;

        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }

        return current;
    }
}
```

Đoạn code là ví dụ cho Spring Kafka 3.x và minh họa cách quan sát lỗi. Trong ứng dụng thực tế, hãy dùng logger và một handler có khả năng lưu hoặc chuyển tiếp event theo chính sách nghiệp vụ. Nếu dùng Spring Kafka phiên bản cũ hơn, kiểu future và callback có thể khác; hãy đối chiếu API của phiên bản đang chạy.

Không nên nuốt exception rồi trả về trạng thái thành công cho luồng gọi. Nếu gửi event là điều kiện để hoàn tất nghiệp vụ, hãy truyền kết quả thất bại về caller hoặc lưu event vào một cơ chế bền vững để xử lý sau. Nếu producer chỉ gửi event phụ trợ, hãy xác định rõ mức độ mất event có thể chấp nhận.

## 4. Chọn cách khắc phục

Có hai hướng chính: giảm kích thước event hoặc tăng giới hạn có kiểm soát trên tất cả thành phần cần thiết. Ưu tiên xem lại thiết kế payload trước khi nâng giới hạn toàn cluster.

### 4.1. Giảm kích thước payload

Kiểm tra xem event có đang mang dữ liệu mà consumer không thực sự cần hay không:

- Chỉ gửi các trường cần thiết cho consumer.
- Tránh nhúng ảnh, PDF, file đính kèm hoặc nội dung nhị phân lớn vào message.
- Tránh lặp lại dữ liệu đã có thể tra cứu bằng ID.
- Giới hạn số phần tử trong collection và độ dài trường text.
- Xem lại headers để tránh đưa metadata lớn hoặc trùng lặp vào mỗi record.
- Dùng schema gọn và định dạng serialization phù hợp.

Với nội dung lớn, thường nên lưu nội dung vào object storage hoặc hệ thống file chuyên dụng, sau đó gửi một event nhỏ chứa tham chiếu:

```json
{
  "eventId": "evt-12345",
  "eventType": "document.created",
  "documentId": "doc-987",
  "objectKey": "documents/2026/11/doc-987",
  "contentType": "application/pdf",
  "contentLength": 18432000,
  "checksum": "sha256:..."
}
```

Consumer dùng `objectKey` để lấy nội dung và kiểm tra checksum. Thiết kế này cần xử lý quyền truy cập, thời hạn lưu object, vòng đời xóa, khả năng object chưa sẵn sàng khi event đến và xử lý lại event. Không đưa URL có credential hoặc token truy cập dài hạn vào Kafka message.

### 4.2. Dùng compression đúng mục đích

Producer hỗ trợ các kiểu nén như gzip, snappy, lz4 và zstd tùy phiên bản Kafka client và broker. Ví dụ cấu hình:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": zstd
```

Nén phù hợp với payload có tính lặp hoặc văn bản lớn. Dữ liệu đã nén hoặc dữ liệu có entropy cao có thể giảm rất ít. Compression cũng tiêu tốn CPU và có thể thay đổi latency.

Hãy đo kích thước trước và sau nén bằng workload thực tế. Nếu một record đơn lẻ đã vượt giới hạn chưa nén của producer, chỉ bật compression có thể vẫn không giải quyết được lỗi `max.request.size`.

### 4.3. Tăng giới hạn producer khi kích thước lớn là hợp lệ

Nếu event lớn là yêu cầu nghiệp vụ có chủ đích, cấu hình `max.request.size` ở producer. Ví dụ dưới đây dùng giới hạn 5 MiB:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[max.request.size]": 5242880
```

Giá trị trong ví dụ là 5 × 1024 × 1024 byte. Hãy chọn giá trị dựa trên kích thước lớn nhất đã đo, có tính đến key, headers và overhead. Đặt giới hạn nghiệp vụ của event thấp hơn giới hạn kỹ thuật để có khoảng dự phòng.

Spring Boot bind các thuộc tính Kafka client qua map `spring.kafka.producer.properties`. Dấu ngoặc vuông giúp giữ nguyên tên property có dấu chấm trong YAML.

### 4.4. Đồng bộ giới hạn broker và topic

Broker dùng `message.max.bytes` làm giới hạn mặc định cho record batch. Topic có thể đặt `max.message.bytes` để ghi đè giới hạn đó.

Ví dụ trong cấu hình broker:

```properties
message.max.bytes=5242880
replica.fetch.max.bytes=6291456
```

Ví dụ thay đổi giới hạn cho một topic bằng Kafka CLI:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --alter \
  --add-config max.message.bytes=5242880
```

Sau khi thay đổi, kiểm tra cấu hình topic hiệu lực:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --describe
```

Cú pháp CLI và cách áp dụng broker configuration có thể thay đổi theo phiên bản Kafka và cách cluster được quản lý. Với cluster do nhà cung cấp quản lý, thực hiện thay đổi qua cơ chế cấu hình được nền tảng hỗ trợ.

`replica.fetch.max.bytes` cần được xem xét cùng với giới hạn batch để follower broker có thể fetch và replicate batch lớn. Kafka có cơ chế trả về batch đầu tiên lớn hơn giới hạn fetch để bảo đảm tiến trình, nhưng cấu hình replication fetch đủ lớn vẫn giúp hành vi rõ ràng và ổn định hơn.

### 4.5. Đồng bộ giới hạn consumer

Consumer phải có khả năng fetch batch mà topic cho phép. Trong Spring Boot có thể cấu hình:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[max.partition.fetch.bytes]": 6291456
        "[fetch.max.bytes]": 16777216
```

Ví dụ đặt giới hạn mỗi partition là 6 MiB và tổng fetch response là 16 MiB. Điều chỉnh theo số partition có thể được fetch đồng thời, kích thước batch, số consumer và ngân sách bộ nhớ của ứng dụng.

Không phải mọi consumer đều là Spring application. Hãy kiểm tra các consumer viết bằng Kafka client thuần, Kafka Connect, Kafka Streams và consumer service do nhóm khác quản lý trước khi tăng giới hạn topic. Một producer thành công không có nghĩa toàn bộ consumer đã sẵn sàng nhận batch lớn.

### 4.6. Ví dụ bộ cấu hình đồng bộ

Giả sử event lớn nhất được phép ở tầng nghiệp vụ là khoảng 4 MiB. Một bộ giá trị minh họa có thể là:

| Thành phần | Giá trị minh họa | Mục đích |
|---|---:|---|
| Giới hạn nghiệp vụ của event | 4 MiB | Chặn payload bất thường từ sớm |
| Producer `max.request.size` | 5 MiB | Cho khoảng dự phòng cho batch/request |
| Broker `message.max.bytes` | 5 MiB | Chấp nhận batch theo giới hạn cluster |
| Topic `max.message.bytes` | 5 MiB | Giới hạn cụ thể cho topic |
| Broker `replica.fetch.max.bytes` | 6 MiB | Cho replica fetch batch lớn |
| Consumer `max.partition.fetch.bytes` | 6 MiB | Fetch batch từ một partition |
| Consumer `fetch.max.bytes` | 16 MiB | Giới hạn tổng fetch response |

Đây chỉ là bộ số minh họa, không phải cấu hình mặc định cho mọi cluster. Giá trị cần được kiểm chứng với phiên bản Kafka, compression, kích thước batch thực tế, số partition, số consumer và giới hạn tài nguyên. Không sao chép bộ số này nếu workload có yêu cầu khác.

## 5. Không retry vô hạn lỗi RecordTooLarge

`RecordTooLarge` thường là lỗi cấu hình hoặc dữ liệu không đáp ứng giới hạn, không phải lỗi tạm thời như broker mất kết nối. Gửi lại cùng một record với cùng payload và cùng cấu hình sẽ thường thất bại tiếp.

Chính sách xử lý nên phân loại:

| Loại lỗi | Hướng xử lý |
|---|---|
| Record hợp lệ nhưng giới hạn producer cấu hình thấp | Điều chỉnh producer sau khi xác minh giới hạn toàn tuyến |
| Record hợp lệ nhưng broker/topic từ chối | Điều chỉnh giới hạn broker/topic và các consumer liên quan |
| Payload vượt giới hạn nghiệp vụ | Từ chối event, sửa dữ liệu nguồn hoặc chuyển nội dung lớn sang object storage |
| Serializer tạo payload lớn bất thường | Sửa schema, serializer hoặc dữ liệu đầu vào |
| Lỗi mạng hoặc broker tạm thời | Retry có backoff và giới hạn theo chính sách gửi |

Đối với producer, dead-letter topic không tự động giải quyết được record quá lớn. Nếu bản thân payload không thể được ghi vào Kafka, gửi nguyên payload đó sang DLT có thể gặp đúng lỗi cũ. Có thể lưu payload vào kho bền vững rồi gửi một thông điệp quarantine nhỏ gồm event ID, object key, checksum, topic đích và nguyên nhân lỗi. Quy trình này cần quyền truy cập và thời hạn lưu rõ ràng.

Nếu event được ghi từ transaction nghiệp vụ, hãy bảo đảm lỗi gửi không làm mất dấu event. Outbox pattern có thể giữ event trong database cùng transaction nghiệp vụ, sau đó một publisher xử lý gửi và lưu trạng thái. Với outbox, record quá lớn vẫn phải được phân loại và xử lý; outbox chỉ giúp giữ lại công việc để không mất event.

## 6. Tác động vận hành khi tăng giới hạn

Tăng giới hạn kích thước có thể làm tăng tài nguyên cần thiết trên toàn hệ thống:

- **Heap và bộ nhớ:** producer, broker và consumer có thể cần giữ batch lớn hơn trong bộ nhớ. Nhiều partition hoặc nhiều request đồng thời làm mức sử dụng tăng nhanh.
- **Network:** request và response lớn hơn làm tăng băng thông, thời gian truyền và độ nhạy với sự cố mạng.
- **Replication:** follower phải fetch và ghi batch lớn; độ trễ replication có thể tăng.
- **Consumer latency:** deserialize và xử lý payload lớn tốn CPU, bộ nhớ và thời gian. Cần xem xét `max.poll.interval.ms` nếu xử lý lâu.
- **Retry và replay:** message lớn được gửi lại nhiều lần làm tăng tải mạng và dung lượng lưu trữ.
- **Observability:** log payload lớn có thể làm tăng chi phí; nên ghi kích thước, event type và event ID thay vì nội dung đầy đủ.

Giới hạn lớn hơn cũng làm tăng tác động của một producer gửi payload bất thường. Nên có giới hạn ở tầng API hoặc domain, metric phân bố kích thước event và cảnh báo khi payload tiến gần ngưỡng.

## 7. Quy trình triển khai thay đổi an toàn

Khi cần tăng giới hạn, thực hiện theo trình tự:

1. Thu thập exception gốc, kích thước sau serialization, topic, producer client ID và cấu hình hiện hành.
2. Xác nhận event lớn là hợp lệ và có consumer thực sự cần toàn bộ payload.
3. Kiểm tra giới hạn producer, broker, topic, replication và tất cả consumer đang đọc topic.
4. Chọn một giới hạn nghiệp vụ tối đa; đặt các giới hạn kỹ thuật có khoảng dự phòng phù hợp.
5. Thử trên môi trường staging với payload gần ngưỡng, payload vượt ngưỡng và tải đồng thời.
6. Xác nhận producer nhận acknowledgement, consumer fetch và deserialize thành công, replication ổn định.
7. Theo dõi send error rate, record size, request latency, consumer lag, broker request metrics, heap và replication lag sau triển khai.
8. Ghi lại cấu hình mới, phạm vi topic/broker, người sở hữu và quy trình rollback.

Khi thay đổi giới hạn topic, kiểm tra các consumer cũ và connector liên quan. Nếu không thể nâng cấp hoặc cấu hình tất cả consumer, hãy giữ payload dưới giới hạn chung thấp nhất hoặc chuyển nội dung lớn ra khỏi Kafka.

## 8. Checklist chẩn đoán nhanh

- [ ] Đã xác định exception gốc và thành phần phát sinh lỗi.
- [ ] Đã đo byte sau serializer; đã tính đến key và headers.
- [ ] Đã phân biệt record đơn lẻ quá lớn với batch/request quá lớn.
- [ ] Đã kiểm tra `max.request.size` của producer đang chạy.
- [ ] Đã kiểm tra `message.max.bytes` ở broker và `max.message.bytes` ở topic.
- [ ] Đã kiểm tra `replica.fetch.max.bytes` nếu tăng giới hạn batch.
- [ ] Đã kiểm tra `max.partition.fetch.bytes` và `fetch.max.bytes` của consumer.
- [ ] Đã xác minh mọi consumer, connector và ứng dụng downstream có thể đọc batch mới.
- [ ] Đã kiểm thử payload gần ngưỡng, payload vượt ngưỡng và tải đồng thời.
- [ ] Đã có chính sách cho event vượt giới hạn, không retry vô hạn.
- [ ] Đã thiết lập metric và cảnh báo về kích thước event cùng tỷ lệ gửi lỗi.

## 9. Nguyên tắc vận hành

Hãy xem `RecordTooLarge` là tín hiệu cần kiểm tra cả hợp đồng dữ liệu và giới hạn kỹ thuật. Nếu event đang mang nội dung lớn mà consumer chỉ cần định danh hoặc metadata, hãy chuyển nội dung sang object storage và gửi tham chiếu qua Kafka. Nếu kích thước lớn là yêu cầu nghiệp vụ thực sự, tăng giới hạn có kiểm soát và đồng bộ producer, broker, topic, replication cùng consumer.

Trong mọi trường hợp, đặt giới hạn kích thước ở tầng nghiệp vụ, theo dõi kích thước event sau serialization và kiểm thử đường đi từ producer đến consumer. Điều này giúp lỗi được phát hiện sớm, tránh retry vô ích và ngăn một thay đổi cấu hình tạo ra sự cố ở thành phần downstream.

