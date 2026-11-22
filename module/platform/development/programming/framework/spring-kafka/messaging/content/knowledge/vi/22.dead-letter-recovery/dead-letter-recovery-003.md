# Xác định tên topic dead letter

## 1. Topic dead letter dùng để làm gì?

Trong Spring Kafka, khi listener xử lý record thất bại và các lần retry đã hết, ứng dụng có thể chuyển record sang một topic riêng để điều tra hoặc phục hồi sau. Topic này thường được gọi là dead-letter topic (DLT), đôi khi được gọi là dead-letter queue (DLQ).

Ví dụ, consumer group `order-projection` đọc topic `orders`. Một record có payload hợp lệ về mặt Kafka nhưng không thể chuyển đổi hoặc cập nhật database. Sau số lần retry đã cấu hình, `DeadLetterPublishingRecoverer` có thể gửi record sang `orders.DLT`. Consumer xử lý luồng chính tiếp tục với record kế tiếp theo chính sách recovery.

DLT giúp tách record cần điều tra khỏi luồng xử lý bình thường. Nó không tự sửa dữ liệu, không tự bảo đảm record sẽ được xử lý lại và cũng không thay thế việc ghi log, cảnh báo hoặc quy trình vận hành.

## 2. Tên DLT mặc định của Spring Kafka

`DeadLetterPublishingRecoverer` cho phép chỉ định một hàm quyết định topic và partition đích. Nếu dùng constructor mặc định chỉ truyền Kafka template, Spring Kafka áp dụng quy ước:

- Topic đích là tên topic gốc cộng hậu tố `.DLT`.
- Partition đích là partition của record gốc.

Ví dụ:

| Topic nguồn | Partition nguồn | DLT mặc định | Partition DLT |
|---|---:|---|---:|
| `orders` | 0 | `orders.DLT` | 0 |
| `orders` | 3 | `orders.DLT` | 3 |
| `payments` | 1 | `payments.DLT` | 1 |
| `inventory.events` | 2 | `inventory.events.DLT` | 2 |

Quy ước này dễ dự đoán: nhìn tên DLT có thể biết record đến từ topic nào. Khi giữ nguyên partition, DLT cần có số partition đủ để nhận mọi partition nguồn. Nếu `orders` có 6 partition, `orders.DLT` cần có ít nhất 6 partition để ánh xạ partition 0 đến 5.

Không nhầm tên DLT với tên retry topic. Retry topic thường giữ record để thử lại sau một khoảng trễ; DLT là nơi lưu record đã hết chính sách retry hoặc được xác định là không thể xử lý theo luồng hiện tại.

~~~mermaid
flowchart TD
    A["Topic orders"] --> B["Consumer group order-projection"]
    B --> C{"Listener xử lý thành công?"}
    C -->|Có| D["Commit offset theo AckMode"]
    C -->|Không| E["DefaultErrorHandler"]
    E --> F{"Còn lần retry?"}
    F -->|Có| G["Backoff rồi gọi listener lại"]
    G --> C
    F -->|Không| H["DeadLetterPublishingRecoverer"]
    H --> I["Topic orders.DLT"]
    I --> J["Điều tra / sửa dữ liệu / replay có kiểm soát"]
~~~

## 3. Cấu hình topic và partition đích bằng DeadLetterPublishingRecoverer

Khi muốn chỉ định rõ quy tắc đặt tên, dùng constructor nhận destination resolver. Resolver nhận record gốc và exception, sau đó trả về `TopicPartition` chứa tên topic và partition đích.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterConfiguration {

    @Bean
    DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

        // Không xem recovery là thành công nếu gửi DLT thất bại.
        recoverer.setFailIfSendResultIsError(true);

        return recoverer;
    }
}
~~~

Resolver trong ví dụ thể hiện tường minh quy tắc mặc định: lấy topic gốc, thêm `.DLT` và giữ nguyên partition. Việc khai báo tường minh hữu ích khi sau này cần đổi naming convention hoặc thêm định tuyến theo loại lỗi.

`setFailIfSendResultIsError(true)` yêu cầu recoverer báo lỗi nếu việc publish DLT thất bại. Nếu DLT publish không thành công, record chưa được phục hồi an toàn; error handler cần tiếp tục xem đó là lỗi recovery thay vì âm thầm bỏ qua. Kiểm tra API theo phiên bản Spring Kafka đang sử dụng.

