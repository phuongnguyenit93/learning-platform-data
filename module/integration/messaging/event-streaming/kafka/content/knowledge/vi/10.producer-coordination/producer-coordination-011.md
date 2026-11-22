# Xử lý kết quả gửi không xác định khi mất kết nối hoặc hết hạn

## Mục tiêu bài học

Một producer có thể gửi record đến Kafka, broker đã append record vào partition nhưng acknowledgement bị mất trên đường về. Ứng dụng khi đó nhận timeout hoặc lỗi kết nối mà không biết record đã được ghi hay chưa. Nếu gửi lại một record mới một cách mù quáng, hệ thống có thể tạo sự kiện trùng; nếu coi lần gửi đó chắc chắn thất bại và bỏ qua, hệ thống có thể làm mất sự kiện.

Tình huống này được gọi là *ambiguous send outcome* — kết quả gửi không xác định. Bài học giúp phân biệt lỗi chắc chắn chưa gửi, lỗi broker từ chối và lỗi không thể xác định record đã được append hay chưa. Người học sẽ tìm hiểu các timeout của producer, retry nội bộ, idempotent producer, event ID, consumer deduplication và transactional outbox để thiết kế luồng gửi có thể phục hồi.

Sau bài học, người học có thể:

- Giải thích vì sao mất acknowledgement không chứng minh record chưa được ghi.
- Phân biệt max.block.ms, request.timeout.ms, delivery.timeout.ms và timeout do ứng dụng tự chờ Future.
- Phân loại kết quả gửi thành xác nhận thành công, từ chối chắc chắn hoặc chưa xác định.
- Hiểu phạm vi bảo vệ của producer retry và idempotence.
- Thiết kế event ID ổn định, consumer inbox/deduplication và transactional outbox.
- Xử lý kết quả gửi bất đồng bộ bằng KafkaProducer và Spring Kafka.
- Chọn chiến lược retry mà không tạo tác động nghiệp vụ lặp hoặc phá vỡ ordering.

## 1. Vì sao kết quả gửi có thể không xác định?

Producer gửi record qua mạng. Broker có thể nhận request, append record vào log, sau đó gửi acknowledgement về producer. Nếu kết nối bị ngắt sau khi broker append nhưng trước khi producer nhận được acknowledgement, hai phía có thông tin khác nhau:

- Broker đã ghi record.
- Producer chỉ thấy request không có phản hồi hoặc kết nối bị đóng.

Producer không thể suy ra chắc chắn record đã được ghi chỉ từ việc socket bị timeout.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant P as Kafka Producer
    participant B as Broker
    App->>P: send(record)
    P->>B: Produce request
    B->>B: Append record vào partition
    B--xP: Produce response bị mất
    P-->>App: Timeout / network exception
    Note over B,P: Broker có record, producer chưa biết kết quả
    App->>P: Gửi lại nếu ứng dụng quyết định retry
    P->>B: Produce request mới
    B->>B: Có thể append thêm một bản ghi
~~~

Đây là lý do một lần gửi có thể kết thúc bằng exception nhưng record vẫn tồn tại trong Kafka. Exception chỉ cho biết producer không nhận được kết quả thành công theo thời hạn hoặc giao thức; nó không phải lúc nào cũng chứng minh broker chưa append.

### 1.1. Ba trạng thái kết quả nên phân biệt

Ở tầng ứng dụng, nên biểu diễn kết quả theo ba trạng thái:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| ACKNOWLEDGED | Producer nhận acknowledgement và có metadata | Ghi nhận topic, partition, offset; hoàn tất trạng thái gửi |
| REJECTED | Có bằng chứng request bị từ chối hoặc lỗi xảy ra trước khi record được chấp nhận gửi | Sửa dữ liệu/quyền/cấu hình hoặc chuyển sang xử lý lỗi |
| UNKNOWN | Không đủ bằng chứng để kết luận record đã được append hay chưa | Giữ event ID, đối soát hoặc retry theo cơ chế idempotent |

Không nên gom mọi exception thành REJECTED. Timeout sau khi request đã rời producer, mất kết nối khi chờ response hoặc một số lỗi xảy ra sau append có thể dẫn đến UNKNOWN.

