# AckMode TIME

Trong Spring Kafka, **AckMode.TIME** là chế độ xác nhận do listener container quản lý, trong đó container commit các offset đang chờ khi khoảng thời gian cấu hình đã trôi qua kể từ lần commit trước. Chế độ này cho phép ứng dụng gom nhiều record đã xử lý thành một lần commit theo thời gian, thay vì commit sau từng record hoặc đợi đủ một số lượng record cố định.

AckMode.TIME điều khiển thời điểm lưu tiến độ đọc của consumer group. Nó không làm thay đổi nội dung record, thứ tự trong partition hay cách listener thực hiện nghiệp vụ. Vì offset có thể chưa được commit trong một khoảng thời gian sau khi listener xử lý xong, ứng dụng cần chấp nhận khả năng một số record được giao lại nếu process dừng trước lần commit tiếp theo.

## 1. AckMode là gì?

Kafka consumer có thể đọc record và di chuyển vị trí đọc trong bộ nhớ trước khi committed offset được lưu trên broker. Committed offset là checkpoint mà consumer group sử dụng khi khởi động hoặc khôi phục sau sự cố.

Spring Kafka listener container quản lý việc xác nhận và commit offset thông qua thuộc tính **ContainerProperties.AckMode**. Với các chế độ tự động như RECORD, BATCH và TIME, listener không cần tự gọi **Acknowledgment.acknowledge()** cho mỗi record. Container theo dõi kết quả xử lý và quyết định thời điểm commit theo chế độ đã cấu hình.

**AckMode.TIME** có ý nghĩa:

- Listener xử lý record theo luồng bình thường.
- Khi listener xử lý thành công, container ghi nhận offset tương ứng là có thể commit.
- Container theo dõi thời gian kể từ lần commit trước.
- Khi **ackTime** đã trôi qua và có offset đang chờ, container commit các offset đã được xác nhận.
- Sau lần commit, mốc thời gian được cập nhật cho chu kỳ tiếp theo.

**ackTime** được tính bằng milliseconds trong API **ContainerProperties**. Trong cấu hình Spring Boot hiện đại, thuộc tính **spring.kafka.listener.ack-time** được bind dưới dạng thời lượng, ví dụ **5s**.

## 2. Luồng hoạt động

Sơ đồ dưới đây mô tả ý tưởng của chế độ TIME. Container chỉ commit tiến độ đã được listener xử lý thành công và đủ điều kiện xác nhận theo error handler đang dùng.

~~~mermaid
flowchart TD
    A["Consumer poll records"] --> B["Listener container gọi listener"]
    B --> C{"Listener xử lý thành công?"}
    C -->|Có| D["Container ghi nhận offset đã xử lý"]
    C -->|Không| E["Chuyển lỗi tới error handler"]
    D --> F{"Đã đến ngưỡng ackTime?"}
    F -->|Chưa| G["Tiếp tục xử lý; offset vẫn đang chờ commit"]
    G --> A
    F -->|Rồi| H["Commit offset đang chờ"]
    H --> I["Cập nhật thời điểm commit gần nhất"]
    I --> A
    E --> J["Retry hoặc recovery theo cấu hình"]
    J --> A
~~~

Ví dụ, container commit thành công lúc 10:00:00 và **ackTime** được đặt là 5 giây. Các record được xử lý thành công lúc 10:00:01, 10:00:02 và 10:00:04 sẽ tạo ra tiến độ đang chờ commit. Khi container kiểm tra điều kiện thời gian và thấy đã qua ngưỡng, nó commit offset mới nhất cho các partition liên quan.

Thời điểm commit thực tế có thể muộn hơn chính xác 5 giây. **ackTime** là ngưỡng để container quyết định commit; việc commit còn phụ thuộc vòng poll, thời gian listener chạy, xử lý batch và khả năng broker phản hồi. Không nên dùng nó như một deadline thời gian thực chính xác đến từng mili giây.

Nếu không có record mới hoặc không có offset đang chờ, không có tiến độ mới cần commit. TIME không phải một tác vụ nền buộc broker nhận một commit rỗng sau mỗi khoảng thời gian.

## 3. Cấu hình AckMode.TIME

### 3.1 Cấu hình bằng Spring Boot

