# Khi nào cần một partition duy nhất

Kafka bảo đảm thứ tự record trong phạm vi một partition. Nếu mọi record của một topic đều được ghi vào đúng một partition, topic đó có một chuỗi append duy nhất để consumer đọc theo offset. Đây là cách đơn giản nhất để có thứ tự chung cho toàn bộ record của topic, nhưng cũng tạo ra giới hạn rõ ràng về khả năng ghi và tiêu thụ song song.

Trong module `SPRING_KAFKA_MESSAGING`, producer gửi event bằng `KafkaTemplate` và consumer nhận event bằng `@KafkaListener`. Quyết định dùng một partition cần dựa trên yêu cầu ordering thực tế, lưu lượng dữ liệu, khả năng xử lý của consumer và kế hoạch mở rộng. Nhiều trường hợp chỉ cần giữ thứ tự theo một thực thể như `orderId`; khi đó dùng key để định tuyến vào cùng partition thường phù hợp hơn việc dồn toàn bộ topic vào một partition.

## 1. Một partition duy nhất có ý nghĩa gì?

Một topic Kafka có thể có một hoặc nhiều partition. Mỗi partition là một log độc lập, có offset tăng dần theo thứ tự record được append vào log đó.

Với topic chỉ có một partition:

```text
Topic: system-events

Partition 0
  offset 0 -> ServiceStarted
  offset 1 -> ConfigurationLoaded
  offset 2 -> UserSignedIn
  offset 3 -> ServiceStopped
```

Consumer đọc partition `0` theo thứ tự offset. Vì không có partition thứ hai, mọi record của topic cùng nằm trong một chuỗi log. Đây là cơ sở để ứng dụng quan sát một thứ tự append chung cho các event của topic.

Thứ tự đó là thứ tự broker append record vào partition, không mặc nhiên là thứ tự thời gian nghiệp vụ. Nếu hai producer gửi event đồng thời, broker xác định thứ tự append khi nhận các record. Kafka không thể tự suy ra event nào xảy ra trước trong hệ thống bên ngoài. Nếu nghiệp vụ cần thứ tự nhân quả, ứng dụng vẫn phải điều phối producer hoặc mang sequence/version trong event để xác minh thứ tự nghiệp vụ.

Một partition duy nhất chỉ tạo thứ tự trong topic đó. Nó không tạo thứ tự chung giữa nhiều topic, và cũng không bảo đảm thứ tự toàn cục giữa các hệ thống độc lập.

## 2. Khi nào cần một partition?

Chọn một partition khi ứng dụng thực sự cần mọi record trong topic đi qua một chuỗi append duy nhất và lưu lượng đủ thấp để một partition xử lý được.

Một số trường hợp có thể phù hợp:

- **Luồng điều khiển có lưu lượng thấp:** các lệnh hoặc thay đổi cấu hình cần được đọc theo cùng thứ tự append.
- **Audit log đơn giản:** một nguồn ghi có kiểm soát phát các mốc trạng thái nhỏ và consumer cần đọc một chuỗi sự kiện duy nhất.
- **Workflow tuần tự:** một luồng công việc nhỏ cần xử lý từng bước theo thứ tự trong cùng topic.
- **Bài tập, demo hoặc môi trường phát triển:** muốn quan sát offset và ordering mà chưa cần phân vùng song song.
- **Tích hợp legacy:** hệ thống cũ yêu cầu một luồng tuần tự và throughput đã được đo là nằm trong giới hạn một partition.

Ví dụ, service quản lý một thiết bị có thể phát các event trạng thái như `DeviceRegistered`, `DeviceActivated`, `DeviceDisabled`. Nếu toàn bộ luồng trạng thái có lưu lượng nhỏ và yêu cầu consumer đọc theo một thứ tự append chung, một partition có thể là thiết kế đơn giản.

Tuy nhiên, nếu topic chứa event của hàng nghìn thiết bị hoặc đơn hàng độc lập, việc dồn mọi event vào một partition thường làm giảm khả năng mở rộng. Khi đó, cần xác định thực thể nào cần giữ thứ tự và chọn key tương ứng.

## 3. Phân biệt thứ tự toàn topic và thứ tự theo key

Đây là hai yêu cầu khác nhau:

| Yêu cầu | Thiết kế thường phù hợp | Phạm vi thứ tự |
|---|---|---|
| Mọi record của topic phải có một thứ tự append chung | Topic có một partition | Toàn bộ record trong topic |
| Event của cùng một đơn hàng phải có thứ tự | Dùng `orderId` làm key trên topic nhiều partition | Các event của cùng key, khi routing ổn định |
| Event của mỗi tài khoản phải có thứ tự, các tài khoản khác xử lý song song | Dùng `accountId` làm key | Trong từng partition chứa tài khoản đó |
| Cần xử lý song song các event độc lập | Nhiều partition và key phân bố đều | Không có thứ tự toàn topic |

