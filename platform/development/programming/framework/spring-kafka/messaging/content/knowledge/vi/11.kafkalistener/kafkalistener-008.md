# Khai báo topicPattern

Khi một listener cần nhận dữ liệu từ một nhóm topic có tên theo quy ước, khai báo từng topic trong `topics` có thể trở nên khó bảo trì. Ví dụ, hệ thống tạo các topic `orders.created`, `orders.updated`, `orders.cancelled` theo loại sự kiện, hoặc tạo topic theo tenant như `tenant-101.orders`, `tenant-102.orders`. Spring Kafka hỗ trợ thuộc tính `topicPattern` trong `@KafkaListener` để đăng ký consumer bằng biểu thức chính quy (regular expression).

Với `topicPattern`, Kafka consumer đăng ký một pattern và tự phát hiện các topic hiện có hoặc mới được tạo có tên khớp pattern khi metadata được cập nhật. Cách này phù hợp với hệ thống có topic động hoặc nhiều topic tuân theo một naming convention. Cần chọn pattern đủ hẹp để listener chỉ nhận đúng nhóm dữ liệu mà nó có trách nhiệm xử lý.

## 1. `topicPattern` là gì?

`topicPattern` là thuộc tính của `@KafkaListener`, nhận một chuỗi biểu diễn Java regular expression. Spring Kafka chuyển pattern này cho Kafka consumer để đăng ký dạng pattern subscription.

Ví dụ:

```java
@KafkaListener(
        topicPattern = "orders\\..*",
        groupId = "order-projection")
public void consume(String payload) {
    // Xử lý sự kiện từ các topic có tên bắt đầu bằng orders.
}
```

Pattern `orders\\..*` trong Java string biểu diễn regex `orders\..*`:

- `orders` là phần tên cố định.
- `\.` khớp dấu chấm thật trong tên topic; dấu `.` không escape sẽ có nghĩa là một ký tự bất kỳ trong regex.
- `.*` khớp phần tên còn lại, kể cả chuỗi rỗng.

Vì vậy pattern có thể khớp `orders.created`, `orders.updated` và `orders.audit.v2`. Nó cũng có thể khớp `orders.` nếu topic đó tồn tại. Pattern không tự tạo topic; nó chỉ đăng ký nhận dữ liệu từ các topic phù hợp được Kafka phát hiện.

Kafka áp dụng regex để kiểm tra toàn bộ tên topic. Vì vậy, pattern `orders` chỉ khớp topic có tên chính xác là `orders`; muốn khớp các topic có tiền tố `orders.`, cần thêm phần mở rộng như `orders\..*`.

## 2. Khác biệt giữa `topics`, `topicPattern` và `topicPartitions`

`@KafkaListener` cung cấp ba cách chỉ định nguồn dữ liệu phổ biến:

| Thuộc tính | Cách đăng ký | Khi phù hợp |
| --- | --- | --- |
| `topics` | Danh sách tên topic cố định | Ứng dụng biết chính xác topic cần đọc |
| `topicPattern` | Regex khớp tên topic | Topic được tạo động hoặc có quy ước đặt tên |
| `topicPartitions` | Chỉ định topic và partition cụ thể | Cần gán thủ công một tập partition |

Ví dụ dùng `topics`:

```java
@KafkaListener(
        topics = {"orders.created", "orders.updated"},
        groupId = "order-projection")
public void consume(String payload) {
    // Nhận dữ liệu từ hai topic đã khai báo.
}
```

Ví dụ dùng `topicPattern`:

```java
@KafkaListener(
        topicPattern = "orders\\.(created|updated)",
        groupId = "order-projection")
public void consume(String payload) {
    // Nhận dữ liệu từ orders.created hoặc orders.updated.
}
```

Ví dụ dùng `topicPartitions`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.TopicPartition;

@KafkaListener(
        topicPartitions = @TopicPartition(
                topic = "orders.events",
                partitions = {"0", "2"}),
        groupId = "order-projection")