Ngược lại, không phải mọi lỗi đều mơ hồ. Ví dụ lỗi serialization trước khi gửi, topic không hợp lệ hoặc broker trả lỗi authorization là các dấu hiệu từ chối rõ ràng. Cần phân loại theo exception thực tế, nguyên nhân gốc và giai đoạn phát sinh.

### 1.2. Kafka không có API hỏi lại trạng thái một request theo event ID

Kafka không cung cấp một API tổng quát để producer hỏi broker: “Request gửi event ID X vừa rồi đã được append hay chưa?”. Offset chỉ được trả về khi producer nhận được metadata thành công. Nếu response bị mất, ứng dụng có thể không biết offset của bản ghi.

Vì vậy, muốn xử lý kết quả không xác định, ứng dụng cần mang theo một định danh ổn định của sự kiện và thiết kế nơi nhận có thể nhận diện bản ghi lặp. Có thể dùng consumer inbox, unique constraint trong database hoặc một luồng đối soát riêng.

## 2. Phân biệt các loại timeout của producer

Các timeout Kafka có phạm vi khác nhau. Dùng nhầm chúng dễ dẫn đến retry sai.

| Cấu hình/timeout | Phạm vi | Điều nó không có nghĩa |
|---|---|---|
| max.block.ms | Thời gian send() có thể chờ metadata hoặc chờ buffer cấp chỗ trước khi đưa record vào quá trình gửi | Không phải thời gian chờ broker acknowledgement cho toàn bộ lần gửi |
| request.timeout.ms | Thời gian client chờ response cho một request gửi đến broker | Không phải tổng thời gian tối đa của mọi lần retry |
| delivery.timeout.ms | Tổng thời gian tối đa producer cố gắng giao record, bao gồm batching, request và retry | Hết hạn không chứng minh broker chưa append record |
| Future.get(timeout) | Thời gian thread ứng dụng chờ kết quả Future | Timeout của get() không tự hủy request gửi trong producer |

### 2.1. max.block.ms

Khi gọi producer.send(record), producer có thể cần lấy metadata để biết partition leader hoặc chờ buffer có đủ chỗ. max.block.ms giới hạn thời gian chờ đồng bộ ở giai đoạn này.

Nếu send() ném timeout vì không lấy được metadata hoặc không cấp được buffer trong giới hạn, record có thể chưa được đưa vào hàng đợi gửi của producer. Đây là tình huống khác với việc request đã được gửi đi nhưng response bị mất.

### 2.2. request.timeout.ms

Đây là giới hạn chờ response cho một request đến broker. Nếu hết hạn, producer có thể retry khi lỗi thuộc loại có thể retry và còn thời gian delivery. Một request timeout không nhất thiết kết thúc toàn bộ lần gửi.

### 2.3. delivery.timeout.ms

Đây là giới hạn tổng thời gian producer cố gắng giao một record. Khi thời gian này hết, callback/Future có thể hoàn tất bằng exception. Nếu một request trước đó đã được broker append nhưng response bị mất, ứng dụng vẫn không có metadata để biết vị trí record.

### 2.4. Timeout do ứng dụng tự chờ Future

Ví dụ:

~~~java
RecordMetadata metadata = producer.send(record).get(2, TimeUnit.SECONDS);
~~~

Nếu get() ném TimeoutException, điều đó chỉ có nghĩa thread hiện tại đã chờ hai giây mà chưa nhận kết quả. Producer có thể vẫn đang retry và Future vẫn có thể hoàn tất sau đó. Timeout của get() không hủy record khỏi producer buffer và không chứng minh việc gửi thất bại.

Không nên bắt timeout này rồi lập tức gửi một ProducerRecord mới mà không dùng event ID ổn định và cơ chế deduplication.

## 3. Producer retry và idempotence bảo vệ điều gì?

Kafka producer có thể tự retry một số lỗi tạm thời như lỗi network hoặc leader thay đổi. Retry nội bộ là một phần của giao thức gửi; ứng dụng không cần tự gửi một record mới cho mỗi lần retry.

### 3.1. Bật idempotent producer

Ví dụ cấu hình:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());

props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120000);
props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30000);
~~~

Idempotent producer sử dụng producer ID và sequence number để broker nhận diện retry của cùng một batch trong producer session. Khi retry theo giao thức, broker có thể tránh append trùng do acknowledgement bị mất.