Có thể cấu hình listener container qua **application.yml**:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: inventory-service
    listener:
      ack-mode: time
      ack-time: 5s
~~~

Trong ví dụ:

- **enable-auto-commit: false** để Kafka client không tự commit theo chu kỳ riêng. Spring Kafka container quản lý commit.
- **ack-mode: time** chọn chế độ commit theo thời gian.
- **ack-time: 5s** đặt ngưỡng thời gian giữa các lần commit là 5 giây.

Nếu phiên bản Spring Boot cũ dùng cách bind thời lượng khác, hãy đối chiếu metadata cấu hình của đúng phiên bản. Ở API Java của Spring Kafka, **setAckTime** nhận giá trị milliseconds.

### 3.2 Cấu hình bằng ConcurrentKafkaListenerContainerFactory

Khi tạo listener container factory thủ công, có thể đặt mode và khoảng thời gian trên **ContainerProperties**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.TIME);

        factory.getContainerProperties().setAckTime(5_000L);

        return factory;
    }
}
~~~

Listener có thể sử dụng factory này:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service",
        containerFactory = "orderListenerFactory"
    )
    public void handle(OrderEvent event) {
        inventoryService.reserve(event);
    }
}
~~~

Khi listener kết thúc bình thường, container ghi nhận tiến độ xử lý. Container sẽ commit theo ngưỡng TIME đã đặt. Phương thức listener không cần nhận tham số **Acknowledgment** chỉ để sử dụng AckMode.TIME.

### 3.3 Kiểm tra cấu hình hiệu lực

Trong môi trường có nhiều profile, container factory riêng hoặc cấu hình được tạo bằng code, hãy xác định factory mà listener thực sự sử dụng. Cấu hình ở một factory không ảnh hưởng đến listener đang dùng factory khác.

Cần kiểm tra ít nhất:

- Listener đang gắn với container factory nào.
- **AckMode** hiệu lực của container.
- **ackTime** hiệu lực và đơn vị thời gian.
- **enable.auto.commit** của consumer.
- Có transaction manager hoặc error handler làm thay đổi đường commit hay không.

Không nên chỉ nhìn file YAML rồi kết luận cấu hình đã có hiệu lực. Giá trị có thể bị profile, biến môi trường hoặc cấu hình Java ghi đè.

## 4. AckMode.TIME khác gì các chế độ khác?

Spring Kafka cung cấp nhiều chế độ để chọn cách container xác nhận offset. Điểm khác nhau chính là điều kiện khiến container commit.

| AckMode | Thời điểm commit | Đặc điểm |
|---|---|---|
| **RECORD** | Sau khi từng record được listener xử lý thành công | Tiến độ được lưu thường xuyên; tăng số lần commit |
| **BATCH** | Sau khi tất cả record trong một poll batch được xử lý | Gom commit theo batch; đây là chế độ mặc định phổ biến của container |
| **TIME** | Khi thời gian kể từ lần commit trước đạt **ackTime** và có offset chờ | Gom commit theo thời gian |
| **COUNT** | Khi số lượng record đã xử lý kể từ lần commit trước đạt **ackCount** | Gom commit theo số lượng |
| **COUNT_TIME** | Khi đạt ngưỡng thời gian hoặc ngưỡng số lượng | Kết hợp giới hạn theo thời gian và số record |
| **MANUAL** | Sau khi listener gọi **acknowledge()**, container xử lý commit theo semantics của chế độ manual | Ứng dụng chủ động xác nhận |
| **MANUAL_IMMEDIATE** | Commit ngay khi **acknowledge()** được gọi trên consumer thread | Ứng dụng chủ động xác nhận và yêu cầu commit ngay |

### TIME và BATCH

BATCH commit theo ranh giới poll: khi toàn bộ record trả về trong một lần poll đã được xử lý. TIME dựa trên thời gian từ lần commit trước, nên một lần commit có thể bao gồm tiến độ tích lũy qua nhiều lần poll.

Nếu một poll trả về batch lớn, BATCH có thể commit ngay khi xử lý xong batch đó, còn TIME có thể giữ offset chờ đến khi ngưỡng thời gian đạt. Vì vậy, hai mode có hành vi khác nhau ngay cả khi cùng consumer, listener và **max.poll.records**.

### TIME và COUNT

