# retries, retry.backoff.ms và lỗi có thể thử lại

Khi producer gửi record đến Kafka, một số lỗi chỉ mang tính tạm thời: leader của partition vừa thay đổi, mạng chập chờn hoặc broker chưa có đủ replica trong ISR để xác nhận ghi. Kafka producer có thể tự gửi lại request khi gặp lỗi được đánh dấu là có thể thử lại. Các cấu hình **retries**, **retry.backoff.ms**, **retry.backoff.max.ms**, **request.timeout.ms** và **delivery.timeout.ms** phối hợp để kiểm soát hành vi này.

Retry giúp luồng gửi chịu được sự cố ngắn, nhưng không làm mọi lỗi tự biến mất và cũng không bảo đảm ứng dụng không bao giờ nhận record trùng. Cần phân biệt lỗi tạm thời với lỗi cấu hình/dữ liệu, hiểu giới hạn thời gian gửi, bật idempotence khi phù hợp và tránh tạo thêm một vòng retry không kiểm soát ở tầng nghiệp vụ.

## 1. Vì sao producer cần retry?

Producer gửi record đến broker leader của partition. Trong quá trình đó có thể xảy ra:

- Broker leader dừng hoặc partition vừa bầu leader mới.
- Kết nối mạng bị reset hoặc response bị mất.
- Broker xử lý request chậm hơn request.timeout.ms.
- ISR giảm xuống dưới min.insync.replicas, khiến broker tạm thời từ chối ghi với acks=all.
- Cluster đang quá tải và không thể phản hồi trong thời gian mong muốn.

Một số tình huống có thể tự hồi phục sau vài mili giây hoặc vài giây. Producer retry giúp client tiếp tục gửi mà không bắt ứng dụng phải tự phát hiện từng lần leader election hoặc lỗi mạng.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant P as Kafka Producer
    participant L as Broker leader
    participant F as Follower
    App->>P: send(record)
    P->>L: ProduceRequest
    L-->>P: Lỗi tạm thời / timeout
    Note over P: Chờ retry.backoff
    P->>L: Gửi lại request
    L->>F: Replication
    F-->>L: Replica bắt kịp
    L-->>P: ProduceResponse thành công
    P-->>App: Callback / Future thành công
~~~

Producer quản lý retry nội bộ cho những lỗi được client xem là có thể thử lại. Ứng dụng thường chỉ nhận kết quả cuối cùng: gửi thành công hoặc gửi thất bại sau khi hết giới hạn retry/thời gian.

## 2. Phân biệt lỗi có thể thử lại và lỗi không thể tự khắc phục bằng retry

Không phải mọi exception đều nên retry. Có thể chia lỗi theo nguyên nhân:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi leader/metadata tạm thời | NOT_LEADER_OR_FOLLOWER, UNKNOWN_TOPIC_OR_PARTITION trong lúc metadata thay đổi | Client refresh metadata và retry theo cơ chế Kafka |
| Lỗi mạng hoặc timeout | NetworkException, RequestTimedOutException | Retry có backoff; đồng thời kiểm tra broker và mạng nếu kéo dài |
| Replica chưa đủ điều kiện ghi | NOT_ENOUGH_REPLICAS, NOT_ENOUGH_REPLICAS_AFTER_APPEND | Có thể retry khi ISR phục hồi; kiểm tra replication và min.insync.replicas |
| Dữ liệu không hợp lệ | SerializationException, RecordTooLargeException | Sửa dữ liệu, serializer hoặc giới hạn kích thước; retry nguyên trạng không giải quyết được |
| Quyền truy cập/cấu hình | TopicAuthorizationException, ClusterAuthorizationException, topic name không hợp lệ | Sửa ACL, cấu hình hoặc tên topic |
| Lỗi phiên bản/giao thức | API hoặc version không được hỗ trợ | Đồng bộ phiên bản client/broker và cấu hình tương thích |

Tên exception và khả năng retry cụ thể phụ thuộc Kafka client/broker version và trạng thái request. Kafka client có cơ chế phân loại lỗi qua các exception có thể retry; không nên tự coi mọi KafkaException là retriable.

### Lỗi có thể retry không đồng nghĩa lần gửi trước chắc chắn chưa ghi

