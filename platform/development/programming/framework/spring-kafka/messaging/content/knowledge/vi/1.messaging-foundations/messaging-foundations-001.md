# Spring Kafka giải quyết bài toán gì trong ứng dụng Spring

Trong một ứng dụng Spring, các thành phần thường cần trao đổi dữ liệu với nhau hoặc phối hợp với những hệ thống bên ngoài. Một cách quen thuộc là gọi REST API trực tiếp: dịch vụ A gửi yêu cầu đến dịch vụ B và chờ phản hồi. Cách này phù hợp khi cần kết quả ngay, nhưng có thể tạo ra chuỗi phụ thuộc chặt chẽ. Chẳng hạn, sau khi tạo đơn hàng, hệ thống còn phải cập nhật kho, gửi thông báo, ghi nhận dữ liệu phân tích và khởi tạo giao hàng. Nếu mọi việc đều được gọi đồng bộ, thời gian xử lý của yêu cầu tạo đơn hàng phụ thuộc vào tất cả dịch vụ phía sau. Một dịch vụ chậm hoặc tạm thời không hoạt động có thể làm cả luồng bị chậm hoặc thất bại.

Kafka cung cấp một cách giao tiếp khác: ứng dụng phát ra sự kiện lên một luồng dữ liệu, còn các ứng dụng quan tâm tự đọc và xử lý sự kiện đó. Spring Kafka giúp ứng dụng Spring sử dụng cơ chế này thông qua các thành phần quen thuộc của Spring như dependency injection, cấu hình ngoài, quản lý vòng đời và xử lý lỗi. Để hiểu Spring Kafka giải quyết bài toán gì, trước hết cần phân biệt vai trò của Kafka với vai trò của Spring Kafka.

## 1. Bài toán giao tiếp bất đồng bộ giữa các thành phần

Giả sử dịch vụ đơn hàng cần thông báo rằng một đơn hàng đã được tạo. Thay vì gọi lần lượt dịch vụ kho, thông báo và phân tích, dịch vụ đơn hàng có thể phát sự kiện `OrderCreated` lên topic `orders.created`.

Các dịch vụ khác đăng ký đọc topic đó theo nhu cầu:

- Dịch vụ kho nhận sự kiện để giữ hoặc trừ tồn kho.
- Dịch vụ thông báo gửi email hoặc thông báo đến người mua.
- Dịch vụ phân tích cập nhật số liệu kinh doanh.

Dịch vụ đơn hàng chỉ cần hoàn thành việc phát sự kiện theo chính sách xác nhận đã chọn. Các dịch vụ nhận sự kiện có thể xử lý độc lập, với tốc độ và thời điểm riêng. Việc thêm một consumer mới, chẳng hạn dịch vụ chăm sóc khách hàng, thường không đòi hỏi sửa luồng xử lý bên trong dịch vụ đơn hàng.

Mô hình này đem lại một số lợi ích:

1. **Giảm phụ thuộc trực tiếp:** bên phát sự kiện không cần biết tất cả bên nhận hoặc gọi API của từng bên.
2. **Xử lý ngoài luồng yêu cầu:** những công việc không cần hoàn thành trước khi trả phản hồi có thể được thực hiện bất đồng bộ.
3. **Tiếp nhận tải theo nhịp xử lý:** Kafka lưu giữ bản ghi trong khoảng thời gian cấu hình; consumer có thể đọc tiếp khi hoạt động trở lại, miễn là dữ liệu vẫn còn trong thời hạn lưu giữ.
4. **Một sự kiện, nhiều mục đích sử dụng:** nhiều consumer group độc lập có thể đọc cùng một topic, ví dụ nhóm kho và nhóm phân tích đều nhận được sự kiện tạo đơn.
5. **Có thể đọc lại dữ liệu:** consumer group có thể điều chỉnh vị trí đọc hoặc dùng một group mới để xử lý lại dữ liệu còn được lưu giữ.

