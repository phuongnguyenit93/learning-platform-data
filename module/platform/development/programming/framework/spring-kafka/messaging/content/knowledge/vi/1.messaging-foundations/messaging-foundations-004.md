# Mô hình publish-subscribe trong Kafka

## 1. Publish-subscribe là gì?

Publish-subscribe (pub/sub) là mô hình giao tiếp trong đó bên phát sự kiện (*publisher* hoặc *producer*) gửi thông điệp đến một kênh chung, còn bên nhận (*subscriber* hoặc *consumer*) đăng ký nhận thông điệp từ kênh đó. Hai phía không cần gọi trực tiếp nhau và thường không cần biết danh tính hay địa chỉ của nhau.

Ví dụ, khi một đơn hàng được tạo, dịch vụ Order phát sự kiện `OrderCreated`. Dịch vụ Inventory có thể nhận sự kiện để giữ hàng, dịch vụ Notification gửi email, còn dịch vụ Analytics cập nhật số liệu. Order chỉ chịu trách nhiệm công bố sự kiện; nó không cần gọi lần lượt ba dịch vụ này.

Mô hình này giúp giảm phụ thuộc giữa các dịch vụ, cho phép thêm hoặc thay đổi consumer mà ít ảnh hưởng publisher, đồng thời hỗ trợ xử lý bất đồng bộ. Đổi lại, hệ thống cần quan tâm đến giao nhận thông điệp, thứ tự xử lý, lỗi lặp, độ trễ và khả năng quan sát.

## 2. Kafka hiện thực pub/sub như thế nào?

Kafka là một nền tảng event streaming phân tán. Producer ghi record vào một **topic**; Kafka lưu các record trong log được chia thành các **partition**; consumer đọc record từ partition theo offset. Broker là tiến trình Kafka lưu trữ dữ liệu và phục vụ yêu cầu đọc/ghi. Một cụm Kafka thường có nhiều broker để phân tán tải và tăng khả năng chịu lỗi.

<escape>
Producer Order ── OrderCreated ──▶ Topic: orders
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                   Consumer       Consumer     Consumer
                   group: stock   group: mail  group: analytics
                   (Inventory)    (Notify)     (Analytics)
</escape>

Trong Kafka, topic đóng vai trò kênh sự kiện. Producer có thể gửi record mà không cần biết consumer nào đang hoạt động. Consumer tự chủ động poll dữ liệu từ Kafka; broker không cần mở một kết nối riêng để đẩy từng sự kiện đến từng subscriber.

Một điểm quan trọng: Kafka không xóa record ngay sau khi một consumer đọc xong. Record được giữ lại theo chính sách retention (thời gian hoặc dung lượng) và có thể được nhiều consumer group đọc độc lập. Vì vậy, một consumer mới có thể đọc lại dữ liệu cũ nếu cấu hình offset và retention cho phép.

## 3. Topic, partition và offset

### Topic

Topic là tên logic của một luồng record, thường được đặt theo loại sự kiện hoặc miền nghiệp vụ, chẳng hạn `orders`, `payments` hay `inventory-events`. Producer ghi vào topic; consumer đăng ký một hoặc nhiều topic để đọc.

Nên đặt tên topic thể hiện rõ nội dung và phạm vi nghiệp vụ. Với hệ thống lớn, cần thống nhất quy ước tên, schema, quyền truy cập và chính sách retention để các nhóm dịch vụ có thể tích hợp an toàn.

### Partition

Mỗi topic được chia thành một hoặc nhiều partition. Một partition là một log có thứ tự: record mới được nối vào cuối log và được đánh số bằng offset tăng dần. Các partition có thể nằm trên những broker khác nhau, giúp Kafka phân tán lưu trữ và xử lý.

Kafka chỉ đảm bảo thứ tự trong phạm vi một partition, không đảm bảo thứ tự tổng thể giữa nhiều partition. Nếu cần các sự kiện của cùng một đơn hàng được xử lý theo thứ tự, producer nên dùng `orderId` làm message key. Kafka sẽ ánh xạ cùng key vào cùng partition theo partitioner mặc định (trong điều kiện số partition và cấu hình tương ứng không thay đổi theo cách làm thay đổi ánh xạ).

Tăng số partition có thể tăng khả năng xử lý song song, nhưng cũng có thể thay đổi ánh xạ key sang partition và làm phức tạp yêu cầu thứ tự. Vì vậy cần chọn số partition dựa trên thông lượng, số consumer dự kiến và đặc tính nghiệp vụ.

### Offset

Offset là vị trí của một record trong một partition. Offset giúp consumer theo dõi vị trí đọc và tiếp tục từ vị trí đã lưu sau khi khởi động lại. Offset có ý nghĩa trong phạm vi từng partition, không phải số thứ tự toàn cục của topic.