public void consume(String payload) {
    // Chỉ nhận partition 0 và 2 của orders.events.
}
```

Ba thuộc tính trên là các cách đăng ký subscription khác nhau; không khai báo đồng thời `topics`, `topicPattern` và `topicPartitions` trong cùng một listener. Hãy chọn cách phù hợp với yêu cầu định tuyến và phân công partition.

## 3. Cú pháp regex thường dùng

Một số thành phần regex hữu ích khi đặt tên topic:

| Regex | Ý nghĩa | Ví dụ topic khớp |
| --- | --- | --- |
| `orders\..*` | Bắt đầu bằng `orders.` rồi theo sau là chuỗi bất kỳ | `orders.created`, `orders.v2.audit` |
| `orders\.(created|updated)` | Chỉ một trong hai hậu tố | `orders.created`, `orders.updated` |
| `tenant-[0-9]+\.orders` | `tenant-`, một hoặc nhiều chữ số, rồi `.orders` | `tenant-101.orders` |
| `(orders|payments)\..*` | Bắt đầu bằng `orders.` hoặc `payments.` | `orders.created`, `payments.completed` |
| `events\.v[0-9]+\..*` | Topic có version số | `events.v1.orders`, `events.v2.users` |

Trong Java annotation, dấu gạch chéo ngược của regex phải được escape thêm một lần trong string literal. Ví dụ regex `orders\..*` được viết thành `"orders\\..*"` trong Java source.

Nếu pattern đặt trong YAML, có thể dùng single-quoted scalar để giữ nguyên dấu gạch chéo:

```yaml
app:
  kafka:
    topic-pattern: 'orders\.(created|updated|cancelled)'
```

Không nên dùng `.*` một cách tùy tiện. Pattern quá rộng có thể khiến listener đăng ký cả các topic không thuộc nghiệp vụ, làm tăng số partition, consumer lag, lưu lượng mạng và nguy cơ xử lý nhầm dữ liệu.

## 4. Khai báo `topicPattern` trong @KafkaListener

Ví dụ listener nhận tất cả topic sự kiện đơn hàng có hậu tố phù hợp:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
            id = "order-event-listener",
            topicPattern = "orders\\.(created|updated|cancelled)",
            groupId = "order-projection")
    public void onMessage(ConsumerRecord<String, String> record) {
        String topic = record.topic();
        String orderId = record.key();
        String payload = record.value();

        // Xử lý event dựa trên topic và payload.
    }
}
```

Ở đây listener đăng ký pattern cho ba loại topic. Dùng `ConsumerRecord` giúp xác định chính xác record đến từ topic nào, từ đó có thể phân biệt cách xử lý `created`, `updated` và `cancelled`.

Nếu các topic có cùng schema và cùng quy tắc xử lý, listener có thể nhận DTO chung. Nếu mỗi topic có schema khác nhau, cần có chiến lược deserialize và dispatch rõ ràng; chỉ dựa vào tên topic không giải quyết được sự khác biệt kiểu dữ liệu.

## 5. Đưa pattern ra cấu hình ngoài

Không nhất thiết hard-code regex trong annotation. Spring Kafka hỗ trợ property placeholder trong thuộc tính `topicPattern`:

```yaml
app:
  kafka:
    topic-pattern: 'orders\.(created|updated|cancelled)'

spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
```

```java
@Component
public class OrderEventListener {

    @KafkaListener(
            id = "order-event-listener",
            topicPattern = "${app.kafka.topic-pattern}",
            groupId = "${spring.kafka.consumer.group-id}")
    public void onMessage(ConsumerRecord<String, String> record) {
        // Xử lý record.
    }
}
```

Lưu ý: trong YAML single-quoted string, chỉ cần một dấu `\` để biểu diễn regex escape. Ví dụ `orders\.` ở YAML sẽ được đưa vào property dưới dạng `orders\.` (một dấu gạch chéo ngược trước dấu chấm). Trong Java annotation literal viết trực tiếp, cần hai dấu gạch chéo ngược trong source: `orders\\.`.

Tách pattern ra cấu hình giúp dùng regex khác nhau theo profile local, test hoặc production mà không phải sửa code. Hãy xác minh property sau khi Spring Boot bind và kiểm tra log khởi động nếu pattern không hợp lệ.

## 6. Topic động được phát hiện như thế nào?

Khi consumer đăng ký bằng pattern, Kafka client dùng metadata của cluster để tìm các topic khớp regex. Khi một topic mới được tạo và metadata được làm mới, consumer có thể tự động đăng ký các partition của topic đó.

Ví dụ:

```text
Pattern: orders\..*

Ban đầu:
  orders.created
  orders.updated

Sau đó tạo thêm:
  orders.cancelled

