# Delivery semantics

Delivery semantics mô tả một thông điệp được giao và xác nhận như thế nào giữa publisher, broker và consumer: thông điệp có thể bị mất không, có thể xuất hiện nhiều lần không, thứ tự được bảo đảm đến đâu và hệ thống xác định thành công tại thời điểm nào. Khi kết nối Spring Modulith với broker qua adapter, cần hiểu rõ bảo đảm của từng chặng để thiết kế retry, acknowledgement và xử lý trùng phù hợp.

Ba cách diễn đạt phổ biến là **at-most-once**, **at-least-once** và **effectively-once**. Chúng không phải ba nút cấu hình có thể bật để tự động bảo đảm toàn bộ hệ thống. Delivery semantics đầu cuối là kết quả của cách publisher ghi dữ liệu, adapter gửi message, broker lưu và phân phối message, consumer xử lý side effect, rồi xác nhận message.

## 1. Ba kiểu delivery semantics

| Semantics | Bảo đảm | Rủi ro chính | Khi thường cân nhắc |
| --- | --- | --- | --- |
| At-most-once | Một message được giao không quá một lần theo cơ chế đã chọn. | Message có thể mất nếu lỗi xảy ra trước khi xác nhận hoặc trước khi lưu bền vững. | Dữ liệu có thể tái tạo, thông báo không quan trọng hoặc chấp nhận bỏ sót. |
| At-least-once | Message được thử giao cho đến khi có xác nhận hoặc đạt chính sách dừng. | Consumer có thể nhận cùng message nhiều lần. | Sự kiện nghiệp vụ quan trọng cần tránh mất, consumer có thể xử lý idempotent. |
| Effectively-once | Tác động nghiệp vụ quan sát được chỉ xảy ra một lần dù message có thể được giao lặp. | Cần idempotency, transaction và lưu dấu xử lý đúng cách; không tự có từ broker. | Giao dịch nghiệp vụ cần kết quả nhất quán trước retry và redelivery. |

### At-most-once

Với at-most-once, sender hoặc broker không thử giao lại sau một số tình huống lỗi. Nếu message bị mất trước khi được lưu bền vững hoặc consumer xác nhận quá sớm, hệ thống không có lần giao tiếp theo để khôi phục. Đổi lại, consumer không phải xử lý duplicate do cơ chế retry của chặng đó.

Ví dụ, một telemetry event có thể được gửi theo kiểu fire-and-forget nếu số liệu được tổng hợp từ nguồn khác và đôi khi thiếu một mẫu vẫn chấp nhận được. Cùng cách làm đó không phù hợp cho `OrderPaid` nếu việc mất event khiến đơn hàng không được cập nhật.

### At-least-once

At-least-once ưu tiên không bỏ mất message bằng cách giữ message cho đến khi có acknowledgement hoặc thử lại khi timeout. Nếu consumer đã commit nghiệp vụ nhưng acknowledgement bị mất trên đường về broker, broker có thể giao lại message. Vì vậy duplicate là hành vi bình thường cần dự kiến.

Ví dụ, consumer nhận `OrderConfirmed`, ghi reservation vào database rồi bị dừng trước khi ack. Broker giao lại message sau khi consumer khởi động; nếu không có idempotency, reservation có thể bị tạo hai lần.

### Effectively-once

Effectively-once tập trung vào kết quả nghiệp vụ: một message có thể được nhận nhiều lần, nhưng các lần lặp không tạo thêm tác động. Consumer thường dùng message ID ổn định cùng inbox table có unique constraint, hoặc một thao tác nghiệp vụ vốn đã idempotent. Việc kiểm tra ID đã xử lý, cập nhật nghiệp vụ và ghi nhận ID phải nằm trong cùng transaction database.

Đây là cách đạt kết quả một lần trong phạm vi transaction và side effect được kiểm soát. Nếu consumer còn gọi dịch vụ ngoài, gửi email hoặc phát message khác, các tác động đó cần cơ chế idempotency/outbox riêng. Không nên gọi đây là exactly-once end-to-end nếu chưa chứng minh được tất cả ranh giới đều nằm trong cùng bảo đảm nguyên tử.

## 2. Xác định các ranh giới acknowledgement