Một tình huống quan trọng: leader đã append record nhưng response không đến được producer. Producer chỉ nhìn thấy timeout và không biết chắc record đã được ghi hay chưa. Nếu gửi lại như một record mới, có thể xuất hiện hai bản ghi cùng nội dung.

NOT_ENOUGH_REPLICAS_AFTER_APPEND cũng cần được hiểu cẩn thận: record có thể đã được append ở leader trước khi điều kiện ISR không còn đáp ứng mức xác nhận. Không nên suy luận rằng nhận lỗi đồng nghĩa record chưa tồn tại trong log.

## 3. Các cấu hình điều khiển retry

| Cấu hình | Vai trò |
|---|---|
| retries | Số lần producer được phép thử lại request thất bại do lỗi có thể retry |
| retry.backoff.ms | Khoảng chờ ban đầu giữa các lần retry |
| retry.backoff.max.ms | Giới hạn trên của khoảng backoff khi client hỗ trợ backoff tăng dần |
| request.timeout.ms | Thời gian tối đa producer chờ phản hồi cho một request |
| delivery.timeout.ms | Tổng giới hạn thời gian từ lúc send() trả về đến khi record được xác nhận hoặc thất bại |
| linger.ms | Thời gian producer có thể chờ gom thêm record vào batch trước khi gửi |
| enable.idempotence | Bật cơ chế chống ghi trùng do retry ở cấp producer protocol |
| acks | Mức xác nhận producer yêu cầu từ broker |

### retries

retries giới hạn số lần thử lại khi gặp lỗi có thể retry. Tăng giá trị này không đồng nghĩa record chắc chắn được gửi thành công: thời gian giao record vẫn bị giới hạn bởi delivery.timeout.ms.

Ở các Kafka client hiện đại, giá trị mặc định có thể rất lớn để retry trong giới hạn thời gian giao record. Giá trị mặc định thay đổi theo phiên bản, vì vậy hãy kiểm tra cấu hình của đúng Kafka client đang dùng thay vì sao chép một con số từ môi trường khác.

### retry.backoff.ms và retry.backoff.max.ms

retry.backoff.ms giúp producer không gửi request lặp liên tục khi broker đang lỗi. Một số phiên bản client hỗ trợ tăng backoff dần sau các lần thất bại, tối đa đến retry.backoff.max.ms.

Ví dụ cấu hình:

~~~properties
retry.backoff.ms=100
retry.backoff.max.ms=1000
~~~

Đây là ví dụ giá trị, không phải khuyến nghị cố định cho mọi hệ thống. Nếu backoff quá thấp, producer có thể tạo thêm tải trong lúc cluster đang phục hồi. Nếu quá cao, record phải chờ lâu dù lỗi đã hết. Hãy chọn dựa trên độ dài sự cố cần chịu đựng và yêu cầu latency của nghiệp vụ.

### request.timeout.ms và delivery.timeout.ms

Hai cấu hình có phạm vi khác nhau:

- request.timeout.ms giới hạn thời gian chờ phản hồi của một request.
- delivery.timeout.ms giới hạn tổng thời gian giao một record, bao gồm thời gian chờ batch, các lần request và backoff retry.

delivery.timeout.ms là giới hạn cuối cùng của lần gửi. Khi hết thời gian này, producer hoàn tất record với lỗi timeout ngay cả khi retries vẫn còn. Vì vậy, chỉ tăng retries mà không xem xét delivery timeout có thể không thay đổi kết quả.

Kafka yêu cầu delivery.timeout.ms không nhỏ hơn tổng request.timeout.ms và linger.ms. Hãy kiểm tra ràng buộc cấu hình của phiên bản client đang sử dụng.

## 4. Quan hệ giữa retry, acks và replication

Retry chỉ có ý nghĩa khi broker có khả năng phục hồi và điều kiện ghi có thể trở lại hợp lệ. Với dữ liệu quan trọng, producer thường kết hợp:

~~~properties
acks=all
enable.idempotence=true
retries=2147483647
max.in.flight.requests.per.connection=5
delivery.timeout.ms=120000
request.timeout.ms=30000
retry.backoff.ms=100
retry.backoff.max.ms=1000
~~~

Các giá trị trên chỉ là ví dụ minh họa. Hãy xác nhận chúng tương thích với phiên bản client, SLA latency, replication factor và min.insync.replicas của cluster.