TIME không giới hạn số record bằng một ngưỡng đếm. Nếu throughput cao, rất nhiều record có thể được xử lý trong một khoảng **ackTime**. COUNT commit khi đủ số record, bất kể khoảng thời gian đã trôi qua.

### TIME và COUNT_TIME

COUNT_TIME hữu ích khi muốn có cả ngưỡng thời gian và ngưỡng số record. Container có thể commit khi một trong hai ngưỡng đạt. Đây là lựa chọn cần cân nhắc nếu ứng dụng muốn hạn chế cả thời gian giữ offset lẫn số lượng record đã xử lý nhưng chưa commit.

### TIME và MANUAL

TIME là chế độ tự động do container quản lý. MANUAL yêu cầu listener chủ động gọi **Acknowledgment.acknowledge()**. Không nên chọn MANUAL chỉ vì muốn thay đổi thời gian commit; hãy chọn mode phản ánh đúng nơi ứng dụng muốn kiểm soát việc xác nhận.

## 5. Quan hệ giữa ackTime và committed offset

Offset là số thứ tự của record trong một partition. Khi commit, consumer group lưu vị trí tiếp theo cần đọc, tức offset sau record cuối cùng đã được xác nhận, chứ không lưu lại offset của record cuối cùng như một chỉ số đã xử lý.

Ví dụ, consumer xử lý thành công các record đến offset 104 trong partition 0. Khi commit tiến độ đó, committed offset được lưu là 105. Khi consumer khởi động lại từ committed offset, record tiếp theo cần đọc là offset 105.

Với AckMode.TIME, committed offset có thể chậm hơn vị trí consumer đã xử lý trong bộ nhớ. Có thể hình dung ba vị trí:

- **Position**: vị trí consumer client đã đọc hoặc tiến tới trong lần chạy hiện tại.
- **Processed position**: tiến độ listener đã xử lý thành công.
- **Committed position**: checkpoint đã được broker lưu cho consumer group.

Committed position là điểm phục hồi sau restart. Position trong bộ nhớ có thể tiến xa hơn committed position trong khi container chờ ngưỡng thời gian.

Với nhiều partition, commit chứa offset tương ứng cho từng partition mà consumer đang sở hữu và có tiến độ cần xác nhận. AckMode.TIME không tạo một offset toàn cục cho toàn bộ topic.

## 6. Tác động đến delivery semantics

### 6.1 Khoảng thời gian có thể phát sinh redelivery

Giả sử consumer xử lý một record thành công nhưng offset chưa đến lần commit tiếp theo. Nếu process dừng đột ngột, broker chỉ biết committed offset cũ. Sau khi consumer khởi động lại hoặc partition được giao cho consumer khác, record đã xử lý nhưng chưa commit có thể được giao lại.

Ví dụ với **ackTime = 5s**:

| Thời điểm | Sự kiện | Trạng thái |
|---|---|---|
| 10:00:00 | Commit thành công đến offset 100 | Committed offset là 101 |
| 10:00:01 | Xử lý offset 101 thành công | Chưa commit |
| 10:00:02 | Xử lý offset 102 thành công | Chưa commit |
| 10:00:04 | Xử lý offset 103 thành công | Chưa commit |
| 10:00:05 trở đi | Container kiểm tra ngưỡng TIME và commit tiến độ mới | Committed offset có thể tiến lên 104 |
| Trước lần commit thành công | Process dừng | Các record chưa commit có thể được đọc lại |

Bảng là một timeline minh họa. Thời điểm commit còn phụ thuộc vòng xử lý của container và kết quả commit thực tế.

TIME không tự tạo ra exactly-once processing. Chế độ này phù hợp với mô hình at-least-once: record có thể được giao lại, nên side effect nghiệp vụ phải an toàn khi thực hiện lặp.

### 6.2 Idempotency vẫn cần thiết

Nếu listener trừ tồn kho trong database rồi process dừng trước khi commit offset, record có thể được giao lại và listener có thể trừ tồn kho lần thứ hai. Việc đặt **ackTime** ngắn hơn chỉ thu hẹp khoảng thời gian có thể redeliver trong một số tình huống; nó không loại bỏ race giữa side effect và commit.

Các cách bảo vệ phổ biến:

- Dùng **eventId** duy nhất và lưu dấu đã xử lý trong cùng transaction database với thay đổi nghiệp vụ.
- Đặt unique constraint trên inbox table để cùng một event không thể tạo hai lần xử lý.
- Thiết kế thao tác nghiệp vụ theo dạng upsert hoặc conditional update có thể chạy lại an toàn.
- Nếu consumer phát event tiếp theo, dùng transactional outbox để đồng bộ thay đổi database và sự kiện đầu ra.

Không dựa vào committed offset như một bằng chứng rằng database hoặc API bên ngoài đã hoàn tất đúng một lần.

### 6.3 Thời gian commit không phải thời gian xử lý

**ackTime** chỉ điều khiển thời điểm container commit offset. Nó không đặt giới hạn thời gian cho listener, không hủy một lời gọi database đang chạy và không làm cho record được xử lý nhanh hơn.

Nếu listener xử lý một record trong 20 giây và **ackTime** là 5 giây, container vẫn phải đợi listener hoàn tất theo luồng xử lý trước khi có thể xác nhận tiến độ tương ứng. Ngưỡng 5 giây không có nghĩa record đó sẽ được commit sau đúng 5 giây tính từ lúc bắt đầu xử lý.

## 7. Chọn ackTime như thế nào?

Giá trị phù hợp phụ thuộc vào khả năng chấp nhận redelivery, chi phí commit, thông lượng và thời gian xử lý nghiệp vụ.

### Khoảng thời gian ngắn

Ưu điểm:

- Tiến độ đọc được lưu thường xuyên hơn.
- Số record có thể bị đọc lại sau một lần dừng đột ngột thường nhỏ hơn trong cùng điều kiện tải.
- Consumer group có checkpoint mới hơn để tiếp tục sau restart.

Đổi lại, commit diễn ra thường xuyên hơn, có thể làm tăng request tới broker và chi phí xử lý commit.

### Khoảng thời gian dài

Ưu điểm:

- Có thể gom nhiều record vào một lần commit.
- Giảm tần suất commit trong workload có throughput cao.
- Giảm một phần overhead liên quan tới commit offset.

Đổi lại, nhiều record đã được xử lý có thể chưa được lưu checkpoint. Khi process dừng hoặc partition rebalance, consumer có thể phải xử lý lại một đoạn lớn hơn.

### Cách chọn thực tế

Hãy bắt đầu từ yêu cầu nghiệp vụ:

1. Xác định side effect nào cần chống lặp và khả năng idempotency đã có.
2. Xác định mức độ redelivery có thể chấp nhận khi process restart hoặc consumer rebalance.
3. Đo throughput và chi phí commit hiện tại.
4. Chọn một **ackTime** ban đầu có chủ đích, ví dụ 1 đến 5 giây cho một workload cần checkpoint tương đối thường xuyên.
5. Đo commit rate, commit latency, consumer lag và thời gian xử lý.
6. Thử nghiệm khi consumer dừng đột ngột để quan sát số record được giao lại.
7. Điều chỉnh giá trị dựa trên kết quả, sau đó ghi vào runbook.

Khoảng 1 đến 5 giây chỉ là điểm bắt đầu để thử nghiệm, không phải giá trị chuẩn cho mọi hệ thống. Một hệ thống xử lý batch lớn, throughput cao hoặc downstream chậm có thể cần lựa chọn khác.

## 8. Các yếu tố cấu hình có liên quan

### enable.auto.commit

Khi Spring Kafka container quản lý acknowledgement, nên để Kafka client không tự commit theo chu kỳ riêng:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

Spring Kafka container thường tắt auto commit nếu người dùng không cấu hình khác. Đặt rõ **false** giúp ý định cấu hình dễ đọc và tránh việc một profile vô tình bật auto commit. Nếu bật auto commit, client có thể lưu offset độc lập với thời điểm listener hoàn thành theo AckMode.TIME, làm sai kỳ vọng về checkpoint.

### max.poll.records

**max.poll.records** giới hạn số record được trả về trong một lần poll. Nó ảnh hưởng kích thước batch và thời gian container cần để xử lý kết quả poll, nhưng không phải ngưỡng commit của TIME.

Nếu batch có nhiều record và listener xử lý chậm, việc xử lý có thể kéo dài qua **ackTime**. Container chỉ commit tiến độ đã xử lý theo semantics của listener và error handler.

### max.poll.interval.ms