## 4. Gắn recoverer vào DefaultErrorHandler

Recoverer thường được sử dụng sau khi retry của listener đã hết. Bean `DefaultErrorHandler` cần được gắn vào listener container factory mà listener sử dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer deadLetterPublishingRecoverer) {

    return new DefaultErrorHandler(
        deadLetterPublishingRecoverer,
        new FixedBackOff(1000L, 2L)
    );
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener tham chiếu factory này:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-projection",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void handle(OrderCreatedEvent event) {
    orderProjectionService.apply(event);
}
~~~

`FixedBackOff(1000L, 2L)` minh họa chờ một giây giữa các lần thử lại, tối đa hai lần retry bổ sung sau lần gọi đầu tiên. Khi hết retry, error handler gọi recoverer để publish DLT.

Nếu listener dùng factory khác, cấu hình error handler trên đúng factory đó. Chỉ khai báo bean recoverer mà không gắn error handler vào container sẽ không làm listener tự động chuyển record sang DLT.

## 5. Các quy ước đặt tên DLT thường dùng

Không có một tên hậu tố duy nhất bắt buộc cho mọi hệ thống. Điều quan trọng là tên topic ổn định, có thể dự đoán và được producer, consumer, vận hành thống nhất.

| Quy ước | Ví dụ với topic `orders` | Khi phù hợp |
|---|---|---|
| Theo topic nguồn | `orders.DLT` | Mặc định đơn giản; các consumer group có thể cùng đưa lỗi vào một DLT |
| Theo topic và consumer group | `orders.order-projection.DLT` | Mỗi subscriber cần hàng đợi lỗi và quyền replay riêng |
| Theo topic và nhóm lỗi | `orders.invalid.DLT`, `orders.dependency.DLT` | Có quy trình xử lý khác nhau theo nhóm lỗi ổn định |
| Có namespace môi trường | `prod.orders.DLT` | Nhiều môi trường dùng chung một Kafka cluster |
| Theo domain rồi topic | `commerce.orders.DLT` | Tổ chức topic theo domain hoặc bounded context |

### Dùng một DLT chung cho topic nguồn

`orders.DLT` là lựa chọn đơn giản khi một record lỗi cần được điều tra tập trung. Nếu nhiều consumer group cùng đọc `orders`, các record lỗi của chúng có thể được gửi chung vào DLT này.

Ưu điểm là ít topic và dễ tìm record lỗi. Tuy nhiên, consumer vận hành DLT cần biết record lỗi từ group nào; metadata gốc do recoverer thêm vào có thể hỗ trợ việc này. Các nhóm cũng cần thống nhất quyền truy cập và quy trình replay.

Spring Kafka thêm các header dead-letter để lưu thông tin record ban đầu và nguyên nhân phục hồi, chẳng hạn topic, partition, offset gốc cùng loại exception. Consumer DLT có thể đọc metadata này để xác định nguồn record; tên topic DLT và header nguồn bổ sung cho nhau.

### Tách DLT theo consumer group

Nếu `order-projection` và `fraud-monitor` có chủ sở hữu, SLA và quy trình khôi phục khác nhau, có thể tách:

- `orders.order-projection.DLT`
- `orders.fraud-monitor.DLT`

Cách này giảm việc một nhóm replay nhầm record thuộc trách nhiệm nhóm khác. Tuy nhiên, tên group ID Kafka có thể chứa ký tự không phù hợp với quy tắc tên topic hoặc quá dài. Nếu đưa group vào tên DLT, hãy dùng một mã định danh ngắn, ổn định và được cấu hình rõ ràng, không nối nguyên group ID tùy tiện.

Resolver cần biết subscriber mà nó phục vụ. Thông thường, tạo recoverer riêng cho từng container hoặc truyền một định danh subscriber ổn định vào cấu hình recoverer.

~~~java
@Bean
DeadLetterPublishingRecoverer orderProjectionRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    String subscriber = "order-projection";

    return new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + "." + subscriber + ".DLT",
            record.partition()
        )
    );
}
~~~

Trong ví dụ, subscriber là cấu hình tĩnh của recoverer. Không suy ra consumer group từ payload hoặc header không đáng tin cậy.