acks=all yêu cầu leader chờ các replica trong ISR xác nhận theo cơ chế Kafka. Nếu ISR thấp hơn min.insync.replicas, broker có thể từ chối ghi. Retry chỉ thành công khi ISR phục hồi trong giới hạn delivery timeout. Nếu broker không thể phục hồi kịp, producer vẫn trả lỗi.

Không nên chỉ tăng retry để che giấu tình trạng replica liên tục mất đồng bộ. Cần theo dõi ISR shrink/expand, replication lag, broker availability và lỗi ghi.

## 5. Idempotent producer giúp retry an toàn hơn

Khi producer bật enable.idempotence=true, Kafka cấp producer ID và client gửi sequence number cho từng partition. Broker dùng thông tin này để nhận diện batch retry, tránh append lại một batch đã được chấp nhận trước đó.

Idempotence giải quyết tình huống producer không nhận được response và phải gửi lại cùng batch trong cơ chế retry của Kafka. Nó không tự loại bỏ:

- Ứng dụng gọi publish hai lần cho cùng một sự kiện.
- Hai producer độc lập cùng phát một sự kiện nghiệp vụ.
- Consumer xử lý lại record sau khi restart hoặc rebalance.
- Việc ứng dụng tự tạo một ProducerRecord mới để retry sau khi lần gửi cũ đã hết delivery timeout.

Với Kafka client hiện đại, idempotence tương thích với tối đa 5 request đang bay trên mỗi connection. Nếu tắt idempotence, retry kết hợp với nhiều request in-flight có thể làm thay đổi thứ tự: batch sau được ghi trước trong khi batch trước thất bại rồi mới retry.

Nếu nghiệp vụ cần tránh trùng ở cấp business, hãy dùng event ID ổn định và thiết kế consumer idempotent. Idempotence của producer là bảo đảm ở giao thức gửi, không thay thế khóa duy nhất hoặc transaction ở hệ thống đích.

## 6. Ordering khi producer retry

Giả sử producer gửi hai batch A rồi B vào cùng partition:

1. A gặp lỗi tạm thời.
2. B được broker ghi thành công.
3. A được retry và ghi sau B.

Nếu producer không bật idempotence và cho phép nhiều request in-flight, thứ tự ghi có thể khác thứ tự ứng dụng gửi. Điều này đặc biệt nguy hiểm khi hai record là các trạng thái liên tiếp của cùng một thực thể.

Để giảm nguy cơ:

- Bật idempotent producer với cấu hình tương thích.
- Dùng key ổn định để các sự kiện của cùng thực thể đi cùng partition.
- Không tạo thêm retry ở tầng ứng dụng khi producer vẫn đang quản lý lần gửi cũ.
- Nếu phải retry nghiệp vụ sau khi lần gửi cuối cùng thất bại, dùng event ID/version và kiểm soát thứ tự phát lại.

Idempotence giúp giữ thứ tự trong các retry của một producer session theo cơ chế Kafka. Nó không thiết lập thứ tự giữa nhiều producer độc lập hoặc giữa nhiều topic.

## 7. Cấu hình retry trong Java Kafka Producer

Ví dụ tạo producer với String key và String value:

~~~java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put(
    "key.serializer",
    "org.apache.kafka.common.serialization.StringSerializer"
);
properties.put(
    "value.serializer",
    "org.apache.kafka.common.serialization.StringSerializer"
);
properties.put("acks", "all");
properties.put("enable.idempotence", true);
properties.put("retries", Integer.MAX_VALUE);
properties.put("max.in.flight.requests.per.connection", 5);
properties.put("delivery.timeout.ms", 120_000);
properties.put("request.timeout.ms", 30_000);
properties.put("retry.backoff.ms", 100);
properties.put("retry.backoff.max.ms", 1_000);

KafkaProducer<String, String> producer =
    new KafkaProducer<>(properties);
~~~

Trong ứng dụng thật, quản lý vòng đời producer bằng dependency injection hoặc một bean dùng chung thay vì tạo producer mới cho từng record. Producer cần được đóng đúng cách khi ứng dụng dừng để flush các record đang chờ trong giới hạn thời gian phù hợp.

## 8. Cấu hình trong Spring Boot và Spring Kafka