Consumer pattern subscription:
  orders.created      -> được đăng ký
  orders.updated      -> được đăng ký
  orders.cancelled    -> được phát hiện sau metadata refresh
```

Việc phát hiện topic mới không nhất thiết xảy ra ngay tại thời điểm topic được tạo. Kafka client làm mới metadata theo cơ chế và cấu hình của phiên bản client; thuộc tính `metadata.max.age.ms` liên quan đến chu kỳ làm mới metadata định kỳ. Có thể có những lần refresh sớm hơn do hoạt động của client hoặc thay đổi metadata. Vì vậy, không thiết kế quy trình nghiệp vụ phụ thuộc vào việc listener nhận topic mới ngay lập tức sau lệnh tạo topic.

Khi topic mới khớp pattern được phát hiện, consumer group có thể cần rebalance để phân bổ partition mới cho các consumer. Trong thời gian rebalance, việc xử lý có thể tạm gián đoạn. Ứng dụng cần xử lý record idempotent và theo dõi log/metric rebalance nếu topic được tạo thường xuyên.

Khi một topic bị xóa, metadata cũng cần được cập nhật để consumer phản ánh thay đổi subscription và assignment. Việc xóa topic khi consumer đang hoạt động cần được điều phối cẩn thận, nhất là khi còn record chưa xử lý.

## 7. Consumer group khi dùng topicPattern

`topicPattern` xác định tập topic mà consumer đăng ký; `groupId` xác định nhóm consumer phối hợp đọc các partition thuộc tập đó.

Nếu ba consumer cùng dùng pattern `orders\..*` và cùng `groupId=order-projection`, Kafka phân phối các partition của tất cả topic khớp pattern giữa ba consumer. Một partition trong group tại một thời điểm chỉ được gán cho một consumer.

Nếu một consumer group khác, chẳng hạn `order-analytics`, cũng đăng ký cùng pattern, group đó có tiến độ offset riêng và có thể đọc cùng các record độc lập với `order-projection`.

Điều này có nghĩa:

- Cùng pattern và cùng group ID: các consumer chia nhau tải trên các partition phù hợp.
- Cùng pattern nhưng group ID khác: mỗi group nhận luồng dữ liệu riêng và commit offset riêng.
- Thêm topic khớp pattern: các partition mới tham gia group subscription và có thể gây rebalance.

Không dùng một group ID chung cho hai ứng dụng nếu mục tiêu là cả hai ứng dụng đều phải nhận đầy đủ mọi event. Khi dùng chung group, chúng sẽ chia tải thay vì mỗi ứng dụng nhận một bản sao độc lập.

## 8. Chọn pattern theo ranh giới nghiệp vụ

Một pattern tốt thể hiện đúng nhóm topic thuộc cùng một consumer logic. Ví dụ:

| Nhóm topic | Pattern đề xuất | Mục đích |
| --- | --- | --- |
| Sự kiện đơn hàng | `orders\.(created|updated|cancelled)` | Một projection xử lý vòng đời đơn hàng |
| Sự kiện thanh toán | `payments\.(authorized|captured|refunded)` | Một consumer tổng hợp trạng thái thanh toán |
| Topic theo tenant | `tenant-[0-9]+\.orders` | Xử lý các topic đơn hàng của tenant có ID số |
| Event version 2 | `events\.v2\..*` | Tách consumer cho hợp đồng dữ liệu phiên bản 2 |

Không nên gom các topic chỉ vì chúng có cùng tiền tố nếu schema, quyền truy cập hoặc logic xử lý khác nhau. Một listener nhận nhiều topic vẫn cần phân biệt nguồn dữ liệu và xác thực payload phù hợp trước khi áp dụng nghiệp vụ.

Với topic theo tenant, cân nhắc số lượng topic và partition tổng cộng. Hàng nghìn topic với nhiều partition có thể làm tăng metadata, số assignment và chi phí vận hành của consumer group. Nếu dữ liệu có thể được phân vùng bằng key trong một số topic dùng chung, mô hình đó có thể đơn giản hơn việc tạo một topic cho mỗi tenant.

## 9. Quyền truy cập và bảo vệ dữ liệu

Pattern subscription chỉ giúp chọn tên topic. Nó không cấp quyền đọc topic. Trong cluster bật authorization, principal của ứng dụng cần có quyền phù hợp để khám phá topic và đọc các topic/partition được đăng ký. Quyền cụ thể phụ thuộc cấu hình bảo mật và cơ chế ACL của cluster.

Một pattern quá rộng có thể khiến consumer thử đăng ký topic mà principal không được phép đọc. Khi đó, listener có thể gặp lỗi authorization hoặc chỉ đọc được một phần tập topic mong muốn. Hãy phối hợp naming convention, regex và ACL để giới hạn đúng phạm vi.

Tránh pattern chung như `.*` trong production nếu không có yêu cầu rõ ràng. Pattern rộng làm tăng rủi ro nhận dữ liệu ngoài phạm vi, kể cả các topic nội bộ hoặc topic do nhóm khác quản lý. Không log payload hoặc header nhạy cảm chỉ vì listener dùng chung cho nhiều topic.

## 10. Kiểm thử topicPattern

Kiểm thử tích hợp nên xác minh listener nhận record từ nhiều topic khớp pattern và không nhận topic ngoài pattern.

Ví dụ cấu hình test với Embedded Kafka:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(properties = {
        "app.kafka.topic-pattern=orders\\..*",
        "spring.kafka.consumer.auto-offset-reset=earliest"
})
@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.created", "orders.updated", "payments.created"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class TopicPatternListenerTest {
    // Inject KafkaTemplate và listener test để gửi/kiểm tra record.
}
```

