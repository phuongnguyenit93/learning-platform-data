# Event và Kafka topic

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua hợp đồng sự kiện. Khi một sự kiện cần được chuyển tới một ứng dụng khác, Apache Kafka có thể đóng vai trò nền tảng truyền tải. Để tích hợp đúng, cần hiểu quan hệ giữa event nghiệp vụ, Kafka record, topic, partition và consumer group. Những khái niệm này liên quan với nhau nhưng không đồng nghĩa.

Spring Modulith giúp tổ chức event ở ranh giới module và đánh dấu những event cần externalize. Kafka cung cấp nơi lưu trữ phân tán và cơ chế phân phối record tới các consumer. Ứng dụng cần nối hai phần bằng integration phù hợp, đồng thời quyết định cách đặt topic, chọn key, serialize payload, xác nhận gửi và phục hồi khi có lỗi.

## 1. Phân biệt application event, Kafka record và topic

**Application event** mô tả một điều đã xảy ra trong nghiệp vụ của ứng dụng, ví dụ một đơn hàng được xác nhận hoặc một mặt hàng được giữ chỗ. Event thường được biểu diễn bằng một class hoặc record Java.

**Kafka record** là đơn vị dữ liệu được producer gửi vào Kafka. Một record gồm topic, partition, offset, key, value, timestamp và các header. Value thường chứa payload đã serialize từ application event.

**Topic** là luồng record có tên trong Kafka. Topic được chia thành một hoặc nhiều partition để lưu trữ và xử lý song song. Consumer đọc record từ partition theo offset.

Có thể hình dung đường đi:

~~~text
Nghiệp vụ trong module
        |
        v
Application event
        |
        v
Spring Modulith externalization
        |
        v
Logical target
        |
        v
Kafka integration / producer
        |
        v
Kafka topic
        |
        +---- partition 0
        +---- partition 1
        +---- partition 2
                 |
                 v
          Consumer group
                 |
                 v
          Ứng dụng nhận event
~~~

Ví dụ, khi kho giữ chỗ thành công, module Inventory phát event **StockReserved**. Event đó có thể được listener nội bộ dùng để cập nhật projection, đồng thời được externalize để hệ thống vận chuyển đọc và cập nhật trạng thái đơn hàng.

Một event có thể tạo ra nhiều publication tới các listener khác nhau. Một Kafka topic cũng có thể chứa nhiều record cùng loại hoặc nhiều loại event nếu contract và consumer được thiết kế để phân biệt chúng. Vì vậy, không nên coi tên class Java, tên event và tên topic là cùng một khái niệm.

## 2. Đánh dấu event cần externalize trong Spring Modulith

Một event có thể được đánh dấu bằng **@Externalized** để chỉ ra rằng nó cần được chuyển ra ngoài ứng dụng:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("inventory.stock-reserved.v1")
public record StockReserved(
    UUID eventId,
    UUID reservationId,
    String warehouseId,
    int quantity,
    Instant occurredAt
) {}
~~~

Chuỗi trong **@Externalized** là target logic của externalization. Integration có thể ánh xạ target đó tới Kafka topic, hoặc dùng nó làm tên topic trực tiếp nếu cách cấu hình đang dùng quy định như vậy. Không nên mặc định mọi phiên bản hoặc mọi integration đều tự động ánh xạ target thành topic vật lý theo cùng một quy tắc.

Giữ target logic trong event contract giúp domain không phụ thuộc vào tên cluster, broker hoặc môi trường triển khai. Ví dụ, target **inventory.stock-reserved.v1** có thể được ánh xạ tới topic khác nhau ở local, staging và production thông qua cấu hình của integration.

Cùng event vẫn có thể được listener nội bộ xử lý:

~~~java
@Component
class StockReservationProjection {

    @ApplicationModuleListener
    void on(StockReserved event) {
        // Cập nhật projection trong ứng dụng.
    }
}
~~~

Listener nội bộ và externalization phục vụ hai ranh giới khác nhau. Khi tạm dừng Kafka outbound, không nên vô tình tắt producer hoặc các listener nội bộ không liên quan.

