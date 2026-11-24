# Nhận từ nhiều topic hoặc mẫu tên topic

Một ứng dụng Kafka consumer có thể cần đọc nhiều topic trong cùng một luồng xử lý. Ví dụ, dịch vụ audit cần nhận sự kiện tạo đơn, hủy đơn và giao hàng; một bộ xử lý theo phiên bản cần đọc mọi topic có tên theo mẫu orders.*. Spring Cloud Stream Kafka Binder hỗ trợ cả hai cách: liệt kê nhiều topic trong thuộc tính destination hoặc đăng ký một regular expression để Kafka consumer tìm các topic phù hợp.

Hai cách này có mục đích khác nhau. Danh sách topic phù hợp khi tập topic đã biết và ổn định. Topic pattern phù hợp khi topic được tạo theo quy ước tên và ứng dụng cần tự động nhận các topic mới khớp mẫu. Với cả hai cách, một input binding vẫn có một cấu hình consumer và một consumer group; vì vậy cần xem xét schema, offset, quyền truy cập và cách phân biệt topic nguồn trước khi gom chúng vào cùng binding.

## 1. Một input binding có thể đọc nhiều topic

Trong functional model, input binding thường có tên bằng tên function cộng hậu tố -in-0. Ví dụ function bean auditEvents tạo binding auditEvents-in-0. Thuộc tính destination của binding có thể nhận danh sách topic Kafka phân tách bằng dấu phẩy:

```yaml
spring:
  cloud:
    function:
      definition: auditEvents
    stream:
      bindings:
        auditEvents-in-0:
          destination: orders.created,orders.cancelled,orders.shipped
          group: order-audit
          content-type: application/json
```

Với cấu hình này, một input binding đăng ký tiêu thụ từ ba topic. Kafka Binder kết nối binding với các topic tương ứng và dùng consumer group order-audit. Tất cả message từ ba topic đi vào cùng một function:

```java
@Bean
Consumer<OrderEvent> auditEvents() {
    return event -> auditService.record(event);
}
```

Danh sách destination được áp dụng cho input binding. Mọi topic trong danh sách dùng chung cấu hình binding như group, content type, concurrency, retry và các thuộc tính consumer của Kafka Binder. Nếu một topic cần group, content type, security policy hoặc error handling khác, hãy cân nhắc tạo binding riêng.

Không đặt khoảng trắng hoặc ký tự phân cách không cần thiết trong tên topic. Mỗi topic phải tồn tại hoặc được provision theo chính sách Kafka Binder/broker. Nếu môi trường tắt auto topic creation, quản trị viên cần tạo trước tất cả topic và cấp quyền cho ứng dụng.

## 2. Phân biệt nhiều topic với nhiều consumer group

Khi một binding đọc nhiều topic, các topic được tiêu thụ trong cùng consumer group. Kafka quản lý offset theo từng cặp topic-partition. Các consumer instance trong cùng group chia sẻ các partition thuộc tất cả topic mà group đã subscribe.

Ví dụ, group order-audit đọc ba topic:

| Topic | Partition | Tiến độ tiêu thụ |
|---|---|---|
| orders.created | 0, 1 | Offset riêng cho từng partition |
| orders.cancelled | 0, 1 | Offset riêng cho từng partition |
| orders.shipped | 0, 1 | Offset riêng cho từng partition |

Nếu cần hai ứng dụng độc lập đều nhận toàn bộ sự kiện, mỗi ứng dụng cần consumer group riêng. Nếu hai instance của cùng một ứng dụng dùng cùng group, Kafka phân phối partition giữa chúng thay vì gửi mọi message đến cả hai instance.

Một binding đọc nhiều topic không tạo thứ tự toàn cục giữa các topic. Kafka chỉ bảo đảm thứ tự trong từng partition. Message từ orders.created và orders.cancelled có thể được đọc hoặc xử lý xen kẽ; không thể suy ra thứ tự nghiệp vụ chỉ từ tên topic. Nếu nghiệp vụ cần thứ tự, hãy mang theo aggregate version/sequence hoặc thiết kế luồng sự kiện theo một partition key và quy ước rõ ràng.