Từ lúc event được tạo đến khi nghiệp vụ phía nhận hoàn tất có nhiều mốc xác nhận khác nhau. Một chặng thành công không có nghĩa chặng tiếp theo đã thành công.

| Ranh giới | Xác nhận có nghĩa gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| Transaction nguồn commit | Thay đổi nghiệp vụ và dữ liệu được ghi trong transaction nguồn đã commit. | Broker đã nhận message. |
| Adapter gửi thành công | Adapter nhận được xác nhận theo giao thức hoặc API của broker. | Consumer đã xử lý message. |
| Broker lưu message | Broker đã nhận và lưu theo durability/configuration được chọn. | Consumer đã commit nghiệp vụ. |
| Consumer xử lý xong | Logic consumer hoàn tất theo định nghĩa của ứng dụng. | Broker đã nhận acknowledgement nếu ack là một thao tác riêng. |
| Consumer ack/commit offset | Broker được phép coi message hoặc vị trí đọc đã được xác nhận. | Side effect ngoài transaction của consumer đã hoàn tất nếu ứng dụng xác nhận quá sớm. |

Với RabbitMQ, publisher confirms xác nhận broker đã nhận trách nhiệm đối với publish theo cấu hình queue/exchange và durability; consumer acknowledgements cho phép broker loại message khỏi hàng chờ giao lại. Với Kafka, producer acknowledgement và consumer offset commit là hai cơ chế riêng; offset commit cần được phối hợp với việc xử lý record. Chi tiết chính xác phụ thuộc cấu hình, phiên bản và client.

Một quy tắc quan trọng cho consumer at-least-once là chỉ ack hoặc commit offset sau khi side effect bền vững đã commit. Nếu ack trước khi ghi database, tiến trình có thể dừng và broker sẽ không giao lại message trong khi nghiệp vụ chưa được lưu. Nếu commit database trước rồi dừng trước ack, message có thể được giao lại; consumer cần idempotency để xử lý tình huống này.

## 3. Đặt Spring Modulith vào đúng chặng

Spring Modulith tổ chức application events và việc giao event đến các listener trong cùng ứng dụng. Event Publication Registry theo dõi publication đến transactional listener, ghi nhận publication hoàn tất và cho phép phát hiện publication còn dang dở theo cơ chế lưu trữ/cấu hình đang dùng.

Khi cần gửi event ra broker, Spring Modulith hỗ trợ externalization và tích hợp với adapter phù hợp. Event có thể được đánh dấu để externalize, ví dụ:

```java
import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
```

Đích `orders` là routing value theo cấu hình externalization của ứng dụng; ý nghĩa cụ thể và cách ánh xạ sang exchange, topic hoặc destination phụ thuộc adapter. Cần cấu hình broker integration tương ứng và kiểm tra cách adapter chuyển đổi event thành message. Annotation không tự tạo ra một broker, queue hoặc consumer.

Đối với listener nội bộ, `@ApplicationModuleListener` thường được dùng để nhận event bất đồng bộ sau commit. Đối với event externalized, adapter chịu trách nhiệm chuyển event qua ranh giới process. Hai luồng có thể cùng bắt đầu từ một application event nhưng có đích nhận và cơ chế xác nhận khác nhau.

Không đồng nhất trạng thái publication nội bộ với trạng thái xử lý ở consumer ngoài. Khi broker xác nhận publish, điều đó không có nghĩa consumer đã commit nghiệp vụ. Khi consumer ngoài ack message, điều đó cũng không chứng minh một listener nội bộ khác đã hoàn tất. Hãy xác định rõ từng chặng nào được registry theo dõi và adapter/broker nào chịu trách nhiệm xác nhận.

## 4. Tránh mất event giữa database và broker bằng outbox

Một lỗi kinh điển xảy ra khi ứng dụng commit dữ liệu nghiệp vụ rồi mới gửi message:

1. Đơn hàng được cập nhật thành `CONFIRMED` và transaction commit.
2. Tiến trình dừng trước khi adapter gửi `OrderConfirmed`.
3. Database đã có đơn hàng mới nhưng broker không có message.