Để dùng Kafka, ứng dụng có thể chọn integration Kafka được Spring Modulith hỗ trợ hoặc xây dựng adapter riêng bằng Spring Kafka. Dependency, auto-configuration và cách khai báo bean cần khớp với phiên bản Spring Modulith và Spring Kafka đang dùng. Hãy kiểm tra tài liệu đúng phiên bản trước khi chọn tên class cấu hình hoặc API cụ thể; annotation **@Externalized** tự nó không cấu hình broker, serializer, topic hay credential.

## 3. Chọn ranh giới và tên topic

Topic nên thể hiện luồng dữ liệu mà consumer cần đăng ký. Tên topic thường chứa domain, loại sự kiện và version của contract:

~~~text
inventory.stock-reserved.v1
billing.payment-captured.v1
shipping.shipment-dispatched.v1
~~~

Một quy ước đặt tên tốt cần:

- Có domain sở hữu event để biết ai chịu trách nhiệm về contract.
- Dùng tên sự kiện hoặc luồng nghiệp vụ có ý nghĩa ổn định.
- Có version khi thay đổi contract không tương thích.
- Tránh đưa tên môi trường, hostname hoặc tên cluster vào event type.
- Tránh dùng tên quá chung như **events** hoặc **messages** khiến consumer phải đoán payload.

Có hai cách tổ chức phổ biến:

| Cách tổ chức | Đặc điểm | Khi phù hợp |
|---|---|---|
| Một topic cho một event type hoặc luồng nghiệp vụ | Contract và quyền truy cập rõ, dễ cấu hình consumer | Các event có schema, retention hoặc ownership khác nhau |
| Một topic cho nhiều event type cùng domain | Giảm số topic, gom luồng liên quan | Có envelope chứa event type/version và consumer có thể định tuyến an toàn |

Nếu nhiều event type dùng chung topic, payload cần có trường nhận dạng loại event và version. Consumer phải xử lý event không biết theo chính sách rõ ràng, ví dụ bỏ qua có log, chuyển sang quarantine hoặc dừng consumer tùy mức độ quan trọng. Không nên deserialize mọi record vào một class chỉ dựa vào giả định rằng tất cả payload có cùng cấu trúc.

Không tạo một topic mới cho từng instance hoặc từng tenant nếu không có yêu cầu vận hành rõ ràng. Số lượng topic lớn làm tăng chi phí quản lý partition, ACL, retention, monitoring và nâng cấp schema.

## 4. Partition, key và thứ tự record

Topic được chia thành các partition. Mỗi partition là một log có thứ tự record riêng. Kafka bảo đảm thứ tự đọc trong một partition; Kafka không bảo đảm thứ tự toàn cục giữa các partition của cùng topic.

Producer thường gửi record cùng một key cho cùng partition theo partitioner đang sử dụng. Vì vậy, key là quyết định quan trọng khi event cần giữ thứ tự theo một thực thể nghiệp vụ.

Ví dụ, nếu cần giữ thứ tự các event của cùng một reservation, có thể dùng **reservationId** làm key:

~~~java
String key = event.reservationId().toString();

kafkaTemplate.send(
    "inventory.stock-reserved.v1",
    key,
    event
);
~~~

Đây là ví dụ dùng Spring Kafka để gửi record; tên topic ở đây là topic vật lý đã được cấu hình cho ứng dụng. Nếu cần thứ tự theo đơn hàng thay vì reservation, hãy dùng **orderId**. Chọn key theo aggregate hoặc thực thể mà consumer cần xử lý theo thứ tự.

| Key | Hệ quả |
|---|---|
| **orderId** | Event của cùng đơn hàng thường đi cùng partition |
| **reservationId** | Event của cùng lần giữ chỗ thường đi cùng partition |
| **eventId** | Mỗi event thường phân tán hơn; không tạo thứ tự theo aggregate |
| Không có key | Record có thể được phân phối theo chiến lược producer; không có bảo đảm thứ tự theo nghiệp vụ |

Key có cardinality cao thường giúp phân tán tải. Nếu tất cả record đều dùng một key cố định, chúng sẽ dồn vào một partition và tạo hot partition. Ngược lại, nếu chọn key ngẫu nhiên trong khi cần thứ tự theo aggregate, các event liên quan có thể nằm ở partition khác nhau.

Khi tăng số partition, phép ánh xạ key sang partition có thể thay đổi. Nếu hệ thống phụ thuộc vào thứ tự theo key trong thời gian dài, việc tăng partition cần được xem như thay đổi vận hành có ảnh hưởng đến ordering và được lập kế hoạch.

