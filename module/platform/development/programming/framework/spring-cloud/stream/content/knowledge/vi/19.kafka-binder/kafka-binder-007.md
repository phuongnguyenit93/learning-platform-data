# Ánh xạ KafkaHeaders và metadata topic, partition, offset

Khi Spring Cloud Stream nhận một bản ghi từ Kafka, ứng dụng thường chỉ cần payload để xử lý nghiệp vụ. Tuy nhiên, nhiều tác vụ vận hành cần biết bản ghi đến từ topic nào, partition nào và có offset bao nhiêu: ghi log để truy vết, phát hiện xử lý lặp, điều tra lỗi, đối chiếu tiến độ consumer hoặc chuyển tiếp sự kiện mà vẫn giữ message key.

Kafka binder tích hợp Spring Kafka để chuyển metadata của Kafka record thành các header trong Spring Message. Lớp **KafkaHeaders** cung cấp các hằng số giúp truy cập những header này mà không phải ghi chuỗi tên thủ công. Ở chiều gửi, một số header đặc biệt còn cho phép chỉ định message key, topic hoặc nhận metadata sau khi broker xác nhận gửi thành công.

Bài học này tập trung vào cách đọc và sử dụng metadata của topic, partition, offset; phân biệt header của Spring Message với Kafka record header; và cách theo dõi metadata của bản ghi đầu ra.

## 1. Kafka record và Spring Message

Một Kafka record có các thành phần chính:

- **Topic:** luồng dữ liệu mà bản ghi được ghi vào.
- **Partition:** phân vùng cụ thể bên trong topic.
- **Offset:** vị trí của bản ghi trong partition đó.
- **Key:** khóa tùy chọn dùng để định tuyến và giữ thứ tự theo partition.
- **Value:** payload của bản ghi.
- **Timestamp:** thời điểm gắn với bản ghi theo timestamp type của Kafka.
- **Headers:** tập metadata dạng key/value do producer gửi kèm record.

Spring Cloud Stream chuyển record thành Spring Message để function xử lý. Spring Message gồm payload và Spring Messaging headers. Khi nhận record, Kafka binder/Spring Kafka bổ sung các header đặc biệt để biểu diễn metadata của record, chẳng hạn topic nhận, partition nhận và offset.

~~~mermaid
flowchart LR
    A[Kafka record] --> B[Kafka binder và Spring Kafka]
    B --> C[Spring Message]
    C --> D[Function hoặc Consumer]
    C --> E[Payload]
    C --> F[Message headers]
    F --> G[Topic]
    F --> H[Partition]
    F --> I[Offset]
    F --> J[Timestamp và key]
~~~

Điểm quan trọng: payload là dữ liệu nghiệp vụ; metadata nằm ở headers. Ví dụ, OrderCreated có thể chứa orderId và total, còn topic/partition/offset mô tả vị trí vận chuyển của bản ghi trong Kafka. Không cần thêm các trường này vào JSON nghiệp vụ chỉ để ghi log hoặc kiểm tra vị trí record.

## 2. KafkaHeaders là gì?

**org.springframework.kafka.support.KafkaHeaders** là lớp chứa các hằng số header dành cho tích hợp Spring Kafka. Kafka binder sử dụng những header này khi ánh xạ giữa Spring Message và Kafka record.

Một số header thường dùng:

| Hằng số | Hướng | Ý nghĩa |
|---|---|---|
| **KafkaHeaders.RECEIVED_TOPIC** | Inbound | Topic mà record được nhận từ đó. |
| **KafkaHeaders.RECEIVED_PARTITION** | Inbound | Partition chứa record nhận được. |
| **KafkaHeaders.OFFSET** | Inbound | Offset của record nhận được trong partition. |
| **KafkaHeaders.RECEIVED_TIMESTAMP** | Inbound | Timestamp của record nhận được. |
| **KafkaHeaders.RECEIVED_KEY** | Inbound | Key của record nhận được, nếu có. |
| **KafkaHeaders.TOPIC** | Outbound | Topic đích khi binder được cấu hình cho phép dùng topic header. |
| **KafkaHeaders.MESSAGE_KEY** | Outbound | Key được gửi cùng record. |
| **KafkaHeaders.PARTITION** | Outbound | Partition đích trong các luồng gửi hỗ trợ chỉ định partition. |
| **KafkaHeaders.RECORD_METADATA** | Kết quả gửi | RecordMetadata do Kafka client trả về sau khi gửi thành công. |
| **KafkaHeaders.ACKNOWLEDGMENT** | Inbound | Đối tượng Acknowledgment khi binding dùng chế độ xác nhận thủ công. |