Đây là giới hạn thời gian tối đa giữa các lần gọi poll trước khi consumer bị xem là không còn tiến triển và có thể rời group. Nó khác với **ackTime**:

- **ackTime**: ngưỡng thời gian để container quyết định commit offset đang chờ.
- **max.poll.interval.ms**: giới hạn thời gian giữa các lần poll của consumer.

Tăng **ackTime** không sửa được consumer bị rời group do xử lý một batch quá lâu. Ngược lại, tăng **max.poll.interval.ms** không tự làm offset được commit thường xuyên hơn.

### pollTimeout

**pollTimeout** điều khiển thời gian consumer chờ dữ liệu trong một lần poll. Nó có thể ảnh hưởng độ trễ quan sát được trong vòng poll, nhưng không thay thế **ackTime** và không đặt thời gian commit.

### Commit đồng bộ và bất đồng bộ

Spring Kafka container có thể thực hiện commit đồng bộ hoặc bất đồng bộ theo cấu hình **syncCommits**. Cách commit ảnh hưởng việc container chờ kết quả commit và cách lỗi commit được quan sát. Hãy xem cấu hình container thực tế và log khi broker không phản hồi hoặc commit thất bại.

Dù commit theo cách nào, không được đánh dấu nghiệp vụ là hoàn tất chỉ vì listener đã chạy qua. Ứng dụng cần phân biệt listener success, commit success và side effect nghiệp vụ.

## 9. Xử lý lỗi listener với AckMode.TIME

AckMode.TIME không quyết định toàn bộ chính sách xử lý exception. Khi listener ném exception, Spring Kafka chuyển lỗi tới error handler được cấu hình. Error handler có thể retry, seek để đọc lại, recover record hoặc áp dụng một chính sách khác.

Cần trả lời các câu hỏi sau trong cấu hình production:

- Lỗi tạm thời nào được retry?
- Backoff và số lần retry là bao nhiêu?
- Khi retry hết giới hạn, record được phục hồi hoặc chuyển DLT theo cơ chế nào?
- Khi error handler recover thành công, offset có được commit theo cấu hình **ackAfterHandle** hoặc **commitRecovered** không?
- Nếu listener xử lý một batch và một record lỗi, phần offset nào được giữ hoặc commit?
- Nếu commit offset thất bại sau khi listener thành công, ứng dụng sẽ quan sát và phục hồi như thế nào?

Không giả định mọi record đã được poll đều tự động được commit chỉ vì **ackTime** đã hết. Container chỉ nên xác nhận tiến độ theo kết quả xử lý và chính sách recovery. Với các trường hợp dùng transaction manager, cần đọc semantics của transactional listener container vì offset có thể được phối hợp với transaction thay vì commit độc lập theo cách thông thường.

### Ví dụ listener có xử lý lỗi

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void handle(OrderEvent event) {
    inventoryService.reserveIdempotently(event.eventId(), event);
}
~~~

Trong ví dụ, nếu **reserveIdempotently** ném exception, error handler của container sẽ quyết định retry hoặc recovery. Nếu listener hoàn tất bình thường, offset được ghi nhận để commit theo TIME. Tính idempotent của nghiệp vụ bảo vệ trường hợp record được giao lại trước khi commit thành công.

## 10. Quan sát AckMode.TIME trong production

Để hiểu chế độ TIME đang hoạt động như mong đợi, cần quan sát cả commit và xử lý record.

### Chỉ số nên theo dõi

| Chỉ số | Điều cần quan sát |
|---|---|
| Consumer lag | Khoảng cách giữa tiến độ producer và consumer |
| Commit rate | Tần suất consumer commit offset |
| Commit latency | Thời gian broker phản hồi commit |
| Records consumed rate | Số record consumer xử lý theo thời gian |
| Listener processing time | Thời gian xử lý record hoặc batch |
| Redelivery / duplicate rate | Tần suất record được xử lý lại |
| Rebalance count | Tần suất consumer group thay đổi thành viên hoặc assignment |
| Retry và DLT rate | Số lỗi listener được retry hoặc recovery |

Kafka consumer metrics có các metric liên quan đến commit và lag, chẳng hạn **commit-rate**, **commit-latency-avg**, **commit-latency-max** và **records-lag-max**. Tên metric khi xuất qua Micrometer hoặc hệ thống monitoring có thể được chuẩn hóa theo convention của ứng dụng.