## 5. Gửi event từ producer

Producer chuyển event thành Kafka record và gửi tới topic. Với Spring Kafka, **KafkaTemplate** là API phổ biến để gửi message. Ví dụ adapter minh họa:

~~~java
@Component
class StockReservedKafkaPublisher {

    private final KafkaTemplate<String, StockReserved> kafkaTemplate;

    StockReservedKafkaPublisher(
            KafkaTemplate<String, StockReserved> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, StockReserved>> publish(
            StockReserved event) {

        String topic = "inventory.stock-reserved.v1";
        String key = event.reservationId().toString();

        return kafkaTemplate.send(topic, key, event);
    }
}
~~~

Ví dụ này dùng API Spring Kafka 3.x, trong đó thao tác send trả về **CompletableFuture**. Serializer cho value và key cần được cấu hình để Kafka producer có thể chuyển object và key thành byte. Nếu dùng phiên bản Spring Kafka khác, kiểu trả về và cấu hình có thể khác.

Lời gọi send có thể trả về trước khi broker xác nhận record đã được ghi. Nếu ứng dụng cần coi publication hoàn tất sau khi Kafka xác nhận, adapter phải theo dõi kết quả bất đồng bộ và truyền lỗi gửi ra đúng luồng xử lý. Không được coi việc đưa record vào hàng đợi nội bộ của producer là bằng chứng broker đã nhận thành công.

Trong ứng dụng dùng externalization do Spring Modulith quản lý, phần integration chịu trách nhiệm nối target logic với producer và xác định thời điểm publication được xem là hoàn tất. Nếu tự viết adapter, hãy đảm bảo kết quả gửi Kafka được phản ánh vào kết quả xử lý listener hoặc cơ chế publication tương ứng. Không đánh dấu listener thành công ngay khi mới khởi tạo lời gọi send nếu lỗi gửi vẫn có thể xảy ra sau đó.

## 6. Cấu hình producer và độ bền khi gửi

Producer có một số cấu hình ảnh hưởng trực tiếp đến độ tin cậy:

| Cấu hình | Vai trò |
|---|---|
| **bootstrap.servers** | Danh sách broker để producer khởi tạo kết nối |
| **key.serializer** | Chuyển key thành byte |
| **value.serializer** | Chuyển payload thành byte |
| **acks** | Mức xác nhận producer yêu cầu từ broker |
| **enable.idempotence** | Hạn chế duplicate do producer retry trong phạm vi semantics Kafka hỗ trợ |
| **retries** | Số lần producer thử lại khi gặp lỗi có thể phục hồi |
| **delivery.timeout.ms** | Giới hạn tổng thời gian chờ gửi và retry |
| **linger.ms** và **batch.size** | Điều chỉnh gom batch và throughput |

Một cấu hình minh họa cho producer ưu tiên độ bền:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

Đây chỉ là ví dụ property cho Spring Boot/Spring Kafka; cần kiểm tra binding và giá trị phù hợp với phiên bản đang sử dụng. **acks=all** yêu cầu xác nhận từ các replica đang nằm trong ISR theo cấu hình broker. Để tăng độ bền, cần phối hợp với replication factor và **min.insync.replicas** ở topic/broker. Nếu cấu hình replica không phù hợp, acks=all một mình không bảo đảm mức độ bền mong muốn.

Producer idempotence giúp kiểm soát duplicate phát sinh từ retry của producer theo cơ chế Kafka. Nó không thay thế idempotency ở consumer, không bảo đảm một side effect trong database chỉ xảy ra một lần và không làm toàn bộ quy trình nghiệp vụ trở thành exactly-once.

## 7. Consumer group và cách nhiều ứng dụng đọc topic

Consumer đọc record từ topic theo partition và lưu offset để biết vị trí đã xử lý. Các consumer có cùng **group.id** thuộc một consumer group. Kafka phân chia partition của topic giữa các consumer trong cùng group.

~~~text
Topic: inventory.stock-reserved.v1
  partition 0 ----> consumer A
  partition 1 ----> consumer B
  partition 2 ----> consumer C

Consumer group: inventory-projection
~~~

Một partition trong cùng consumer group tại một thời điểm chỉ được gán cho một consumer. Nếu có nhiều consumer hơn số partition, một số consumer sẽ không có partition để đọc. Nếu có ít consumer hơn partition, một consumer có thể nhận nhiều partition.

Hai consumer group khác nhau đọc cùng topic độc lập:

~~~text
Kafka topic: inventory.stock-reserved.v1
        |
        +---- group: order-service
        |
        +---- group: analytics-service
        |
        +---- group: audit-service
~~~

Mỗi group có offset riêng. Do đó, một record có thể được nhiều ứng dụng xử lý độc lập. Không dùng chung group ID nếu mục tiêu là mỗi ứng dụng phải nhận toàn bộ event. Dùng chung group ID khi các instance là thành viên của cùng một ứng dụng logic và cần chia tải.

Consumer Spring Kafka có thể được khai báo như sau:

~~~java
@Component
class StockReservedConsumer {

