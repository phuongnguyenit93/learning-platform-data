# Delivery mode và điều kiện lưu thông điệp bền vững

Khi một producer gửi message vào RabbitMQ, message có thể được đánh dấu là persistent hoặc transient. Delivery mode là một thuộc tính của từng message, cho RabbitMQ biết message cần được giữ lại qua lần khởi động lại broker hay có thể bị loại khi broker restart. Tuy nhiên, chỉ đặt delivery mode thành persistent chưa đủ để bảo đảm message còn tồn tại sau restart. Queue nhận message cũng phải durable, exchange và binding phải được khôi phục, message phải được định tuyến đến queue, và publisher cần biết broker đã chấp nhận message đến mức nào.

Spring Cloud Stream RabbitMQ Binder ánh xạ những khái niệm này thành các cấu hình producer và consumer. Bài học tập trung vào điều kiện lưu bền vững, cách khai báo delivery mode, durable subscription, publisher confirms và lựa chọn classic queue hay quorum queue. Mục tiêu là thiết kế một đường đi mà message quan trọng không biến mất chỉ vì ứng dụng consumer tạm dừng hoặc broker khởi động lại.

## 1. Delivery mode là thuộc tính của message

AMQP 0-9-1 định nghĩa delivery mode cho message:

| Delivery mode | Giá trị AMQP | Ý nghĩa |
|---|---:|---|
| `NON_PERSISTENT` / transient | 1 | Message không được yêu cầu giữ qua broker restart |
| `PERSISTENT` | 2 | Message được đánh dấu cần lưu bền vững |

Delivery mode nằm trong message properties. Nó không quyết định queue có tồn tại sau restart hay không. Queue có vòng đời và thuộc tính durability riêng.

Với classic queue:

- Message persistent được giữ lại sau restart nếu nó nằm trong durable queue.
- Message transient có thể bị loại khi broker restart, ngay cả khi queue là durable.
- Message persistent nằm trong non-durable queue cũng không còn sau restart vì chính queue bị xóa.

Vì vậy, producer và topology phải phối hợp. Không thể khắc phục một queue tạm thời bằng cách chỉ gửi message persistent.

## 2. Queue durable và exchange durable

RabbitMQ có thể khôi phục metadata của durable queue và durable exchange sau khi node khởi động lại. Queue chứa message; exchange định tuyến message đến queue. Binding nối exchange với queue bằng routing key hoặc quy tắc binding.

Đối với một luồng sự kiện cần tồn tại qua restart:

1. Exchange phải durable để topology định tuyến được khôi phục.
2. Queue của consumer group phải durable để queue và backlog còn tồn tại.
3. Binding giữa exchange và queue phải tồn tại; khi cả hai đầu đều durable, RabbitMQ lưu binding trong topology và khôi phục nó sau restart.
4. Message gửi vào queue classic phải có delivery mode persistent.
5. Publisher phải theo dõi publisher confirm để biết broker đã chấp nhận message.

Exchange durable không phải nơi lưu message. Nếu exchange tồn tại nhưng không có queue được bind phù hợp, message không có nơi lưu. Nếu queue durable nhưng message transient, message có thể bị loại khi broker restart.

RabbitMQ Binder mặc định tạo topic exchange cho destination. Thuộc tính `exchangeDurable` mặc định là `true`; `exchangeAutoDelete` mặc định là `true`. Nếu exchange cần tồn tại lâu dài ngay cả khi không còn queue bind vào, cân nhắc đặt `exchange-auto-delete: false`. Việc durable và auto-delete điều khiển hai hành vi khác nhau: durable liên quan đến restart, còn auto-delete liên quan đến việc xóa exchange sau khi các queue bind cuối cùng bị gỡ.

## 3. Durable consumer group trong RabbitMQ Binder

RabbitMQ Binder ánh xạ destination thành exchange. Với mỗi consumer group, binder tạo một queue và bind queue đó vào exchange. Queue group là nơi message được giữ khi consumer tạm dừng.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-processing
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              durable-subscription: true
              exchange-durable: true
              exchange-auto-delete: false
~~~

Trong ví dụ, group `order-processing` làm cho binder tạo queue có tên dựa trên destination và group. `durable-subscription` mặc định là `true` và chỉ có tác dụng khi binding có group. Khi bật, subscription/queue được khai báo durable để có thể tồn tại qua broker restart.