## 3. Đọc topic nguồn từ message headers

Khi nhiều topic đi vào cùng một binding, function thường cần biết message đến từ topic nào để chọn logic phù hợp. Kafka Binder đưa metadata của record vào Spring Message headers. Có thể đọc topic, partition và offset bằng các header của Spring Kafka:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderEvent>> auditEvents() {
    return message -> {
        String topic = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
            .get(KafkaHeaders.OFFSET, Long.class);

        OrderEvent event = message.getPayload();
        auditService.record(topic, partition, offset, event);
    };
}
```

Các header này giúp xác định nguồn dữ liệu và điều tra message. Chúng không thay thế eventType trong payload: topic cho biết nơi record được lưu, còn eventType mô tả ý nghĩa nghiệp vụ. Nếu cùng một topic chứa nhiều loại event, consumer vẫn cần discriminator trong payload hoặc schema.

Không nên dùng topic name làm nguồn xác thực producer hoặc tenant. Topic là metadata định tuyến do broker cung cấp; quyền publish và quyền đọc phải được kiểm soát bằng Kafka ACL, danh tính client và chính sách ứng dụng.

## 4. Khi nào nên dùng topic pattern?

Nếu topic được tạo theo quy ước tên, ví dụ:

- orders.created.v1
- orders.cancelled.v1
- orders.shipped.v1
- orders.created.v2

thì việc cập nhật danh sách destination mỗi khi có topic mới có thể gây tốn công. Kafka Binder hỗ trợ đăng ký consumer bằng regular expression. Khi đó, destination được hiểu là biểu thức mẫu tên topic thay vì một tên topic cố định.

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: auditEvents
    stream:
      bindings:
        auditEvents-in-0:
          destination: '^orders\.(created|cancelled|shipped)\.v[0-9]+$'
          group: order-audit
          content-type: application/json
      kafka:
        bindings:
          auditEvents-in-0:
            consumer:
              destination-is-pattern: true
```

Ở đây destination là regular expression. Thuộc tính destination-is-pattern thuộc Kafka Binder consumer properties và phải được bật để binder diễn giải destination như một Pattern. Regex trên chỉ khớp topic bắt đầu bằng orders., theo sau là created, cancelled hoặc shipped, rồi đến phần version dạng v1, v2, v3...

Nên neo regex bằng ^ và $ để tránh khớp các topic có tiền tố/hậu tố ngoài dự kiến. Dùng nhóm lựa chọn và phiên bản cụ thể thay vì mẫu quá rộng như .*; một regex rộng có thể khiến ứng dụng vô tình đọc topic nội bộ hoặc topic của nhóm nghiệp vụ khác.

## 5. Phát hiện topic mới khớp pattern

Kafka consumer đăng ký pattern và broker trả về các topic hiện khớp mẫu. Khi một topic mới được tạo và tên của nó khớp regex, consumer có thể nhận topic đó sau khi metadata được làm mới.

Thời gian phát hiện topic mới phụ thuộc thuộc tính consumer metadata.max.age.ms. Tài liệu Kafka Binder hiện hành ghi nhận giá trị mặc định của Kafka client là 300.000 ms (5 phút). Có thể điều chỉnh ở cấu hình consumer:

```yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvents-in-0:
          destination: '^orders\..*\.v[0-9]+$'
          group: order-audit
      kafka:
        bindings:
          auditEvents-in-0:
            consumer:
              destination-is-pattern: true
              configuration:
                metadata.max.age.ms: 30000
```

Ví dụ đặt metadata refresh ở 30 giây. Giá trị nhỏ hơn có thể giúp nhận topic mới nhanh hơn nhưng cũng làm tăng tần suất cập nhật metadata. Chọn giá trị theo yêu cầu vận hành và tải của cluster; không xem đây là thời gian đảm bảo tuyệt đối từ lúc tạo topic đến lúc consumer bắt đầu đọc.

