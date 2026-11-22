# Đọc một hoặc nhiều record

## 1. Hai cách nhận dữ liệu trong Spring Kafka

Kafka consumer lấy dữ liệu bằng thao tác poll. Một lần poll có thể trả về nhiều record thuộc các partition mà consumer đang sở hữu. Spring Kafka listener container nhận kết quả poll, chuyển dữ liệu sang kiểu mà listener yêu cầu rồi gọi phương thức được đánh dấu @KafkaListener.

Ở tầng ứng dụng, Spring Kafka hỗ trợ hai kiểu xử lý chính:

- **Record listener:** mỗi lần gọi listener nhận một record. Container gọi phương thức nhiều lần để xử lý các record của lần poll.
- **Batch listener:** mỗi lần gọi listener nhận một danh sách record được lấy từ một lần poll. Ứng dụng xử lý cả nhóm record trong một lần gọi.

~~~mermaid
flowchart TD
    A["Kafka broker"] --> B["Consumer poll"]
    B --> C["Spring Kafka listener container"]
    C --> D{"Listener mode"}
    D -->|Record| E["Gọi listener cho từng record"]
    D -->|Batch| F["Gọi listener với một batch"]
    E --> G["Xử lý nghiệp vụ"]
    F --> G
    G --> H["Xác nhận / commit offset theo ack mode"]
~~~

Cả hai kiểu đều dùng consumer group, partition assignment và offset của Kafka. Điểm khác nhau nằm ở cách container chuyển dữ liệu cho phương thức listener và cách ứng dụng tổ chức xử lý.

## 2. Đọc từng record với record listener

Đây là cách đơn giản và thường phù hợp khi mỗi sự kiện cần được xử lý độc lập. Một listener có thể nhận trực tiếp payload đã được deserialize:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    public void handle(OrderCreatedEvent event) {
        orderService.createOrderProjection(event);
    }
}
~~~

Trong ví dụ, Kafka deserializer chuyển value thành OrderCreatedEvent; message converter có thể tham gia khi ứng dụng dùng mô hình Spring Message. Phương thức handle chỉ tập trung vào nghiệp vụ.

Nếu cần metadata của record, nhận ConsumerRecord<K, V> thay vì chỉ nhận payload:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-audit"
    )
    public void handle(ConsumerRecord<String, OrderCreatedEvent> record) {
        String key = record.key();
        OrderCreatedEvent event = record.value();

        log.info(
            "Nhận topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            key
        );

        auditService.record(event);
    }
}
~~~

ConsumerRecord cung cấp cả dữ liệu và metadata:

| Thành phần | Ý nghĩa |
|---|---|
| topic() | Tên topic chứa record |
| partition() | Partition chứa record |
| offset() | Vị trí của record trong partition |
| key() | Key dùng để định tuyến hoặc nhận diện record |
| value() | Payload sau khi deserialize |
| timestamp() | Timestamp gắn với record |
| headers() | Các header đi kèm record |

Offset chỉ có ý nghĩa trong phạm vi một partition. Không dùng offset làm mã định danh nghiệp vụ toàn cục; nếu cần nhận diện một sự kiện xuyên suốt các lần gửi và retry, hãy đưa eventId vào payload hoặc metadata theo quy ước của ứng dụng.

### Khi nào chỉ nhận payload, khi nào nhận ConsumerRecord?

Chỉ nhận payload khi nghiệp vụ cần dữ liệu sự kiện và không cần metadata Kafka. Cách này làm chữ ký listener gọn, dễ kiểm thử.

Nhận ConsumerRecord khi cần ghi log có topic, partition và offset; cần đọc key hoặc header; hoặc cần điều tra lỗi dựa trên vị trí record. Không nên truyền ConsumerRecord sâu vào domain model nếu phần nghiệp vụ không cần biết chi tiết Kafka.

## 3. Đọc nhiều record với batch listener

Batch listener nhận một nhóm record trong mỗi lần gọi phương thức. Cách này hữu ích khi có thể xử lý nhiều sự kiện cùng lúc, ví dụ ghi nhiều dòng vào database, gọi một API hỗ trợ bulk hoặc gom dữ liệu để giảm chi phí xử lý lặp lại.

Có hai cách bật batch listener trong ứng dụng Spring Boot.

### Cấu hình batch mode bằng application.yml

Với Spring Boot có hỗ trợ thuộc tính listener type, có thể đặt:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-batch-processor
      max-poll-records: 100
      enable-auto-commit: false
    listener:
      type: batch
~~~

