# Xác nhận kết quả gửi trước khi hoàn tất use case

Trong một use case có phát sự kiện Kafka, việc gọi `KafkaTemplate.send()` chưa có nghĩa sự kiện đã được gửi thành công. Producer gửi dữ liệu theo cơ chế bất đồng bộ: lời gọi thường trả về ngay một đối tượng đại diện cho kết quả trong tương lai, trong khi Kafka client tiếp tục gửi record và chờ phản hồi từ broker. Nếu use case đánh dấu hoàn tất hoặc trả về thành công trước khi kết quả gửi được xác nhận, ứng dụng có thể báo thành công dù sự kiện cuối cùng bị lỗi.

Với một use case mà việc phát sự kiện là điều kiện để hoàn tất, ứng dụng cần chờ kết quả gửi thành công hoặc giữ use case ở trạng thái đang chờ cho đến khi kết quả đó được xác định. Điều này giúp ranh giới hoàn tất của nghiệp vụ phản ánh đúng điều hệ thống đã bảo đảm.

## 1. Phân biệt gọi send, broker acknowledgment và xử lý ở consumer

Một lần gửi qua Spring Kafka có nhiều mốc khác nhau:

1. Ứng dụng gọi `KafkaTemplate.send()` và Kafka client nhận yêu cầu gửi. Record có thể được đưa vào buffer để gửi sau.
2. Producer gửi request đến broker đang giữ vai trò leader của partition đích.
3. Broker phản hồi theo cấu hình `acks` của producer. Khi nhận được phản hồi thành công, kết quả gửi có thể được xem là thành công theo chính sách acknowledgment đã chọn.
4. Consumer đọc record, xử lý nghiệp vụ và commit offset của consumer group ở một thời điểm sau đó.

Các mốc này mang ý nghĩa khác nhau. `send()` trả về không đồng nghĩa broker đã xác nhận. Broker acknowledgment cũng không đồng nghĩa consumer đã đọc hoặc hoàn thành xử lý. Nếu use case chỉ yêu cầu sự kiện được Kafka tiếp nhận bền vững, có thể hoàn tất sau khi nhận kết quả gửi thành công theo cấu hình phù hợp. Nếu yêu cầu là một hệ thống khác đã xử lý sự kiện, producer acknowledgment không đủ; cần một cơ chế xác nhận ở tầng ứng dụng như request/reply, trạng thái workflow hoặc sự kiện phản hồi.

## 2. `KafkaTemplate.send()` trả về kết quả bất đồng bộ

Trong Spring Kafka 3.x, các phương thức `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`. Future hoàn tất khi Kafka producer nhận được kết quả thành công hoặc lỗi cho lần gửi. Khi thành công, `SendResult` cung cấp record đã gửi và metadata của broker, chẳng hạn topic, partition, offset và timestamp.

