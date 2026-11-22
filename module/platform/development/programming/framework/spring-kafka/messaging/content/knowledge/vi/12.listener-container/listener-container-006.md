# AckMode RECORD

## 1. AckMode là gì?

Kafka consumer đọc record theo offset. Sau khi ứng dụng xử lý record, consumer group cần lưu một offset đã commit để biết lần đọc tiếp theo nên bắt đầu ở đâu. Trong Spring Kafka, listener container quản lý việc xác nhận tiến độ này thông qua `AckMode`.

`AckMode.RECORD` yêu cầu container commit offset sau khi listener xử lý thành công từng record. Khi phương thức listener trả về bình thường, container xem record đó đã được xử lý xong và xác nhận offset tương ứng. Nếu listener ném exception, record chưa được xác nhận theo luồng thành công; error handler sẽ quyết định retry, phục hồi hoặc chuyển xử lý lỗi theo cấu hình.

`RECORD` phù hợp với record listener, nơi mỗi lần gọi phương thức chỉ xử lý một record. Chế độ này giúp tiến độ commit bám sát từng record, giảm số record phải đọc lại khi một record phía sau bị lỗi.

## 2. Cách RECORD hoạt động trong một lần poll

Một lần `poll()` của Kafka consumer có thể trả về nhiều record. Với record listener, Spring Kafka gọi phương thức listener lần lượt cho từng record trong kết quả poll. Khi một lần gọi hoàn tất thành công, `AckMode.RECORD` xác nhận offset của record đó.

Ví dụ consumer nhận ba record liên tiếp từ cùng partition:

| Record | Offset | Kết quả listener | Tiến độ commit minh họa |
|---|---:|---|---:|
| A | 40 | Thành công | 41 |
| B | 41 | Thành công | 42 |
| C | 42 | Ném exception | Chưa commit 43 theo luồng thành công |

Kafka lưu offset tiếp theo cần đọc, vì vậy xử lý xong record offset 40 thì offset được commit là 41. Nếu record C thất bại, các record A và B đã được xác nhận; lần xử lý lại có thể bắt đầu từ offset 42 sau khi lỗi được xử lý theo error handler.

~~~mermaid
flowchart TD
    A["Consumer poll"] --> B["Record offset 40"]
    B --> C["Listener xử lý A"]
    C --> D["Thành công"]
    D --> E["Commit offset 41"]
    E --> F["Record offset 41"]
    F --> G["Listener xử lý B"]
    G --> H["Thành công"]
    H --> I["Commit offset 42"]
    I --> J["Record offset 42"]
    J --> K["Listener xử lý C"]
    K --> L["Exception"]
    L --> M["Error handler: retry / recover"]
~~~

Bảng và sơ đồ minh họa các record của cùng một partition. Khi một poll chứa record từ nhiều partition, offset được quản lý riêng cho từng partition; không có một offset duy nhất đại diện cho toàn bộ topic.

## 3. Cấu hình AckMode.RECORD bằng Spring Boot

Nếu toàn bộ listener record trong ứng dụng đều cần commit sau từng record, có thể cấu hình trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: record
~~~

Ý nghĩa các thuộc tính:

- `spring.kafka.listener.type: single` chọn chế độ listener xử lý từng record.
- `spring.kafka.listener.ack-mode: record` yêu cầu commit offset sau mỗi lần listener xử lý thành công một record.
- `enable-auto-commit: false` tắt auto commit theo lịch của Kafka client để listener container quản lý tiến độ commit.
- `auto-offset-reset: earliest` chỉ áp dụng khi group chưa có offset hợp lệ; nó không ghi đè offset đã commit.

Spring Kafka listener container thường quản lý commit offset thay cho auto commit của Kafka consumer. Hãy để `enable-auto-commit` ở `false` để hành vi xác nhận do `AckMode` quyết định rõ ràng.

## 4. Ví dụ record listener với RECORD