Giao tiếp bất đồng bộ cũng có chi phí. Kết quả xử lý thường không xuất hiện ngay trong phản hồi tạo đơn hàng; hệ thống phải chấp nhận độ trễ và tính nhất quán cuối cùng. Consumer cần xử lý việc nhận lại bản ghi, lỗi tạm thời và trạng thái xử lý dở dang. Kafka cũng cần được triển khai, giám sát và vận hành như một hạ tầng riêng.

## 2. Những khái niệm Kafka cần nắm

Kafka lưu các bản ghi trong **topic**. Một bản ghi thường có key, value, timestamp và headers. Với ví dụ trên, topic có thể là `orders.created`, key là mã đơn hàng và value chứa nội dung sự kiện.

Topic được chia thành các **partition** để lưu trữ và xử lý song song. Mỗi bản ghi trong một partition có một **offset** tăng dần, dùng để xác định vị trí của bản ghi trong partition đó. Offset không phải mã định danh toàn cục cho mọi topic; nó chỉ có ý nghĩa trong phạm vi một partition.

Key có ảnh hưởng đến việc chọn partition. Với partitioner mặc định, các bản ghi có cùng key thường được đưa về cùng partition. Vì vậy, nếu dùng `orderId` làm key, các sự kiện của cùng một đơn hàng thường được đọc theo thứ tự trong cùng partition. Kafka bảo đảm thứ tự trong một partition, không bảo đảm một thứ tự tổng thể giữa mọi partition của topic.

Consumer đọc bản ghi từ topic. Các consumer có cùng **consumer group** phối hợp chia nhau những partition được gán cho group đó. Một partition tại một thời điểm chỉ được gán cho tối đa một consumer trong cùng group. Nếu có nhiều consumer group khác nhau, mỗi group có tiến độ đọc riêng và có thể nhận cùng một dữ liệu.

Ví dụ:

| Thành phần | Vai trò |
| --- | --- |
| Topic `orders.created` | Lưu các sự kiện tạo đơn hàng |
| Partition 0, 1, 2 | Chia dữ liệu để tăng khả năng lưu trữ và xử lý song song |
| Key `orderId` | Giúp các sự kiện của cùng đơn hàng thường đi cùng partition |
| Consumer group `inventory-service` | Đọc sự kiện để xử lý tồn kho |
| Consumer group `analytics-service` | Đọc cùng sự kiện để cập nhật phân tích |
| Offset | Ghi nhận vị trí đọc của từng partition trong mỗi group |

Kafka không hoạt động giống một hàng đợi đơn giản, nơi một thông điệp được lấy ra thì biến mất khỏi hệ thống. Bản ghi được giữ theo chính sách retention của topic. Consumer group lưu tiến độ đọc bằng offset; việc một group đã đọc bản ghi không ngăn group khác đọc bản ghi đó.

## 3. Spring Kafka bổ sung điều gì cho ứng dụng Spring?

Kafka có Java client để gửi và nhận bản ghi. Tuy nhiên, khi tích hợp trực tiếp client vào ứng dụng Spring, đội phát triển phải tự tổ chức nhiều phần như khởi tạo producer và consumer, quản lý vòng đời, chạy vòng lặp poll, cấu hình serializer, xử lý lỗi, điều phối luồng và tích hợp với transaction.

Spring Kafka cung cấp các abstraction để đưa những công việc đó vào mô hình lập trình Spring. Các thành phần chính gồm:

| Thành phần | Bài toán được hỗ trợ |
| --- | --- |
| `KafkaTemplate` | Gửi bản ghi đến topic bằng một API có thể inject vào service |
| `@KafkaListener` | Khai báo phương thức nhận và xử lý bản ghi |
| Listener container | Quản lý consumer, poll dữ liệu, gọi listener và điều phối vòng đời |
| Serializer và deserializer | Chuyển đổi dữ liệu giữa object hoặc kiểu Java và byte array trên Kafka |
| Error handler và retry | Xác định cách xử lý khi listener phát sinh lỗi |
| Dead-letter topic (DLT) | Chuyển bản ghi không thể xử lý sang nơi lưu riêng để kiểm tra hoặc xử lý lại |
| Transaction support | Phối hợp việc đọc, xử lý và ghi dữ liệu Kafka trong phạm vi transaction Kafka được cấu hình |