Với Kafka client hiện đại, idempotence thường được bật mặc định trong các cấu hình tương thích; khai báo rõ trong ví dụ giúp người học hiểu yêu cầu. Khi bật, producer cần các cấu hình tương thích như acks=all, retry và giới hạn max.in.flight.requests.per.connection phù hợp. Hãy kiểm tra tài liệu của phiên bản client đang dùng.

### 3.2. Idempotence không giải quyết mọi lần gửi lại ở tầng ứng dụng

Idempotence bảo vệ retry của cùng producer session theo giao thức Kafka. Nó không tự nhận diện hai lần gọi send() độc lập là cùng một sự kiện nghiệp vụ.

Ví dụ:

1. Ứng dụng gửi OrderPaid với event ID evt-100.
2. Broker append record nhưng acknowledgement bị mất.
3. Producer kết thúc lần gửi với timeout.
4. Ứng dụng khởi động lại hoặc tạo producer mới rồi gửi lại OrderPaid như một request mới.

Lần gửi mới có thể được xem là record mới và được append lần nữa. Kafka producer idempotence không thay thế event ID và deduplication ở tầng nghiệp vụ.

### 3.3. Vai trò của acks và ISR

acks quyết định mức xác nhận producer yêu cầu:

| acks | Ý nghĩa | Ghi chú |
|---|---|---|
| 0 | Không chờ broker acknowledgement | Không có xác nhận offset từ broker |
| 1 | Chờ leader xác nhận append local | Có thể mất dữ liệu nếu leader lỗi trước khi replica khác sao chép |
| all | Chờ điều kiện acknowledgement từ ISR | Kết hợp với min.insync.replicas để xác định mức replication tối thiểu |

acks=all tăng độ bền xác nhận nhưng không loại bỏ hoàn toàn trạng thái UNKNOWN. Nếu broker đã append mà response bị mất, producer vẫn không biết kết quả. Cấu hình này giảm rủi ro mất dữ liệu khi broker xác nhận, còn event ID và deduplication xử lý retry nghiệp vụ.

## 4. Thiết kế event ID ổn định

Mỗi sự kiện nghiệp vụ nên có một định danh ổn định được tạo trước lần gửi đầu tiên. Khi retry, ứng dụng phải giữ nguyên ID đó.

Ví dụ payload:

~~~json
{
  "eventId": "evt-2026-000042",
  "eventType": "OrderPaid",
  "aggregateId": "order-42",
  "sequence": 7,
  "occurredAt": "2026-11-20T10:15:30Z",
  "data": {
    "orderId": "order-42",
    "amount": 125000
  }
}
~~~

Có thể đặt event ID trong payload, header hoặc cả hai. Header giúp middleware và tracing đọc ID mà không cần deserialize payload; payload giúp consumer và hệ thống lưu trữ nghiệp vụ vẫn giữ được ID sau khi chuyển đổi định dạng.

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>("orders", orderId, payload);

record.headers().add(
    "event-id",
    eventId.getBytes(StandardCharsets.UTF_8)
);
~~~

Quy tắc quan trọng:

- Tạo event ID một lần ở ranh giới nghiệp vụ.
- Lưu event ID cùng dữ liệu cần retry.
- Không tạo ID mới mỗi lần retry.
- Dùng ID làm khóa duy nhất trong nơi consumer ghi nhận sự kiện đã xử lý.
- Nếu cần ordering theo aggregate, giữ key và sequence nghiệp vụ ổn định.

## 5. Consumer deduplication bằng Inbox pattern

Consumer có thể nhận cùng một event nhiều lần, đặc biệt khi producer retry ở tầng ứng dụng hoặc consumer xử lý xong nhưng chưa commit offset. Inbox pattern ghi nhận event ID đã xử lý trong database.

Ví dụ bảng:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng một database transaction, consumer:

1. Thử insert event ID vào bảng inbox.
2. Nếu insert thành công, thực hiện thay đổi nghiệp vụ.
3. Commit cả inbox record và thay đổi nghiệp vụ trong cùng transaction.
4. Nếu event ID đã tồn tại, bỏ qua tác động nghiệp vụ lặp.

Pseudocode:

~~~java
@Transactional
public void handle(OrderPaid event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return; // Sự kiện này đã được xử lý trước đó.
    }

    orderRepository.markPaid(event.orderId(), event.amount());
}
~~~