Nếu không khai báo group, binder tạo anonymous queue có tên ngẫu nhiên và auto-delete. Queue này phù hợp với client tạm thời, nhưng không phù hợp với consumer cần nhận lại message đã phát trong thời gian ứng dụng dừng. Message persistent gửi đến exchange không tự tạo ra một queue bền vững để lưu trữ.

Có thể đặt `durable-subscription: false` cho group nếu muốn queue không bền vững theo nhu cầu cụ thể. Khi đó, không được kỳ vọng backlog của queue còn sau broker restart hoặc khi queue bị xóa.

## 4. Provision queue trước khi consumer khởi động

Một tình huống dễ bị bỏ sót: producer bắt đầu publish trước khi consumer group từng khởi tạo queue. Nếu exchange chưa có queue được bind phù hợp, RabbitMQ không có nơi lưu message. Delivery mode persistent không giữ lại một message không được định tuyến.

Spring Cloud Stream hỗ trợ `required-groups` trên output binding để binder provision queue/binding cho các consumer group cần nhận message, ngay cả khi consumer chưa chạy:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            required-groups:
              - order-processing
      rabbit:
        bindings:
          orders-out-0:
            producer:
              delivery-mode: PERSISTENT
              exchange-durable: true
              exchange-auto-delete: false
~~~

Với `required-groups`, binder tạo queue và binding cho group được liệt kê. Điều này hữu ích khi producer và consumer được triển khai độc lập, hoặc producer có thể phát event trước lần chạy đầu tiên của consumer. Queue được provision theo cấu hình của binder; hãy xác minh queue thực tế và thuộc tính durability trong RabbitMQ Management UI.

`required-groups` không thay thế group trên input binding của consumer. Hai phía cần dùng cùng tên group và cùng destination. Nếu không có queue được provision hoặc queue binding không khớp, publisher có thể gửi thành công đến exchange nhưng không có consumer queue nào nhận message.

## 5. Cấu hình delivery mode trong Rabbit binder

Rabbit binder có thuộc tính producer `deliveryMode`. Giá trị mặc định hiện tại là `PERSISTENT`. Có thể khai báo tường minh để hợp đồng gửi message dễ kiểm tra:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
      rabbit:
        bindings:
          orders-out-0:
            producer:
              delivery-mode: PERSISTENT
~~~

Thuộc tính nằm dưới `spring.cloud.stream.rabbit.bindings.<bindingName>.producer`. `PERSISTENT` là lựa chọn phù hợp cho event nghiệp vụ cần được giữ trong durable queue qua restart. Chỉ chọn `NON_PERSISTENT` khi dữ liệu có thể được tái tạo hoặc mất đi mà không gây sai lệch nghiệp vụ, chẳng hạn một số loại telemetry ngắn hạn.

Không nhầm delivery mode với:

- `durableSubscription`: durability của consumer group queue.
- `exchangeDurable`: durability của exchange.
- Publisher confirms: xác nhận broker đã xử lý publish.
- Consumer acknowledgement: xác nhận ứng dụng đã xử lý message.

Mỗi cơ chế bảo vệ một giai đoạn khác nhau.

## 6. Điều kiện để message persistent được khôi phục

Với classic queue, bảng sau tóm tắt các trường hợp phổ biến:

| Queue | Message | Kết quả sau broker restart |
|---|---|---|
| Durable | Persistent | Được khôi phục theo cơ chế lưu trữ của RabbitMQ |
| Durable | Transient | Message có thể bị loại khi restart |
| Non-durable | Persistent | Queue bị xóa; message không còn nơi lưu |
| Non-durable | Transient | Queue và message đều không tồn tại sau restart |

Điều kiện còn bao gồm việc message đã được route vào queue. Nếu exchange không có binding phù hợp, message không được lưu vào queue nào. Nếu queue có TTL hoặc length limit, message vẫn có thể hết hạn hoặc bị loại theo policy trước khi consumer xử lý.

