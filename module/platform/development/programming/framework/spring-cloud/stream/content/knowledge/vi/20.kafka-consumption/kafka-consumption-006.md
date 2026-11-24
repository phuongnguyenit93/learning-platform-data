# Xác nhận thủ công bằng `KafkaHeaders.ACKNOWLEDGMENT`

Kafka Binder của Spring Cloud Stream thường để listener container quản lý việc commit offset theo cấu hình acknowledgement của Spring for Apache Kafka. Khi cần quyết định chính xác thời điểm một record được xem là đã xử lý, consumer có thể dùng chế độ xác nhận thủ công (`MANUAL` hoặc `MANUAL_IMMEDIATE`) và lấy đối tượng `Acknowledgment` từ header `KafkaHeaders.ACKNOWLEDGMENT`.

Manual acknowledgement hữu ích khi nghiệp vụ cần hoàn tất một transaction database, lưu trạng thái xử lý hoặc xác nhận một side effect trước khi Kafka ghi nhận tiến độ consumer group. Tuy nhiên, gọi `acknowledge()` chỉ điều khiển commit offset theo semantics của Spring Kafka. Nó không tạo transaction nguyên tử giữa Kafka và database, không biến Kafka thành queue có lệnh requeue và không tự bảo đảm exactly-once.

## 1. Vì sao cần xác nhận thủ công?

Kafka lưu record trong log theo partition. Consumer group theo dõi tiến độ đọc bằng committed offset cho từng partition. Khi listener xử lý record, listener container cần biết thời điểm có thể commit offset để sau restart group tiếp tục từ vị trí phù hợp.

Với cấu hình acknowledgement tự động của container, framework quyết định thời điểm commit dựa trên `AckMode`, ví dụ sau mỗi record (`RECORD`) hoặc sau khi xử lý xong các record được trả về từ một lần `poll()` (`BATCH`). Khi dùng manual acknowledgement, ứng dụng gọi `Acknowledgment.acknowledge()` sau khi đạt điểm hoàn tất đã định nghĩa.

Ví dụ, một consumer xử lý `OrderCreated` và cập nhật tồn kho:

1. Kafka giao record cho consumer.
2. Spring Cloud Stream chuyển record thành message và gọi hàm consumer.
3. Ứng dụng cập nhật tồn kho trong transaction database.
4. Transaction commit thành công.
5. Consumer gọi `acknowledge()` để báo rằng record có thể được tính vào tiến độ đã xử lý.

Nếu commit offset trước bước 4, ứng dụng có thể mất cơ hội đọc lại record khi database chưa được cập nhật. Nếu database commit xong nhưng ứng dụng dừng trước bước 5, Kafka có thể giao lại record; consumer cần idempotency để không áp dụng thay đổi tồn kho lần thứ hai.

## 2. Bật manual acknowledgement cho đúng binding