Với topic mới, consumer group vẫn cần xác định offset bắt đầu theo cấu hình startOffset và chính sách offset của Kafka. Nếu group chưa có offset đã commit cho topic-partition mới, consumer sẽ áp dụng quy tắc bắt đầu đã cấu hình. Hãy quyết định rõ có cần đọc lịch sử của topic mới hay chỉ quan tâm message phát sinh sau khi consumer bắt đầu nhận.

## 6. Khác biệt giữa danh sách topic và regex

| Tiêu chí | Danh sách destination | Topic pattern |
|---|---|---|
| Cấu hình | orders.created,orders.cancelled | Regex trong destination |
| Cần bật destination-is-pattern | Không | Có |
| Tập topic | Được khai báo tường minh | Được xác định theo tên topic khớp regex |
| Topic mới | Cần cập nhật cấu hình hoặc binding | Tự được phát hiện khi metadata refresh |
| Provision topic | Binder có thể provision các tên đã biết nếu được phép | Binder không provision topic vì không biết tập tên cụ thể |
| Kafka Binder enable-dlq | Có thể cấu hình theo hỗ trợ của binding/binder | Không được hỗ trợ khi destination-is-pattern=true |
| Rủi ro chính | Quên thêm topic mới hoặc danh sách cấu hình lệch | Regex khớp quá rộng hoặc vô tình nhận topic ngoài phạm vi |

Không kết hợp danh sách phân tách bằng dấu phẩy với regex trong cùng một destination. Chọn một cách biểu diễn cho mỗi input binding. Nếu một nhóm topic cố định cần chính sách riêng, dùng danh sách rõ ràng; nếu topic phát sinh theo quy ước tên và cùng chính sách xử lý, dùng pattern.

## 7. Giới hạn provision và DLQ khi dùng pattern

Khi destination-is-pattern được bật, Kafka Binder không biết chính xác tên các topic sẽ được khớp ở thời điểm provision binding. Vì vậy:

- Binder không tự tạo các topic theo regex.
- Các topic cần được tạo bởi Kafka administrator, nền tảng triển khai hoặc producer có quyền phù hợp.
- Kafka Binder không cho bật enable-dlq trên binding dùng destination pattern, vì binder không thể provision DLQ theo tập topic chưa biết.

Đây là khác biệt quan trọng khi thiết kế error handling. Nếu cần DLQ cho pattern subscription, hãy thiết kế error flow ở tầng ứng dụng hoặc dùng một cơ chế lưu lỗi tập trung có tên destination xác định. Khi gửi lỗi sang một topic chung, lưu topic nguồn, partition, offset, key, event ID và exception metadata trong bản ghi lỗi để có thể điều tra.

Không giả định bật autoCreateTopics ở binder sẽ tạo các topic khớp regex. Cũng không bật enableDlq rồi kỳ vọng binder tự suy ra một DLQ phù hợp cho từng topic chưa tồn tại lúc khởi động.

## 8. Tất cả topic trong một binding cần có hợp đồng dữ liệu tương thích

Một binding có một cấu hình content type và một chiến lược deserialization/conversion. Khi gom nhiều topic vào một binding, các message phải có định dạng tương thích với cách consumer chuyển đổi payload.

Ví dụ, nếu cả ba topic đều gửi cùng envelope:

```java
public record DomainEvent(
    String eventId,
    String eventType,
    int schemaVersion,
    JsonNode payload
) {}
```

thì một consumer có thể deserialize mọi topic về DomainEvent rồi dispatch theo eventType. Nếu orders.created gửi OrderCreated, orders.cancelled gửi OrderCancelled và orders.shipped gửi một schema hoàn toàn khác, một Consumer<OrderCreated> sẽ không phải lựa chọn an toàn cho binding đọc cả ba.

Có ba hướng xử lý:

1. Chuẩn hóa các topic dùng chung một envelope/schema và để payload bên trong được dispatch theo eventType/version.
2. Nhận dạng byte[] hoặc kiểu trung gian rồi chọn deserializer theo topic nguồn, nếu ứng dụng thật sự cần hỗ trợ nhiều wire format.
3. Tạo binding riêng cho từng topic hoặc nhóm topic có schema và chính sách khác nhau.

Không chỉ dựa vào tên topic để đoán schema nếu producer có thể thay đổi quy ước. Hãy quản lý schema version, content type và eventType như một phần của hợp đồng sự kiện.

## 9. Consumer group, partition và khả năng mở rộng

Một consumer group đọc nhiều topic sẽ nhận tổng số partition của tất cả topic đã đăng ký. Kafka phân phối các partition đó cho các consumer instance trong group. Nếu tổng partition lớn hơn số consumer, một consumer có thể nhận nhiều partition. Nếu số consumer vượt tổng partition, một số consumer sẽ không có partition để xử lý.

Concurrency của binding làm tăng số consumer nội bộ trong mỗi instance. Ví dụ ba topic, mỗi topic có bốn partition, tổng cộng mười hai partition. Nếu ứng dụng chạy ba replica với concurrency hai, group có tối đa sáu consumer; mỗi consumer có thể nhận khoảng hai partition tùy assignment strategy.

Việc thêm topic mới có thể làm thay đổi số partition và kích hoạt rebalance. Theo dõi thời gian rebalance, lag và tải theo topic/partition. Không tăng concurrency vô hạn; năng lực database và downstream vẫn là giới hạn thực tế.

## 10. Quyền truy cập và kiểm soát phạm vi topic

Consumer dùng danh sách topic hoặc regex đều cần quyền đọc các topic tương ứng. Với pattern, quyền cần được tính cho cả topic sẽ được tạo trong tương lai. Tùy cấu hình cluster và cơ chế ACL, consumer có thể cần quyền mô tả metadata để phát hiện topic phù hợp.

Các nguyên tắc:

- Dùng prefix và naming convention riêng cho domain, ví dụ orders.*.
- Regex nên giới hạn event type và version cần nhận.
- Cấp ACL read/describe tối thiểu cho tập topic hợp lệ.
- Không dùng regex rộng để đọc mọi topic trong cluster.
- Kiểm tra topic mới được tạo có đúng owner, retention, partition count và schema policy.
- Theo dõi danh sách topic thực tế mà binding đang subscribe.

Một topic khớp regex không có nghĩa ứng dụng được phép xử lý mọi dữ liệu trong topic đó. Producer authentication, ACL và kiểm tra event type vẫn cần được thực hiện.

## 11. Khi nào nên tách thành nhiều binding?

Dùng một binding cho nhiều topic khi các topic có cùng:

- Consumer group và yêu cầu chia tải.
- Content type, serializer/deserializer và schema envelope.
- Chính sách retry, DLQ/error handling và acknowledgement.
- Quyền truy cập và vòng đời vận hành.
- Mục tiêu xử lý và yêu cầu thứ tự tương thích.

Tách binding nếu một topic cần schema khác, consumer group khác, retry khác, retention hoặc quyền truy cập khác. Ví dụ, audit service có thể đọc orders.created và orders.cancelled trong một binding nếu cả hai dùng cùng envelope. Một consumer xử lý payment riêng có thể cần binding và group độc lập để không bị ảnh hưởng bởi tải hoặc lỗi từ luồng đơn hàng.

## 12. Ví dụ hoàn chỉnh: đọc topic đơn hàng theo pattern

Giả sử các team phát hành topic theo quy ước:

- orders.created.v1
- orders.cancelled.v1
- orders.shipped.v1
- orders.created.v2

Audit service đọc mọi event đơn hàng có version:

```yaml
spring:
  cloud:
    function:
      definition: auditOrders
    stream:
      bindings:
        auditOrders-in-0:
          destination: '^orders\.(created|cancelled|shipped)\.v[0-9]+$'
          group: audit-service
          content-type: application/json
      kafka:
        bindings:
          auditOrders-in-0:
            consumer:
              destination-is-pattern: true
              configuration:
                metadata.max.age.ms: 60000
```