Đối với quorum queue, queue luôn durable và dữ liệu được replicate theo giao thức Raft. Quorum queue được thiết kế cho độ bền và tính sẵn sàng cao hơn queue classic đơn lẻ. RabbitMQ lưu message trong quorum queue trên disk bất kể delivery mode của message; tuy nhiên, delivery mode gốc được giữ khi message bị dead-letter sang queue khác. Nếu DLQ đích là classic queue và cần giữ message qua restart, hãy bảo đảm message ở DLQ là persistent và DLQ là durable. Producer vẫn cần publisher confirms để biết message đã được quorum chấp nhận; message chưa được confirm vẫn có thể đang trên đường truyền hoặc chưa được leader chấp nhận.

## 7. Publisher confirms: biết broker đã chấp nhận message

Publish qua AMQP là thao tác bất đồng bộ. Việc client ghi frame vào socket không chứng minh broker đã nhận và lưu message. Mạng có thể đứt sau khi broker nhận message nhưng trước khi confirm về client; hoặc message có thể chưa tới broker.

Publisher confirms cho phép producer nhận xác nhận từ broker:

- `ack`: broker đã xử lý publish theo semantics của queue được định tuyến.
- `nack`: broker không thể chấp nhận publish.
- Nếu message không được route và publish là mandatory, broker có thể trả message về client bằng `basic.return`; return được gửi trước publisher confirm.

Với persistent message được route đến durable classic queue, RabbitMQ gửi publisher confirm sau khi message được lưu xuống disk theo cơ chế message store. Việc ghi được gom theo batch để giảm chi phí I/O, nên confirm có thể có độ trễ. Với quorum queue, confirm được gửi sau khi quorum replica chấp nhận message.

Publisher confirm không có nghĩa consumer đã xử lý message. Nó chỉ xác nhận giai đoạn publish đến broker. Consumer acknowledgement là tín hiệu độc lập ở giai đoạn nhận và xử lý.

## 8. Bật publisher confirms trong Spring Cloud Stream

Spring Boot có thể cấu hình connection factory dùng correlated publisher confirms và publisher returns:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orders-out-0:
            producer:
              use-confirm-header: true
~~~

Với `use-confirm-header`, ứng dụng gắn correlation data vào outbound message và chờ kết quả confirm tương ứng. `publisher-confirm-type: correlated` là điều kiện để connection factory phát publisher confirms. `publisher-returns: true` cho phép nhận lại message không route khi publishing được cấu hình mandatory trong đường gửi.

Ví dụ dùng `StreamBridge`:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.support.AmqpHeaders;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public void publishAndCheck(
        StreamBridge streamBridge,
        OrderCreated event) throws Exception {

    CorrelationData correlation =
        new CorrelationData(event.eventId());

    Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(AmqpHeaders.PUBLISH_CONFIRM_CORRELATION, correlation)
        .build();

    boolean sent = streamBridge.send("orders-out-0", message);
    if (!sent) {
        throw new IllegalStateException("Output binding did not accept the message");
    }

    var confirm = correlation.getFuture().get(10, TimeUnit.SECONDS);
    if (!confirm.isAck()) {
        throw new IllegalStateException("RabbitMQ did not confirm the publish");
    }
    if (correlation.getReturnedMessage() != null) {
        throw new IllegalStateException("Message was not routed to a queue");
    }
}
~~~

Ví dụ minh họa cách chờ kết quả correlated confirm và kiểm tra returned message. Trong ứng dụng production, cần xử lý timeout, interruption, nack và retry; không chặn thread nghiệp vụ quá lâu nếu có thể xử lý confirm bất đồng bộ. Correlation ID phải duy nhất cho từng lần publish đang chờ xác nhận.

Nếu không bật returns và cờ mandatory trên đường gửi, publisher có thể nhận confirm nhưng không biết message không được route đến queue nào. Confirm và return giải quyết hai câu hỏi khác nhau: broker đã xử lý publish chưa, và message có được route đến queue hay không. Hãy kiểm tra cấu hình của binder/template thực tế để bảo đảm cờ mandatory được bật khi ứng dụng cần phát hiện message không có queue nhận.

## 9. Retry publish và khả năng trùng lặp

Giả sử broker đã nhận message nhưng kết nối bị đứt trước khi publisher nhận confirm. Producer không biết chắc message đã được lưu hay chưa. Nếu gửi lại, có thể xuất hiện hai bản message; nếu không gửi lại, có thể mất message khi broker chưa nhận.

Vì vậy, publisher confirms thường được kết hợp với retry và consumer idempotency:

- Gắn `eventId` ổn định cho message.
- Nếu confirm bị timeout hoặc connection đóng, retry cùng event ID.
- Consumer lưu event ID đã xử lý hoặc dùng unique constraint để loại duplicate.
- Không tạo event ID mới cho cùng một nghiệp vụ mỗi lần retry.

Publisher confirm giảm nguy cơ mất message nhưng không tạo exactly-once end-to-end. Khi confirm bị mất trên đường về client, gửi lại có thể tạo duplicate. Consumer cần chấp nhận redelivery và xử lý lặp an toàn.

## 10. Consumer acknowledgement bảo vệ giai đoạn xử lý

Sau khi message được giao cho consumer, broker cần biết khi nào có thể xóa message khỏi queue. Rabbit binder mặc định dùng `acknowledgeMode: AUTO`: listener container xác nhận message sau khi handler kết thúc thành công theo cơ chế của container. Nếu xử lý thất bại, binder/broker áp dụng retry, reject hoặc requeue theo cấu hình.

Phân biệt:

| Tín hiệu | Ai gửi? | Bảo vệ giai đoạn nào? |
|---|---|---|
| Publisher confirm | RabbitMQ gửi producer | Broker đã chấp nhận publish |
| Consumer ack | Consumer/container gửi RabbitMQ | Ứng dụng đã xử lý delivery và broker có thể loại message |
| Consumer nack/reject | Consumer/container gửi RabbitMQ | Xử lý thất bại; broker có thể requeue hoặc dead-letter |

Nếu consumer ack trước khi hoàn tất tác dụng phụ nghiệp vụ, process chết sau đó có thể làm mất công việc. Nếu consumer hoàn tất database nhưng chết trước ack, broker có thể giao lại và tạo duplicate. Hãy dùng idempotency/inbox cho tác dụng phụ và để acknowledgement gắn với thời điểm xử lý đã hoàn tất.

## 11. Chọn classic queue hay quorum queue

Classic queue durable phù hợp với nhiều workload đơn giản cần tồn tại qua restart của node sở hữu queue. Tuy nhiên, classic queue không tự replicate dữ liệu giữa các node theo mô hình quorum.

Quorum queue là queue replicated, durable, dùng Raft để duy trì bản sao và bầu leader. Trong Rabbit binder, có thể yêu cầu queue group dùng quorum queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-processing
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              quorum:
                enabled: true
                initial-group-size: 3
~~~

Quorum queue cần số thành viên phù hợp với cluster và có thể tiếp tục phục vụ khi còn majority replica. Publisher confirms là cách producer biết quorum đã chấp nhận message. Quorum queue có độ trễ ghi cao hơn một queue classic đơn lẻ do phải replicate và thống nhất trạng thái.

Chọn quorum queue khi yêu cầu có tính sẵn sàng cao và dữ liệu quan trọng cần được replicate. Với queue tạm thời, exclusive queue hoặc workload không cần replication, classic queue có thể phù hợp hơn. Không tạo quorum queue trên một cluster không đủ node hoặc không có kế hoạch đặt replica hợp lý.

## 12. Queue, exchange và binding cần cùng một vòng đời

Một durable queue không giúp ích nếu topology không thể định tuyến message đến nó. Với Rabbit binder, mỗi destination thường được ánh xạ thành topic exchange; queue của từng group được bind vào exchange. Các điều kiện cần xác minh:

- Exchange có đúng tên và durable.
- Queue group tồn tại, durable và không phải anonymous auto-delete.
- Binding dùng đúng routing key hoặc pattern.
- Producer có quyền publish vào exchange.
- Consumer có quyền đọc queue.
- Queue không bị TTL, auto-delete hoặc policy xóa ngoài dự kiến.
- Nếu producer cần phát trước khi consumer chạy, `required-groups` đã provision queue.

Nếu dùng hạ tầng có sẵn, binder có thể tắt `declareExchange` hoặc `bindQueue`; lúc đó đội vận hành phải đảm bảo topology đã được tạo và bind đúng. Đừng giả định cấu hình durable của binder có thể sửa một queue đã tồn tại với arguments khác mà không có migration.

## 13. Những giới hạn của persistent message

Persistent không có nghĩa message được lưu trữ vĩnh viễn. Message vẫn có thể bị loại bởi:

- Consumer ack sau khi xử lý.
- Message TTL hết hạn.
- Queue length limit hoặc overflow policy.
- Queue bị xóa hoặc hết hạn.
- DLQ có TTL/overflow riêng.
- Quản trị viên purge/delete queue.
- Disk alarm, lỗi storage hoặc sự cố vượt phạm vi chịu lỗi của queue type.

Persistent cũng không tự tạo bản sao dự phòng. Với classic queue, dữ liệu nằm trên node sở hữu queue. Muốn chịu được node failure cần queue replicated, chẳng hạn quorum queue, cùng cluster có số replica và vị trí đặt phù hợp.

Không dùng RabbitMQ queue như kho lưu trữ dài hạn hoặc hệ thống archive. Nếu cần lưu lịch sử sự kiện, hãy ghi vào database, object storage hoặc event log phù hợp với thời gian retention.

## 14. Kiểm thử độ bền vững

Kiểm thử cần xác minh hành vi sau restart và khi publish thất bại, không chỉ xác nhận ứng dụng khởi động:

1. Tạo durable exchange và durable consumer group queue.
2. Publish message persistent và chờ publisher confirm.
3. Tạm dừng consumer, xác nhận message vẫn nằm ở queue.
4. Khởi động lại RabbitMQ node theo kịch bản test; xác nhận durable queue và persistent message được khôi phục.
5. Lặp lại với transient message để xác nhận nó không được kỳ vọng tồn tại sau restart.
6. Lặp lại với non-durable/anonymous queue và xác nhận queue tạm thời không được khôi phục.
7. Publish vào exchange không có queue binding; bật publisher returns/mandatory và xác nhận producer nhận returned message.
8. Dừng consumer sau khi nhận nhưng trước khi ack; xác nhận message được redeliver.
9. Với quorum queue, dừng một node và xác nhận queue vẫn hoạt động khi còn majority.
10. Mô phỏng mất kết nối trước khi confirm đến publisher; retry cùng event ID và xác nhận consumer deduplicate.

Test Binder hữu ích để kiểm tra cấu hình binding và logic ứng dụng, nhưng không chứng minh durability sau broker restart, disk persistence, quorum replication hay publisher confirms. Dùng RabbitMQ broker thật hoặc Testcontainers cho các kiểm thử này; với quorum queue cần môi trường cluster nhiều node.

## 15. Checklist triển khai

- [ ] Producer gửi message với delivery mode `PERSISTENT` cho dữ liệu quan trọng.
- [ ] Consumer group có tên ổn định; queue không phải anonymous auto-delete.
- [ ] `durable-subscription` được bật cho group queue.
- [ ] Exchange durable và có vòng đời phù hợp; kiểm tra `exchange-auto-delete`.
- [ ] Binding và routing key trỏ message vào đúng queue.
- [ ] Dùng `required-groups` nếu queue cần được provision trước khi consumer chạy.
- [ ] Publisher confirms được bật và kết quả ack/nack được xử lý.
- [ ] Publisher returns/mandatory được bật khi cần phát hiện message không route.
- [ ] Consumer acknowledgement chỉ xảy ra sau khi xử lý nghiệp vụ hoàn tất.
- [ ] Consumer có idempotency để xử lý redelivery hoặc publisher retry.
- [ ] Đã chọn classic durable hay quorum queue theo mức chịu lỗi cần thiết.
- [ ] Đã kiểm thử restart, node failure, unroutable publish và redelivery.

Để message còn tồn tại qua restart, cần đồng thời có message persistent và queue durable; exchange và binding phải được khôi phục để message đi đúng nơi. RabbitMQ Binder mặc định gửi persistent message và tạo durable subscription khi có consumer group, nhưng ứng dụng vẫn cần xác nhận queue/topology thực tế. Publisher confirms giúp biết broker đã chấp nhận message, còn consumer acknowledgements xác nhận xử lý đã hoàn tất. Khi kết hợp hai tín hiệu, queue phù hợp và idempotent processing, ứng dụng có thể xây dựng luồng giao nhận bền vững hơn mà không nhầm một thuộc tính đơn lẻ với bảo đảm toàn hệ thống.

## Tài liệu tham khảo

- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [RabbitMQ — Queues and Durability](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