    @KafkaListener(
        topics = "inventory.stock-reserved.v1",
        groupId = "order-service"
    )
    void on(StockReserved event) {
        // Xử lý event cho order-service.
    }
}
~~~

Ví dụ giả định consumer đã được cấu hình JSON deserializer và kiểu payload tương ứng. Với nhiều event type trong cùng topic, consumer cần cơ chế type mapping hoặc envelope rõ ràng thay vì ép mọi payload thành một class.

## 8. Offset, acknowledgment và delivery semantics

Kafka consumer theo dõi offset để biết record tiếp theo cần đọc. Thời điểm commit offset quyết định record có thể được đọc lại sau lỗi hay không.

Nếu commit offset trước khi lưu kết quả nghiệp vụ, process có thể dừng sau commit nhưng trước khi ghi database. Record sẽ không được đọc lại trong lần chạy tiếp theo, khiến side effect bị mất. Nếu ghi database xong nhưng chưa commit offset, record có thể được đọc lại và side effect có thể lặp.

Vì vậy, một consumer cần thiết kế rõ ranh giới giữa xử lý nghiệp vụ và commit offset:

1. Nhận record và xác định event ID.
2. Kiểm tra event đã được xử lý chưa.
3. Ghi nhận event cùng thay đổi nghiệp vụ trong transaction phù hợp.
4. Chỉ xác nhận/commit offset sau khi công việc đã hoàn tất theo chính sách đã chọn.

Trong nhiều hệ thống, consumer chấp nhận **at-least-once delivery** và dùng idempotency để xử lý duplicate an toàn. Kafka có transaction và các chế độ exactly-once cho những luồng Kafka-to-Kafka phù hợp, nhưng không tự động tạo transaction nguyên tử giữa Kafka và một database hoặc API bên ngoài.

Một bảng inbox có thể dùng event ID để chống xử lý trùng:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ghi inbox và thay đổi dữ liệu nghiệp vụ trong cùng database transaction. Nếu insert gặp khóa đã tồn tại, consumer có thể kết luận event đã được xử lý trước đó và kết thúc an toàn. Mỗi consumer logic cần namespace riêng để không chặn các consumer độc lập.

## 9. Event Publication Registry và Kafka delivery

Spring Modulith Event Publication Registry theo dõi việc giao application event tới các listener. Khi registry được cấu hình với persistence phù hợp, ứng dụng có thể truy vấn và phục hồi các publication chưa hoàn tất sau lỗi hoặc restart.

Khi externalization listener gửi event tới Kafka, cần thống nhất điều kiện đánh dấu publication hoàn tất. Đối với một adapter chờ broker acknowledgment, publication chỉ nên được xem là hoàn tất sau khi gửi được xác nhận theo semantics đã chọn. Nếu gửi thất bại, lỗi cần được truyền ra listener để publication còn incomplete và có thể được retry.

Có một cửa sổ lỗi quan trọng: broker có thể đã ghi record nhưng ứng dụng dừng trước khi registry ghi nhận listener hoàn tất. Khi phục hồi, cùng publication có thể được gửi lại. Consumer vì vậy vẫn phải hỗ trợ duplicate bằng event ID hoặc idempotency key. Registry giúp producer phục hồi publication; inbox/idempotency bảo vệ hiệu ứng nghiệp vụ ở consumer. Hai cơ chế bổ sung cho nhau.

Không nhầm Event Publication Registry với Kafka consumer offset. Registry theo dõi publication ở phía ứng dụng producer/listener; offset theo dõi vị trí đọc của consumer group trong Kafka. Chúng thuộc hai ranh giới và có thể tiến triển độc lập.

## 10. Retry, dead-letter topic và replay

Có hai nơi có thể xảy ra retry:

- **Producer/externalization retry:** ứng dụng chưa gửi được record hoặc chưa nhận được xác nhận từ Kafka.
- **Consumer retry:** ứng dụng nhận record nhưng không xử lý được payload hoặc nghiệp vụ.

Producer retry thường xử lý lỗi kết nối, broker tạm thời không sẵn sàng hoặc timeout. Với lỗi kéo dài, cần backoff, giới hạn retry và theo dõi publication incomplete. Không retry quá dày khi cluster đang quá tải.

Consumer retry xử lý lỗi deserialize, dependency hoặc nghiệp vụ. Một chiến lược thường gặp là chuyển record không thể xử lý sau số lần thử nhất định sang **dead-letter topic (DLT)**. DLT nên giữ payload gốc cùng key, headers quan trọng, topic/partition/offset nguồn, thời điểm lỗi và thông tin lỗi đã rút gọn.

~~~text
Main topic
    |
    v
Consumer
    |
    +---- xử lý thành công ----> commit offset
    |
    +---- lỗi tạm thời --------> retry theo policy
    |
    +---- hết retry -----------> dead-letter topic
                                      |
                                      v
                                Điều tra / replay
~~~

Không đưa mọi lỗi vào DLT ngay lập tức. Lỗi tạm thời có thể được retry; lỗi dữ liệu không hợp lệ có thể cần quarantine và can thiệp. Nếu thứ tự theo key là yêu cầu nghiệp vụ, việc retry một record lâu trong khi tiếp tục xử lý record sau có thể làm thay đổi thứ tự quan sát. Chọn blocking retry, retry topic hay DLT dựa trên yêu cầu ordering và khả năng xử lý của consumer.

Replay từ DLT cần quy trình có kiểm soát. Giữ event ID ban đầu, ghi nhận lý do replay và dùng idempotency ở consumer. Không sửa payload trực tiếp trong DLT mà không lưu dấu vết; nếu cần hiệu chỉnh dữ liệu, hãy tạo một event nghiệp vụ mới hoặc bản ghi replay có audit rõ ràng.

## 11. Schema, serialization và versioning

Kafka lưu byte trong record value. Producer và consumer phải thống nhất cách diễn giải byte đó. Một số lựa chọn thường gặp:

| Định dạng | Đặc điểm |
|---|---|
| JSON | Dễ đọc và thuận tiện tích hợp; cần quy ước type, version, date/time và decimal |
| Avro | Schema rõ và có hệ sinh thái schema registry phổ biến |
| Protobuf | Định nghĩa message bằng schema, hỗ trợ tiến hóa trường theo quy tắc riêng |
| JSON Schema | Mô tả cấu trúc JSON và có thể dùng để validate payload |

Nếu dùng JSON, cần xác định cách biểu diễn **Instant**, **BigDecimal**, enum, null và trường tùy chọn. Không để producer gửi timestamp theo locale hoặc tiền tệ dưới dạng double mà không có contract. Nếu dùng schema registry, quản lý compatibility mode và quy trình đăng ký schema trước khi producer phát payload mới.

Một thay đổi tương thích ngược thường có thể thêm trường tùy chọn với default phù hợp. Thay đổi kiểu trường, ý nghĩa trường, đơn vị thời gian hoặc scale tiền tệ có thể phá consumer cũ. Khi thay đổi không tương thích, version hóa event contract hoặc topic, triển khai consumer mới trước và chuyển producer theo kế hoạch.

## 12. Topic lifecycle, retention và compaction

Topic không chỉ là tên để gửi message. Cấu hình topic quyết định dữ liệu được lưu bao lâu và cách broker quản lý log:

- **Partitions:** mức song song tối đa của consumer group và phân bố tải.
- **Replication factor:** số bản sao của partition.
- **min.insync.replicas:** số replica tối thiểu cần sẵn sàng cho một số mức acknowledgment.
- **Retention:** thời gian hoặc dung lượng dữ liệu được giữ trước khi Kafka xóa theo policy.
- **Cleanup policy:** xóa theo retention hoặc compact theo key.

Với cleanup policy **delete**, record cũ được xóa theo retention time/size. Với **compact**, Kafka giữ lại giá trị mới nhất theo key theo cơ chế compaction; compact không tương đương lưu toàn bộ lịch sử event. Chọn policy dựa trên mục đích dữ liệu. Event history cần replay có thể cần retention đủ dài; topic dùng làm changelog trạng thái có thể phù hợp với compaction.

Không nên tăng retention mà không xem xét dung lượng broker, tốc độ phát event và khả năng consumer replay. Khi consumer ngừng hoạt động lâu hơn retention, nó có thể không còn đọc được toàn bộ dữ liệu cũ. SLA phục hồi cần tính đến retention thực tế của topic.

## 13. Bảo mật và quan sát

Producer và consumer cần được cấp quyền tối thiểu theo topic và consumer group. Trong môi trường production, cấu hình TLS, xác thực và ACL theo cơ chế của Kafka cluster. Không ghi credential hoặc secret vào source code, event payload hay log.

Nên theo dõi các chỉ số:

| Chỉ số | Điều cần phát hiện |
|---|---|
| Producer send failures | Lỗi gửi tới broker |
| Producer request latency | Broker phản hồi chậm |
| Record send rate | Lưu lượng event theo topic |
| Consumer lag | Consumer đang chậm so với record mới |
| Rebalance count | Consumer group thường xuyên thay đổi phân công |
| Incomplete publications | Event phía ứng dụng chưa externalize hoàn tất |
| DLT rate | Số record cần can thiệp |
| Oldest unprocessed record | Tuổi công việc chưa xử lý |

Log nên có event ID, logical target, topic, key, partition, offset, consumer group và correlation ID khi có. Không ghi toàn bộ payload nhạy cảm. Với một đợt replay hoặc migration, thêm change ID để truy vấn toàn bộ log liên quan.

## 14. Kiểm thử đường đi event tới Kafka

Một bộ kiểm thử tích hợp nên xác minh đường đi từ event đến consumer, không chỉ kiểm tra một method gửi message:

1. Publish application event và xác nhận event được externalize theo target đã chọn.
2. Xác nhận target được ánh xạ tới đúng topic vật lý.
3. Kiểm tra key, payload, timestamp và headers của Kafka record.
4. Xác nhận consumer group nhận được record và deserialize đúng kiểu.
5. Gửi hai event cùng aggregate key và xác minh ordering trong cùng partition theo thiết kế.
6. Mô phỏng lỗi producer để xác nhận publication chưa hoàn tất có thể được phục hồi.
7. Mô phỏng consumer xử lý xong nhưng chưa commit offset để xác nhận duplicate được idempotent xử lý.
8. Kiểm tra retry và DLT với payload lỗi hoặc dependency tạm thời không sẵn sàng.
9. Kiểm tra consumer group độc lập có thể đọc cùng topic mà không chia mất record của nhau.
10. Kiểm tra retention, replay và quyền truy cập trong môi trường gần production.

Có thể dùng broker test hoặc Testcontainers cho kiểm thử tích hợp. Với kiểm thử đơn vị, mock transport chỉ xác nhận logic mapping; nó không chứng minh serializer, ACL, partition assignment hoặc broker acknowledgment hoạt động như mong muốn.

## 15. Các quyết định cần chốt trước khi production

Trước khi đưa event lên Kafka, hãy trả lời:

- Event nào được externalize và module nào sở hữu contract?
- Logical target được ánh xạ tới topic vật lý ở đâu?
- Một topic chứa một event type hay nhiều loại event?
- Key nào giữ ordering theo aggregate?
- Số partition, replication factor và retention dựa trên lưu lượng/SLA nào?
- Producer chờ acknowledgment tới mức nào và xử lý timeout ra sao?
- Consumer group nào cần nhận toàn bộ record độc lập?
- Consumer commit offset sau khi nào và idempotency được lưu ở đâu?
- Retry, DLT và replay có owner cùng runbook chưa?
- Serializer, schema compatibility, ACL, TLS và dashboard đã sẵn sàng chưa?

Khi phân biệt rõ application event, logical target, Kafka topic và consumer group, ứng dụng có thể đưa sự kiện ra ngoài mà vẫn giữ ranh giới module. Kết hợp key theo aggregate, contract có version, xác nhận gửi, publication tracking, consumer idempotency và giám sát giúp luồng event qua Kafka có thể mở rộng và phục hồi khi gặp sự cố.