spring.kafka.listener.type: batch yêu cầu các listener container tự động cấu hình theo batch mode. Thuộc tính max-poll-records ánh xạ đến cấu hình Kafka consumer max.poll.records, giới hạn số record tối đa trả về trong một lần poll.

Listener có thể nhận danh sách payload:

~~~java
import java.util.List;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-batch-processor"
    )
    public void handleBatch(
            @Payload List<OrderCreatedEvent> events) {

        orderService.createOrderProjections(events);
    }
}
~~~

Spring Kafka chuyển payload của các record trong batch thành danh sách OrderCreatedEvent. Cách này thuận tiện khi nghiệp vụ chỉ cần dữ liệu sự kiện.

### Dùng ConsumerRecord trong batch

Nếu cần metadata của từng record, dùng danh sách ConsumerRecord:

~~~java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchAuditListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-batch-audit"
    )
    public void handleBatch(
            List<ConsumerRecord<String, OrderCreatedEvent>> records) {

        for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
            log.info(
                "topic={}, partition={}, offset={}, key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()
            );

            auditService.record(record.value());
        }
    }
}
~~~

Dùng List<ConsumerRecord<K, V>> khi mỗi phần tử cần key, partition, offset hoặc header. Dùng List<V> khi chỉ cần payload và muốn chữ ký phương thức đơn giản.

### Cấu hình batch bằng listener container factory

Trong ứng dụng cần nhiều listener với chế độ khác nhau, có thể tạo một ConcurrentKafkaListenerContainerFactory riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(
            new DefaultErrorHandler(new FixedBackOff(1000L, 2L))
        );
        return factory;
    }
}
~~~

Chỉ định factory trên listener muốn đọc theo batch:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-processor",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(List<OrderCreatedEvent> events) {
    orderService.createOrderProjections(events);
}
~~~

Cách này cho phép cùng một ứng dụng có listener xử lý từng record và listener xử lý batch. Mỗi listener phải dùng container factory phù hợp với kiểu tham số của phương thức.

Không cấu hình một listener là batch nhưng lại khai báo phương thức chỉ nhận một payload đơn, hoặc ngược lại. Kiểu tham số listener và chế độ container phải khớp nhau.

## 4. Kích thước batch được quyết định như thế nào?

Batch mà listener nhận thường là tập record trả về từ một lần poll của một consumer. Batch có thể chứa record từ nhiều partition được gán cho consumer đó.

max.poll.records là giới hạn số record tối đa consumer trả về trong một lần poll. Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
~~~

Giá trị này không có nghĩa mỗi lần listener luôn nhận đủ 200 record. Batch thực tế có thể nhỏ hơn do lượng dữ liệu hiện có, tốc độ producer, số partition được gán, giới hạn fetch hoặc thời điểm poll.

Một số cấu hình liên quan:

| Thuộc tính | Vai trò |
|---|---|
| max.poll.records | Giới hạn số record trả về trong một lần poll |
| max.poll.interval.ms | Giới hạn thời gian giữa các lần poll trước khi consumer bị xem là không còn hoạt động trong group |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch tối đa cho một partition trong một fetch |
| fetch.max.bytes | Giới hạn tổng dữ liệu fetch cho một request |
| fetch.min.bytes | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch |
| fetch.max.wait.ms | Thời gian broker tối đa chờ để đáp ứng fetch.min.bytes |

Các giới hạn kích thước fetch và giới hạn số record là những cơ chế khác nhau. max.poll.records giới hạn số phần tử ứng dụng nhận từ poll; các thuộc tính fetch điều khiển lượng dữ liệu broker trả về. Record lớn cũng có thể làm batch thực tế nhỏ hơn dự kiến.

Khi xử lý batch, cần bảo đảm thời gian xử lý một lần poll không vượt max.poll.interval.ms. Nếu listener mất quá lâu để xử lý batch, consumer có thể bị loại khỏi group và Kafka thực hiện rebalance. Có thể giảm max.poll.records, tối ưu xử lý bulk, tăng giới hạn thời gian phù hợp hoặc điều chỉnh số consumer và partition.

Kích thước batch và concurrency là hai khái niệm khác nhau. Batch là số record một consumer nhận trong một lần poll; concurrency là số consumer mà listener container tạo ra để xử lý song song. Mỗi consumer có poll và batch riêng, còn số consumer có partition để đọc vẫn bị giới hạn bởi số partition được gán trong group.

## 5. Batch không tạo thứ tự toàn cục giữa các partition

Một batch có thể chứa record đến từ nhiều partition. Kafka bảo đảm thứ tự trong từng partition, nhưng không tạo ra một thứ tự toàn cục giữa các partition.

Ví dụ, batch có thể chứa:

| Thứ tự trong danh sách minh họa | Partition | Offset |
|---:|---|---:|
| 1 | P0 | 10 |
| 2 | P1 | 7 |
| 3 | P0 | 11 |
| 4 | P1 | 8 |

Có thể dựa vào thứ tự của record trong cùng partition để xử lý tuần tự theo key hoặc thực thể nghiệp vụ. Không suy luận rằng record ở P0 luôn xảy ra trước record ở P1 chỉ vì nó xuất hiện trước trong danh sách batch.

Nếu nghiệp vụ cần giữ thứ tự cho các sự kiện của cùng một đơn hàng, producer nên dùng orderId làm key để các sự kiện của đơn hàng được đưa vào cùng partition. Batch listener vẫn phải tôn trọng thứ tự đó khi xử lý.

## 6. Xác nhận offset khi đọc record hoặc batch

Đọc record và commit offset là hai việc khác nhau. Spring Kafka listener container quản lý việc commit dựa trên AckMode và cấu hình consumer.

Với record listener, container có thể xác nhận tiến độ sau mỗi record nếu dùng AckMode.RECORD, hoặc sau khi xử lý xong toàn bộ record của một lần poll nếu dùng AckMode.BATCH. BATCH là chế độ mặc định phổ biến của listener container.

Với batch listener, container xử lý cả danh sách như một lần gọi. Khi listener hoàn tất bình thường, container xác nhận offset của batch theo ack mode đang cấu hình. AckMode.RECORD không phù hợp với batch listener vì phương thức chỉ nhận cả batch như một đơn vị xử lý.

Nếu bật manual acknowledgment, listener nhận thêm tham số Acknowledgment và chỉ gọi acknowledge() sau khi ứng dụng hoàn tất công việc theo chính sách đã chọn:

~~~java
import java.util.List;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderBatchListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-manual-batch",
        containerFactory = "manualBatchFactory"
    )
    public void handle(
            List<OrderCreatedEvent> events,
            Acknowledgment acknowledgment) {

        orderService.createOrderProjections(events);
        acknowledgment.acknowledge();
    }
}
~~~

Factory manualBatchFactory phải được cấu hình batch mode và ack mode MANUAL hoặc MANUAL_IMMEDIATE. Chỉ xác nhận sau khi thao tác nghiệp vụ đã hoàn tất. Nếu commit offset trước khi lưu dữ liệu hoặc xử lý xong, lỗi có thể khiến record bị bỏ qua khi consumer tiếp tục.
Có thể khai báo factory dành riêng cho listener này (đặt cùng các import và bean trong lớp cấu hình ở ví dụ trước):

~~~java
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
        manualBatchFactory(
                ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
    return factory;
}
~~~

Manual acknowledgment không tự tạo transaction phân tán với database. Nếu cần đồng bộ kết quả ghi database và tiến độ Kafka, cần thiết kế transaction phù hợp hoặc dùng mẫu outbox/inbox tùy chiều dữ liệu.

## 7. Xử lý lỗi trong batch listener

Với record listener, lỗi thường gắn với một lần xử lý một record. Với batch listener, một lần gọi có thể xử lý nhiều record, nên cần xác định cách xử lý khi một phần tử trong batch thất bại.

Cách đơn giản là để exception thoát khỏi listener. Error handler của container sẽ áp dụng chính sách lỗi đã cấu hình. Tùy error handler và ack mode, batch có thể được retry như một đơn vị, dẫn đến các record đã xử lý thành công trước đó được nhận lại.

Nếu cần chỉ rõ vị trí record lỗi, Spring Kafka hỗ trợ BatchListenerFailedException. Kết hợp với DefaultErrorHandler, ứng dụng có thể chỉ ra index của record thất bại để error handler xử lý phần đã thành công và phần còn lại theo chính sách:

~~~java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-processor",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(
        List<ConsumerRecord<String, OrderCreatedEvent>> records) {

    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.createOrderProjection(records.get(index).value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Không xử lý được record trong batch",
                ex,
                index
            );
        }
    }
}
~~~

Cách xử lý cụ thể phụ thuộc cấu hình DefaultErrorHandler, backoff, recoverer và ack mode. Cần kiểm thử trường hợp lỗi ở đầu, giữa và cuối batch để xác minh record nào được retry, record nào đã commit và record nào được chuyển đến nơi phục hồi.

Vì batch có thể được chạy lại, thao tác nghiệp vụ nên idempotent. Nếu một số record trong batch đã ghi database thành công rồi batch thất bại, lần gọi sau có thể nhận lại chúng. Có thể dùng event ID và ràng buộc duy nhất trong database để ngăn áp dụng một sự kiện nhiều lần.