Listener nhận một sự kiện đơn hàng và gọi nghiệp vụ đồng bộ:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderProjectionService orderProjectionService;

    public OrderCreatedListener(
            OrderProjectionService orderProjectionService) {
        this.orderProjectionService = orderProjectionService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor"
    )
    public void handle(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

Khi `orderProjectionService.apply(event)` hoàn tất và phương thức `handle` trả về bình thường, container có thể commit offset của record theo `AckMode.RECORD`. Nếu lời gọi nghiệp vụ ném exception, container chuyển lỗi đến error handler.

Chữ ký listener chỉ nhận payload nên mã nghiệp vụ không cần phụ thuộc vào metadata Kafka. Nếu cần kiểm tra topic, partition, offset hoặc key, có thể nhận `ConsumerRecord`:

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
    public void handle(
            ConsumerRecord<String, OrderCreatedEvent> record) {

        auditService.record(
            record.value(),
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
~~~

`AckMode.RECORD` được cấu hình trên listener container. Không cần gọi `Acknowledgment.acknowledge()` trong listener khi dùng chế độ này.

## 5. Cấu hình RECORD bằng listener container factory

Nếu ứng dụng có nhiều listener và chỉ một số listener cần `RECORD`, hãy tạo container factory riêng. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            recordKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);
        factory.setCommonErrorHandler(kafkaErrorHandler);

        return factory;
    }
}
~~~

Chỉ định factory cho listener cần chế độ này:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    containerFactory = "recordKafkaListenerContainerFactory"
)
public void handle(OrderCreatedEvent event) {
    orderProjectionService.apply(event);
}
~~~

Các listener dùng factory mặc định vẫn có thể giữ `BATCH` hoặc chế độ được cấu hình riêng. Tên factory trong thuộc tính `containerFactory` phải khớp với tên bean Spring đã khai báo.

Không đặt `AckMode.RECORD` trên batch listener. Batch listener nhận cả danh sách record trong một lần gọi và cần một chế độ xác nhận phù hợp với xử lý theo batch, thường là `BATCH` hoặc manual acknowledgment.

## 6. RECORD khác gì BATCH, TIME và COUNT?

Spring Kafka cung cấp nhiều `AckMode` để cân bằng giữa độ sát của tiến độ commit, chi phí commit và cách xử lý lỗi.

| AckMode | Thời điểm xác nhận offset | Cách sử dụng thường gặp |
|---|---|---|
| `RECORD` | Sau mỗi record listener xử lý thành công | Muốn commit sát từng record |
| `BATCH` | Sau khi xử lý xong các record của một lần poll | Mặc định phổ biến, phù hợp cả luồng xử lý theo poll |
| `TIME` | Khi đã qua khoảng thời gian cấu hình và có record cần xác nhận | Muốn giới hạn tần suất commit theo thời gian |
| `COUNT` | Khi đạt số record cần xác nhận | Muốn gom commit theo số lượng |
| `COUNT_TIME` | Khi đạt ngưỡng số record hoặc thời gian | Kết hợp giới hạn theo số lượng và thời gian |
| `MANUAL` | Sau khi listener gọi `acknowledge()`, container xử lý commit theo chu kỳ phù hợp | Ứng dụng chủ động quyết định lúc xác nhận |
| `MANUAL_IMMEDIATE` | Commit ngay khi `acknowledge()` được gọi trên consumer thread | Cần xác nhận tường minh tại thời điểm xử lý |

`RECORD` và `BATCH` là hai lựa chọn dễ so sánh nhất:

- `RECORD` commit sau từng record thành công. Nếu record tiếp theo lỗi, các record trước đó đã có thể được xác nhận.
- `BATCH` chờ listener xử lý xong các record của poll rồi mới xác nhận tiến độ của batch. Nếu batch thất bại, có thể phải đọc lại nhiều record hơn tùy error handler và ack mode.