Với pattern `orders\..*`, listener cần nhận record từ `orders.created` và `orders.updated`; topic `payments.created` không khớp. Trong test hoàn chỉnh, có thể dùng `BlockingQueue<ConsumerRecord<?, ?>>` hoặc một spy bean để ghi nhận record listener nhận được, sau đó assert tên topic và payload.

Nếu test phụ thuộc vào assignment, hãy chờ listener container được gán đủ partition trước khi gửi record, ví dụ dùng `ContainerTestUtils.waitForAssignment(...)` với `KafkaListenerEndpointRegistry`. Điều này tránh race condition khi producer gửi trước khi listener sẵn sàng.

Để kiểm tra discovery động, tạo một topic mới sau khi listener đã chạy, đợi metadata refresh và rebalance hoàn tất, sau đó gửi record vào topic mới. Test này cần timeout hợp lý vì thời gian phát hiện topic không nhất thiết tức thời. Không dùng sleep cố định ngắn rồi kết luận pattern subscription không hoạt động.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Listener không nhận topic mong muốn | Regex sai hoặc dấu chấm chưa escape | Kiểm tra pattern bằng Java regex và tên topic thực tế |
| Pattern chỉ khớp một tên topic | Dùng regex literal thay vì wildcard | Dùng `.*`, nhóm `(a|b)` hoặc lớp ký tự phù hợp |
| Pattern trong Java không khớp | Escape dấu `\` chưa đúng | Nhớ rằng Java string cần escape thêm một lần |
| Topic mới không được nhận ngay | Client chưa làm mới metadata hoặc chưa rebalance | Kiểm tra metadata refresh, log và consumer assignment |
| Listener nhận quá nhiều topic | Pattern quá rộng | Giới hạn tiền tố, hậu tố hoặc version cụ thể |
| Một ứng dụng không nhận đủ record | Hai ứng dụng dùng chung group ID | Dùng group ID riêng nếu mỗi ứng dụng cần bản sao độc lập |
| Authorization exception | Principal không có quyền với topic được pattern khớp | Kiểm tra ACL, quyền discover và read |
| Listener xử lý sai schema | Nhiều topic có payload không đồng nhất | Phân biệt schema/topic và cấu hình deserializer phù hợp |

## 12. Kết luận

`topicPattern` trong `@KafkaListener` cho phép Spring Kafka đăng ký consumer bằng regex thay vì liệt kê từng topic. Cách này phù hợp khi topic được tạo động hoặc tuân theo một naming convention ổn định. Kafka client có thể phát hiện topic mới khớp pattern khi metadata được làm mới; việc đó có thể dẫn đến rebalance trong consumer group.

Hãy viết regex hẹp theo ranh giới nghiệp vụ, escape đúng dấu chấm, đưa pattern ra cấu hình ngoài khi cần và chọn `groupId` theo mục đích chia tải hay nhận bản sao độc lập. Pattern không tạo topic và cũng không cấp quyền đọc; topic phải tồn tại, principal phải có quyền phù hợp, và listener cần được kiểm thử với nhiều topic cùng các trường hợp topic động.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-driven.html)
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