Ví dụ:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Could not publish order event: orderId={}", orderId, exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info("Published order event: topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
```

`whenComplete()` hữu ích để quan sát kết quả, ghi log hoặc cập nhật metric. Tuy nhiên, nếu phương thức gọi chỉ đăng ký callback rồi trả về ngay, use case vẫn có thể kết thúc trước khi callback chạy. Callback tự nó không giữ use case ở trạng thái chờ. Muốn kết quả gửi quyết định kết quả use case, phải chờ future hoặc kết hợp future vào kết quả bất đồng bộ mà use case trả về.

Ở Spring Kafka trước 3.0, API gửi dùng `ListenableFuture` và callback tương ứng. Khi làm việc với dự án cũ, cần dùng đúng kiểu future của phiên bản Spring Kafka đang cài đặt; không sao chép trực tiếp ví dụ `CompletableFuture` vào API cũ.

## 3. Chờ kết quả gửi trước khi trả về thành công

Nếu hợp đồng của use case yêu cầu trả lời đồng bộ, có thể chờ future bằng `get()` với thời hạn rõ ràng. Ví dụ dưới đây chỉ trả về `OrderAccepted` sau khi broker đã xác nhận lần gửi theo cấu hình producer:

```java
@Service
public class CreateOrderUseCase {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CreateOrderUseCase(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public OrderAccepted execute(CreateOrder command) {
        Order order = createOrder(command);
        OrderCreated event = OrderCreated.from(order);

        try {
            SendResult<String, OrderCreated> result = kafkaTemplate
                    .send("orders", order.getId(), event)
                    .get(5, TimeUnit.SECONDS);

            RecordMetadata metadata = result.getRecordMetadata();
            return new OrderAccepted(
                    order.getId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
        }
        catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new EventPublicationInterruptedException(
                    order.getId(), exception);
        }
        catch (ExecutionException | TimeoutException exception) {
            throw new EventPublicationFailedException(
                    order.getId(), exception);
        }
    }
}
```

Các kiểu `Order`, `OrderCreated`, `OrderAccepted` và exception trong ví dụ là kiểu miền nghiệp vụ minh họa. Điểm quan trọng là use case chỉ tạo kết quả thành công sau khi `get()` trả về `SendResult`. Nếu gửi thất bại hoặc không có kết quả trong thời hạn chờ, use case đi theo nhánh lỗi đã định nghĩa.

`get()` chặn thread đang gọi trong thời gian chờ. Cách này dễ hiểu và phù hợp khi hợp đồng nghiệp vụ cần một kết quả đồng bộ, nhưng không nên dùng tùy tiện trên các thread có số lượng giới hạn, chẳng hạn thread xử lý request của web server với lưu lượng lớn. Thời gian chờ cần phù hợp với `delivery.timeout.ms`, độ trễ mạng và ngân sách thời gian của request. Nếu timeout của use case ngắn hơn thời gian producer được phép tiếp tục gửi, ứng dụng có thể ngừng chờ trong khi Kafka client vẫn đang hoàn tất lần gửi.

Một `TimeoutException` từ `future.get(timeout, unit)` chỉ cho biết caller đã hết thời gian chờ. Nó không chứng minh broker chắc chắn chưa ghi record. Kết quả có thể chưa về do phản hồi chậm dù broker đã lưu record. Vì vậy, không nên tự động gửi lại cùng nghiệp vụ bằng một event ID mới ngay khi caller timeout; điều đó có thể tạo sự kiện trùng. Hãy dùng event ID ổn định và cơ chế idempotency ở consumer hoặc một quy trình tra cứu/trạng thái gửi có thể xử lý kết quả chưa rõ.

## 4. Kết hợp future vào use case bất đồng bộ

Nếu tầng ứng dụng hỗ trợ bất đồng bộ, use case có thể trả về `CompletableFuture` và chỉ hoàn tất future đó sau khi việc gửi thành công. Cách này không giữ một thread chờ trong lúc broker xử lý:

```java
public CompletableFuture<OrderAccepted> execute(CreateOrder command) {
    Order order = createOrder(command);
    OrderCreated event = OrderCreated.from(order);

    return kafkaTemplate.send("orders", order.getId(), event)
            .thenApply(result -> {
                RecordMetadata metadata = result.getRecordMetadata();
                return new OrderAccepted(
                        order.getId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            })
            .whenComplete((accepted, failure) -> {
                if (failure != null) {
                    log.error("Order event publication failed: orderId={}",
                            order.getId(), failure);
                }
            });
}
```

`thenApply()` chuyển kết quả gửi thành kết quả use case. Nếu future gửi hoàn tất bất thường, future kết quả cũng hoàn tất bất thường và caller có thể xử lý lỗi. `whenComplete()` chỉ quan sát kết quả; nó không biến lỗi thành thành công. Controller hoặc tầng gọi cần trả về/kết hợp chính future này thay vì bỏ nó đi rồi trả HTTP success ngay lập tức.

Ví dụ, một endpoint có thể trả về `CompletionStage<ResponseEntity<OrderAccepted>>` và ánh xạ kết quả khi future hoàn tất. Nếu hợp đồng API cho phép nhận yêu cầu trước rồi xử lý nền, endpoint có thể trả `202 Accepted` cùng operation ID; khi đó trạng thái operation phải thể hiện rõ `PENDING`, `SUCCEEDED` hoặc `FAILED`. Trạng thái `PENDING` không được trình bày như thể sự kiện đã được Kafka xác nhận.

## 5. Cấu hình acknowledgment để có bảo đảm phù hợp

Chờ future là cần thiết, nhưng mức độ bảo đảm của kết quả thành công còn phụ thuộc cấu hình producer và broker. Với sự kiện quan trọng, cấu hình thường dùng là `acks=all` cùng producer idempotence:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        max.in.flight.requests.per.connection: 5
```

Các giá trị timeout chỉ là ví dụ; cần điều chỉnh theo môi trường và thời gian đáp ứng mà use case cho phép. Khi bật idempotence, Kafka client yêu cầu các thiết lập tương thích về acknowledgment, retry và số request đang bay trên một connection. Không nên đặt các giá trị xung đột với điều kiện của producer idempotent. Với các Kafka client hiện đại, idempotence được bật mặc định trong nhiều cấu hình mặc định, nhưng khai báo rõ ràng giúp ý định vận hành dễ kiểm tra hơn.

Ý nghĩa chính của `acks`:

| Giá trị | Khi nào producer nhận xác nhận? | Hệ quả chính |
|---|---|---|
| `0` | Không chờ broker acknowledgment. | Producer không có xác nhận broker cho lần gửi; khó phát hiện lỗi gửi ở phía broker. |
| `1` | Khi leader partition ghi record vào log cục bộ và phản hồi. | Có thể mất record nếu leader lỗi trước khi replica khác sao chép record. |
| `all` hoặc `-1` | Khi các replica đang thuộc ISR xác nhận theo giao thức replication. | Tăng độ bền; có thể từ chối ghi nếu ISR không đáp ứng `min.insync.replicas`. |

`acks=all` không có nghĩa mọi replica được cấu hình cho partition đều phải xác nhận. Nó áp dụng cho tập replica đang nằm trong ISR (in-sync replicas). Thuộc tính broker/topic `min.insync.replicas` đặt số replica tối thiểu phải có trong ISR để broker chấp nhận ghi với `acks=all`. Ví dụ, replication factor là 3 và `min.insync.replicas=2` cho phép ghi khi có ít nhất hai replica trong ISR. Nếu số replica trong ISR thấp hơn ngưỡng, producer có thể nhận lỗi `NotEnoughReplicas` hoặc lỗi liên quan thay vì thành công giả.

Producer idempotence giúp tránh tạo bản ghi trùng do Kafka producer tự retry một lần gửi trong cùng phiên producer, bằng sequence number và producer ID. Nó không tự khử trùng các lệnh nghiệp vụ được ứng dụng gửi lại như hai lời gọi `send()` độc lập sau timeout, khởi động lại ứng dụng hoặc tạo producer session mới. Với retry ở tầng use case, nên dùng event ID ổn định và thiết kế consumer idempotent.

## 6. Xử lý lỗi gửi và retry có kiểm soát

Future gửi có thể hoàn tất bất thường do nhiều nguyên nhân: lỗi serialization, topic hoặc metadata không hợp lệ, lỗi xác thực/ủy quyền, broker không sẵn sàng, timeout, thiếu replica trong ISR hoặc lỗi mạng. Cần phân biệt lỗi cấu hình/logic với lỗi tạm thời để quyết định hành động tiếp theo.

Kafka producer đã có cơ chế retry cho các lỗi có thể retry. `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng hoàn tất một lần gửi, bao gồm thời gian chờ gửi batch, chờ phản hồi và retry. `request.timeout.ms` giới hạn thời gian chờ phản hồi cho một request; `max.block.ms` có thể ảnh hưởng thời gian lời gọi `send()` chờ metadata hoặc buffer khi producer chưa thể tiếp nhận record. Đây là các giới hạn khác nhau với timeout do caller truyền vào `future.get()`.

Khi future thất bại, cần:

- Ghi nhận event ID, use case ID, topic và loại lỗi để truy vết; tránh ghi toàn bộ payload nhạy cảm vào log.
- Giữ nguyên trạng thái lỗi hoặc pending phù hợp; không bắt exception rồi tiếp tục trả kết quả thành công.
- Để Kafka producer xử lý retry cho lỗi tạm thời theo cấu hình, rồi chỉ áp dụng retry ở tầng ứng dụng sau khi đã hiểu kết quả lần gửi trước.
- Dùng backoff, giới hạn số lần retry và event ID ổn định nếu cần retry ở tầng use case.
- Đưa các trường hợp lỗi kéo dài hoặc không thể khôi phục vào luồng phục hồi như outbox retry, dead-letter workflow hoặc cảnh báo vận hành.

Nếu caller timeout nhưng future vẫn đang chạy, không nên giả định lần gửi đã thất bại hoàn toàn. Cần có chiến lược cho kết quả chưa xác định: theo dõi future đến khi có kết quả, lưu trạng thái operation, hoặc cho phép gửi lại với cùng định danh nghiệp vụ và cơ chế khử trùng ở phía nhận.

## 7. Ranh giới hoàn tất khi use case còn ghi cơ sở dữ liệu

Một vấn đề phổ biến là use case vừa ghi database vừa phát sự kiện Kafka. Hai thao tác này thuộc hai hệ thống lưu trữ khác nhau và không tự động trở thành một giao dịch nguyên tử chỉ vì được đặt trong cùng một phương thức Java hoặc cùng một phương thức có `@Transactional`.

Nếu commit database trước rồi gửi Kafka, database có thể đã lưu đơn hàng nhưng sự kiện gửi thất bại. Nếu gửi Kafka trước rồi commit database, consumer có thể nhận sự kiện trong khi giao dịch database cuối cùng rollback. Chờ Kafka acknowledgment giúp biết kết quả gửi, nhưng không loại bỏ khoảng hở giữa hai hệ thống.

Với use case cần bảo đảm trạng thái database và ý định phát sự kiện được lưu cùng nhau, transactional outbox là một mẫu thiết kế phổ biến:

```text
Use case
   |
   v
Database transaction
   |-- ghi thay đổi nghiệp vụ
   |-- ghi event vào bảng outbox
   |
   v
Commit database
   |
   v
Outbox publisher đọc event chưa gửi
   |
   v
KafkaTemplate.send() và chờ kết quả
   |
   +---- thất bại ----> giữ trạng thái để retry
   |
   v
Broker acknowledgment thành công
   |
   v
Đánh dấu event outbox đã gửi
```

Trong mô hình này, use case có thể hoàn tất khi thay đổi nghiệp vụ và bản ghi outbox đã được commit trong cùng transaction database. Điều đó bảo đảm ý định phát sự kiện không bị mất khi ứng dụng dừng. Publisher tiếp tục gửi cho đến khi nhận xác nhận Kafka; sau đó đánh dấu outbox đã gửi. Nếu publisher dừng sau khi Kafka đã nhận record nhưng trước khi đánh dấu outbox, nó có thể gửi lại record. Vì vậy consumer vẫn cần idempotency dựa trên event ID.

Spring Kafka hỗ trợ Kafka transaction và có thể phối hợp transaction manager với transaction manager khác theo cơ chế đồng bộ transaction. Cách phối hợp này có thứ tự commit và giới hạn riêng; nó không biến database và Kafka thành một distributed transaction nguyên tử theo mặc định. Nếu dùng Kafka transaction, phải phân biệt thời điểm send future hoàn tất với thời điểm transaction Kafka commit thành công. Một record trong transaction chưa commit có thể chưa hiển thị cho consumer dùng `isolation.level=read_committed`. Với transaction, use case chỉ nên báo thành công sau khi ranh giới transaction đã hoàn tất thành công.

## 8. Ghi nhận bằng chứng gửi để vận hành và hỗ trợ

Khi broker xác nhận thành công, `SendResult` cung cấp metadata hữu ích để liên kết log của ứng dụng với log Kafka:

```java
SendResult<String, OrderCreated> result = future.get();
RecordMetadata metadata = result.getRecordMetadata();

log.info(
        "Kafka publish confirmed: eventId={}, topic={}, partition={}, offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset());
```

Nên theo dõi số lần gửi thành công/thất bại, tỷ lệ retry, độ trễ gửi, timeout, lỗi serialization, thời gian chờ buffer và số lượng event outbox đang chờ. Khi điều tra một use case, event ID và operation ID giúp đối chiếu giữa log ứng dụng, record Kafka và kết quả xử lý phía consumer.

Không dùng log callback thành công làm bằng chứng rằng consumer đã hoàn tất. Metadata topic/partition/offset chỉ xác nhận vị trí record được ghi theo chính sách acknowledgment của producer. Nếu nghiệp vụ cần biết consumer đã xử lý xong, hãy thiết kế một acknowledgment ở tầng ứng dụng, chẳng hạn response event mang cùng correlation ID hoặc một trạng thái workflow được cập nhật bởi consumer.

## 9. Nguyên tắc áp dụng trong use case

- Xác định rõ điều kiện hoàn tất: broker đã xác nhận nhận record, hay consumer đã hoàn thành nghiệp vụ.
- Không coi việc gọi `KafkaTemplate.send()` hoặc đăng ký callback là bằng chứng gửi thành công.
- Với use case đồng bộ, chờ future có timeout và chuyển lỗi gửi thành lỗi use case; bảo toàn trạng thái interrupt khi bắt `InterruptedException`.
- Với use case bất đồng bộ, trả về hoặc kết hợp future để caller chỉ nhận kết quả cuối cùng khi việc gửi đã có kết quả.
- Chọn `acks`, idempotence, replication factor và `min.insync.replicas` theo yêu cầu độ bền; cấu hình timeout phù hợp ngân sách thời gian.
- Phân biệt timeout của caller với kết quả gửi cuối cùng chưa xác định; dùng event ID ổn định để xử lý retry an toàn.
- Khi vừa ghi database vừa phát Kafka, cân nhắc transactional outbox để lưu thay đổi nghiệp vụ và ý định phát sự kiện trong cùng transaction database.
- Ghi log metadata gửi thành công và theo dõi lỗi, retry, độ trễ; không suy diễn từ producer acknowledgment rằng consumer đã xử lý xong.

Một use case chỉ nên được xem là hoàn tất ở đúng ranh giới mà hợp đồng nghiệp vụ cam kết. Nếu cam kết bao gồm việc Kafka đã tiếp nhận sự kiện, hãy chờ xác nhận gửi thành công theo cấu hình producer. Nếu cam kết bao gồm xử lý ở hệ thống nhận, cần thêm xác nhận ở tầng ứng dụng. Việc phân biệt hai mức này giúp kết quả trả về cho caller phản ánh đúng trạng thái thực tế của quy trình.