`TIME`, `COUNT` và `COUNT_TIME` giảm tần suất commit bằng cách gom nhiều record trước khi xác nhận. Điều này có thể giảm overhead commit nhưng làm tăng số record có khả năng được nhận lại khi consumer dừng bất ngờ trước lần commit tiếp theo.

## 7. RECORD và xử lý lỗi

`AckMode.RECORD` không tự quyết định retry bao nhiêu lần hoặc xử lý record lỗi ở đâu. Nó chỉ quy định thời điểm container xác nhận offset sau khi listener xử lý thành công. Việc retry và phục hồi do error handler quản lý.

Có thể cấu hình `DefaultErrorHandler` với backoff cố định cho một record lỗi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        return new DefaultErrorHandler(
            new FixedBackOff(1000L, 2L)
        );
    }
}
~~~

`FixedBackOff(1000L, 2L)` minh họa khoảng chờ một giây giữa các lần thử lại, với hai lần retry bổ sung sau lần xử lý ban đầu. Trong ví dụ container factory ở phần trước, Spring inject bean `DefaultErrorHandler` này và đăng ký bằng `factory.setCommonErrorHandler(kafkaErrorHandler)`. Nếu dùng factory khác, hãy đăng ký error handler tương ứng trên factory đó.

Với một record có offset 42:

1. Listener nhận record và xử lý thất bại.
2. Error handler chờ theo backoff rồi gọi lại listener theo chính sách retry.
3. Nếu retry thành công, container xác nhận tiến độ record đó.
4. Nếu hết retry, recoverer có thể ghi record lỗi vào dead-letter topic hoặc thực hiện hành động phục hồi đã cấu hình. Việc xác nhận offset sau recovery phụ thuộc cấu hình error handler và recoverer.

Nếu không có recoverer hoặc recovery thất bại, record có thể tiếp tục được xử lý lỗi theo chính sách container. Cần kiểm thử cụ thể để biết offset có được commit sau khi recovery hay không.

Với `RECORD`, các record trước đó đã xử lý thành công có thể được commit riêng. Điều này giúp giới hạn phạm vi đọc lại khi một record phía sau thất bại. Tuy nhiên, nếu listener đã thực hiện side effect rồi ném exception, record có thể được nhận lại và side effect có thể lặp. Hãy thiết kế nghiệp vụ idempotent, ví dụ dùng `eventId` và ràng buộc duy nhất ở database.

## 8. Những giới hạn cần lưu ý

### Listener phải hoàn tất công việc trước khi trả về

Container xác định listener thành công khi phương thức xử lý hoàn tất bình thường. Nếu listener chỉ khởi chạy một tác vụ bất đồng bộ rồi trả về ngay, container có thể commit offset trước khi tác vụ đó hoàn thành:

~~~java
@KafkaListener(topics = "orders", groupId = "order-processor")
public void handle(OrderCreatedEvent event) {
    executor.submit(() -> orderService.apply(event));
    // Phương thức trả về ngay; container có thể xác nhận offset.
}
~~~

Nếu tác vụ nền thất bại sau khi phương thức đã trả về, Kafka có thể đã lưu offset và không tự giao lại record. Với `AckMode.RECORD`, hãy hoàn tất nghiệp vụ đồng bộ trước khi trả về, hoặc chọn mô hình xử lý bất đồng bộ có quản lý acknowledgment và vòng đời lỗi rõ ràng.

### Commit offset và transaction database là hai việc riêng

`AckMode.RECORD` không tự tạo giao dịch nguyên tử giữa commit offset Kafka và ghi dữ liệu vào database. Nếu database đã ghi thành công nhưng tiến trình dừng trước khi commit offset, record có thể được đọc lại. Nếu ứng dụng commit offset trước khi dữ liệu bền vững, lỗi sau đó có thể làm mất tác động nghiệp vụ.

Với nghiệp vụ cần phối hợp trạng thái database và Kafka, cần xem xét transaction phù hợp hoặc mẫu Inbox/Outbox, đồng thời thiết kế idempotent để chịu được việc nhận lại.