Các header inbound như RECEIVED_TOPIC và RECEIVED_PARTITION được tạo từ metadata của record; chúng không phải những trường mà producer nghiệp vụ nhất thiết phải tự thêm vào Kafka record headers.

### Lưu ý về tên hằng số theo phiên bản

Tên hằng số của Spring Kafka đã thay đổi ở một số phiên bản:

- Từ Spring Kafka 2.9, **RECEIVED_PARTITION** thay cho tên cũ **RECEIVED_PARTITION_ID**; tên cũ được đánh dấu deprecated ở các phiên bản tương ứng.
- Từ Spring Kafka 2.9, **RECEIVED_KEY** thay cho **RECEIVED_MESSAGE_KEY**; tên cũ được đánh dấu deprecated.
- Ở các phiên bản cũ hơn, mã nguồn có thể cần dùng tên hằng số cũ.

Hãy dùng hằng số có trong dependency Spring Kafka mà Spring Cloud Stream BOM của dự án quản lý. Không tự viết chuỗi nội bộ như kafka_receivedPartition hoặc kafka_receivedTopic nếu có thể dùng hằng số, vì tên và alias có thể khác giữa các phiên bản.

## 3. Đọc topic, partition và offset từ Consumer<Message<T>>

Với mô hình hàm, một Consumer có thể nhận toàn bộ Message để truy cập payload lẫn headers:

~~~java
import java.util.function.Consumer;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderMetadataFunctions {

    @Bean
    public Consumer<Message<OrderCreated>> inspectOrderRecord() {
        return message -> {
            String topic = message.getHeaders()
                    .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
            Integer partition = message.getHeaders()
                    .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
            Long offset = message.getHeaders()
                    .get(KafkaHeaders.OFFSET, Long.class);

            OrderCreated event = message.getPayload();
            log.info(
                    "Nhận orderId={}, topic={}, partition={}, offset={}",
                    event.orderId(), topic, partition, offset
            );
        };
    }
}
~~~

Trong ví dụ, function đọc ba giá trị:

- **topic** là tên topic nguồn.
- **partition** là chỉ số partition chứa record.
- **offset** là vị trí record trong partition đó.

Không nên ép kiểu mọi header thành String. Offset là số nguyên 64 bit và partition là số nguyên; hãy đọc đúng kiểu mà Spring Kafka cung cấp. Nếu cần tương thích với nhiều phiên bản hoặc header mapper tùy chỉnh, hãy kiểm tra kiểu thực tế trong integration test.

Một ví dụ cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: inspectOrderRecord
    stream:
      bindings:
        inspectOrderRecord-in-0:
          destination: orders
          group: order-audit
          content-type: application/json
~~~

Với binding trên, consumer nhận dữ liệu từ topic orders. Các giá trị metadata được lấy từ record thực tế do Kafka giao, không phải từ tên binding. Tên binding là inspectOrderRecord-in-0; tên topic là orders. Hai tên này có mục đích khác nhau.

### Trường hợp key có thể null

Kafka cho phép record không có key. Khi key là null, header key nhận có thể không xuất hiện trong Spring Message. Vì vậy, đọc key như một header tùy chọn:

~~~java
Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);
if (key == null) {
    log.debug("Record không có key");
}
~~~

Đừng dùng key null như một giá trị định danh mặc định cho mọi sự kiện. Nếu cần idempotency hoặc phân vùng theo nghiệp vụ, producer phải phát một key có ý nghĩa và consumer phải kiểm tra trường hợp key thiếu.

## 4. Ý nghĩa của topic, partition và offset

Ba trường này thường được ghi cùng nhau để định danh vị trí của một record:

~~~text
topic = orders
partition = 2
offset = 18427
~~~

Có thể hiểu đây là record ở vị trí offset 18427 của partition 2 trong topic orders.

### Topic

Topic là tên luồng dữ liệu logic. Một ứng dụng có thể đọc từ nhiều topic thông qua nhiều input binding hoặc một binding được cấu hình pattern. Metadata topic cho biết record thực sự đến từ topic nào, hữu ích khi một binding đọc nhiều topic hoặc dùng pattern.