Consumer group lưu tiến độ đọc (committed offset) cho từng partition. Khi consumer đọc record, điều đó không tự động có nghĩa offset đã được commit. Commit quá sớm có thể làm mất cơ hội xử lý lại khi ứng dụng gặp lỗi; commit quá muộn có thể khiến record được xử lý lặp sau khi khởi động lại. Do đó, thời điểm commit cần phù hợp với kết quả xử lý nghiệp vụ.

## 4. Consumer group tạo ra cách phân phối pub/sub

Consumer group là tập hợp các consumer cùng chia sẻ một `group.id`. Trong một group, mỗi partition tại một thời điểm được gán cho tối đa một consumer trong group. Các consumer cùng group vì vậy chia nhau tải của topic thay vì mỗi consumer đều nhận toàn bộ record.

Các group khác nhau đọc độc lập. Với topic `orders`, group `inventory-service` có thể xử lý giữ hàng, trong khi group `notification-service` xử lý gửi thông báo. Cả hai group đều có thể đọc cùng một record `OrderCreated`, mỗi group duy trì offset riêng.

| Cấu hình | Kết quả |
|---|---|
| Nhiều consumer trong cùng group | Chia partition và tải xử lý; một record thuộc partition được một consumer của group xử lý tại một thời điểm |
| Một consumer trong mỗi group khác nhau | Mỗi group có tiến độ đọc riêng và có thể đọc cùng dữ liệu |
| Số consumer trong group lớn hơn số partition | Một số consumer không được gán partition và ở trạng thái rảnh |
| Số consumer nhỏ hơn hoặc bằng số partition | Có thể xử lý song song trên nhiều partition, tùy số partition được gán và năng lực ứng dụng |

Ví dụ, topic có 4 partition và group có 2 consumer thì mỗi consumer thường nhận 2 partition. Nếu group có 5 consumer, tối đa 4 consumer có partition được gán; consumer còn lại không tăng thông lượng đọc của group. Khi thành viên group thay đổi, Kafka thực hiện rebalance để phân công lại partition.

## 5. Gửi và nhận sự kiện với Spring Kafka

Spring Kafka cung cấp `KafkaTemplate` để gửi record và `@KafkaListener` để khai báo phương thức nhận record. Cấu hình kết nối thường được đặt trong `application.yml`.

### Cấu hình cơ bản

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: notification-service
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.messaging
```

`bootstrap-servers` là danh sách địa chỉ broker để client khởi tạo kết nối. Serializer chuyển key/value thành byte trước khi gửi; deserializer chuyển byte thành kiểu dữ liệu ứng dụng khi nhận. Cấu hình JSON cần được thống nhất giữa producer và consumer, đặc biệt là kiểu dữ liệu, header type và danh sách package được tin cậy. Trong môi trường thực tế, nên cấu hình xác thực, mã hóa kết nối và schema compatibility theo yêu cầu triển khai.

### Producer dùng KafkaTemplate

```java
public record OrderCreated(String orderId, BigDecimal total) {}

@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

Lệnh `send` gửi record đến topic `orders`, dùng `orderId` làm key và sự kiện làm value. Kết quả trả về là `CompletableFuture`, nên ứng dụng có thể xử lý kết quả gửi bất đồng bộ, ghi log khi gửi thất bại hoặc bổ sung cơ chế retry phù hợp. Không nên coi việc gọi `send` là bằng chứng record đã được broker xác nhận; cần quan sát kết quả hoàn tất của future và cấu hình producer acknowledgement phù hợp.