### Tách DLT theo nhóm lỗi

Có thể phân luồng một số lỗi có cách phục hồi khác nhau:

- `orders.invalid.DLT` lưu payload không hợp lệ hoặc vi phạm contract.
- `orders.dependency.DLT` lưu record hết retry do dependency downstream.
- `orders.processing.DLT` lưu lỗi xử lý còn lại cần điều tra.

Chỉ nên tạo một số nhóm lỗi ổn định có chủ sở hữu và quy trình cụ thể. Không tạo topic theo tên exception, event ID hoặc từng request; cách đó làm tăng số topic, ACL, cấu hình và chi phí vận hành.

## 6. Resolver định tuyến theo loại lỗi

Destination resolver có thể xét exception để chọn DLT. Ví dụ sau minh họa hai nhóm lỗi: dữ liệu không hợp lệ và lỗi xử lý còn lại.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Bean
DeadLetterPublishingRecoverer categorizedRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltKafkaTemplate,
        (record, exception) -> {
            String suffix =
                exception instanceof InvalidOrderEventException
                    ? ".invalid.DLT"
                    : ".failed.DLT";

            return new TopicPartition(
                record.topic() + suffix,
                record.partition()
            );
        }
    );
}
~~~

Đây là ví dụ tối giản. Trong ứng dụng thật, exception có thể được bọc bởi exception của listener adapter hoặc framework. Nếu cần phân loại theo nguyên nhân gốc, hãy duyệt cause chain có giới hạn và dùng các exception nghiệp vụ riêng biệt. Không dựa vào chuỗi message của exception vì nội dung có thể thay đổi theo phiên bản hoặc ngôn ngữ.

Nếu lỗi tạm thời có khả năng phục hồi, nên retry với backoff hoặc dùng retry topic có delay thay vì đưa ngay vào DLT. DLT phù hợp với record đã hết chính sách retry hoặc lỗi không thể xử lý tự động.

## 7. Giữ hay thay đổi partition khi chuyển sang DLT?

Có hai chiến lược chính.

| Chiến lược | Cách resolver trả về | Kết quả |
|---|---|---|
| Giữ partition nguồn | `new TopicPartition(dltTopic, record.partition())` | Record ở partition Pn nguồn sang partition Pn của DLT |
| Để producer chọn partition | `new TopicPartition(dltTopic, -1)` | Kafka producer chọn partition theo key/partitioner |

Giữ partition nguồn hữu ích khi muốn dễ đối chiếu và giữ quan hệ partition giữa topic chính và DLT. Khi dùng cách này, DLT phải có partition tương ứng với mọi partition nguồn.

Nếu trả partition `-1`, producer chọn partition theo cơ chế partitioner. Điều này có thể hữu ích khi DLT có số partition khác topic nguồn, nhưng record không còn được ánh xạ vào cùng chỉ số partition. Không dựa vào cách này nếu quy trình vận hành cần đối chiếu partition một-một hoặc yêu cầu thứ tự theo partition nguồn.

Dù giữ partition, DLT vẫn là topic khác. Không có thứ tự toàn cục giữa topic nguồn và DLT. Nếu cần xử lý thứ tự nghiệp vụ, phải thiết kế theo key, partition và quy trình replay phù hợp.

## 8. Tạo DLT topic và cấu hình vận hành

Tên topic trong resolver không tự bảo đảm topic đã tồn tại. Cần tạo DLT trước khi record lỗi được publish hoặc cấu hình cơ chế tự tạo topic có kiểm soát.

Có thể khai báo `NewTopic` bean trong Spring Kafka:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DeadLetterTopicConfiguration {

    @Bean
    NewTopic ordersDltTopic() {
        // Ví dụ topic nguồn có 6 partition.
        return new NewTopic("orders.DLT", 6, (short) 3);
    }
}
~~~

Spring Boot thường cấu hình `KafkaAdmin` để tạo các `NewTopic` bean khi ứng dụng khởi động. Số partition và replication factor trong ví dụ chỉ mang tính minh họa: DLT giữ partition nguồn cần có đủ partition tương ứng; replication factor không được vượt số broker phù hợp trong cluster.