## 8. Chọn record listener hay batch listener?

| Tiêu chí | Record listener | Batch listener |
|---|---|---|
| Cách gọi | Một lần cho từng record | Một lần cho một danh sách từ poll |
| Độ phức tạp | Đơn giản, dễ tách lỗi | Cần xử lý lỗi và offset theo batch |
| Tối ưu bulk | Phải tự gom hoặc xử lý từng record | Có thể gọi bulk API hoặc batch database |
| Metadata | Nhận một ConsumerRecord | Nhận danh sách ConsumerRecord |
| Xử lý từng sự kiện độc lập | Phù hợp | Có thể phải tự lặp qua danh sách |
| Thời gian xử lý | Dễ giới hạn theo từng record | Cần theo dõi tổng thời gian của batch |
| Xử lý lỗi một phần | Error handler xử lý theo record | Cần xác định vị trí lỗi trong batch khi muốn xử lý một phần |

Chọn record listener khi:

- Mỗi sự kiện có logic riêng và cần xử lý độc lập.
- Muốn cấu hình retry hoặc quan sát lỗi theo từng record.
- Xử lý một record đủ nhanh và không có lợi ích rõ ràng khi gom nhóm.

Chọn batch listener khi:

- Database hoặc dịch vụ đích hỗ trợ ghi/gọi theo lô.
- Có thể giảm chi phí kết nối hoặc round-trip bằng thao tác bulk.
- Ứng dụng có thể xử lý một danh sách record trong thời gian giới hạn.
- Đã thiết kế rõ cách retry, commit và chống xử lý trùng.

Batch không tự động làm hệ thống nhanh hơn. Nếu nghiệp vụ vẫn phải xử lý từng record tuần tự, chi phí quản lý batch và xử lý lỗi có thể lớn hơn lợi ích. Hãy đo thông lượng, độ trễ và tài nguyên trước khi quyết định.

## 9. Kiểm thử listener nhận một hoặc nhiều record

Với record listener, kiểm thử cần xác minh mỗi record tạo đúng tác động nghiệp vụ và metadata được đọc đúng nếu listener dùng ConsumerRecord.

Với batch listener, kiểm thử cần xác minh:

- Listener nhận được danh sách record và xử lý đủ phần tử.
- Batch có ít hơn max.poll.records vẫn được xử lý bình thường.
- Batch chứa record từ nhiều partition không làm sai logic theo key.
- Lỗi ở một vị trí có hành vi retry/commit như cấu hình.
- Consumer không vượt max.poll.interval.ms với kích thước batch dự kiến.

Có thể dùng Embedded Kafka hoặc Testcontainers để kiểm thử tích hợp. Gửi một số record vào topic, dùng consumer group riêng cho bài test và chờ đến khi listener xử lý đủ số lượng mong đợi. Nên dùng Awaitility hoặc cơ chế chờ có timeout thay vì Thread.sleep() cố định.

Không nên khẳng định batch luôn có đúng số record đã cấu hình. Producer có thể mới gửi một phần dữ liệu, consumer có thể poll trước khi các record còn lại xuất hiện, và broker còn áp dụng các giới hạn fetch. Bài kiểm thử nên xác nhận hành vi với batch có kích thước thay đổi.

## 10. Checklist triển khai

- [ ] Chọn record listener hay batch listener theo cách xử lý nghiệp vụ.
- [ ] Kiểu tham số listener khớp với chế độ container.
- [ ] Serializer/deserializer tương thích với payload.
- [ ] Dùng ConsumerRecord khi cần metadata Kafka; chỉ nhận payload khi không cần metadata.
- [ ] Đặt max.poll.records theo thông lượng và thời gian xử lý thực tế.
- [ ] Bảo đảm xử lý batch không vượt max.poll.interval.ms.
- [ ] Hiểu batch có thể chứa nhiều partition và không có thứ tự toàn cục.
- [ ] Chọn ack mode và chính sách commit phù hợp.
- [ ] Có error handler và cách xử lý lỗi một phần khi dùng batch.
- [ ] Thiết kế idempotent để chịu được việc record được nhận lại.
- [ ] Kiểm thử batch có kích thước thay đổi và các vị trí phát sinh lỗi.

Trong Spring Kafka, record listener giúp xử lý từng sự kiện rõ ràng, còn batch listener giúp ứng dụng xử lý một nhóm record trong một lần gọi để tận dụng thao tác bulk. Hiểu cách poll tạo batch, cách offset được xác nhận và cách error handler xử lý lỗi sẽ giúp chọn đúng mô hình đọc cho từng luồng messaging.