Đảo thứ tự gửi trước rồi commit cũng có vấn đề: broker có thể nhận event trong khi transaction nguồn rollback. Outbox giải quyết khoảng trống này bằng cách ghi trạng thái nghiệp vụ và bản ghi cần gửi trong cùng một transaction database.

```java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.confirm();
    orders.save(order);

    OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            order.getId(),
            Instant.now()
    );

    outbox.append(OutboxMessage.pending(
            event.eventId(),
            "orders",
            event
    ));
}
```

`OutboxMessage` và `outbox` trong ví dụ là abstraction do ứng dụng định nghĩa. Một relay đọc các bản ghi đã commit, gửi qua adapter và đánh dấu đã publish sau khi nhận xác nhận phù hợp từ broker. Nếu relay dừng sau khi broker nhận message nhưng trước khi đánh dấu bản ghi, relay có thể gửi lại cùng message ID. Do đó outbox thường cung cấp at-least-once, và consumer vẫn phải idempotent.

Event Publication Registry của Spring Modulith và outbox có thể cùng xuất hiện trong một kiến trúc nhưng có vai trò khác nhau. Registry quản lý publication đến transactional listener theo mô hình Spring Modulith. Outbox tùy biến thường quản lý việc chuyển message từ transaction database sang broker hoặc một hệ thống bên ngoài. Chọn cơ chế theo ranh giới cần bảo vệ, tránh triển khai hai cơ chế retry độc lập cho cùng một chặng mà không có quy tắc phối hợp.

## 5. Thiết kế consumer idempotent

Consumer cần một định danh message ổn định. Publisher không tạo ID mới cho mỗi lần retry; broker redelivery phải giữ cùng ID để consumer nhận ra message cũ.

Một inbox table đơn giản có thể có cấu trúc:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(150) NOT NULL,
    message_id    VARCHAR(200) NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