Trong production, nhiều tổ chức quản lý topic bằng Infrastructure as Code hoặc quy trình quản trị Kafka thay vì để mọi ứng dụng tự tạo topic. Dù dùng cách nào, hãy xác minh topic được tạo trước khi bật consumer có thể publish DLT.

Các thuộc tính vận hành nên xác định trước:

- **Partitions:** đủ để ánh xạ partition nguồn nếu resolver giữ partition.
- **Replication factor:** phù hợp số broker và yêu cầu độ bền.
- **Retention:** đủ dài cho thời gian phát hiện, điều tra và replay.
- **Cleanup policy:** thường dùng `delete` để giữ từng record lỗi theo thời gian; chỉ dùng compaction khi có chủ đích giữ trạng thái mới nhất theo key.
- **ACL:** consumer group xử lý chính cần quyền ghi DLT; nhóm điều tra cần quyền đọc; quy trình replay cần quyền đọc DLT và ghi topic đích.
- **Monitoring:** theo dõi số record mới, tốc độ tăng, tuổi record cũ nhất và lỗi publish DLT.

Không dùng retention quá ngắn khiến record lỗi bị xóa trước khi nhóm phụ trách điều tra. Cũng không giữ vô thời hạn mà không có chính sách dung lượng, phân loại và xóa dữ liệu.

## 9. Tên DLT và môi trường triển khai

Nếu nhiều môi trường dùng chung cluster, thêm namespace môi trường vào tên topic để tránh producer hoặc consumer ở môi trường này đọc nhầm dữ liệu của môi trường khác.

Ví dụ:

| Môi trường | Topic nguồn | DLT |
|---|---|---|
| Local | `local.orders` | `local.orders.DLT` |
| Test | `test.orders` | `test.orders.DLT` |
| Staging | `staging.orders` | `staging.orders.DLT` |
| Production | `prod.orders` | `prod.orders.DLT` |

Một cách khác là dùng cluster riêng cho từng môi trường và giữ tên topic ngắn như `orders`/`orders.DLT`. Chọn một quy ước nhất quán trong toàn nền tảng.

Đừng ghép profile, pod ID hoặc build number vào tên DLT. Tên topic cần ổn định qua lần triển khai để record lỗi cũ vẫn được nhóm vận hành tìm thấy.

## 10. Quy tắc hợp lệ và giới hạn tên topic Kafka

Tên topic phải tuân thủ quy tắc của Kafka broker. Các điểm cần nhớ:

- Tên topic có độ dài tối đa 249 ký tự.
- Các ký tự ASCII chữ và số, dấu chấm `.`, gạch dưới `_` và gạch nối `-` là các ký tự thông dụng được hỗ trợ.
- Không dùng tên chính xác là `.` hoặc `..`.
- Tên topic phân biệt chữ hoa/chữ thường; `orders.DLT` và `orders.dlt` là hai tên khác nhau.
- Tránh tên bắt đầu bằng `__` vì tiền tố này thường dành cho topic nội bộ của Kafka.

Khi ghép tên nguồn với suffix, kiểm tra độ dài cuối cùng. Topic nguồn đã dài gần giới hạn có thể khiến tên DLT vượt 249 ký tự. Hãy đặt giới hạn cho tên topic nguồn hoặc dùng suffix ngắn hơn theo contract.

Không chuẩn hóa tên topic ở producer và consumer theo hai cách khác nhau. Một thay đổi từ `.DLT` sang `.dlt` cần được xem là thay đổi cấu hình/contract và phải có kế hoạch chuyển dữ liệu, ACL, consumer và retention tương ứng.

## 11. Kiểm thử quy tắc xác định tên DLT

Nên kiểm thử destination resolver độc lập để bảo đảm tên topic và partition đích đúng contract.

Ví dụ kiểm tra hàm resolver do ứng dụng định nghĩa. Tách quy tắc tạo đích thành một phương thức giúp unit test trực tiếp kết quả:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;

final class DeadLetterDestination {

    private DeadLetterDestination() {
    }

    static TopicPartition defaultDltDestination(
            ConsumerRecord<?, ?> record) {
        return new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        );
    }
}
~~~

Unit test cho quy tắc trên:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;

class DeadLetterDestinationTest {