### Consumer dùng @KafkaListener

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders", groupId = "notification-service")
    public void onOrderCreated(OrderCreated event) {
        // Xử lý nghiệp vụ: tạo yêu cầu gửi thông báo.
        System.out.printf("Order %s, total %s%n",
                event.orderId(), event.total());
    }
}
```

Spring Kafka quản lý vòng đời listener container và việc poll record. `groupId` xác định consumer group; các instance của cùng dịch vụ có thể tham gia cùng group để chia partition. Trong ứng dụng thực tế, nên chuyển xử lý nghiệp vụ sang service riêng, kiểm soát lỗi và bảo đảm thao tác có thể chịu được việc một sự kiện được giao lại.

## 6. Ví dụ luồng xử lý giữa các dịch vụ

Giả sử Order Service tạo đơn hàng. Sau khi đơn hàng được xác nhận, nó phát `OrderCreated` lên topic `orders`. Inventory Service đọc sự kiện trong group `inventory-service` để giữ hàng. Notification Service đọc cùng topic trong group `notification-service` để gửi email. Analytics Service có thể đọc trong group riêng để cập nhật báo cáo.

Các dịch vụ có thể triển khai và mở rộng độc lập. Khi cần thêm Fraud Detection, nhóm phát triển chỉ cần triển khai một consumer group mới đọc topic `orders`; Order Service không cần biết consumer mới tồn tại. Tuy nhiên, hợp đồng sự kiện phải ổn định: cần quy định tên và ý nghĩa field, phiên bản schema, thời điểm phát sự kiện và cách xử lý dữ liệu không tương thích.

Sự kiện nên mô tả một điều đã xảy ra, ví dụ `OrderCreated` hoặc `PaymentCaptured`, thay vì yêu cầu consumer thực hiện một lệnh tùy ý. Producer cần phát sự kiện tại thời điểm nghiệp vụ phù hợp. Nếu cập nhật cơ sở dữ liệu và gửi Kafka phải nhất quán, có thể xem xét Transactional Outbox để tránh tình trạng dữ liệu đã commit nhưng sự kiện không được gửi (hoặc ngược lại).

## 7. Những đặc tính cần hiểu khi vận hành

### Giao nhận và xử lý lặp

Trong thực tế, consumer có thể xử lý một record thành công nhưng chưa kịp commit offset trước khi dừng. Khi chạy lại, record đó có thể được đọc và xử lý lần nữa. Vì vậy, ứng dụng thường cần thiết kế handler idempotent: xử lý cùng một `eventId` nhiều lần vẫn không tạo ra tác dụng phụ trùng lặp. Có thể lưu event ID đã xử lý với ràng buộc duy nhất trong cơ sở dữ liệu hoặc dùng khóa nghiệp vụ phù hợp.

### Retry và dead-letter topic

Lỗi tạm thời như timeout hoặc dịch vụ phụ thuộc không sẵn sàng có thể được retry với số lần và khoảng chờ giới hạn. Lỗi dữ liệu không hợp lệ hoặc lỗi không thể khắc phục nên được chuyển đến dead-letter topic để điều tra và xử lý lại có kiểm soát. Retry vô hạn có thể giữ partition bị kẹt và làm tăng độ trễ cho các record phía sau.

### Thứ tự và song song

Thứ tự chỉ được bảo đảm trong một partition. Consumer xử lý song song bên trong ứng dụng cũng có thể làm thay đổi thứ tự hoàn tất, ngay cả khi record được poll theo thứ tự. Nếu nghiệp vụ phụ thuộc thứ tự, hãy dùng key ổn định, kiểm soát concurrency và tránh xử lý đồng thời các record cùng khóa.

### Retention và replay

Kafka giữ record theo cấu hình retention độc lập với việc consumer đã đọc hay chưa. Khi cần dựng lại projection hoặc sửa lỗi xử lý, consumer group có thể đọc lại dữ liệu còn được lưu. Việc replay phải được chuẩn bị để không gây lặp tác dụng phụ trong hệ thống bên ngoài.

## 8. Khi nào nên dùng mô hình này?

Pub/sub với Kafka phù hợp khi một sự kiện cần được nhiều hệ thống quan tâm, các bên cần triển khai độc lập, lưu lượng lớn hoặc cần khả năng phát lại dữ liệu. Mô hình cũng hữu ích khi muốn tách luồng xử lý chính khỏi các tác vụ phụ như gửi thông báo, cập nhật chỉ mục tìm kiếm và phân tích.

Kafka không tự giải quyết mọi vấn đề tích hợp. Với một lời gọi cần phản hồi ngay, truy vấn dữ liệu đồng bộ hoặc thao tác CRUD đơn giản, HTTP/gRPC có thể phù hợp hơn. Với Kafka, đội ngũ cần vận hành broker, theo dõi consumer lag, quản lý schema, phân quyền topic, retention, retry và dead-letter.

## 9. Tổng kết

- Producer công bố record lên topic; consumer chủ động đọc record từ Kafka.
- Topic được chia thành partition; mỗi partition là một log có thứ tự và offset riêng.
- Thứ tự được bảo đảm trong một partition, vì vậy key giúp gom các sự kiện liên quan vào cùng partition.
- Consumer cùng group chia partition; các group khác nhau có thể đọc cùng dữ liệu với offset độc lập.
- `KafkaTemplate` hỗ trợ gửi sự kiện và `@KafkaListener` hỗ trợ nhận sự kiện trong Spring Kafka.
- Thiết kế consumer cần tính đến commit offset, xử lý lặp, idempotency, retry, dead-letter và replay.

Khi nắm vững các thành phần này, có thể thiết kế luồng sự kiện giữa các dịch vụ sao cho publisher và subscriber ít phụ thuộc nhau, đồng thời kiểm soát được khả năng mở rộng và độ tin cậy khi vận hành.