insertIfAbsent cần được triển khai bằng unique constraint hoặc câu lệnh insert có xử lý conflict phù hợp với database. Việc ghi inbox và cập nhật nghiệp vụ phải nằm trong cùng transaction; nếu commit tách rời, ứng dụng có thể đánh dấu đã xử lý nhưng chưa cập nhật nghiệp vụ hoặc cập nhật nghiệp vụ mà chưa lưu dấu deduplication.

Inbox không tự tạo exactly-once cho mọi side effect. Nếu handler gọi HTTP, gửi email hoặc cập nhật một hệ thống ngoài database transaction, cần thêm idempotency key ở dịch vụ đích hoặc một outbox riêng cho side effect đó.

## 6. Transactional Outbox cho producer

Một trường hợp phổ biến là ứng dụng vừa cập nhật database vừa phát sự kiện Kafka. Nếu ghi database thành công nhưng gửi Kafka thất bại, hai hệ thống không đồng nhất. Nếu gửi Kafka thành công nhưng database rollback, Kafka chứa sự kiện không có thay đổi nghiệp vụ tương ứng.

Transactional outbox giải quyết khoảng hở này bằng cách ghi thay đổi nghiệp vụ và event vào cùng một transaction database. Một relay riêng đọc outbox và gửi Kafka.

~~~mermaid
flowchart TD
    A[Request nghiệp vụ] --> B[DB transaction]
    B --> C[Cập nhật bảng nghiệp vụ]
    B --> D[Insert outbox event với eventId ổn định]
    C --> E[Commit DB]
    D --> E
    E --> F[Outbox relay đọc event chưa gửi]
    F --> G[Publish Kafka]
    G --> H{Có acknowledgement?}
    H -->|Có| I[Đánh dấu outbox đã gửi]
    H -->|Không xác định| J[Giữ trạng thái pending/unknown]
    J --> F
~~~

Nếu relay gửi record nhưng mất acknowledgement, nó có thể gửi lại cùng outbox row và cùng event ID. Consumer inbox nhận diện bản lặp và không thực hiện nghiệp vụ hai lần.

Outbox không làm cho việc gửi Kafka trở thành exactly-once ở mọi tầng. Nó bảo đảm thay đổi database và ý định phát event được commit nguyên tử; relay có thể gửi lặp, vì vậy consumer vẫn cần idempotency.

### 6.1. Cấu trúc outbox gợi ý

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL
);
~~~

Một relay có thể lấy các row PENDING, publish với key là aggregate_id, header/payload chứa event_id, rồi cập nhật trạng thái khi nhận acknowledgement. Nếu kết quả không xác định, row cần được giữ lại để retry hoặc đối soát theo chính sách. Không xóa row chỉ vì một lần gửi timeout.

## 7. Xử lý kết quả gửi trong KafkaProducer

Ví dụ dưới đây minh họa callback. Khi thành công, ứng dụng lưu metadata. Khi có exception, ứng dụng lưu event ID và lỗi để tầng điều phối phân loại; callback không tự quyết định gửi lại một record mới.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executor;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

public class ReliablePublisher {

    private final KafkaProducer<String, String> producer;
    private final SendResultStore resultStore;
    private final Executor resultExecutor;

    public ReliablePublisher(
            KafkaProducer<String, String> producer,
            SendResultStore resultStore,
            Executor resultExecutor) {
        this.producer = producer;
        this.resultStore = resultStore;
        this.resultExecutor = resultExecutor;
    }

    public void publish(String eventId, String orderId, String payload) {
        ProducerRecord<String, String> record =
            new ProducerRecord<>("orders", orderId, payload);

        record.headers().add(
            "event-id",
            eventId.getBytes(StandardCharsets.UTF_8)
        );

        producer.send(record, (metadata, exception) ->
            resultExecutor.execute(() -> {
                if (exception == null) {
                    resultStore.recordAcknowledged(
                        eventId,
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset()
                    );
                    return;
                }

                // Lưu kết quả và nguyên nhân để tầng điều phối phân loại.
                // Không gửi một record mới ngay trong callback.
                resultStore.recordNeedsReview(
                    eventId,
                    exception.getClass().getSimpleName(),
                    exception.getMessage()
                );
            })
        );
    }
}
~~~