Các thuộc tính producer được cấu hình qua spring.kafka.producer.properties:

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
        request.timeout.ms: 30000
        retry.backoff.ms: 100
        retry.backoff.max.ms: 1000
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Ví dụ gửi record bằng KafkaTemplate:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public void publish(OrderCreated event) {
        kafkaTemplate
            .send("orders.events", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    // Producer đã áp dụng retry nội bộ trước khi hoàn tất future.
                    // Ghi nhận lỗi cuối cùng và phân loại nguyên nhân.
                    return;
                }

                var metadata = result.getRecordMetadata();
                // Ghi nhận topic, partition và offset khi gửi thành công.
            });
    }
}
~~~

Trong các phiên bản Spring Kafka hiện đại, KafkaTemplate.send trả về CompletableFuture. Các phiên bản cũ có thể dùng ListenableFuture. Future hoàn tất sau khi producer client kết thúc lần gửi, bao gồm các lần retry nội bộ; callback không phải nơi để tự động retry vô hạn.

## 9. Khi nào cần retry ở tầng ứng dụng?

Thông thường, hãy để Kafka producer xử lý retry cho lỗi request tạm thời. Retry ở tầng ứng dụng chỉ nên dùng khi có lý do nghiệp vụ rõ ràng, ví dụ:

- Cần chờ một dependency ngoài Kafka phục hồi trước khi tạo lại event.
- Lần gửi đã kết thúc với lỗi cuối cùng và ứng dụng có cơ chế lưu bền vững event để phát lại.
- Có quy trình sửa dữ liệu hoặc schema trước khi thử lại.

Nếu dùng application retry, cần:

1. Giới hạn số lần và tổng thời gian retry.
2. Dùng exponential backoff có jitter để tránh nhiều instance cùng retry một lúc.
3. Dùng event ID ổn định để nhận diện lần phát lại.
4. Ghi nhận trạng thái gửi bền vững, chẳng hạn bằng Transactional Outbox.
5. Bảo đảm consumer có thể xử lý idempotent khi cùng event được phát lại.
6. Phân biệt lỗi tạm thời với lỗi vĩnh viễn; không retry serialization, authorization hoặc record vượt kích thước mãi mãi.

Không gọi KafkaTemplate.send đệ quy ngay trong callback mà không có giới hạn. Khi cluster đang lỗi, cách này có thể tạo vòng lặp retry ở nhiều tầng, làm tăng tải và khiến ứng dụng cạn thread hoặc bộ nhớ.

## 10. Transactional Outbox và phát lại an toàn

Nếu ứng dụng cần lưu nghiệp vụ vào database rồi phát sự kiện Kafka, có thể xảy ra tình huống database commit thành công nhưng Kafka gửi thất bại. Nếu chỉ retry trong bộ nhớ, ứng dụng restart có thể mất event cần phát.

Transactional Outbox giải quyết khoảng trống này:

1. Trong cùng transaction database, lưu thay đổi nghiệp vụ và một outbox record.
2. Một relay đọc các outbox record chưa gửi và publish đến Kafka.
3. Khi Kafka xác nhận thành công, relay đánh dấu outbox record đã gửi.
4. Nếu relay dừng trước khi đánh dấu, record có thể được gửi lại; consumer cần idempotent theo event ID.

Outbox không làm Kafka và database thành một distributed transaction tự động. Nó bảo đảm event cần phát được lưu bền vững cùng thay đổi nghiệp vụ và cho phép retry có kiểm soát sau restart.

## 11. Lỗi nào nên retry và lỗi nào nên dừng?

| Tình huống | Retry nội bộ producer | Hành động ứng dụng |
|---|---|---|
| Leader vừa thay đổi | Client thường tự refresh metadata và retry | Theo dõi nếu lỗi kéo dài |
| Network timeout ngắn | Client retry theo cấu hình | Kiểm tra kết nối nếu vượt delivery timeout |
| ISR tạm thời thiếu replica | Có thể retry | Điều tra replication nếu tái diễn |
| SerializationException | Không thể sửa bằng retry cùng dữ liệu | Sửa serializer hoặc payload; lưu lỗi để xử lý |
| Authorization failure | Retry không sửa được quyền | Cấp quyền đúng và kiểm tra principal |
| RecordTooLargeException | Retry không làm record nhỏ hơn | Giảm payload hoặc điều chỉnh giới hạn có kiểm soát |
| Topic/partition cấu hình sai | Không nên retry vô hạn | Sửa topic hoặc metadata/config |
| Delivery timeout hết hạn | Lần gửi đã kết thúc thất bại ở phía client | Ghi nhận event chưa được xác nhận; replay theo cơ chế có ID/idempotence |