### Partition

Partition là đơn vị lưu trữ và song song hóa trong topic. Chỉ số partition thường bắt đầu từ 0. Kafka bảo đảm thứ tự record trong một partition, không bảo đảm thứ tự tổng thể giữa nhiều partition.

Partition giúp xác định:

- Consumer nào trong group đang được gán xử lý record.
- Phạm vi thứ tự mà Kafka bảo đảm.
- Nơi cần kiểm tra khi một partition bị lag hoặc mất leader.
- Vị trí của record khi điều tra hoặc phát lại dữ liệu.

### Offset

Offset là vị trí của record trong một partition. Nó tăng theo quá trình ghi dữ liệu vào partition, nhưng không phải số thứ tự toàn cục của topic.

Các điểm cần nhớ:

- Offset chỉ có ý nghĩa khi đi cùng topic và partition.
- Hai partition khác nhau có thể cùng có offset 100.
- Offset không phải timestamp và không cho biết thời gian xử lý.
- Offset không phải số lượng record đã đọc.
- Topic compaction, giao dịch và các cơ chế nội bộ có thể khiến dãy offset quan sát được có khoảng trống.

Vì vậy, khóa định danh vị trí nên là bộ ba **topic + partition + offset**. Không dùng riêng offset làm primary key toàn hệ thống.

### Offset của record và committed offset

**KafkaHeaders.OFFSET** biểu diễn offset của record đang được xử lý. Trong khi đó, committed offset của consumer group thường biểu diễn vị trí tiếp theo mà group sẽ đọc trong partition. Vì thế, nếu consumer đã xử lý record offset 25 và commit tiến độ tiếp theo, committed offset có thể là 26.

Đọc header offset không đồng nghĩa đã commit offset. Việc commit phụ thuộc ack mode, transaction, cấu hình binder và quá trình xử lý message. Nếu cần điều khiển xác nhận thủ công, hãy dùng cơ chế acknowledgment được Kafka binder hỗ trợ và không tự cập nhật offset chỉ dựa trên giá trị header.

## 5. Ghi log và truy vết theo metadata

Khi ghi log, nên kết hợp event ID của nghiệp vụ với vị trí Kafka:

~~~java
@Bean
public Consumer<Message<OrderCreated>> auditOrders() {
    return message -> {
        var headers = message.getHeaders();

        String topic = headers.get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = headers.get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = headers.get(
                KafkaHeaders.OFFSET, Long.class);

        OrderCreated event = message.getPayload();
        log.info(
                "order event: eventId={}, orderId={}, source={}-{}@{}",
                event.eventId(),
                event.orderId(),
                topic,
                partition,
                offset
        );
    };
}
~~~

Thông tin này hữu ích khi:

- Tìm một record trong Kafka bằng topic, partition và offset.
- Đối chiếu log ứng dụng với công cụ quản trị Kafka.
- Điều tra consumer xử lý chậm hoặc record gây lỗi.
- Ghi nhận vị trí nguồn khi chuyển record sang một destination khác.
- So sánh số lần giao lại và xác định record bị xử lý lặp.

Không đưa toàn bộ header map vào log một cách mặc định. Header có thể chứa dữ liệu nhạy cảm, token, thông tin định tuyến hoặc metadata nội bộ. Chỉ ghi những trường cần thiết và áp dụng chính sách che dữ liệu.

## 6. Dùng @Header để lấy riêng từng giá trị

Nếu handler chỉ cần một vài trường, có thể khai báo tham số với annotation **@Header** trong các API listener hỗ trợ. Với function bean của Spring Cloud Stream, cách đơn giản và rõ ràng là nhận Message<T>; điều này giữ payload và metadata trong một đối tượng thống nhất.

Ví dụ một phương thức xử lý trong lớp service nhận giá trị đã trích xuất:

~~~java
public void recordPosition(
        OrderCreated event,
        String topic,
        Integer partition,
        Long offset) {
    positionRepository.save(
            event.eventId(), topic, partition, offset);
}
~~~

Consumer có thể đọc headers rồi chuyển sang service:

~~~java
@Bean
public Consumer<Message<OrderCreated>> positionConsumer(
        PositionService service) {
    return message -> {
        var headers = message.getHeaders();
        service.recordPosition(
                message.getPayload(),
                headers.get(KafkaHeaders.RECEIVED_TOPIC, String.class),
                headers.get(KafkaHeaders.RECEIVED_PARTITION, Integer.class),
                headers.get(KafkaHeaders.OFFSET, Long.class)
        );
    };
}
~~~

Không để tầng domain phụ thuộc trực tiếp vào lớp KafkaHeaders nếu không cần. Có thể chuyển metadata thành một record nội bộ:

~~~java
public record KafkaRecordPosition(
        String topic,
        int partition,
        long offset) {
}
~~~

Sau đó adapter messaging tạo KafkaRecordPosition và truyền vào service. Cách này giúp logic nghiệp vụ dễ kiểm thử và ít phụ thuộc framework hơn.

## 7. Phân biệt KafkaHeaders với Kafka record headers

Hai khái niệm có liên quan nhưng không giống nhau:

| Khái niệm | Nơi tồn tại | Ví dụ |
|---|---|---|
| Spring Message headers | Trong đối tượng Message của ứng dụng. | contentType, correlationId, kafka_receivedTopic. |
| Kafka record headers | Trong record lưu trên Kafka, mỗi header là key và byte[] value. | traceparent, tenant-id, event-source. |
| Kafka record metadata | Thuộc record do Kafka quản lý. | Topic, partition, offset, timestamp, key. |
| KafkaHeaders constants | Hằng số Java để truy cập/ánh xạ metadata trong Spring. | RECEIVED_TOPIC, RECEIVED_PARTITION, OFFSET. |

Ví dụ, **KafkaHeaders.RECEIVED_TOPIC** là Spring Message header do adapter cung cấp để mô tả topic nguồn. Nó không phải một trường nghiệp vụ được producer ghi vào phần Kafka record headers.

Ngược lại, một custom header như **tenant-id** có thể được producer thêm vào Spring Message, sau đó Kafka binder ánh xạ thành Kafka record header và consumer đọc lại qua Spring Message. Header mapper chịu trách nhiệm chuyển đổi giữa hai biểu diễn.

### Header mapper mặc định

Kafka binder dùng header mapper để ánh xạ Spring Messaging headers sang Kafka Headers và ngược lại. Kafka hỗ trợ native headers từ kafka-clients 0.11.0.0. Thuộc tính **spring.cloud.stream.kafka.binder.headers** là cấu hình tương thích cũ, chỉ cần khi giao tiếp với ứng dụng Spring Cloud Stream phiên bản 1.3.x trở xuống dùng kafka-clients thấp hơn 0.11.0.0.

Nếu cần tùy chỉnh mapping, có thể chỉ định bean mapper:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          header-mapper-bean-name: kafkaBinderHeaderMapper
~~~

Bean được chỉ định phải triển khai kiểu header mapper mà binder hỗ trợ. Nếu custom mapper bỏ qua một header, consumer sẽ không nhận được header đó dù producer đã đặt nó. Vì vậy, khi thay mapper mặc định, hãy kiểm tra cả chiều gửi và chiều nhận.

### Lọc header bằng headerPatterns

Kafka producer binding hỗ trợ **headerPatterns**, một danh sách pattern để quyết định Spring Message headers nào được ánh xạ sang Kafka record headers. Mặc định, binder ánh xạ tất cả header phù hợp ngoại trừ các header framework dành riêng như id và timestamp.

Ví dụ chỉ cho phép một số header nghiệp vụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orderPublisher-out-0:
            producer:
              header-patterns: eventType,tenant-*,traceparent
~~~

Khi dùng danh sách cho phép, những header không khớp pattern sẽ không được gửi sang Kafka. Đừng lọc nhầm header mà consumer hoặc hệ thống quan sát đang phụ thuộc. Hãy kiểm thử trên record thực tế sau khi publish.

## 8. Đặt message key khi gửi record

Message key là thành phần của Kafka record, không phải payload và cũng không phải một Kafka record header thông thường. Trong Spring Cloud Stream, có thể đặt key bằng **KafkaHeaders.MESSAGE_KEY**:

~~~java
@Bean
public Supplier<Message<OrderCreated>> orderPublisher() {
    return () -> {
        OrderCreated event = nextOrder();
        return MessageBuilder.withPayload(event)
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .build();
    };
}
~~~