Khi dùng Spring Boot, Spring Kafka tích hợp với cơ chế cấu hình và auto-configuration của Boot. Các thuộc tính kết nối broker, producer và consumer thường được khai báo trong `application.yml` hoặc `application.properties`. Service có thể inject `KafkaTemplate`; phương thức có `@KafkaListener` được listener container quản lý.

Spring Kafka không thay thế Kafka broker. Broker vẫn chịu trách nhiệm lưu trữ, sao chép partition, quản lý metadata và phân phối bản ghi. Spring Kafka là lớp tích hợp phía ứng dụng, giúp sử dụng Kafka thuận tiện và nhất quán với hệ sinh thái Spring.

## 4. Luồng gửi và nhận cơ bản

Để minh họa, ví dụ sau dùng chuỗi làm key và value. Trong hệ thống thực tế, value thường là JSON hoặc một định dạng có schema như Avro hay Protobuf.

### Cấu hình kết nối

Với broker Kafka đang chạy tại máy cục bộ, cấu hình tối thiểu có thể như sau:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

`bootstrap-servers` chỉ ra địa chỉ broker dùng để khởi đầu kết nối. Producer dùng serializer để chuyển key và value thành byte trước khi gửi. Consumer dùng deserializer tương ứng để chuyển byte nhận được về kiểu Java.

`auto-offset-reset: earliest` được áp dụng khi consumer group chưa có offset đã commit hợp lệ cho partition, chẳng hạn khi group mới bắt đầu đọc. Thuộc tính này không tự đưa một group đang có offset quay lại đầu topic. Muốn đọc lại dữ liệu, cần chủ động thay đổi vị trí đọc hoặc sử dụng một consumer group mới, đồng thời bảo đảm dữ liệu vẫn còn trong retention.

Ứng dụng cần có dependency `spring-kafka`. Nếu dùng Spring Boot dependency management, nên để Boot quản lý phiên bản tương thích thay vì tự chọn một phiên bản Spring Kafka không đồng bộ.

### Gửi sự kiện bằng `KafkaTemplate`

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String eventJson) {
        return kafkaTemplate.send("orders.created", orderId, eventJson);
    }
}
```

`KafkaTemplate` được inject như một dependency Spring. Lệnh `send` chỉ rõ topic, key và value. Key là `orderId`, nhờ đó các sự kiện cùng đơn hàng thường được định tuyến vào cùng partition theo partitioner mặc định.

Trong các phiên bản Spring Kafka hiện đại, `send` trả về `CompletableFuture`. Mã gọi nên quan sát kết quả hoàn tất để biết việc gửi thành công hay thất bại và ghi nhận lỗi phù hợp. Không nên xem việc gọi `send` là bằng chứng rằng broker đã lưu bản ghi thành công.

### Nhận sự kiện bằng `@KafkaListener`

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
public class OrderProjectionListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        String orderId = record.key();
        String eventJson = record.value();

        // Chuyển đổi sự kiện và cập nhật read model tương ứng.
    }
}
```

`@KafkaListener` đánh dấu phương thức nhận bản ghi. Listener container tạo và quản lý Kafka consumer, gọi phương thức khi có dữ liệu, đồng thời phối hợp việc commit offset và xử lý lỗi theo cấu hình. Nhờ đó, mã nghiệp vụ tập trung vào việc diễn giải sự kiện và thực hiện tác vụ cần thiết.