```

Consumer thực hiện kiểm tra, cập nhật nghiệp vụ và ghi inbox trong cùng transaction:

```java
@Transactional
public void handle(OrderConfirmed message) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "inventory-order-confirmed",
            message.eventId(),
            Instant.now()
    );

    if (!firstDelivery) {
        return;
    }

    inventory.reserveFor(message.orderId());
}
```

`insertIfAbsent` là thao tác database có ràng buộc unique, ví dụ `INSERT ... ON CONFLICT DO NOTHING` ở database hỗ trợ cú pháp đó. Không chỉ gọi `existsById` rồi insert mà thiếu unique constraint: hai consumer đồng thời có thể cùng thấy message chưa tồn tại và cùng thực hiện nghiệp vụ.

Nếu `inventory.reserveFor` thất bại, transaction cần rollback cả inbox record để lần giao lại có thể thử lại. Nếu nghiệp vụ đã commit nhưng acknowledgement bị mất, lần giao lại gặp unique key và không lặp tác động. Với side effect không thể cùng transaction như HTTP call, email hoặc payment gateway, cần truyền idempotency key tới dịch vụ đích hoặc ghi một outbox tiếp theo để tách tác động đó thành chặng có thể phục hồi.

## 6. Thứ tự message và partitioning

Delivery semantics còn bao gồm thứ tự. Nhiều broker bảo đảm thứ tự trong một phạm vi nhất định, chẳng hạn một partition hoặc một queue, nhưng không bảo đảm thứ tự toàn cục khi có nhiều partition, consumer hoặc worker.

Nếu event của cùng một aggregate phải được xử lý theo thứ tự, hãy dùng aggregate ID làm partition key hoặc routing key, đồng thời giữ sequence/version tăng đơn điệu trên aggregate. Consumer có thể kiểm tra sequence để phát hiện message đến sai thứ tự hoặc bị thiếu.

Ví dụ, `OrderConfirmed` phải được xử lý trước `OrderShipped` cho cùng một đơn. Nếu hai event được gửi đến hai partition khác nhau, consumer có thể nhận `OrderShipped` trước. Có thể định tuyến cả hai theo `orderId` để giữ cùng partition, hoặc thiết kế consumer chịu được việc đến lệch thứ tự bằng cách kiểm tra trạng thái và sequence.

Các điểm cần quyết định:

- Thứ tự cần bảo đảm toàn hệ thống hay chỉ theo aggregate/key?
- Key nào xác định nhóm message cần đi cùng thứ tự?
- Có cho phép xử lý song song các key khác nhau không?
- Consumer sẽ làm gì khi sequence bị thiếu hoặc message đến trễ?
- Retry có làm một message chậm chặn các message sau cùng key không?

Không tăng số partition hoặc số consumer mà chưa xem xét tác động lên thứ tự. Tăng song song thường cải thiện throughput nhưng có thể thay đổi cách phân phối key và thứ tự hoàn tất.

## 7. Retry, dead-letter và poison message

Retry phù hợp với lỗi tạm thời như timeout hoặc broker/service phụ thuộc gián đoạn. Message không thể xử lý do payload sai, schema không tương thích hoặc vi phạm quy tắc nghiệp vụ có thể trở thành poison message: retry liên tục không làm lỗi biến mất.

Một chính sách vận hành nên có:

- Phân loại lỗi có thể retry và lỗi không thể retry.
- Backoff tăng dần, giới hạn thời gian và jitter.
- Giới hạn số lần thử hoặc deadline tổng.
- Dead-letter queue (DLQ) hoặc trạng thái cần can thiệp sau khi hết ngân sách.
- Công cụ tra cứu message, nguyên nhân lỗi và lịch sử attempt.
- Quy trình redrive sau khi sửa lỗi, giữ nguyên message ID và audit việc gửi lại.

Không retry đồng thời ở mọi tầng mà không tính tổng số lần thử. Ví dụ, broker redelivery 5 lần, adapter retry 3 lần và HTTP client retry 4 lần có thể tạo nhiều lần gọi downstream hơn dự kiến. Chọn nơi làm chủ retry cho mỗi chặng; nếu cần retry ở nhiều tầng, đặt giới hạn và quan sát riêng từng tầng.

DLQ không phải nơi để quên message. Cần cảnh báo backlog, đặt thời hạn lưu, phân quyền truy cập, ghi lý do chuyển vào DLQ và định nghĩa ai có quyền redrive. Khi redrive, tránh tạo message ID mới nếu đó vẫn là cùng một sự kiện; nếu phát sinh một hành động nghiệp vụ mới, hãy tạo event mới và liên kết `causation_id` với message gốc.

## 8. Delivery semantics theo broker và adapter

Adapter là lớp chuyển đổi giữa mô hình event của ứng dụng và giao thức broker. Adapter cần làm rõ cách ánh xạ event type, payload, header, routing key, message ID, acknowledgement và lỗi.

| Thành phần | Câu hỏi cần xác nhận |
| --- | --- |
| Publisher/adapter | Khi nào API gửi trả thành công? Có chờ publisher confirm/ack từ broker không? Timeout được phân loại thế nào? |
| Broker destination | Message có được lưu bền vững không? Replication, retention và durability được cấu hình ra sao? |
| Routing | Message đi vào topic, exchange, queue hoặc partition nào? Có routing key/partition key không? |
| Consumer adapter | Message được ack khi nào? Có manual ack hay auto ack? Offset commit được phối hợp với transaction thế nào? |
| Serialization | Payload có schema/version? Consumer xử lý event type hoặc version chưa biết ra sao? |
| Failure handling | Retry, redelivery, DLQ và redrive được cấu hình ở tầng nào? |

Với RabbitMQ, kiểm tra publisher confirms, durable exchange/queue, message persistence, consumer acknowledgement và dead-letter routing. Durable queue một mình không có nghĩa mọi message đều được lưu bền vững; cấu hình message và queue phải phù hợp với bảo đảm mong muốn.

Với Kafka, kiểm tra producer `acks`, idempotent producer, replication/minimum in-sync replicas, partition key và consumer offset commit. Idempotent producer giúp giảm duplicate do retry ở producer trong phạm vi Kafka hỗ trợ; nó không làm cho side effect trong database của consumer tự động exactly-once. Kafka transactions có thể bảo đảm các thao tác đọc/ghi trong phạm vi Kafka transaction, nhưng không tự bao trùm một transaction database tùy ý.

Không suy ra semantics chỉ từ tên adapter hoặc annotation. Hãy xem cấu hình thực tế, client version, broker durability, retry/ack mode và cách adapter đánh dấu publication thành công. Cùng một adapter có thể cho kết quả khác nhau khi thay đổi cấu hình xác nhận hoặc độ bền message.

## 9. Kiểm thử delivery semantics

Kiểm thử cần mô phỏng lỗi tại ranh giới giữa các chặng, đặc biệt là trường hợp một bên đã commit còn acknowledgement chưa đến bên kia.

1. Publisher commit dữ liệu nghiệp vụ và outbox record trong cùng transaction; rollback thì cả hai cùng không tồn tại.
2. Broker từ chối publish hoặc timeout; adapter không đánh dấu message đã gửi thành công.
3. Broker nhận message nhưng relay dừng trước khi đánh dấu outbox; lần chạy lại có thể gửi duplicate với cùng message ID.
4. Consumer commit database rồi dừng trước acknowledgement; redelivery không tạo tác động nghiệp vụ thứ hai.
5. Consumer lỗi trước commit; inbox và thay đổi nghiệp vụ cùng rollback để message có thể được thử lại.
6. Poison message vượt giới hạn retry và được chuyển vào DLQ với thông tin truy vết.
7. Redrive giữ liên kết với event gốc và tạo audit rõ ràng.
8. Các message cùng aggregate được xử lý theo quy tắc thứ tự đã chọn.
9. Serialization tương thích giữa producer và consumer ở các phiên bản schema được hỗ trợ.

Kiểm thử tích hợp với broker thực tế hoặc Testcontainers giúp xác minh publisher confirms, ack, redelivery, partitioning và DLQ. Kiểm thử đơn vị có thể xác minh phân loại lỗi, chính sách backoff và idempotency logic, nhưng không thay thế kiểm thử giao thức broker.

## 10. Quan sát delivery trong môi trường chạy

Theo dõi cả trạng thái từng chặng và độ trễ đầu cuối. Một dashboard hữu ích có thể gồm:

- số message được publish thành công, publish thất bại và timeout;
- backlog và tuổi message lâu nhất ở broker;
- consumer lag hoặc số message đang unacknowledged;
- tỷ lệ redelivery, retry, DLQ và redrive;
- thời gian từ lúc event phát sinh đến lúc consumer commit nghiệp vụ;
- số duplicate bị inbox loại bỏ;
- lỗi serialization, routing không tìm thấy destination và schema không tương thích.

Log và trace nên dùng message ID, event type, aggregate ID, correlation ID, destination, partition/routing key và consumer name. Không đưa toàn bộ payload hoặc dữ liệu nhạy cảm vào metric label hay log mặc định. Với message được retry, giữ ID ổn định để có thể nối các lần giao lại vào cùng một timeline.

## 11. Checklist chọn delivery semantics

- [ ] Đã xác định message có thể mất hay phải được giao lại.
- [ ] Đã chọn at-most-once, at-least-once hoặc mục tiêu effectively-once cho từng chặng.
- [ ] Publisher chỉ coi gửi thành công sau acknowledgement phù hợp với yêu cầu durability.
- [ ] Consumer ack/commit offset sau khi side effect bền vững đã commit.
- [ ] Message ID ổn định qua retry và redelivery.
- [ ] Consumer có idempotency/inbox với unique constraint và transaction phù hợp.
- [ ] Outbox bảo vệ khoảng trống giữa transaction database và broker khi cần.
- [ ] Thứ tự được định nghĩa theo key/aggregate và kiểm thử.
- [ ] Retry có giới hạn, phân loại lỗi, backoff, DLQ và quy trình redrive.
- [ ] Cấu hình adapter/broker được kiểm tra thay vì suy ra từ tên công nghệ.
- [ ] Có metric, log và trace cho từng chặng giao nhận.

Delivery semantics là thuộc tính của toàn bộ đường đi message, không chỉ của broker. Trong Spring Modulith, application event và Event Publication Registry giúp tổ chức giao tiếp nội bộ; externalization và adapter kết nối event với broker. Khi mỗi ranh giới có acknowledgement rõ ràng, message ID ổn định, consumer idempotent và chính sách phục hồi nhất quán, hệ thống có thể đạt mức tin cậy phù hợp với yêu cầu nghiệp vụ mà vẫn kiểm soát được duplicate, mất message và thứ tự xử lý.