Trong Kafka Binder, cấu hình `ackMode` ở phần consumer-specific của binding. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              ack-mode: MANUAL
```

`processOrder-in-0` là input binding của bean `processOrder`. `ack-mode` nhận các giá trị trong enum `AckMode` của Spring Kafka. Hai chế độ dùng cho manual acknowledgement là:

- `MANUAL`: listener chủ động gọi `acknowledge()`. Offset được xếp hàng để commit theo semantics tương tự `BATCH`, tức sau khi các record thuộc lần poll trước được listener xử lý.
- `MANUAL_IMMEDIATE`: commit được thực hiện ngay khi `acknowledge()` được gọi trên consumer thread. Nếu gọi từ thread khác, acknowledgement được xếp hàng và commit theo cơ chế container; không nên giả định luôn có commit tức thời.

Nếu không cấu hình manual mode, container thường dùng `BATCH` theo mặc định của Spring Kafka. Khi manual mode được bật, Kafka Binder đưa header `kafka_acknowledgment` vào message; tên hằng chuẩn trong code là `KafkaHeaders.ACKNOWLEDGMENT`.

Ở các phiên bản Kafka Binder cũ, cấu hình `autoCommitOffset: false` cũng kích hoạt manual acknowledgement và cung cấp header này. Thuộc tính `autoCommitOffset` đã bị deprecated từ Kafka Binder 3.1 để chuyển sang `ackMode`. Với ứng dụng mới, ưu tiên cấu hình `ack-mode`; nếu bảo trì ứng dụng cũ, kiểm tra tài liệu đúng phiên bản trước khi đổi thuộc tính.

## 3. Lấy `Acknowledgment` từ message header

Để đọc Kafka-specific header, hàm consumer cần nhận `Message<T>` thay vì chỉ nhận payload `T`:

```java
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderCreated>> processOrder(InventoryService inventoryService) {
    return message -> {
        Acknowledgment acknowledgment = message.getHeaders().get(
                KafkaHeaders.ACKNOWLEDGMENT,
                Acknowledgment.class);

        if (acknowledgment == null) {
            throw new IllegalStateException(
                    "Kafka acknowledgment header is missing; check the binding ack-mode");
        }

        inventoryService.reserveOnce(message.getPayload());
        acknowledgment.acknowledge();
    };
}
```

Các điểm cần nhớ:

- `KafkaHeaders.ACKNOWLEDGMENT` là hằng header do Spring Kafka cung cấp.
- Giá trị header có kiểu `org.springframework.kafka.support.Acknowledgment`.
- Header này chỉ có khi binding được cấu hình ở chế độ manual tương ứng.
- Dùng `Message<T>` để truy cập header; `Consumer<T>` chỉ nhận payload nên không có cách lấy header qua tham số đó.
- `Acknowledgment` là đối tượng điều khiển nội bộ, không phải metadata nghiệp vụ để serialize hoặc chuyển tiếp sang topic khác.

Không nên âm thầm bỏ qua trường hợp header bị thiếu rồi vẫn trả về bình thường. Điều đó có thể khiến ứng dụng tưởng mình đang kiểm soát commit thủ công trong khi binding thực tế đang dùng chế độ khác. Hãy coi cấu hình sai là lỗi khởi tạo hoặc lỗi xử lý cần được phát hiện rõ ràng.

## 4. Chọn `MANUAL` hay `MANUAL_IMMEDIATE`

Hai chế độ đều yêu cầu ứng dụng gọi `acknowledge()`, nhưng thời điểm commit khác nhau:

| Chế độ | Hành vi khi gọi `acknowledge()` | Khi nào cân nhắc |
|---|---|---|
| `MANUAL` | Đánh dấu record đã ack; container commit theo semantics batch sau khi các record của poll được xử lý | Muốn kiểm soát record nào được xác nhận nhưng chấp nhận commit theo ranh giới poll |
| `MANUAL_IMMEDIATE` | Commit ngay nếu lời gọi diễn ra trên consumer thread; nếu không, container xếp hàng acknowledgement | Cần commit ngay tại listener thread sau khi công việc hoàn tất |

`MANUAL` không có nghĩa offset được commit ngay tại dòng gọi `acknowledge()`. Nó chỉ đánh dấu acknowledgement; container còn phải áp dụng quy tắc commit. `MANUAL_IMMEDIATE` cũng không nên được hiểu là tức thời trong mọi hoàn cảnh: thread gọi là yếu tố quan trọng.

Với xử lý đồng bộ đơn giản, bắt đầu bằng `MANUAL` thường dễ hiểu. Chọn `MANUAL_IMMEDIATE` khi cần semantics commit tức thời và có thể bảo đảm gọi trên consumer thread. Đừng chọn chỉ vì tên chế độ có chữ “immediate”.

## 5. Đặt acknowledgement sau khi nghiệp vụ hoàn tất

Một service riêng có thể quản lý transaction database. Khi lời gọi qua Spring proxy kết thúc bình thường, transaction interceptor commit trước khi trả quyền điều khiển về consumer:

```java
@Service
public class InventoryService {
    private final InventoryRepository inventory;
    private final ProcessedEventRepository processedEvents;

    public InventoryService(
            InventoryRepository inventory,
            ProcessedEventRepository processedEvents) {
        this.inventory = inventory;
        this.processedEvents = processedEvents;
    }

