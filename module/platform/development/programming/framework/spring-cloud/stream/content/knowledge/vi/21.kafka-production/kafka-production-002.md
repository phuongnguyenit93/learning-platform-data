# Chọn topic và partition cho từng thông điệp

Một Kafka producer cần xác định hai đích cho mỗi record: topic lưu trữ và partition bên trong topic đó. Topic thường biểu thị loại sự kiện hoặc miền dữ liệu, còn partition quyết định record nằm ở luồng con nào, được consumer group phân phối cho instance nào và thứ tự nào được giữ. Spring Cloud Stream Kafka Binder cho phép ứng dụng gửi qua output binding, chọn topic theo từng message và chọn partition thông qua record key hoặc cơ chế partitioning của framework.

Không nên gộp mọi khái niệm này thành một thuộc tính duy nhất. Chọn topic là quyết định định tuyến đến destination; chọn partition là quyết định phân phối record trong topic đã chọn. Record key thường giúp Kafka tự chọn partition ổn định cho cùng một khóa. Nếu thật sự cần ép record vào một partition có số cụ thể, đó là lựa chọn ở API Kafka producer cấp thấp và cần cân nhắc việc bỏ qua một phần abstraction của binder.

## 1. Phân biệt topic, partition và record key

Một topic có thể có nhiều partition. Mỗi partition là một log có thứ tự riêng; Kafka không tạo thứ tự toàn cục giữa các partition.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Topic | Nhóm record cùng loại hoặc cùng hợp đồng dữ liệu | orders.created |
| Partition | Một log con trong topic | Partition 0, 1, 2 |
| Record key | Khóa dùng để định tuyến và thường dùng để gom record cùng thực thể | ORD-1001 |
| Offset | Vị trí record trong một partition | Offset 125 |

Ví dụ một topic orders.events có 6 partition. Các sự kiện của cùng đơn hàng có thể dùng orderId làm key để Kafka đưa chúng vào cùng partition. Consumer group có thể xử lý các partition khác nhau song song, trong khi thứ tự trong một partition được duy trì theo thứ tự ghi.

Record key không phải topic name và cũng không phải partition number. Key giúp partitioner chọn partition. Partition number là kết quả định tuyến, trừ khi ứng dụng chủ động chỉ định partition bằng API Kafka cấp thấp.

## 2. Chọn topic cố định bằng output binding

Nếu một output binding luôn gửi một loại sự kiện vào cùng topic, khai báo destination trong binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
~~~

Gửi POJO hoặc Message qua binding:

~~~java
@Service
public class OrderPublisher {
    private final StreamBridge streamBridge;

    public OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
~~~

Tên orders-out-0 là output binding trong ứng dụng; orders.created là topic Kafka đích. Cách này dễ quản lý vì topic, content type, binder và producer settings đều được khai báo tập trung.

Nếu ứng dụng có nhiều loại event với chính sách khác nhau, có thể khai báo nhiều output binding, mỗi binding trỏ đến một topic. Cách này phù hợp khi topic đã biết trước và mỗi luồng cần cấu hình riêng về schema, retry, partition count hoặc bảo mật.

## 3. Chọn topic theo từng message bằng KafkaHeaders.TOPIC

Kafka Binder có thuộc tính useTopicHeader. Khi bật thuộc tính này, giá trị header KafkaHeaders.TOPIC của outbound message sẽ ghi đè destination mặc định của binding. Nếu message không có header này, binder dùng destination đã khai báo trong binding.

Cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        domain-events-out-0:
          destination: events.default
          content-type: application/json
      kafka:
        bindings:
          domain-events-out-0:
            producer:
              use-topic-header: true
~~~

Producer chọn topic từ dữ liệu đã được kiểm tra:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public boolean publish(String targetTopic, DomainEvent event) {
    Message<DomainEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, targetTopic)
        .build();

    return streamBridge.send("domain-events-out-0", message);
}
~~~

Khi useTopicHeader=true, ví dụ trên có thể gửi từng message đến các topic khác nhau qua cùng binding. Nếu useTopicHeader không bật, header topic không được dùng để ghi đè destination và binding tiếp tục gửi đến events.default.