### Log cần đủ ngữ cảnh

Khi điều tra, ghi nhận:

- Consumer group và client ID.
- Topic, partition và offset.
- Thời gian bắt đầu/kết thúc listener.
- Kết quả xử lý và exception nếu có.
- Thời điểm commit và kết quả commit nếu được log.
- Rebalance hoặc việc partition bị thu hồi/giao lại.

Không nên log toàn bộ payload nếu chứa dữ liệu nhạy cảm. Dùng event ID hoặc correlation ID để liên kết log giữa consumer và downstream service.

### Dấu hiệu cấu hình chưa phù hợp

- Commit rate quá cao so với throughput: xem lại **ackTime**, số consumer và chi phí commit.
- Commit rate rất thấp trong khi record liên tục được xử lý: kiểm tra **ackTime**, listener container, cấu hình hiệu lực và lỗi commit.
- Lag tăng dù listener xử lý nhanh: kiểm tra phân bố partition, số consumer, fetch và broker.
- Redelivery tăng sau restart hoặc rebalance: kiểm tra khoảng cách giữa processed position và committed position, cũng như thời gian listener.
- Commit latency tăng: kiểm tra broker, network và group coordinator.

Consumer lag cao không tự chứng minh AckMode.TIME cấu hình sai. Lag còn phụ thuộc tốc độ producer, số partition, số consumer, thời gian xử lý và khả năng phục vụ của broker.

## 11. Kiểm thử hành vi TIME

Nên kiểm thử trên môi trường có Kafka broker thật hoặc test container tương đương. Mock listener có thể kiểm tra logic nghiệp vụ nhưng không chứng minh container commit offset theo đúng thời gian.

Một bài kiểm thử hữu ích nên:

1. Tạo topic với partition đã biết và một consumer group riêng.
2. Cấu hình listener container với AckMode.TIME và **ackTime** ngắn, ví dụ 2 giây.
3. Gửi một số record có event ID khác nhau.
4. Đợi listener xử lý thành công và quan sát committed offset.
5. Xác nhận offset không nhất thiết được commit ngay sau từng record.
6. Chờ ngưỡng thời gian và xác nhận committed offset tiến lên.
7. Dừng consumer đột ngột trước một lần commit trong một kịch bản riêng.
8. Khởi động lại cùng group ID và xác nhận record chưa commit có thể được giao lại.
9. Xác nhận idempotency ngăn side effect nghiệp vụ bị lặp.

Không dùng **Thread.sleep()** với một khoảng cố định duy nhất làm bằng chứng duy nhất. Nên dùng polling assertion với timeout để chờ committed offset hoặc trạng thái listener đạt điều kiện. Điều này giúp kiểm thử ít phụ thuộc vào tải máy và lịch chạy thread hơn.

### Các tình huống nên bao phủ

| Tình huống | Kết quả mong đợi |
|---|---|
| Listener xử lý nhanh, chưa đến **ackTime** | Offset có thể vẫn chưa được commit |
| **ackTime** đã đạt và có offset chờ | Container commit tiến độ đã xác nhận |
| Process dừng trước commit | Record chưa commit có thể được giao lại |
| Process dừng sau commit thành công | Consumer tiếp tục từ committed offset |
| Listener ném exception | Error handler quyết định retry/recovery |
| Commit thất bại | Log/metric phản ánh lỗi; không giả định checkpoint đã tiến lên |
| Không có record mới | Không có offset mới cần commit |

## 12. Các lỗi cấu hình và hiểu nhầm phổ biến

**Nghĩ rằng TIME commit sau đúng N mili giây tính từ từng record.** **ackTime** được tính từ lần commit trước, không phải timer riêng bắt đầu lại cho mỗi record.

**Bật auto commit cùng với container-managed acknowledgement.** Client có thể commit độc lập với listener container và làm sai kỳ vọng về tiến độ. Hãy kiểm tra **enable.auto.commit**.

**Dùng TIME để bảo đảm không có duplicate.** Process có thể dừng sau side effect nhưng trước commit. Consumer vẫn cần idempotency.

**Dùng TIME để sửa consumer lag.** Commit offset không làm listener xử lý nhanh hơn và không tăng năng lực consumer. Cần xem throughput, partition assignment và downstream latency.