    @Transactional
    public void reserveOnce(OrderCreated event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        int updated = inventory.reserveIfAvailable(
                event.productId(), event.quantity());
        if (updated != 1) {
            throw new InsufficientInventoryException(event.productId());
        }

        processedEvents.save(new ProcessedEvent(event.eventId()));
    }
}
```

Consumer gọi service rồi mới xác nhận:

```java
@Bean
Consumer<Message<OrderCreated>> processOrder(InventoryService inventoryService) {
    return message -> {
        Acknowledgment acknowledgment = requireAcknowledgment(message);

        inventoryService.reserveOnce(message.getPayload());

        // Chỉ chạy sau khi transaction trong service đã commit thành công.
        acknowledgment.acknowledge();
    };
}
```

`requireAcknowledgment` là helper ứng dụng đọc header như ví dụ trước. `reserveIfAvailable` nên thực hiện cập nhật có điều kiện ở database, còn bảng `ProcessedEvent` cần unique constraint trên `eventId`. Chỉ kiểm tra `existsById` rồi ghi sau mà không có ràng buộc duy nhất vẫn có race condition khi hai lần giao cùng event được xử lý đồng thời.

Đặt transaction trong service riêng giúp Spring áp dụng proxy rõ ràng. Không gọi một phương thức `@Transactional` qua self-invocation trong cùng object rồi giả định transaction interceptor đã chạy. Cũng không chuyển công việc sang thread khác bên trong transaction rồi coi transaction của thread ban đầu vẫn bao phủ phần việc đó.

## 6. Nếu xử lý thất bại thì sao?

Nếu xử lý nghiệp vụ ném exception trước khi gọi `acknowledge()`, không xác nhận record như đã hoàn tất. Để exception đi tới error handling của binder/container hoặc phân loại nó tại tầng xử lý lỗi theo chính sách đã cấu hình.

```java
@Bean
Consumer<Message<OrderCreated>> processOrder(InventoryService inventoryService) {
    return message -> {
        Acknowledgment acknowledgment = requireAcknowledgment(message);

        try {
            inventoryService.reserveOnce(message.getPayload());
            acknowledgment.acknowledge();
        }
        catch (TransientInventoryException ex) {
            // Không ack; để error handler/retry policy xử lý lỗi tạm thời.
            throw ex;
        }
    };
}
```

Đoạn mã minh họa việc không ack khi transaction thất bại. Cơ chế retry, seek, recover hoặc gửi DLQ được điều khiển bởi error handler và cấu hình Kafka Binder/Spring Kafka. Manual ack không tự tạo retry policy và không tự bật DLQ.

Kafka là log có offset, không phải queue có thao tác đưa một message trở lại cuối hàng đợi. Khi record chưa được commit, consumer có thể đọc lại từ offset đã commit sau khi restart, seek hoặc error handler phục hồi. Vì vậy, không diễn giải `acknowledge()` như lệnh “xóa message” hoặc dùng thuật ngữ `REQUEUE` của RabbitMQ cho Kafka.

### 6.1. Retry và DLQ

Lỗi tạm thời như database timeout có thể được retry với số lần giới hạn và backoff. Lỗi dữ liệu xác định như JSON sai cú pháp hoặc schema không tương thích thường cần cách ly hoặc DLQ thay vì retry vô hạn.

Kafka Binder có hỗ trợ DLQ qua cấu hình consumer như `enable-dlq` và `dlq-name` (tên thuộc tính chính xác phụ thuộc phiên bản). Khi bật DLQ, cần xác định topic đích, partitioning, quyền publish và quy trình phát lại. Chỉ xem record đã được xử lý xong sau khi việc phục hồi/cách ly đã được thực hiện theo đúng hợp đồng của error handler. Không tự ack message gốc trước khi biết việc gửi DLQ đã thành công.

## 7. Hiểu offset và nguy cơ xử lý sai thứ tự

Kafka commit offset theo partition. Offset đã commit đại diện cho vị trí tiếp theo mà consumer group sẽ đọc khi khôi phục; nó không phải một cờ độc lập có thể bật/tắt tùy ý cho mọi record ở bất kỳ thứ tự nào.

Giả sử một partition có record 100, 101 và 102:

- Nếu 100, 101 và 102 đều xử lý thành công rồi được ack, container có thể commit tiến độ sau 102 theo ack mode.
- Nếu 100 chưa hoàn tất nhưng 101 và 102 được ack, việc commit vượt qua 100 có thể khiến 100 bị bỏ qua khi khôi phục.
- Với xử lý đồng thời hoặc ack ngoài thứ tự, cần cơ chế hỗ trợ out-of-order acknowledgements phù hợp và phải hiểu cách container trì hoãn commit. Không giả định gọi `acknowledge()` từ nhiều worker sẽ tự giữ đúng thứ tự.

Spring Kafka có cơ chế `asyncAcks` trong các phiên bản hỗ trợ để trì hoãn commit khi acknowledgements đến ngoài thứ tự và tạm dừng consumer cho tới khi các khoảng trống được hoàn tất. Đây là cấu hình container/version-specific; không bật hoặc dựa vào nó nếu chưa xác minh binder có chuyển cấu hình tương ứng. Cách đơn giản và an toàn hơn cho nhiều nghiệp vụ là xử lý tuần tự theo partition hoặc giữ thứ tự hoàn tất trước khi ack.

## 8. Không chuyển Acknowledgment tùy tiện sang thread khác

`Acknowledgment` gắn với delivery và trạng thái consumer container. Không serialize, lưu vào database hoặc giữ nó như một object lâu dài. Nếu đưa xử lý sang executor:

- Consumer có thể ack trước khi task thực sự hoàn tất nếu callback trả về và auto behavior vẫn được bật.
- `MANUAL_IMMEDIATE` chỉ commit tức thì khi gọi trên consumer thread; gọi từ thread khác có thể chỉ xếp hàng.
- Ack ngoài thứ tự có thể ảnh hưởng tiến độ commit theo partition.
- Process shutdown có thể làm mất task đang nằm trong bộ nhớ, trong khi record vẫn chưa được xác nhận.

Nếu cần xử lý nền, hãy dùng một thiết kế có giới hạn concurrency và lifecycle rõ ràng, đồng thời kiểm tra `asyncAcks`/container semantics của phiên bản cụ thể. Với công việc dài hoặc cần tách khỏi vòng đời consumer, cân nhắc ghi payload vào inbox/durable work table trong transaction rồi ack sau khi dữ liệu đã được lưu bền vững. Worker riêng tiếp tục xử lý inbox và quản lý trạng thái nghiệp vụ.

## 9. Manual acknowledgement không phải exactly-once

Hai cửa sổ lỗi quan trọng vẫn tồn tại:

**Database commit trước, offset commit sau:** database đã cập nhật nhưng process dừng trước `acknowledge()`. Kafka có thể giao lại record. Consumer phải nhận ra `eventId` đã xử lý và không lặp side effect.

**Offset commit trước, database commit sau:** nếu ứng dụng xác nhận quá sớm rồi database rollback hoặc process dừng, Kafka có thể không giao lại record trong khi nghiệp vụ chưa hoàn tất. Đây là lý do phải ack sau điểm hoàn tất nghiệp vụ.

Đối với tác động quan trọng, dùng `eventId` ổn định và inbox/processed-event table có unique constraint. Nếu producer vừa cập nhật database vừa phát event, dùng transactional outbox để tránh dual-write. Manual ack giúp chọn thời điểm commit offset; nó không tạo giao dịch phân tán giữa Kafka, database và dịch vụ ngoài.

## 10. Kiểm thử manual acknowledgement

Kiểm thử cần xác nhận cả việc gọi callback và tiến độ thực tế của consumer group:

| Tình huống | Điều cần xác minh |
|---|---|
| `ack-mode` là `MANUAL` và header tồn tại | Consumer đọc được `Acknowledgment` từ `KafkaHeaders.ACKNOWLEDGMENT` |
| Không gọi `acknowledge()` rồi dừng consumer | Record có thể được đọc lại từ committed offset sau restart |
| Commit database rồi gọi ack | Database có thay đổi và offset tiến lên theo semantics đã cấu hình |
| Database rollback trước ack | Record không bị commit như đã hoàn tất; error handler xử lý theo policy |
| Process dừng sau DB commit trước ack | Redelivery không tạo side effect trùng nhờ idempotency |
| `MANUAL` so với `MANUAL_IMMEDIATE` | Xác nhận khác biệt commit theo poll batch và commit tức thời trên consumer thread |
| Ack ngoài thứ tự | Kiểm tra behavior và cấu hình hỗ trợ; không bỏ qua record chưa hoàn tất |
| DLQ publish thất bại | Message gốc không bị xác nhận như đã cách ly thành công |

Unit test có thể mock `Acknowledgment` để xác nhận `acknowledge()` chỉ được gọi sau khi service thành công. Integration test nên dùng Kafka thật hoặc môi trường kiểm thử tương đương để kiểm tra committed offset, redelivery, retry và DLQ. Test Binder không mô phỏng đầy đủ offset commit và listener container semantics của Kafka.

## 11. Quan sát trong production

Để chẩn đoán acknowledgement, log và metric nên có:

- Binding, destination, consumer group, topic, partition và offset.
- `eventId` và `correlationId` của nghiệp vụ.
- Thời điểm bắt đầu xử lý, transaction commit và gọi acknowledgement.
- Số lần retry, lỗi từ error handler, redelivery và số message DLQ.
- Consumer lag và tốc độ commit offset.
- Thời gian xử lý theo record và số record đang được xử lý.

Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Cảnh báo khi lag tăng, commit bị lỗi, retry kéo dài, DLQ tăng đột biến hoặc thời gian từ database commit đến offset commit vượt ngưỡng. Các chỉ số này giúp phân biệt consumer chậm với consumer đã hoàn tất nghiệp vụ nhưng chưa ghi nhận tiến độ.

## 12. Danh sách kiểm tra trước khi triển khai

- [ ] Đúng binding Kafka cần manual acknowledgement.
- [ ] `ack-mode` được đặt thành `MANUAL` hoặc `MANUAL_IMMEDIATE` theo mục tiêu commit.
- [ ] Consumer nhận `Message<T>` để truy cập header.
- [ ] `KafkaHeaders.ACKNOWLEDGMENT` được lấy với kiểu `Acknowledgment` và được kiểm tra null.
- [ ] Không dùng `autoCommitOffset` deprecated trong cấu hình mới nếu đã có `ack-mode` tương ứng.
- [ ] Chỉ gọi `acknowledge()` sau khi điểm hoàn tất nghiệp vụ đạt được.
- [ ] Transaction database commit trước khi ack; có idempotency cho cửa sổ redelivery.
- [ ] Exception trước ack đi qua retry/error handler/DLQ đã cấu hình.
- [ ] Hiểu `MANUAL` commit theo semantics batch và giới hạn thread của `MANUAL_IMMEDIATE`.
- [ ] Không ack ngoài thứ tự hoặc từ worker thread khi chưa hiểu container semantics.
- [ ] Có integration test xác nhận offset, restart, redelivery và DLQ trên Kafka.
- [ ] Theo dõi consumer lag, commit errors, retry, processing latency và DLQ.

`KafkaHeaders.ACKNOWLEDGMENT` cung cấp quyền điều khiển commit offset cho consumer khi Kafka Binder được cấu hình manual mode. `MANUAL` xếp acknowledgement để commit theo ranh giới poll; `MANUAL_IMMEDIATE` commit ngay khi gọi trên consumer thread. Hãy gọi `acknowledge()` sau khi tác động nghiệp vụ đã được lưu bền vững, giữ consumer idempotent và kiểm thử redelivery. Cách làm này giúp ứng dụng kiểm soát tiến độ Kafka rõ ràng mà vẫn xử lý đúng các cửa sổ lỗi giữa database và broker.

## Tài liệu tham khảo

- [Spring Cloud Stream Kafka Binder — Manual Acknowledgement](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Cloud Stream Kafka Binder — Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring for Apache Kafka — Committing Offsets and AckMode](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