Topic header phải là tên topic Kafka hợp lệ. Hãy kiểm tra giá trị trước khi gửi, ví dụ chỉ cho phép orders.created, orders.cancelled và orders.shipped. Không nhận tên topic tùy ý từ HTTP request hoặc message bên ngoài rồi chuyển thẳng vào KafkaHeaders.TOPIC; điều đó có thể khiến ứng dụng ghi vào topic ngoài phạm vi được cấp quyền.

Topic đích cần tồn tại hoặc được provision theo chính sách cluster. Không giả định việc bật useTopicHeader sẽ tự động tạo mọi topic được chọn động. Hãy kiểm tra autoCreateTopics, quyền AdminClient, cấu hình replication/partition và chính sách quản trị của môi trường.

## 4. Chọn topic động bằng StreamBridge destination

StreamBridge cũng có thể gửi đến một destination name thay vì một binding đã khai báo:

~~~java
streamBridge.send("orders.created", event);
~~~

Khi chưa có output binding tên orders.created, StreamBridge có thể tạo dynamic output binding đến destination đó theo cơ chế của Spring Cloud Stream. Đây là cách khác với KafkaHeaders.TOPIC:

| Cách | Giá trị truyền vào | Cơ chế |
|---|---|---|
| Binding tĩnh | orders-out-0 | Binding đã khai báo, destination cấu hình sẵn |
| KafkaHeaders.TOPIC | Header trên Message | Ghi đè topic cho message qua binding có useTopicHeader |
| StreamBridge dynamic destination | Tên destination trong send | Framework tạo và cache output binding động |

Chọn binding tĩnh nếu tập topic cố định. Dùng topic header nếu muốn giữ một binding và thay đổi topic cho từng message. Dùng dynamic destination nếu ứng dụng cần tạo binding theo destination runtime và chấp nhận quản lý cache, provisioning cùng chính sách bảo mật cho các destination đó.

Không để dữ liệu bên ngoài tùy ý tạo vô hạn tên destination. Giới hạn bằng allowlist hoặc quy tắc tên, kiểm soát quyền publish và theo dõi số lượng dynamic binding được tạo.

## 5. Chọn partition bằng record key của Kafka

Kafka hỗ trợ partitioning native. Với Kafka Binder, cách thông thường để gom record theo khóa là đặt Kafka record key. Kafka producer partitioner sẽ chọn partition dựa trên key và số partition thực tế của topic.

Có thể đặt key trực tiếp trên message bằng KafkaHeaders.KEY:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .build();

streamBridge.send("orders-out-0", message);
~~~

Hoặc cấu hình messageKeyExpression cho output binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

Biểu thức được đánh giá trên outbound message và dùng để đặt key của Kafka record. Dùng KafkaHeaders.KEY khi code cần chỉ định key trực tiếp trên từng message; dùng message-key-expression khi mọi message của binding có cùng quy tắc trích key.

Nếu dùng key là orderId, các record của cùng đơn hàng sẽ được gom theo key. Những đơn hàng khác nhau có thể đi đến các partition khác nhau. Kafka chỉ bảo đảm thứ tự trong một partition, vì vậy key ổn định giúp giữ thứ tự các sự kiện của cùng aggregate trong luồng ghi.

Nếu không có key, Kafka dùng partitioner mặc định của client để phân phối record. Không nên dựa vào hành vi mặc định không có key để giữ thứ tự theo khách hàng hoặc đơn hàng.

## 6. Phân biệt Kafka record key với partitionKeyExpression

Spring Cloud Stream có abstraction partitioning chung cho nhiều middleware. Cấu hình producer có thể trích một partition key rồi tự tính partition:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

partition-key-expression lấy orderId từ payload. partition-count phải lớn hơn 1 để bật partitioning. Mặc định, Spring Cloud Stream chọn partition theo công thức:

~~~text
partition = key.hashCode() % partitionCount
~~~

Có thể tùy chỉnh lựa chọn partition bằng partition-selector-expression hoặc bean PartitionSelectorStrategy. partition-key-expression và partition-key-extractor-name là hai cách trích khóa thay thế nhau; không cấu hình đồng thời cả hai cho cùng binding.

Với Kafka, cần hiểu sự khác biệt:

- Kafka native partitioning dùng record key và partitioner của Kafka producer.
- Spring Cloud Stream partitioning abstraction dùng partition key và thuật toán chọn partition của framework.
- Hai thuật toán có thể cho kết quả khác nhau với cùng giá trị khóa.
- partition-key-expression không nên được hiểu mặc định là Kafka record key.