Kafka dùng key để chọn partition theo partitioner mặc định hoặc partitioner được cấu hình. Những record có cùng key thường được đưa về cùng partition khi số partition và thuật toán phân vùng không đổi. Điều này hữu ích để giữ thứ tự các sự kiện cùng một đơn hàng.

Có thể dùng **messageKeyExpression** của Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      kafka:
        bindings:
          orderPublisher-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

Expression được đánh giá trên outgoing message. Nếu key cần lấy từ header, có thể dùng biểu thức như **headers['tenantKey']**. Với function processor cần giữ key từ record đầu vào, có thể tham chiếu header key nhận được:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          enrichedOrders-out-0:
            producer:
              message-key-expression: headers['kafka_receivedMessageKey']
~~~

Tên header cụ thể phụ thuộc phiên bản Spring Kafka. Trong mã nguồn mới, ưu tiên **KafkaHeaders.RECEIVED_KEY**; cấu hình binder có thể tham chiếu tên header wire/Message tương ứng theo tài liệu phiên bản. Với reactive function, ứng dụng phải tự sao chép metadata cần thiết từ message đầu vào sang message đầu ra vì framework không thể giả định cách giữ headers qua mọi toán tử reactive.

Không dùng offset làm message key chỉ vì offset là duy nhất trong partition. Nếu muốn giữ tất cả sự kiện cùng orderId trên một partition, key phải là orderId hoặc khóa nghiệp vụ tương đương.

## 9. Chọn topic đích bằng KafkaHeaders.TOPIC

Mặc định, destination của output binding quyết định topic đích. Kafka binder có thuộc tính **useTopicHeader** cho phép ghi đè topic theo header **KafkaHeaders.TOPIC**:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        eventRouter-out-0:
          destination: default-events
      kafka:
        bindings:
          eventRouter-out-0:
            producer:
              use-topic-header: true
~~~

Khi bật thuộc tính này, nếu outgoing Message có KafkaHeaders.TOPIC, binder dùng giá trị header làm tên topic đích; nếu không có, binder dùng destination mặc định. Mặc định **useTopicHeader** là false.

Ví dụ:

~~~java
Message<String> message = MessageBuilder
        .withPayload("customer updated")
        .setHeader(KafkaHeaders.TOPIC, "customer-events")
        .setHeader(KafkaHeaders.MESSAGE_KEY, "CUS-100")
        .build();
~~~

Đây là khả năng định tuyến động ở phía producer. Chỉ bật khi ứng dụng thực sự cần chọn topic lúc chạy và đã kiểm soát tập topic được phép. Không lấy một tên topic tùy ý từ request bên ngoài rồi gửi trực tiếp; điều đó có thể khiến ứng dụng phát dữ liệu tới topic ngoài dự kiến hoặc tạo bề mặt truy cập rộng hơn.

## 10. Nhận RecordMetadata sau khi gửi thành công

Metadata inbound mô tả record đã được đọc. Ở chiều producer, nếu cần biết broker đã ghi record vào partition nào và offset nào, Kafka binder cung cấp **recordMetadataChannel**.

Khi gửi thành công, binder chuyển message kết quả tới MessageChannel đã chỉ định và bổ sung header **KafkaHeaders.RECORD_METADATA**. Giá trị header là đối tượng **org.apache.kafka.clients.producer.RecordMetadata** do Kafka client trả về.

Cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      kafka:
        bindings:
          orderPublisher-out-0:
            producer:
              record-metadata-channel: orderRecordMetadataChannel
~~~

Khai báo channel và luồng nhận metadata:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProducerMetadataConfiguration {

    @Bean
    public MessageChannel orderRecordMetadataChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderRecordMetadataFlow() {
        return IntegrationFlow
                .from("orderRecordMetadataChannel")
                .handle((payload, headers) -> {
                    RecordMetadata metadata = headers.get(
                            KafkaHeaders.RECORD_METADATA,
                            RecordMetadata.class);

                    if (metadata != null) {
                        log.info(
                                "Đã gửi tới topic={}, partition={}, offset={}",
                                metadata.topic(),
                                metadata.partition(),
                                metadata.offset()
                        );
                    }
                    return null;
                })
                .get();
    }
}
~~~

Khi publish thành công, RecordMetadata cho biết:

- **topic():** topic mà Kafka ghi record.
- **partition():** partition được chọn.
- **offset():** offset được gán cho record.
- **timestamp():** timestamp do Kafka client/broker trả về theo record metadata.