Trong ứng dụng thật, producer và consumer có thể thuộc hai service riêng. Ví dụ trên đặt chúng cạnh nhau để làm rõ hai đầu của luồng dữ liệu; việc tách service phụ thuộc vào ranh giới nghiệp vụ và cách triển khai.

## 5. Những vấn đề vận hành Spring Kafka giúp tổ chức

Gửi và nhận được một bản ghi mới chỉ là bước đầu. Một luồng messaging đáng tin cậy cần xác định rõ dữ liệu, tiến độ đọc và hành vi khi có lỗi.

### Serialization và hợp đồng dữ liệu

Kafka lưu byte, vì vậy producer và consumer phải thống nhất cách diễn giải value. Với chuỗi JSON, hai phía cần thống nhất tên trường, kiểu dữ liệu và cách biểu diễn thời gian hoặc số tiền. Khi nhiều service cùng dùng một event, thay đổi schema cần có chiến lược tương thích ngược hoặc tương thích xuôi. Với hệ thống lớn, schema registry cùng Avro hoặc Protobuf có thể giúp quản lý hợp đồng dữ liệu rõ ràng hơn.

Không nên gửi nguyên một entity của cơ sở dữ liệu chỉ vì nó đã có sẵn trong ứng dụng. Event nên thể hiện sự kiện nghiệp vụ và chỉ mang những dữ liệu mà consumer cần. Điều này giảm phụ thuộc giữa cấu trúc lưu trữ nội bộ với hợp đồng tích hợp.

### Offset, xác nhận và xử lý lặp

Offset biểu diễn tiến độ đọc của consumer group. Nếu ứng dụng xử lý bản ghi xong nhưng dừng trước khi offset được commit, bản ghi có thể được đọc lại sau khi khởi động hoặc rebalance. Vì vậy, trong nhiều cấu hình thực tế, consumer cần được thiết kế theo hướng **at-least-once**: một bản ghi có thể được giao lại và logic nghiệp vụ phải chịu được việc xử lý lặp.

Một cách phổ biến là làm cho consumer có tính **idempotent**. Ví dụ, khi cập nhật trạng thái đơn hàng, ứng dụng kiểm tra event ID hoặc trạng thái đã xử lý trước khi áp dụng thay đổi. Với thao tác cộng dồn như trừ kho hoặc cộng tiền, việc nhận trùng có thể gây sai lệch nếu không có cơ chế chống trùng phù hợp.

### Retry và dead-letter topic

Không phải lỗi nào cũng nên xử lý giống nhau. Lỗi kết nối tạm thời có thể được thử lại với khoảng chờ tăng dần. Dữ liệu sai định dạng hoặc vi phạm quy tắc nghiệp vụ có thể không bao giờ thành công dù thử lại nhiều lần.

Spring Kafka hỗ trợ cấu hình error handler và retry. Khi đã hết số lần thử hoặc gặp loại lỗi được xem là không thể phục hồi, ứng dụng có thể chuyển bản ghi sang dead-letter topic (DLT). DLT cần giữ đủ thông tin để truy vết, như topic và partition gốc, offset, key, nguyên nhân lỗi và thời điểm xử lý. Đội vận hành cũng cần giám sát DLT và có quy trình sửa dữ liệu hoặc phát lại bản ghi; chỉ chuyển lỗi sang DLT không có nghĩa là sự cố đã được giải quyết.

### Partition và xử lý đồng thời

Spring Kafka cho phép tăng concurrency của listener container để nhiều consumer cùng xử lý một consumer group. Mức song song hữu ích bị giới hạn bởi số partition được gán cho group. Nếu topic có ba partition, tăng số consumer trong cùng group lên mười không làm một partition được xử lý song song bởi mười consumer.

Tăng concurrency có thể tăng thông lượng, nhưng cũng làm tăng số luồng xử lý và khả năng tranh chấp tài nguyên ở cơ sở dữ liệu hoặc dịch vụ phía sau. Nếu nghiệp vụ cần giữ thứ tự theo đơn hàng, cần chọn key nhất quán và tránh tự tạo thêm xử lý song song làm đảo thứ tự giữa các bản ghi cùng key.