Tài liệu Kafka Binder khuyến nghị dùng partitioning native của Kafka trong hầu hết trường hợp. Binder partitioning hữu ích khi cần dùng thuật toán khóa tùy chỉnh hoặc muốn cùng một quy tắc partitioning của Spring Cloud Stream trên nhiều middleware. Nếu consumer hoặc hệ thống khác cần đọc Kafka record key, hãy đặt KafkaHeaders.KEY hoặc cấu hình message-key-expression.

## 7. Chọn partition bằng selector tùy chỉnh

Khi dùng partitioning abstraction, có thể thay đổi thuật toán tính partition:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-selector-expression: key.hashCode() % 12
            partition-count: 12
~~~

partition-selector-expression được đánh giá với biến key đã trích ra. Kết quả phải nằm trong khoảng partition hợp lệ từ 0 đến partitionCount - 1. Nếu cần logic phức tạp, đăng ký bean triển khai PartitionSelectorStrategy và chỉ định partition-selector-name.

Chỉ tùy chỉnh selector khi có yêu cầu rõ ràng, chẳng hạn phải tương thích với một producer khác hoặc cần phân phối theo quy tắc nghiệp vụ đã được công bố. Mọi producer gửi vào cùng topic phải thống nhất thuật toán nếu muốn cùng một key luôn đi đến cùng partition.

Với producer viết bằng nhiều ngôn ngữ, không giả định hashCode của Java tương đương hash của ngôn ngữ khác. Hãy chuẩn hóa thuật toán hash và kiểm thử cùng bộ key mẫu trên tất cả producer.

## 8. partitionCount là gợi ý cho Kafka Binder

Trong Spring Cloud Stream, partition-count là số partition mục tiêu của partitioning abstraction. Với Kafka Binder, giá trị này còn là gợi ý khi provision topic:

- Nếu topic chưa tồn tại và binder được phép tạo topic, partition count được dùng cùng minPartitionCount để xác định số partition provision.
- Nếu topic đã tồn tại với số partition lớn hơn cấu hình, binder dùng số partition thực tế lớn hơn.
- Nếu topic có ít partition hơn cấu hình và autoAddPartitions bị tắt, binder có thể không khởi động được.
- Nếu autoAddPartitions được bật, binder có thể yêu cầu tăng số partition theo cấu hình.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            partition-count: 12
      kafka:
        binder:
          auto-create-topics: true
          auto-add-partitions: false
~~~

Đây là ví dụ minh họa provisioning; trong production, việc tạo hoặc tăng partition nên tuân theo chính sách của Kafka administrator. Không nhầm partition-count với replication-factor: partition count quyết định số log con, còn replication factor quyết định số bản sao của mỗi partition.

## 9. Thay đổi partition count và ảnh hưởng đến cùng một key

Với thuật toán hash modulo, partition của key phụ thuộc số partition. Khi tăng partition count, một key có thể được ánh xạ sang partition khác. Các record cũ vẫn ở partition cũ, còn record mới của cùng key có thể sang partition mới.

Điều này có thể phá vỡ kỳ vọng về thứ tự xuyên suốt lịch sử của aggregate. Kafka giữ thứ tự trong từng partition, nhưng không tự sắp xếp lại record cũ và mới của cùng key nếu chúng nằm ở hai partition khác nhau.

Trước khi tăng partition count:

- Xác định nghiệp vụ có yêu cầu thứ tự tuyệt đối theo key hay không.
- Kiểm tra consumer state store, projection và cách replay.
- Xác định thời điểm dừng hoặc drain producer nếu cần.
- Lập kế hoạch migration hoặc versioned topic nếu thay đổi partition layout ảnh hưởng đến hợp đồng.
- Kiểm thử key mapping trước và sau thay đổi.

Không tăng partition count tùy tiện chỉ để tăng concurrency nếu thứ tự theo key là yêu cầu quan trọng.

## 10. Khi thật sự cần chỉ định partition number

Key-based routing là lựa chọn thông thường: producer cung cấp key, Kafka partitioner chọn partition. Đôi khi ứng dụng cần gửi một record đến một partition số cụ thể, chẳng hạn trong công cụ migration, kiểm thử hoặc một quy trình có quy tắc phân vùng được quản lý thủ công.