**Nhầm ackTime với max.poll.interval.ms.** Một giá trị điều khiển commit; giá trị kia giới hạn thời gian giữa các lần poll. Tăng một giá trị không thay thế vai trò của giá trị còn lại.

**Cho rằng TIME giới hạn số record chưa commit.** Với throughput cao, số record đã xử lý trong khoảng thời gian có thể lớn. Nếu cần điều kiện theo số lượng, xem COUNT hoặc COUNT_TIME.

**Bỏ qua hành vi của error handler.** Retry và recovery có thể ảnh hưởng offset nào được xem là hoàn tất. Hãy kiểm tra **ackAfterHandle**, **commitRecovered**, seek và transaction behavior theo cấu hình thực tế.

**Chỉ kiểm tra cấu hình YAML.** Listener có thể dùng container factory khác hoặc cấu hình Java ghi đè. Xác minh container đang chạy.

## 13. Runbook khi commit offset chậm

Khi thấy offset không tiến lên như mong đợi:

1. Xác định consumer group, topic, partition và committed offset hiện tại.
2. Xác minh listener vẫn nhận và xử lý record.
3. Kiểm tra AckMode hiệu lực của listener container.
4. Đọc giá trị **ackTime** và đơn vị thời gian thực tế.
5. Xác minh **enable.auto.commit=false**.
6. Kiểm tra listener processing time và số record trong mỗi poll.
7. Kiểm tra error handler, retry, recovery và exception đang lặp lại.
8. Kiểm tra log commit, commit latency và lỗi từ broker.
9. Đối chiếu consumer lag và số partition được giao cho consumer.
10. Nếu thay đổi **ackTime**, theo dõi commit rate, lag, duplicate và throughput sau thay đổi.

Nếu offset không tiến lên vì listener đang retry vô hạn hoặc xử lý một record quá lâu, giảm **ackTime** sẽ không giải quyết nguyên nhân. Cần xử lý đúng listener hoặc error handler trước.

## 14. Checklist trước khi dùng AckMode.TIME

**Cấu hình**

- [ ] Listener container thực sự dùng **ContainerProperties.AckMode.TIME**.
- [ ] **ackTime** được đặt rõ ràng và đúng đơn vị.
- [ ] **enable.auto.commit** tắt để container quản lý commit.
- [ ] Profile và container factory không ghi đè cấu hình ngoài dự kiến.
- [ ] Commit sync/async và transaction behavior đã được hiểu rõ.

**Nghiệp vụ và phục hồi**

- [ ] Listener chỉ coi xử lý thành công sau khi side effect cần thiết hoàn tất.
- [ ] Consumer có idempotency để chịu redelivery.
- [ ] Error handler có retry, backoff và recovery rõ ràng.
- [ ] Có quy trình xử lý commit failure và rebalance.
- [ ] DLT/recovery không làm mất khả năng truy vết event gốc.

**Quan sát và kiểm thử**

- [ ] Theo dõi commit rate, commit latency, consumer lag và processing time.
- [ ] Kiểm thử commit sau ngưỡng thời gian.
- [ ] Kiểm thử process dừng trước và sau commit.
- [ ] Kiểm thử listener exception và recovery.
- [ ] Runbook mô tả cách xác minh committed offset và replay.

## 15. Nguyên tắc sử dụng

AckMode.TIME phù hợp khi muốn container gom các offset đã xử lý thành công theo khoảng thời gian. **ackTime** càng ngắn thì checkpoint thường được cập nhật thường xuyên hơn và commit có thể xảy ra nhiều hơn. **ackTime** càng dài thì có thể giảm tần suất commit, nhưng khoảng tiến độ chưa lưu cũng có thể lớn hơn khi consumer dừng đột ngột.

Hãy chọn khoảng thời gian dựa trên yêu cầu redelivery và chi phí commit, sau đó kiểm chứng bằng metric và thử nghiệm sự cố. Giữ **enable.auto.commit** tắt, cấu hình error handler có chủ đích và làm cho listener idempotent. Khi hiểu rõ khác biệt giữa record đã xử lý và offset đã commit, đội vận hành có thể dự đoán hành vi phục hồi của consumer group và điều chỉnh AckMode.TIME một cách an toàn.