Consumer nhận envelope chung và ghi lại topic nguồn:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<DomainEvent>> auditOrders(AuditService auditService) {
    return message -> {
        String topic = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_TOPIC, String.class);

        DomainEvent event = message.getPayload();
        auditService.record(topic, event.eventId(),
            event.eventType(), event.schemaVersion(), event.payload());
    };
}
```

Trong ví dụ, metadata được làm mới mỗi 60 giây để phát hiện topic mới phù hợp. Các topic phải được provision bên ngoài; audit-service dùng một consumer group chung. Vì binding dùng regex, Kafka Binder không hỗ trợ enable-dlq trên binding này. Nếu cần lưu lỗi, thiết kế error flow riêng và lưu topic nguồn cùng metadata record.

## 13. Kiểm thử danh sách topic và pattern

Kiểm thử nên bao gồm các trường hợp:

- Khởi động binding với danh sách nhiều topic và xác nhận message từ từng topic đều đến consumer.
- Gửi message vào topic không thuộc danh sách và xác nhận consumer không nhận.
- Khởi động binding với regex và xác nhận tất cả topic đang khớp được subscribe.
- Tạo topic mới khớp regex sau khi consumer đã chạy; xác nhận nó được phát hiện sau lần metadata refresh.
- Tạo topic không khớp regex và xác nhận nó không được subscribe.
- Kiểm tra offset của từng topic-partition trong cùng consumer group.
- Kiểm tra header received topic/partition/offset và event type trong payload.
- Gửi payload khác schema vào một topic trong tập; xác nhận lỗi conversion được quan sát và xử lý theo chính sách.
- Xác nhận regex binding không bật Kafka Binder enable-dlq; kiểm thử error flow thay thế nếu có.
- Kiểm tra ACL khi topic mới được provision và consumer bắt đầu đọc.

Test Binder có thể kiểm tra logic function và binding ở mức ứng dụng, nhưng không mô phỏng đầy đủ topic discovery, metadata refresh, regex subscription, partition assignment và ACL của Kafka. Cần integration test với Kafka thật hoặc môi trường test broker tương đương để xác nhận các hành vi đó.

## 14. Checklist triển khai

- [ ] Đã chọn danh sách destination hoặc regex cho từng input binding.
- [ ] Nếu dùng danh sách, các topic được phân tách bằng dấu phẩy và tồn tại/provision đúng chính sách.
- [ ] Nếu dùng regex, đã bật `spring.cloud.stream.kafka.bindings.<binding>.consumer.destination-is-pattern`.
- [ ] Regex được neo và giới hạn theo domain/event/version.
- [ ] Đã cấu hình metadata.max.age.ms theo yêu cầu phát hiện topic mới.
- [ ] Đã xác định offset policy cho topic mới và consumer group ổn định.
- [ ] Mọi topic trong binding có content type/schema tương thích.
- [ ] Function có thể xác định topic nguồn bằng KafkaHeaders.RECEIVED_TOPIC khi cần.
- [ ] Đã tính tổng partition của mọi topic để chọn concurrency và số replica.
- [ ] Đã provision topic và cấp ACL read/describe phù hợp.
- [ ] Nếu dùng pattern, không cấu hình Kafka Binder enable-dlq; đã thiết kế error flow thay thế khi cần.
- [ ] Đã kiểm thử topic mới, topic không khớp, schema lỗi, rebalance và metadata refresh với Kafka thật.

Một input binding có thể đọc nhiều topic đã biết bằng danh sách destination hoặc tự tìm topic mới theo regex. Danh sách phù hợp với tập topic cố định; pattern phù hợp với naming convention có kiểm soát. Khi gom nhiều topic, hãy bảo đảm schema và chính sách consumer tương thích, phân biệt nguồn message qua headers, kiểm soát ACL và nhớ rằng pattern subscription không hỗ trợ topic provisioning hay Kafka Binder DLQ.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html)