Metadata này hữu ích để đối chiếu việc gửi, xây dựng audit log hoặc lưu vị trí record. Nó chỉ xuất hiện trên đường kết quả gửi thành công khi recordMetadataChannel được cấu hình. Nếu gửi thất bại, lỗi đi theo producer error handling/error channel nếu đã cấu hình; không có RecordMetadata thành công cho lần gửi đó.

Đừng nhầm RecordMetadata với header RECEIVED_TOPIC/RECEIVED_PARTITION/OFFSET. RecordMetadata thuộc kết quả gửi ở producer; các header RECEIVED_* mô tả record đã được consumer nhận.

## 11. Chuyển tiếp record và bảo toàn metadata cần thiết

Một processor nhận record từ topic orders rồi gửi kết quả sang enriched-orders. Nếu cần giữ key, correlation ID hoặc một số header nghiệp vụ, ứng dụng phải chủ động quyết định header nào cần chuyển tiếp.

Ví dụ:

~~~java
@Bean
public Function<Message<OrderCreated>, Message<OrderEnriched>> enrichOrder(
        CustomerDirectory customers) {
    return input -> {
        OrderCreated event = input.getPayload();
        Customer customer = customers.find(event.customerId());

        OrderEnriched enriched = new OrderEnriched(
                event.orderId(),
                event.customerId(),
                customer.segment(),
                event.total()
        );

        return MessageBuilder.withPayload(enriched)
                .setHeader(
                        KafkaHeaders.MESSAGE_KEY,
                        input.getHeaders().get(KafkaHeaders.RECEIVED_KEY))
                .setHeader(
                        "correlationId",
                        input.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

Đoạn mã chỉ chuyển tiếp key và correlation ID đã chọn. Không sao chép toàn bộ headers từ inbound sang outbound một cách mù quáng:

- **RECEIVED_TOPIC** mô tả topic nguồn; nếu giữ nguyên nó, downstream có thể hiểu nhầm đây là topic đích.
- **RECEIVED_PARTITION** và **OFFSET** mô tả vị trí record cũ, không phải vị trí của record mới.
- **RECORD_METADATA** thuộc kết quả gửi trước đó, không phải metadata của lần gửi mới.
- Header ACKNOWLEDGMENT hoặc CONSUMER gắn với consumer hiện tại và không nên phát ra như metadata nghiệp vụ.

Nếu downstream cần truy vết nguồn, hãy dùng header nghiệp vụ riêng như **sourceTopic**, **sourcePartition**, **sourceOffset** hoặc một cấu trúc provenance có định nghĩa rõ. Khi đó, dữ liệu vị trí nguồn được giữ như thông tin lịch sử, không bị nhầm với metadata Kafka của record mới.

## 12. Metadata, partition và xử lý thứ tự

Topic, partition và offset thường được dùng cùng message key để giải thích thứ tự:

~~~text
orders / partition 0:
  offset 10: orderId=A, status=CREATED
  offset 11: orderId=B, status=CREATED
  offset 12: orderId=A, status=PAID

orders / partition 1:
  offset 4: orderId=C, status=CREATED
  offset 5: orderId=C, status=PAID
~~~

Kafka bảo đảm thứ tự trong từng partition. Nếu cả hai sự kiện của orderId=A được gửi cùng key và partitioning không đổi, chúng có thể nằm cùng partition theo đúng thứ tự ghi. Không thể so sánh offset 12 của partition 0 với offset 5 của partition 1 để kết luận sự kiện nào xảy ra trước trên toàn topic.

Khi xử lý song song:

- Dùng key theo aggregate hoặc thực thể nghiệp vụ cần giữ thứ tự.
- Không dùng partition index làm định danh nghiệp vụ.
- Không giả định tăng số partition sẽ giữ nguyên mapping key sang partition cho các record tương lai.
- Dùng event timestamp hoặc sequence nghiệp vụ nếu cần so sánh thứ tự ngoài phạm vi một partition.
- Theo dõi consumer lag theo từng partition thay vì chỉ nhìn một offset đơn lẻ.

Metadata giúp quan sát và điều tra, nhưng không tự giải quyết thứ tự nghiệp vụ. Nếu consumer xử lý bất đồng bộ nhiều record cùng partition, ứng dụng vẫn cần kiểm soát concurrency để tránh hoàn tất nghiệp vụ sai thứ tự.

## 13. Sử dụng metadata trong kiểm tra và xử lý trùng

Topic-partition-offset là tọa độ của một record trong Kafka log. Có thể dùng bộ ba này để ghi nhận nguồn xử lý hoặc phát hiện một record đã được quan sát trước đó.

Ví dụ khóa vị trí:

~~~java
public record RecordPosition(
        String topic,
        int partition,
        long offset) {
}

static RecordPosition positionOf(Message<?> message) {
    var headers = message.getHeaders();
    return new RecordPosition(
            headers.get(KafkaHeaders.RECEIVED_TOPIC, String.class),
            headers.get(KafkaHeaders.RECEIVED_PARTITION, Integer.class),
            headers.get(KafkaHeaders.OFFSET, Long.class)
    );
}
~~~

Một bảng audit có thể lưu record position cùng event ID và thời điểm xử lý. Nếu cùng một vị trí xuất hiện lại, đó là dấu hiệu record đã được giao lại hoặc logic audit ghi trùng. Tuy nhiên, không nên chỉ dựa vào vị trí Kafka để chống trùng ở cấp nghiệp vụ:

- Một sự kiện nghiệp vụ có thể được phát lại thành record mới với offset khác.
- Cùng một sự kiện có thể được gửi vào hai topic khác nhau.
- Producer retry có thể tạo record trùng nhưng có offset khác nhau.
- Reprocessing hoặc republish có thể thay đổi partition.

Vì vậy, dùng **eventId** hoặc idempotency key cho chống trùng nghiệp vụ. Dùng topic/partition/offset để định danh lần xuất hiện cụ thể trong Kafka log.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Header topic trả về null | Function không nhận Message hoặc không đọc đúng header inbound. | Nhận Message<T> và dùng KafkaHeaders.RECEIVED_TOPIC. |
| Không tìm thấy RECEIVED_PARTITION | Phiên bản Spring Kafka cũ dùng RECEIVED_PARTITION_ID hoặc binding không cung cấp header mong đợi. | Kiểm tra dependency và dùng hằng số đúng phiên bản. |
| Offset bị ép thành Integer và tràn | Offset Kafka là số nguyên 64 bit. | Dùng Long hoặc long. |
| Dùng offset làm ID toàn cục | Offset chỉ duy nhất trong một partition. | Kết hợp topic và partition, hoặc dùng eventId cho nghiệp vụ. |
| Nhầm offset record với committed offset | Header mô tả record đang xử lý; commit thường lưu vị trí tiếp theo. | Kiểm tra ack mode và trạng thái committed offset riêng. |
| Key nhận bị null | Producer không đặt key hoặc record thực sự có key null. | Đọc header tùy chọn và xác định chính sách key ở producer. |
| Custom header không tới consumer | Header mapper hoặc headerPatterns lọc mất header. | Kiểm tra mapper hai chiều và pattern cho phép. |
| Topic header không đổi destination | useTopicHeader chưa bật hoặc header TOPIC không có. | Kiểm tra extended producer property và tên header. |
| Không có RECORD_METADATA | Chưa cấu hình recordMetadataChannel hoặc gửi thất bại. | Kiểm tra channel bean, binding property và producer error channel. |
| Downstream thấy topic/offset cũ | Processor sao chép inbound Kafka metadata sang outbound message. | Chỉ chuyển tiếp key/header nghiệp vụ; dùng sourceTopic/sourceOffset riêng nếu cần provenance. |
| Log cho thấy offset tăng nhưng xử lý thiếu record | Offset có thể có khoảng trống do compaction, giao dịch hoặc record không được trả cho consumer. | Đối chiếu log, isolation level và record thực tế; không coi offset gap là mất dữ liệu. |

Khi điều tra, hãy xác định ứng dụng đang ở chiều producer hay consumer. Với consumer, kiểm tra RECEIVED_TOPIC, RECEIVED_PARTITION và OFFSET. Với producer, kiểm tra MESSAGE_KEY, TOPIC, useTopicHeader và RECORD_METADATA. Sau đó kiểm tra header mapper, phiên bản Spring Kafka và log broker.

## 15. Kiểm thử metadata Kafka

Test binder hữu ích để kiểm thử function và binding ở mức Spring Cloud Stream, nhưng không mô phỏng đầy đủ metadata do Kafka broker gán như partition và offset. Muốn kiểm tra chính xác metadata record, nên có integration test với Kafka broker thử nghiệm, chẳng hạn Embedded Kafka hoặc Testcontainers.

Ma trận kiểm thử đề xuất:

| Tình huống | Thiết lập | Điều cần xác nhận |
|---|---|---|
| Inbound record | Gửi record vào topic đã cấu hình. | Message có RECEIVED_TOPIC, RECEIVED_PARTITION và OFFSET đúng. |
| Nhiều partition | Gửi key khác nhau hoặc cấu hình partition test. | Metadata phản ánh partition thực tế mà broker chọn. |
| Không có key | Gửi record với key null. | Consumer xử lý trường hợp header key không hiện diện. |
| Offset liên tiếp | Gửi nhiều record vào cùng partition. | Offset tăng theo log, không giả định liên tục nếu có compaction/transaction. |
| Custom header | Gửi correlationId hoặc tenant-id. | Header được mapper truyền qua và consumer đọc đúng. |
| Header bị lọc | Cấu hình headerPatterns giới hạn. | Chỉ header khớp pattern được truyền. |
| Dynamic topic | Bật useTopicHeader và gửi KafkaHeaders.TOPIC. | Record được ghi vào topic header chọn. |
| Producer result | Cấu hình recordMetadataChannel. | Kênh nhận message kết quả với KafkaHeaders.RECORD_METADATA. |
| Processor chuyển tiếp | Nhận record rồi phát sang topic khác. | Key và header nghiệp vụ được giữ; metadata inbound không bị dùng nhầm như metadata outbound. |
| Consumer restart | Dừng và khởi động lại consumer. | Record có thể được giao lại theo offset/ack semantics; logic chống trùng hoạt động. |

Trong integration test, hãy đọc lại record từ broker hoặc dùng consumer kiểm thử để xác minh topic, partition, offset và key. Đối chiếu RecordMetadata producer với metadata inbound ở consumer để hiểu rằng producer nhận vị trí ghi thành công, còn consumer nhận vị trí record được giao.

## 16. Checklist trước khi triển khai

- [ ] Consumer nhận Message<T> khi cần đọc Kafka metadata.
- [ ] Dùng KafkaHeaders constants thay vì chuỗi tên tự viết.
- [ ] Đọc topic, partition và offset đúng kiểu dữ liệu.
- [ ] Ghi nhận vị trí bằng bộ ba topic-partition-offset.
- [ ] Dùng eventId hoặc idempotency key cho chống trùng nghiệp vụ.
- [ ] Không coi đọc OFFSET là commit offset hoặc ACK.
- [ ] Phân biệt RECEIVED_* của consumer với TOPIC/MESSAGE_KEY của producer.
- [ ] Không chuyển tiếp RECEIVED_PARTITION, OFFSET hoặc RECORD_METADATA như metadata của record mới.
- [ ] Header mapper và headerPatterns không vô tình loại bỏ custom headers cần thiết.
- [ ] Chỉ bật useTopicHeader khi cần định tuyến động và đã giới hạn topic hợp lệ.
- [ ] Dùng recordMetadataChannel nếu cần xác nhận vị trí record sau khi gửi thành công.
- [ ] Integration test chạy với Kafka thật hoặc broker thử nghiệm để xác nhận metadata.
- [ ] Log không chứa payload nhạy cảm hoặc toàn bộ header map.

Kafka binder ánh xạ metadata của record thành các Spring Message headers để ứng dụng có thể đọc topic, partition và offset ngay trong function. **KafkaHeaders.RECEIVED_TOPIC**, **RECEIVED_PARTITION** và **OFFSET** mô tả record đầu vào; **MESSAGE_KEY** và **TOPIC** hỗ trợ một số lựa chọn khi gửi; **RECORD_METADATA** cung cấp vị trí record đầu ra sau khi gửi thành công và được cấu hình nhận kết quả. Khi phân biệt đúng metadata record với message headers, dùng bộ ba topic-partition-offset và kiểm thử với Kafka broker, ứng dụng có thể truy vết sự kiện và xử lý giao nhận chính xác hơn.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/config-options.html)
- [Spring for Apache Kafka — KafkaHeaders API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/support/KafkaHeaders.html)
- [Spring for Apache Kafka — Receiving Messages and Record Metadata](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