Ví dụ topic `orders` có tám partition. Producer dùng `orderId` làm key; mọi event của cùng đơn hàng được partitioner mặc định định tuyến vào cùng partition nếu cách serialize key, partitioner và số partition không đổi. Các đơn hàng khác nhau có thể nằm ở partition khác nhau và được xử lý song song.

```text
Topic orders (8 partitions)

order-1001: OrderCreated -> PaymentAccepted -> OrderShipped  -> partition 2
order-1002: OrderCreated -> PaymentRejected                  -> partition 5
order-1003: OrderCreated -> PaymentAccepted -> OrderShipped  -> partition 7
```

Consumer vẫn đọc theo offset trong từng partition. Do đó, event của `order-1001` có thứ tự riêng trong partition `2`, còn `order-1002` có thứ tự riêng trong partition `5`. Không có thứ tự Kafka bảo đảm giữa event của hai đơn hàng khác partition.

Nếu chỉ cần thứ tự theo aggregate, không nên hy sinh khả năng song song của toàn topic bằng cách tạo đúng một partition. Hãy dùng aggregate ID làm key và thiết kế consumer theo partition.

## 4. Đánh đổi khi chỉ có một partition

Một partition giúp thứ tự đơn giản nhưng đặt toàn bộ lưu lượng ghi vào một leader và giới hạn số consumer hoạt động song song trong mỗi group.

| Khía cạnh | Topic một partition | Topic nhiều partition |
|---|---|---|
| Ordering | Có một thứ tự append trong topic | Chỉ có thứ tự riêng trong từng partition |
| Ghi song song | Một partition leader xử lý append | Nhiều leader có thể xử lý các partition khác nhau |
| Consumer song song trong một group | Tối đa một consumer được gán partition | Có thể có nhiều consumer hoạt động, tối đa theo số partition được gán |
| Throughput | Bị giới hạn bởi năng lực của một partition/leader | Có thể tăng bằng cách phân phối tải qua nhiều partition và broker |
| Phân bố tải | Mọi record dồn vào cùng partition | Có thể phân bố theo key/partitioner |
| Vận hành | Dễ hình dung và truy vết thứ tự | Cần quan sát nhiều partition và xử lý ordering theo key |

Một partition có thể trở thành điểm nghẽn khi producer gửi nhiều record hoặc consumer xử lý payload nặng. Tăng `concurrency` của listener không tạo thêm partition và không giúp nhiều consumer trong cùng group đọc song song cùng một partition.

## 5. Replication không thay thế partitioning

Partition count và replication factor giải quyết hai mục tiêu khác nhau:

- **Partitioning** chia dữ liệu thành các log độc lập để tăng khả năng phân phối tải và xử lý song song.
- **Replication** tạo bản sao của partition trên các broker để tăng khả năng chịu lỗi và tính sẵn sàng.

Topic có một partition và replication factor bằng ba vẫn chỉ có một partition leader nhận ghi. Hai replica follower sao chép dữ liệu của partition đó; chúng không trở thành hai partition ghi song song.

Ví dụ trên cluster ba broker:

```text
Topic system-events, partition count = 1, replication factor = 3

Broker 1: partition 0 (leader)
Broker 2: partition 0 (replica)
Broker 3: partition 0 (replica)
```

Replication factor 3 cần cluster có đủ broker để đặt replica. Trong production, cần xem cùng producer `acks`, `min.insync.replicas` và trạng thái ISR để chọn mức durability phù hợp. Tăng replication factor có thể cải thiện khả năng chịu lỗi, nhưng không tăng khả năng ghi song song của một partition.

## 6. Tạo topic một partition bằng Spring Kafka

Có thể khai báo topic bằng `KafkaAdmin` và `TopicBuilder`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic systemEventsTopic() {
        return TopicBuilder.name("system-events")
                .partitions(1)
                .replicas(3)
                .build();
    }
}
```

Ví dụ dùng replication factor 3, vì vậy cluster cần có ít nhất ba broker phù hợp. Với local Kafka chỉ có một broker, đổi thành `.replicas(1)`. `KafkaAdmin` dùng khai báo `NewTopic` để yêu cầu tạo topic khi ứng dụng khởi tạo; topic phải được provisioning với cấu hình phù hợp trước khi producer/consumer sử dụng.

Nếu topic đã tồn tại với nhiều partition, thay đổi `.partitions(1)` trong bean `NewTopic` không làm Kafka giảm partition count. Kafka không hỗ trợ giảm số partition của một topic đã tạo. Nếu cần chuyển từ nhiều partition sang một partition, phải tạo topic mới, xác định chiến lược chuyển dữ liệu và chuyển producer/consumer có kiểm soát.

Sau khi tạo, xác minh partition count thực tế bằng Admin API hoặc công cụ quản trị Kafka. Không chỉ dựa vào giá trị trong source code để kết luận cấu hình broker đã đúng.

## 7. Gửi record vào partition duy nhất

Với topic chỉ có partition `0`, partitioner mặc định sẽ chọn partition đó dù key có giá trị hay không, miễn là không có custom partitioner hoặc cấu hình bất thường. Ứng dụng cũng có thể chỉ định partition `0` tường minh.

Ví dụ dùng `KafkaTemplate`:

```java
import java.time.Instant;
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