SendResultStore và Executor là abstraction của ứng dụng, không phải API Kafka. Executor trong ví dụ nên có queue giới hạn và xử lý trường hợp bị từ chối task; tránh thực hiện database I/O blocking trực tiếp trên thread I/O của producer. Nếu không thể lưu trạng thái vì database hoặc executor lỗi, cần log/metric và có cơ chế phục hồi từ outbox hoặc nguồn dữ liệu bền vững.

### 7.1. Phân loại lỗi ở tầng điều phối

Hãy xem exception class, cause chain và giai đoạn lỗi:

| Nhóm lỗi | Ví dụ | Kết luận thường dùng |
|---|---|---|
| Lỗi dữ liệu trước khi gửi | Serializer không serialize được value | REJECTED; sửa payload hoặc serializer |
| Lỗi xác thực/phân quyền | Topic authorization bị từ chối | REJECTED; sửa ACL/credential |
| Lỗi cấu hình/topic rõ ràng | Topic hoặc request không hợp lệ | REJECTED; sửa cấu hình |
| Lỗi tạm thời được producer retry | Leader change hoặc network tạm thời | Để producer retry trong delivery window |
| Broker trả NotEnoughReplicasAfterAppend | Broker báo record đã append nhưng không đủ ISR để đáp ứng acknowledgement | UNKNOWN/needs review; không coi như chắc chắn chưa ghi |
| Broker trả NotEnoughReplicas trước khi append | ISR không đạt điều kiện tối thiểu tại thời điểm kiểm tra | Thường là REJECTED cho lần ghi này; kiểm tra trạng thái ISR |
| Mất kết nối sau khi request có thể đã tới broker | Response timeout, connection reset | UNKNOWN; giữ event ID và đối soát/retry idempotent |
| Hết delivery.timeout.ms | Producer đã hết thời gian giao record | Có thể UNKNOWN; không suy ra chắc chắn chưa append |

Danh sách này là hướng phân loại, không phải ánh xạ cứng cho mọi exception. Một số exception như lỗi replica có thể phát sinh ở các thời điểm khác nhau; hãy xem thông tin lỗi cụ thể và semantics của broker response. Khi không đủ bằng chứng, chọn UNKNOWN thay vì tự khẳng định thất bại.

## 8. Xử lý kết quả gửi trong Spring Kafka

Với Spring Kafka 3.x, KafkaTemplate.send() trả về CompletableFuture<SendResult<K,V>>. Có thể xử lý completion như sau:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>("orders", orderId, payload);