Spring Cloud Stream Kafka Binder tập trung vào key-based routing và partitioning abstraction. Nếu cần ép một partition number chính xác, dùng API producer cấp thấp của Spring Kafka với ProducerRecord:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;

public void publishToExactPartition(
        KafkaTemplate<String, OrderCreated> kafkaTemplate,
        OrderCreated event,
        int partition) {

    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>(
            "orders.events",
            partition,
            event.orderId(),
            event
        );

    kafkaTemplate.send(record);
}
~~~

ProducerRecord nhận topic, partition number, key và value. Partition phải tồn tại trong topic; nếu chỉ định partition không hợp lệ, broker/client sẽ báo lỗi. ProducerFactory phải có key/value serializer tương thích với kiểu dữ liệu.

Đây là API Spring Kafka trực tiếp, không phải cơ chế định tuyến partition tiêu chuẩn của Spring Cloud Stream binder. Ứng dụng phải quản lý KafkaTemplate/ProducerFactory, lỗi gửi, transaction và quan sát kết quả tương ứng. Không thêm header tên partition vào message của binder rồi giả định binder sẽ coi đó là chỉ thị chọn partition nếu chưa xác minh rõ hợp đồng của phiên bản binder đang dùng.

## 11. Kết hợp chọn topic và key trên từng message

Một message có thể mang cả topic header và record key. Ví dụ dịch vụ gửi nhiều loại sự kiện đơn hàng vào các topic tương ứng, đồng thời dùng orderId làm key:

~~~java
public boolean publishEvent(
        String eventType,
        OrderEvent event) {

    String topic = switch (eventType) {
        case "ORDER_CREATED" -> "orders.created";
        case "ORDER_CANCELLED" -> "orders.cancelled";
        case "ORDER_SHIPPED" -> "orders.shipped";
        default -> throw new IllegalArgumentException("Unsupported event type");
    };

    Message<OrderEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, topic)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();

    return streamBridge.send("domain-events-out-0", message);
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        domain-events-out-0:
          destination: events.default
          content-type: application/json
      kafka:
        bindings:
          domain-events-out-0:
            producer:
              use-topic-header: true
~~~

Ví dụ dùng allowlist event type để chọn topic. Một event ORDER_CREATED đi đến orders.created; ORDER_CANCELLED đi đến orders.cancelled. Trong mỗi topic, orderId là Kafka record key để các sự kiện của cùng đơn hàng được định tuyến ổn định theo partitioner của Kafka.

Các topic đích cần có schema tương thích với producer và consumer tương ứng. Nếu topic có schema khác nhau, không gom vào một binding dùng cùng content type/serializer mà không có chiến lược conversion rõ ràng.

## 12. Xác nhận topic và partition thực tế sau khi gửi

Không nên chỉ suy luận partition từ cấu hình. Có thể yêu cầu Kafka Binder gửi metadata của record thành công đến một channel:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-out-0:
            producer:
              record-metadata-channel: sentMetadata
~~~

Message được gửi đến channel sentMetadata có header KafkaHeaders.RECORD_METADATA. Giá trị là RecordMetadata do Kafka client cung cấp, chứa topic, partition và offset mà record thực sự được ghi:

~~~java
RecordMetadata metadata = message.getHeaders()
    .get(KafkaHeaders.RECORD_METADATA, RecordMetadata.class);

log.info("Published to topic={}, partition={}, offset={}",
    metadata.topic(), metadata.partition(), metadata.offset());
~~~

Hãy đăng ký MessageChannel có tên sentMetadata trong application context và xử lý metadata trên channel đó. Metadata thành công giúp kiểm chứng định tuyến thực tế; lỗi gửi đi theo producer error channel nếu đã cấu hình. Không ghi toàn bộ payload nhạy cảm vào log khi quan sát kết quả gửi.