public record SystemEvent(
        String eventId,
        String eventType,
        Instant occurredAt
) {}

public interface SystemEventHandler {
    void handle(SystemEvent event);
}

@Service
public class SystemEventPublisher {

    private final KafkaTemplate<String, SystemEvent> kafkaTemplate;

    public SystemEventPublisher(
            KafkaTemplate<String, SystemEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, SystemEvent>> publish(
            SystemEvent event) {
        return kafkaTemplate.send(
                "system-events",
                0,
                event.eventId(),
                event
        );
    }
}
```

Ở đây producer chỉ định partition `0` và vẫn giữ `eventId` làm key. Key có thể hữu ích cho correlation hoặc nếu topic sau này dùng compaction, nhưng trong topic một partition nó không phân phối record sang partition khác.

Nếu không cần chỉ định tường minh, có thể dùng `kafkaTemplate.send("system-events", event.eventId(), event)`. Khi topic thực sự chỉ có một partition, partitioner sẽ chọn partition `0`.

Gửi là thao tác bất đồng bộ. Trong ứng dụng thực tế, nên quan sát `CompletableFuture<SendResult<K, V>>` để biết gửi thành công hay thất bại và kiểm tra `RecordMetadata.partition()`/`offset()` khi cần truy vết. Không bỏ qua lỗi gửi chỉ vì topic có một partition.

## 8. Đọc topic một partition bằng `@KafkaListener`

Một listener trong consumer group có thể đọc toàn bộ partition duy nhất của topic:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class SystemEventListener {

    private final SystemEventHandler handler;

    public SystemEventListener(SystemEventHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
            id = "systemEventsListener",
            topics = "system-events",
            groupId = "system-events-reader",
            concurrency = "1"
    )
    public void listen(ConsumerRecord<String, SystemEvent> record) {
        System.out.printf(
                "partition=%d offset=%d key=%s type=%s%n",
                record.partition(),
                record.offset(),
                record.key(),
                record.value().eventType()
        );

        handler.handle(record.value());
    }
}
```

Với một partition và một consumer group, tối đa một consumer member được gán partition đó tại một thời điểm. Đặt `concurrency = "1"` thể hiện rõ thiết kế. Nếu tăng concurrency lên lớn hơn một, những consumer con còn lại sẽ không có partition để đọc trong group này.

Một consumer group khác vẫn có thể đọc cùng partition độc lập. Ví dụ group `system-events-audit` và group `system-events-dashboard` đều nhận toàn bộ record của topic theo tiến độ riêng. Điều này không làm tăng song song bên trong một group; nó tạo các luồng đọc độc lập cho các ứng dụng khác nhau.

## 9. Một partition không tự bảo đảm thứ tự nghiệp vụ

Kafka đảm bảo thứ tự append trong partition, nhưng không tự hiểu quan hệ trước/sau của nghiệp vụ. Có một số tình huống cần lưu ý:

- **Nhiều producer:** thứ tự record là thứ tự leader append chúng, không nhất thiết là thứ tự event xảy ra ở các hệ thống nguồn.
- **Producer gửi bất đồng bộ:** các lời gọi gửi từ nhiều thread hoặc nhiều producer cần có quy tắc điều phối nếu thứ tự nghiệp vụ là bắt buộc.
- **Retry và lỗi:** cấu hình producer nên được xem xét cùng idempotence, retry và số request đang bay để tránh thay đổi thứ tự ngoài dự kiến trong những cấu hình cũ hoặc không phù hợp.
- **Consumer xử lý song song:** nếu listener đẩy record sang executor và hoàn tất không theo thứ tự, side effect nghiệp vụ có thể đảo thứ tự dù record được poll theo offset.
- **Timestamp:** timestamp có thể trùng, lệch đồng hồ hoặc biểu thị event đến muộn; không thay thế thứ tự offset.

Nếu cần thứ tự nhân quả nghiêm ngặt, hãy xác định một nguồn phát có thẩm quyền, tuần tự hóa việc phát event hoặc gắn sequence number/version vào từng event để consumer kiểm tra. Một partition giúp tạo một thứ tự append chung, nhưng không tự giải quyết mọi tranh chấp thứ tự ở tầng nghiệp vụ.

## 10. Khi nào không nên dùng một partition?

Tránh chọn một partition duy nhất nếu:

- Topic có throughput ghi/đọc cao hoặc payload lớn.
- Consumer cần scale ngang để xử lý nhiều record song song trong cùng group.
- Event thuộc nhiều aggregate độc lập và chỉ cần thứ tự theo từng aggregate.
- Một partition leader có thể trở thành bottleneck hoặc giới hạn khả năng phục hồi tải.
- Nhiều nhóm nghiệp vụ cần phân phối công việc qua nhiều consumer trong cùng group.

Ví dụ, topic `orders.events` chứa event của hàng triệu đơn hàng. Dùng một partition sẽ dồn toàn bộ tải vào một log. Dùng `orderId` làm key với số partition được tính toán phù hợp cho phép các event của cùng đơn hàng giữ thứ tự trong một partition, trong khi các đơn hàng khác được xử lý song song.

Không dùng một partition như một distributed lock hoặc cơ chế bảo đảm chỉ có một producer. Nhiều producer vẫn có thể ghi vào cùng partition; nhiều consumer group vẫn có thể đọc độc lập. Nếu cần single-writer hoặc leader election ở tầng nghiệp vụ, phải có cơ chế điều phối riêng.

## 11. Mở rộng sau này và thay đổi partition count

Số partition là quyết định kiến trúc có ảnh hưởng lâu dài:

- Kafka cho phép tăng partition count nhưng không hỗ trợ giảm partition count của topic hiện có.
- Khi tăng số partition, key-based partitioner có thể ánh xạ cùng một key sang partition khác do mẫu số thay đổi.
- Record cũ vẫn ở partition cũ, record mới có thể ở partition mới; thứ tự của một key qua giai đoạn chuyển đổi không còn nằm trong một chuỗi offset duy nhất.
- Với topic đang có một partition, chuyển sang nhiều partition cần đánh giá lại yêu cầu ordering, consumer group và cách xử lý dữ liệu lịch sử.

Nếu dự đoán nhu cầu mở rộng sẽ sớm xuất hiện, có thể bắt đầu với nhiều partition và dùng key để giữ thứ tự theo aggregate. Nếu thật sự cần một thứ tự toàn topic, hãy chấp nhận giới hạn throughput và có kế hoạch migration rõ ràng khi yêu cầu thay đổi.

## 12. Kiểm thử ordering của topic một partition

Integration test nên xác minh cả partition thực tế lẫn thứ tự record đọc được:

1. Tạo topic test với đúng một partition và replication factor phù hợp broker test.
2. Gửi một chuỗi event có sequence rõ ràng, ví dụ `1`, `2`, `3`, `4`.
3. Chờ send future hoàn tất và xác minh `RecordMetadata.partition()` bằng `0`.
4. Dùng consumer group riêng đọc topic và kiểm tra partition/offset.
5. Xác minh sequence được đọc theo thứ tự append mong muốn trong test producer đơn.
6. Nếu có nhiều producer hoặc nhiều thread, kiểm thử riêng quy tắc điều phối thứ tự; không giả định timestamp sẽ quyết định thứ tự.
7. Kiểm tra consumer concurrency lớn hơn một không làm tăng số consumer active cho partition duy nhất trong cùng group.

Embedded Kafka hoặc Testcontainers đều có thể dùng cho integration test. Với test một broker, replication factor của topic phải là `1`; cấu hình `3` chỉ phù hợp khi test cluster có đủ broker.

## 13. Checklist quyết định dùng một partition

- [ ] Nhu cầu thực sự là một thứ tự append chung cho mọi record trong topic.
- [ ] Throughput và kích thước payload đã được đo, đủ thấp cho một partition.
- [ ] Đã so sánh với phương án key-based ordering theo aggregate.
- [ ] Đã chấp nhận tối đa một consumer active cho partition trong mỗi group.
- [ ] Replication factor được chọn riêng cho durability, không nhầm với khả năng song song.
- [ ] Producer có quy tắc điều phối nếu nhiều nguồn phát event cần thứ tự nghiệp vụ.
- [ ] Consumer không xử lý bất đồng bộ làm đảo thứ tự side effect ngoài ý muốn.
- [ ] Đã xác minh topic thực tế có đúng một partition.
- [ ] Có kế hoạch migration nếu sau này cần tăng partition count.
- [ ] Có integration test xác minh partition, offset và thứ tự append.

Một partition duy nhất là lựa chọn hợp lý khi topic cần một chuỗi append chung, lưu lượng thấp và consumer có thể xử lý tuần tự. Nếu chỉ cần giữ thứ tự theo từng thực thể, dùng key trên topic nhiều partition thường cân bằng tốt hơn giữa ordering và khả năng mở rộng. Hãy quyết định từ yêu cầu nghiệp vụ và số liệu tải, rồi xác minh bằng integration test trước khi đưa topic vào vận hành.