### Transaction và exactly-once

Spring Kafka hỗ trợ Kafka transaction để phối hợp việc tiêu thụ bản ghi, tạo kết quả và ghi kết quả trở lại Kafka trong cùng phạm vi transaction. Khi cấu hình đúng producer transaction và consumer đọc theo isolation phù hợp, có thể xây dựng luồng consume-process-produce với ngữ nghĩa exactly-once trong phạm vi Kafka.

Điều đó không tự động tạo ra transaction nguyên tử giữa Kafka và một cơ sở dữ liệu quan hệ. Nếu consumer vừa cập nhật database vừa commit offset Kafka, tiến trình vẫn có thể dừng ở khoảng giữa hai thao tác. Các mẫu như transactional outbox, inbox hoặc idempotency thường được dùng để xử lý ranh giới này. Cần xác định chính xác phạm vi bảo đảm trước khi gọi một luồng xử lý là exactly-once.

### Kiểm thử

Kiểm thử producer và consumer nên xác minh cả nội dung lẫn hành vi của luồng dữ liệu: key/value được serialize đúng, consumer đọc đúng topic và group, lỗi được retry theo chính sách, bản ghi lỗi được chuyển đến DLT và xử lý lặp không làm sai trạng thái. Có thể dùng Embedded Kafka hoặc Kafka Testcontainers cho kiểm thử tích hợp. Unit test riêng cho phần xử lý nghiệp vụ vẫn hữu ích, nhưng không thay thế kiểm thử với broker thật khi cần xác minh serialization, partition và offset.

## 6. Khi nào nên dùng Spring Kafka?

Spring Kafka phù hợp khi ứng dụng cần một hoặc nhiều đặc điểm sau:

- Phát sự kiện để nhiều hệ thống độc lập cùng quan tâm.
- Xử lý công việc bất đồng bộ, không cần giữ người dùng chờ toàn bộ chuỗi tác vụ.
- Tiếp nhận lượng sự kiện lớn và mở rộng consumer theo partition.
- Lưu giữ sự kiện trong một khoảng thời gian để consumer có thể đọc tiếp hoặc xử lý lại.
- Xây dựng pipeline dữ liệu, tích hợp dịch vụ hoặc kiến trúc hướng sự kiện.

Gọi REST đồng bộ thường phù hợp hơn khi bên gọi cần kết quả ngay, cần truy vấn dữ liệu hiện tại hoặc cần phản hồi lỗi trực tiếp trong cùng request. Với tác vụ nền nhỏ chỉ tồn tại trong một ứng dụng, một executor hoặc hàng đợi nội bộ có thể đơn giản hơn. Kafka phát huy giá trị khi cần luồng sự kiện bền vững, nhiều consumer độc lập hoặc thông lượng lớn đủ để biện minh cho chi phí vận hành.

## 7. Kết luận

Kafka cung cấp nền tảng lưu trữ và phân phối luồng sự kiện giữa các ứng dụng. Spring Kafka đưa nền tảng đó vào ứng dụng Spring bằng các abstraction như `KafkaTemplate`, `@KafkaListener`, listener container, serializer, error handler và transaction support.

Nhờ vậy, ứng dụng có thể tách bên phát sự kiện khỏi bên xử lý, tổ chức công việc bất đồng bộ và mở rộng các consumer độc lập. Để luồng messaging đáng tin cậy, đội phát triển vẫn phải thiết kế hợp đồng dữ liệu, key và partition, chính sách offset, khả năng xử lý lặp, retry, DLT, transaction và kiểm thử. Spring Kafka cung cấp công cụ để triển khai những quyết định đó; độ tin cậy cuối cùng phụ thuộc vào cách ứng dụng cấu hình và xử lý nghiệp vụ.