## 13. Những lỗi định tuyến thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Message luôn vào topic mặc định | useTopicHeader chưa bật hoặc message không có KafkaHeaders.TOPIC | Kiểm tra producer binding property và header trước khi gửi |
| Topic header không hợp lệ | Tên topic sai hoặc producer không có quyền ghi | Kiểm tra allowlist, topic tồn tại và Kafka ACL |
| Các record cùng orderId nằm ở nhiều partition | Key không ổn định, key serializer không nhất quán hoặc partition count/algorithm thay đổi | Kiểm tra record key, serializer và metadata partition |
| Key không xuất hiện ở consumer | Header mapper tùy chỉnh bỏ qua KafkaHeaders.KEY hoặc producer chưa đặt key | Kiểm tra KafkaHeaderMapper và record trên broker |
| Binder partitioning và producer khác chọn partition khác nhau | Dùng hai thuật toán hash/partitioner khác nhau | Thống nhất một thuật toán hoặc dùng Kafka native key routing |
| Binder không khởi động vì topic có ít partition | partitionCount lớn hơn topic hiện có trong khi autoAddPartitions tắt | Kiểm tra số partition thực tế và provisioning policy |
| Consumer xử lý sai thứ tự nghiệp vụ | Cùng aggregate không dùng cùng key hoặc consumer xử lý song song không kiểm soát | Kiểm tra key, partition và concurrency/processing order |

## 14. Kiểm thử lựa chọn topic và partition

Một bộ kiểm thử tốt nên xác nhận cả định tuyến dự kiến và metadata do broker trả về:

- Gửi message không có KafkaHeaders.TOPIC và xác nhận binder dùng destination mặc định.
- Bật useTopicHeader, gửi hai message có topic header khác nhau và xác nhận chúng đến đúng topic.
- Gửi topic name ngoài allowlist và xác nhận producer từ chối trước khi publish.
- Gửi nhiều message cùng orderId và xác nhận chúng dùng cùng record key và partition.
- Gửi message với orderId khác nhau và quan sát phân bố partition.
- Kiểm tra messageKeyExpression và KafkaHeaders.KEY cho cùng kết quả key.
- So sánh partition do Kafka native key routing và Spring Cloud Stream partitioning abstraction chọn.
- Thay đổi partition count trong môi trường test và xác nhận key có thể được ánh xạ sang partition khác.
- Nếu dùng ProducerRecord để chỉ định partition, kiểm tra partition tồn tại và lỗi khi chỉ định partition ngoài phạm vi.
- Đọc RecordMetadata để xác nhận topic, partition và offset thực tế.

Test Binder hữu ích cho logic function và message headers, nhưng không mô phỏng đầy đủ partitioner, metadata, provisioning, serializer và ACL của Kafka. Cần integration test với Kafka thật hoặc môi trường broker tương đương trước khi phát hành.

## 15. Checklist trước khi triển khai

- [ ] Đã chọn binding tĩnh, KafkaHeaders.TOPIC hoặc dynamic destination theo nhu cầu.
- [ ] Nếu dùng KafkaHeaders.TOPIC, đã bật use-topic-header trên đúng output binding.
- [ ] Topic đích được giới hạn bằng allowlist và có ACL publish phù hợp.
- [ ] Record key ổn định, có serializer tương thích và phản ánh khóa nghiệp vụ.
- [ ] Đã phân biệt Kafka native partitioning với partitionKeyExpression của Spring Cloud Stream.
- [ ] Nếu dùng partitioning abstraction, partition-count lớn hơn 1 và selector nằm trong phạm vi hợp lệ.
- [ ] Đã kiểm tra số partition thực tế và chính sách autoAddPartitions.
- [ ] Đã đánh giá tác động của việc thay đổi partition count đến thứ tự theo key.
- [ ] Chỉ dùng partition number tường minh khi thực sự cần và hiểu rõ việc dùng Kafka producer API trực tiếp.
- [ ] Đã kiểm tra topic, partition và offset qua RecordMetadata hoặc công cụ Kafka.
- [ ] Đã kiểm thử định tuyến với Kafka thật và giám sát lỗi producer.

Chọn topic xác định nơi record được lưu; chọn key hoặc partition xác định record được phân phối như thế nào trong topic đó. Với Spring Cloud Stream Kafka Binder, dùng KafkaHeaders.TOPIC cùng useTopicHeader để ghi đè topic theo từng message, và dùng KafkaHeaders.KEY hoặc messageKeyExpression để Kafka chọn partition ổn định theo khóa. Chỉ dùng partitioning abstraction khi cần thuật toán của Spring Cloud Stream; nếu bắt buộc chỉ định partition number, hãy dùng API Kafka producer trực tiếp và quản lý rõ các trách nhiệm đi kèm.

## Tài liệu tham khảo

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Partitioning](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