Khi nhận lỗi cuối cùng, producer không thể luôn chứng minh record chưa từng được append. Nếu response bị mất sau khi broker ghi thành công, kết quả ở phía client có thể không chắc chắn. Vì vậy, replay cần được thiết kế để chịu được khả năng trùng.

## 12. Kiểm thử hành vi retry

Không chỉ kiểm tra trường hợp broker hoạt động bình thường. Hãy kiểm thử các tình huống lỗi có kiểm soát:

- Tắt broker leader trong lúc gửi và khởi động lại broker.
- Làm gián đoạn kết nối client đến broker trong thời gian ngắn.
- Tạm thời giảm ISR dưới min.insync.replicas rồi khôi phục follower.
- Gửi record lớn hơn giới hạn để xác nhận lỗi không bị retry vô ích.
- Dùng dữ liệu không serialize được để xác nhận lỗi xảy ra ở phía client.
- Quan sát callback/future chỉ hoàn tất sau khi producer kết thúc retry.
- Kiểm tra thứ tự record cùng key khi producer retry.
- Xác minh event ID giúp consumer loại bỏ bản phát lại ở tầng nghiệp vụ.

Trong môi trường test, có thể dùng broker/container riêng và fault injection ở network. Không tạo lỗi bằng cách dừng broker dùng chung hoặc production cluster.

## 13. Theo dõi retry trong vận hành

Các tín hiệu hữu ích:

- Record send rate và record error rate.
- Request latency, request timeout và delivery timeout.
- Số lần retry hoặc tỷ lệ request retry nếu client expose metric tương ứng.
- Batch size, request queue time, buffer available bytes và producer throttle time.
- ISR shrink/expand, replication lag và broker availability.
- Tỷ lệ event được phát lại từ outbox và số event trùng bị consumer loại bỏ.

Tên metric cụ thể thay đổi theo phiên bản Kafka client và hệ thống metrics exporter. Hãy kiểm tra metric thực tế của client đang chạy, sau đó xây dashboard theo các nhóm send, request, retry, buffer và broker health.

Nếu retry tăng đột biến, hãy tìm nguyên nhân gốc ở broker, network hoặc replication. Tăng retries/backoff chỉ thay đổi cách client phản ứng; nó không sửa được cluster đang mất khả năng phục vụ.

## 14. Checklist cấu hình và xử lý lỗi

- retries đủ cho số lần thử lại dự kiến nhưng vẫn nằm trong giới hạn delivery.timeout.ms.
- retry.backoff.ms không quá thấp gây request dồn dập khi broker lỗi.
- retry.backoff.max.ms phù hợp với phiên bản client và thời gian phục hồi mong muốn.
- request.timeout.ms phù hợp với latency của cluster.
- delivery.timeout.ms đáp ứng SLA và lớn hơn ràng buộc request.timeout.ms + linger.ms.
- enable.idempotence=true khi cần chống trùng do retry của producer.
- acks và min.insync.replicas được chọn theo yêu cầu durability.
- max.in.flight.requests.per.connection tương thích với idempotence và yêu cầu ordering.
- Lỗi serialize, authorization và dữ liệu không hợp lệ không bị retry vô hạn.
- Retry ở tầng ứng dụng có giới hạn, backoff, event ID và cơ chế lưu bền vững.
- Có metric và log để phân biệt retry tạm thời với lỗi cuối cùng.

## Kết luận

retries quy định số lần thử lại, retry.backoff.ms đặt khoảng chờ ban đầu và retry.backoff.max.ms giới hạn backoff tăng dần ở các client hỗ trợ. request.timeout.ms giới hạn một request, còn delivery.timeout.ms giới hạn toàn bộ thời gian producer cố gắng giao record. Khi delivery timeout hết hạn, producer trả lỗi dù vẫn còn số lần retry.

Retry hiệu quả nhất khi kết hợp với idempotent producer, acks và replication phù hợp. Hãy để producer xử lý lỗi request tạm thời, phân loại lỗi vĩnh viễn và chỉ thêm retry nghiệp vụ khi có event ID, lưu bền vững và cơ chế chống xử lý trùng. Theo dõi retry cùng broker/ISR health giúp phân biệt sự cố ngắn có thể tự hồi phục với vấn đề cần xử lý ở cluster.