record.headers().add(
    "event-id",
    eventId.getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record).whenCompleteAsync((result, exception) -> {
    if (exception != null) {
        sendResultService.recordNeedsReview(
            eventId,
            exception.getClass().getSimpleName(),
            exception.getMessage()
        );
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    sendResultService.recordAcknowledged(
        eventId,
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
}, sendResultExecutor);
~~~

sendResultExecutor là executor do ứng dụng quản lý. Dùng executor riêng giúp chuyển phần xử lý completion ra khỏi thread hoàn tất gửi của producer. Executor cần có queue giới hạn và chính sách khi quá tải; không dùng thread pool không giới hạn trong hệ thống tải lớn.

Với Spring Kafka 2.x, KafkaTemplate.send() thường trả về ListenableFuture; API callback khác với CompletableFuture của phiên bản 3.x. Hãy kiểm tra phiên bản dependency trước khi áp dụng code.

Khi CompletableFuture hoàn tất exceptionally, không có nghĩa mọi lỗi đều là UNKNOWN. Dùng cùng nguyên tắc phân loại ở phần trước. Không tạo event ID mới khi retry một outbox event.

## 9. Retry an toàn và giữ ordering

Retry có thể xảy ra ở nhiều tầng:

- Kafka producer retry request nội bộ.
- Ứng dụng retry sau khi callback/Future thất bại.
- Outbox relay retry row chưa xác nhận.
- Consumer retry xử lý nghiệp vụ.

Nên xác định một nơi chịu trách nhiệm retry chính cho mỗi giai đoạn để tránh nhiều tầng retry nhân số lần gửi. Producer nội bộ nên được phép xử lý lỗi tạm thời trong delivery.timeout.ms; retry nghiệp vụ nên dùng event ID ổn định và có giới hạn/backoff.

### 9.1. Backoff và giới hạn retry

Khi ứng dụng phải retry, dùng exponential backoff có jitter và giới hạn số lần/thời gian. Tránh vòng lặp retry tức thời vì có thể làm tăng tải đúng lúc broker hoặc network đang gặp sự cố.

Một lịch retry minh họa:

| Lần thử | Thời gian chờ cơ sở |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |

Thêm jitter ngẫu nhiên và giới hạn trần theo SLA của nghiệp vụ. Bảng chỉ là ví dụ; chọn thông số theo timeout, tải và thời gian phục hồi thực tế.

### 9.2. Giữ thứ tự theo aggregate

Nếu nhiều sự kiện cùng aggregate phải theo thứ tự, hãy:

- Dùng cùng key, ví dụ orderId, để các sự kiện vào cùng partition.
- Gắn sequence/version nghiệp vụ tăng dần vào payload.
- Retry cùng event ID và cùng key.
- Tránh publish sự kiện sau vượt qua sự kiện trước khi kết quả của sự kiện trước còn UNKNOWN.
- Nếu cần song song, điều phối theo aggregate key thay vì cho phép cùng aggregate chạy đồng thời không kiểm soát.

Deduplication loại bỏ tác động lặp nhưng không tự sửa thứ tự sai. Consumer có thể nhận event sequence 8 trước sequence 7 nếu ứng dụng phát lại không đúng cách; consumer cần kiểm tra sequence/version nếu nghiệp vụ yêu cầu.

### 9.3. Không dùng dead-letter queue như bằng chứng chưa gửi

Dead-letter topic hữu ích cho record bị consumer xử lý lỗi hoặc record bị từ chối theo chính sách. Nhưng kết quả gửi producer UNKNOWN không nên được đưa vào dead-letter như thể đã xác định record không tồn tại. Hãy lưu trạng thái chưa xác định và dùng event ID để đối soát.

## 10. Kafka transaction và giới hạn exactly-once

Kafka transaction có thể phối hợp việc ghi nhiều topic và commit offset consumer trong cùng một transaction Kafka. Với consume-transform-produce, producer có transactional.id, consumer đọc read_committed và offset đầu vào được gửi vào transaction.

Transaction giúp consumer downstream không nhìn thấy record thuộc transaction chưa commit hoặc đã abort. Nó không tự tạo transaction phân tán giữa Kafka và database bên ngoài.

Khi kết quả commitTransaction() không rõ do mất kết nối, ứng dụng không nên đoán transaction đã commit hay abort rồi phát lại side effect bên ngoài. Cần dùng quy trình phục hồi transactional producer theo tài liệu phiên bản Kafka, giữ transactional.id ổn định cho cùng logical producer và để producer mới khởi tạo/fence producer cũ khi cần. Với side effect database, tiếp tục dùng outbox/inbox hoặc idempotency ở hệ thống đích.

Exactly-once trong Kafka không đồng nghĩa toàn bộ hệ thống nghiệp vụ thực hiện mọi side effect đúng một lần. Phạm vi bảo đảm phải được xác định rõ: giữa các topic Kafka, giữa consumer offset và output topic, hay giữa Kafka và một database/dịch vụ ngoài.

## 11. Quan sát và vận hành trạng thái UNKNOWN

Ứng dụng nên lưu một bản ghi gửi có thể đối soát:

| Trường | Mục đích |
|---|---|
| event_id | Định danh ổn định qua mọi lần retry |
| aggregate_id | Giữ key và ordering theo thực thể |
| topic | Topic đích |
| status | PENDING, ACKNOWLEDGED, REJECTED hoặc UNKNOWN |
| attempt_count | Số lần ứng dụng yêu cầu gửi |
| last_error | Exception cuối cùng và nguyên nhân |
| partition, offset | Metadata khi nhận acknowledgement |
| created_at, updated_at | Thời điểm tạo và lần cập nhật cuối |

Các metric nên theo dõi:

- Số lượng event ở trạng thái UNKNOWN.
- Tuổi lớn nhất của event UNKNOWN.
- Tỷ lệ timeout và connection reset.
- Producer retry rate và delivery timeout rate.
- Số lần retry theo event ID.
- Số event bị deduplicate ở consumer.
- Outbox backlog và thời gian từ tạo event đến acknowledgement.

Đặt cảnh báo khi UNKNOWN tồn tại lâu hơn SLA hoặc outbox backlog tăng liên tục. Đừng xóa trạng thái UNKNOWN chỉ vì đã qua một khoảng thời gian; cần có chính sách retry/đối soát rõ ràng và lưu dấu kiểm toán.

## 12. Quy trình xử lý khi mất kết nối hoặc timeout

Khi producer gặp lỗi không rõ kết quả, thực hiện theo trình tự:

1. **Giữ nguyên event ID:** không tạo một ID mới cho cùng một sự kiện nghiệp vụ.
2. **Ghi nhận trạng thái:** lưu exception, thời điểm, topic, key và attempt; nếu chưa có metadata thì đánh dấu UNKNOWN khi không thể chứng minh thất bại.
3. **Để producer hoàn tất retry nội bộ:** không tạo thêm request mới ngay khi producer vẫn còn xử lý lần gửi ban đầu.
4. **Phân loại lỗi:** phân biệt lỗi serialization/authorization rõ ràng với network timeout hoặc delivery timeout.
5. **Áp dụng retry có kiểm soát:** backoff, jitter, giới hạn thời gian và dùng lại event ID.
6. **Dedupe ở consumer:** dùng inbox/unique constraint để bảo đảm bản ghi lặp không lặp side effect.
7. **Đối soát:** theo dõi event ID ở consumer/inbox hoặc nguồn dữ liệu bền vững; nếu không có xác nhận, retry theo chính sách idempotent.
8. **Giữ ordering:** không cho sự kiện sau của cùng aggregate vượt qua sự kiện trước đang UNKNOWN nếu nghiệp vụ yêu cầu thứ tự.

## 13. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: Mô phỏng mất acknowledgement

1. Dùng môi trường lab có Kafka broker và producer Java.
2. Gửi record có event ID cố định và bật enable.idempotence=true.
3. Quan sát callback và metadata khi kết nối ổn định.
4. Trong môi trường thử nghiệm có kiểm soát, tạo sự cố network sau khi request có thể đã tới broker.
5. Ghi lại exception, trạng thái producer và record mà consumer quan sát được.
6. Giải thích vì sao timeout không chứng minh record chưa được append.

Không thực hiện việc cắt mạng hoặc kill broker trong môi trường production.

### Bài tập 2: Dedupe bằng Inbox

1. Tạo bảng inbox có unique key event_id.
2. Gửi hai record có cùng event ID nhưng cùng payload.
3. Consumer xử lý trong database transaction.
4. Xác minh thay đổi nghiệp vụ chỉ được áp dụng một lần.
5. Thử dừng consumer sau khi database commit nhưng trước khi offset commit; quan sát record được đọc lại và dedupe hoạt động.

### Bài tập 3: Transactional Outbox

1. Tạo bảng nghiệp vụ và bảng outbox.
2. Trong một transaction database, cập nhật đơn hàng và insert event vào outbox.
3. Relay publish event với event ID ổn định.
4. Mô phỏng relay nhận timeout sau khi gửi.
5. Retry cùng outbox row và xác minh consumer inbox loại bản lặp.

### Câu hỏi tự kiểm tra

1. Vì sao broker có thể đã append record nhưng producer vẫn nhận timeout?
2. max.block.ms khác delivery.timeout.ms ở điểm nào?
3. Khi nào max.block.ms có thể hết hạn trước khi record được đưa vào quá trình gửi?
4. Producer idempotence bảo vệ retry nào và không bảo vệ retry nào?
5. Vì sao event ID phải được giữ nguyên qua các lần retry?
6. Inbox cần nằm trong cùng database transaction với side effect nào?
7. Outbox giải quyết khoảng hở giữa database commit và Kafka publish ra sao?
8. Vì sao deduplication không tự bảo đảm ordering?
9. acks=all giúp gì và vì sao vẫn có thể có kết quả UNKNOWN?
10. Exactly-once của Kafka transaction khác exactly-once với database bên ngoài thế nào?

Khi phân biệt được lỗi từ chối rõ ràng và kết quả UNKNOWN, ứng dụng có thể retry có kiểm soát, giữ event ID ổn định và dùng inbox/outbox để bảo vệ nghiệp vụ khỏi tác động lặp khi kết nối Kafka không ổn định.