### RECORD không có nghĩa exactly-once

Commit sau mỗi record chỉ điều chỉnh tiến độ đọc. Nó không bảo đảm hiệu ứng nghiệp vụ chỉ xảy ra đúng một lần. Kafka có thể giao lại record nếu xử lý thành công nhưng commit chưa hoàn tất, hoặc ứng dụng có thể tạo side effect trước khi gặp lỗi.

Hãy phân biệt:

- **At-least-once:** record có thể được nhận lại; ứng dụng cần xử lý duplicate.
- **At-most-once:** có thể mất record nếu commit trước khi xử lý hoàn tất.
- **Exactly-once:** cần một thiết kế transaction và phạm vi bảo đảm rõ ràng; chỉ chọn `AckMode.RECORD` không tạo ra bảo đảm này.

## 9. Kiểm thử AckMode.RECORD

Nên kiểm thử cả luồng thành công và lỗi để xác nhận thời điểm commit:

| Kịch bản | Điều cần xác minh |
|---|---|
| Một record xử lý thành công | Offset tiếp theo của partition được commit |
| Nhiều record trong một poll xử lý thành công | Tiến độ được xác nhận sau từng record |
| Record giữa poll phát sinh exception | Record trước đó đã xác nhận; record lỗi đi qua error handler |
| Retry thành công | Record được xác nhận sau khi listener hoàn tất thành công |
| Recovery thất bại | Offset không bị xác nhận ngoài ý muốn |
| Consumer dừng sau side effect nhưng trước commit | Record có thể được nhận lại và nghiệp vụ phải chịu được duplicate |

Có thể dùng Embedded Kafka hoặc Testcontainers để chạy kiểm thử tích hợp. Gửi các record có `eventId` khác nhau, cố ý làm một record thất bại, sau đó kiểm tra listener invocation, committed offset bằng Kafka Admin API hoặc lệnh `kafka-consumer-groups.sh --describe`.

Không nên chỉ kiểm tra rằng listener đã được gọi. Cần kiểm tra cả offset đã commit và tác động nghiệp vụ để phát hiện trường hợp commit quá sớm hoặc xử lý trùng.

## 10. Khi nào nên chọn AckMode.RECORD?

Chọn `RECORD` khi mỗi record là một đơn vị nghiệp vụ độc lập, listener xử lý đồng bộ và muốn xác nhận tiến độ ngay sau từng record thành công. Chế độ này đặc biệt hữu ích khi một record lỗi không nên khiến toàn bộ các record thành công trước đó trong cùng lần poll phải đọc lại.

Cân nhắc `BATCH` khi muốn giảm số lần commit và chấp nhận phạm vi xử lý lại theo batch. Chọn manual acknowledgment khi ứng dụng cần kiểm soát rõ thời điểm xác nhận, chẳng hạn chỉ ack sau khi hoàn tất một quy trình riêng.

Checklist triển khai:

- [ ] Dùng record listener, không dùng batch listener với `AckMode.RECORD`.
- [ ] Cấu hình `spring.kafka.listener.ack-mode: record` hoặc container factory tương ứng.
- [ ] Để `enable.auto.commit: false` để container quản lý offset.
- [ ] Chỉ trả về bình thường sau khi công việc nghiệp vụ đã hoàn tất.
- [ ] Cấu hình error handler và chính sách retry/recovery phù hợp.
- [ ] Thiết kế idempotent để chịu được việc record được nhận lại.
- [ ] Theo dõi committed offset, consumer lag và lỗi listener.
- [ ] Kiểm thử trường hợp thành công, lỗi, retry và recovery.

`AckMode.RECORD` giúp Spring Kafka xác nhận offset sau từng record được xử lý thành công. Hiểu rõ mối quan hệ giữa thời điểm listener trả về, error handler và commit offset sẽ giúp giới hạn phạm vi đọc lại, đồng thời tránh nhầm việc commit từng record với bảo đảm exactly-once cho toàn bộ nghiệp vụ.