    @Test
    void appendsDltSuffixAndKeepsOriginalPartition() {
        var record = new ConsumerRecord<String, String>(
            "orders",
            2,
            100L,
            "ORD-1001",
            "{\"orderId\":\"ORD-1001\"}"
        );

        var destination = DeadLetterDestination.defaultDltDestination(record);

        assertThat(destination.topic()).isEqualTo("orders.DLT");
        assertThat(destination.partition()).isEqualTo(2);
    }
}
~~~

Nếu dùng resolver tùy chỉnh, đưa resolver thành bean hoặc phương thức riêng để unit test các trường hợp:

- Topic nguồn khác nhau.
- Partition nguồn ở đầu, giữa và cuối dải partition.
- Tên DLT theo consumer group hoặc nhóm lỗi.
- Exception thuộc loại retryable và non-retryable.
- Tên kết quả không vượt giới hạn topic.
- Partition `-1` khi muốn producer tự chọn partition.

Integration test cần tạo topic nguồn và DLT trên Embedded Kafka hoặc Testcontainers, làm listener thất bại có kiểm soát, rồi xác minh record thực sự xuất hiện ở đúng topic/partition. Kiểm tra cả key, value, header gốc và exception metadata.

Đặc biệt, kiểm thử trường hợp DLT không tồn tại, thiếu partition hoặc producer không có quyền ghi. Recovery chỉ được coi là hoàn tất khi record đã được publish theo chính sách xác nhận của ứng dụng.

## 12. Lỗi thường gặp khi đặt tên DLT

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `InvalidTopicException` | Tên có ký tự không hợp lệ hoặc vượt giới hạn | Kiểm tra quy tắc tên Kafka và độ dài sau khi thêm suffix |
| Không tìm thấy partition đích | DLT có ít partition hơn topic nguồn nhưng resolver giữ partition gốc | Tạo đủ partition hoặc chọn partitioner có chủ đích |
| Publish DLT thất bại | Topic chưa tồn tại, ACL thiếu hoặc broker lỗi | Tạo topic trước, cấp quyền và theo dõi send result |
| Các nhóm ghi lỗi lẫn nhau | Nhiều consumer group dùng chung `<topic>.DLT` | Tách DLT theo subscriber nếu cần quyền sở hữu riêng |
| Quá nhiều DLT topic | Tạo topic theo exception, event ID hoặc tenant | Dùng một số nhóm lỗi ổn định và có chủ sở hữu |
| Không tìm ra nguồn record | Tên topic không thể hiện topic gốc và thiếu metadata | Giữ quy ước tên rõ ràng và kiểm tra DLT headers |
| Record lỗi bị xóa trước khi xử lý | Retention quá ngắn | Chọn retention theo SLA điều tra và replay |

## 13. Checklist chọn tên topic dead letter

- [ ] Chọn một naming convention ổn định cho toàn hệ thống.
- [ ] Nếu dùng mặc định Spring Kafka, hiểu quy tắc `<source-topic>.DLT`.
- [ ] Xác định DLT dùng chung theo topic hay tách theo consumer group.
- [ ] Chỉ tách theo nhóm lỗi khi có quy trình và chủ sở hữu rõ ràng.
- [ ] Quyết định giữ partition nguồn hay để producer chọn partition.
- [ ] Nếu giữ partition, tạo DLT có ít nhất số partition bằng topic nguồn.
- [ ] Tạo topic trước và xác minh replication factor, ACL, retention.
- [ ] Kiểm tra tên topic sau khi thêm suffix vẫn hợp lệ và không vượt giới hạn.
- [ ] Phân biệt DLT với retry topic có trì hoãn.
- [ ] Bật xử lý lỗi khi DLT publish thất bại và kiểm thử recovery.
- [ ] Theo dõi số lượng, tuổi record và tốc độ tăng của DLT.
- [ ] Có quy trình điều tra, sửa dữ liệu và replay có kiểm soát.

Tên DLT nên cho biết record đến từ topic nào và thuộc quy trình xử lý lỗi nào. Quy ước `<source-topic>.DLT` là điểm bắt đầu dễ vận hành; khi cần cô lập theo consumer group hoặc nhóm lỗi, hãy dùng destination resolver với tên ổn định, bảo đảm partition và cấu hình topic phù hợp. Việc đặt tên chỉ có giá trị khi đi cùng quyền truy cập, retention, monitoring và quy trình phục hồi rõ ràng.
