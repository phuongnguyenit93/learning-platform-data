# Publisher confirms, publisher returns và thông điệp không có đích nhận

Khi một ứng dụng gửi message tới RabbitMQ, việc gọi hàm gửi thành công chỉ cho biết ứng dụng đã chuyển yêu cầu gửi tới client/binder. Nó chưa chứng minh broker đã nhận message, đã định tuyến message tới queue hoặc consumer đã xử lý xong. Mạng có thể đứt sau khi client gửi frame, exchange có thể không có queue phù hợp, hoặc broker có thể không ghi được message vì lỗi nội bộ.

RabbitMQ cung cấp hai cơ chế bổ sung cho phía publisher:

- **Publisher confirms** cho biết broker đã chấp nhận trách nhiệm đối với message hoặc từ chối message bằng negative acknowledgement.
- **Publisher returns** đưa message trở lại publisher khi message không thể được định tuyến tới bất kỳ queue nào và publisher đã gửi message ở chế độ mandatory.

Spring Cloud Stream RabbitMQ binder tích hợp hai cơ chế này với Spring AMQP. Ứng dụng có thể nhận kết quả bất đồng bộ qua error channel, hoặc gắn correlation data vào message rồi chờ Future của publisher confirm. Bài học này giải thích ý nghĩa từng kết quả, cách cấu hình binder và cách xử lý trường hợp message không có đích nhận.

## 1. Vì sao publisher cần xác nhận?

RabbitMQ là một hệ thống phân tán. Sau khi client ghi dữ liệu vào socket, ứng dụng chưa thể kết luận broker đã nhận và xử lý message. Connection có thể bị ngắt trước khi frame đến broker; broker có thể nhận message nhưng phản hồi bị mất; exchange có thể không tìm được queue đích.

Nếu không theo dõi xác nhận, ứng dụng có thể:

- Báo thành công dù message chưa được broker chấp nhận.
- Mất message khi broker dừng trước khi ghi persistent message xuống đĩa.
- Không phát hiện message bị bỏ vì không có queue nào nhận.
- Gửi lại message khi kết quả lần gửi trước chưa rõ, tạo bản ghi trùng.

Luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A[Ứng dụng publish] --> B[RabbitMQ exchange]
    B --> C{Có queue phù hợp?}
    C -->|Có| D[Queue nhận message]
    C -->|Không| E{mandatory?}
    E -->|false| F[Discard hoặc Alternate Exchange]
    E -->|true| G[Basic.Return về publisher]
    D --> H[Publisher Confirm ACK]
    F --> I[Publisher Confirm ACK sau khi broker xử lý route]
    G --> J[Publisher Confirm ACK sau Basic.Return]
    D --> K[Consumer nhận và xử lý sau đó]
~~~

Publisher confirm và consumer acknowledgement nằm ở hai đầu khác nhau. Confirm phản ánh việc broker nhận trách nhiệm với message; consumer ACK phản ánh việc consumer xác nhận một delivery. Một publisher confirm không có nghĩa consumer đã đọc hoặc xử lý nghiệp vụ thành công.

## 2. Publisher confirms là gì?

Publisher confirms là cơ chế broker gửi xác nhận lại cho publisher sau khi xử lý một lần publish. Khi channel ở confirm mode, RabbitMQ theo dõi các message được publish trên channel và gửi một trong hai kết quả:

- **ACK:** broker đã chấp nhận trách nhiệm đối với message.
- **NACK:** broker không thể xử lý thành công message và từ chối trách nhiệm đối với message đó.

ACK được phát khi message đã được chấp nhận bởi tất cả queue mà exchange định tuyến tới. Với persistent message được route vào durable queue, xác nhận được gửi sau khi message được lưu bền vững. Với quorum queue, broker xác nhận khi quorum replica đã chấp nhận message theo cơ chế của queue.

NACK là trường hợp hiếm, thường liên quan lỗi nội bộ khi broker xử lý queue. Một số cấu hình queue giới hạn độ dài với overflow policy **reject-publish** cũng có thể làm publisher nhận NACK.

### Confirm không phải consumer ACK

| Cơ chế | Bên gửi | Bên xác nhận | Ý nghĩa |
|---|---|---|---|
| Publisher confirm | Producer | RabbitMQ broker | Broker đã chấp nhận trách nhiệm hoặc từ chối message. |
| Consumer acknowledgement | Consumer | RabbitMQ broker | Consumer xác nhận delivery đã được xử lý hoặc yêu cầu reject/requeue. |

Ví dụ, broker có thể ACK cho message ngay sau khi lưu message vào durable queue. Consumer có thể chưa được khởi động hoặc đang offline. Ngược lại, consumer có thể xử lý xong một message nhưng producer chưa nhận được confirm do connection bị đứt. Hai kết quả này không thay thế nhau.

### Confirm không bảo đảm xử lý nghiệp vụ đúng một lần

Publisher confirm bảo vệ đoạn gửi từ publisher tới broker. Nó không bao phủ transaction trong database của consumer, side effect HTTP, hoặc việc consumer commit ACK. Nếu publisher không nhận được confirm trước timeout, kết quả có thể chưa rõ: broker có thể đã nhận message nhưng confirm bị mất trên đường về.

Nếu gửi lại trong trường hợp không rõ kết quả, broker có thể nhận hai bản sao. Hãy gắn event ID ổn định và thiết kế consumer idempotent để xử lý trường hợp publish lại.

## 3. Publisher returns và thông điệp không có đích nhận

RabbitMQ exchange định tuyến message dựa trên exchange type, routing key và các binding. Một message là **unroutable** khi exchange không tìm được queue phù hợp.

Ví dụ:

- Exchange tồn tại nhưng chưa có queue nào được bind.
- Routing key không khớp binding của topic/direct exchange.
- Queue đã bị xóa hoặc binding đã bị gỡ.
- Producer gửi tới exchange đúng tên nhưng dùng routing key sai.

Với AMQP 0-9-1, thuộc tính **mandatory** quyết định cách broker xử lý message không định tuyến được:

- **mandatory=false:** đây là mặc định của giao thức. Broker loại message hoặc chuyển nó tới Alternate Exchange nếu exchange có cấu hình alternate exchange.
- **mandatory=true:** nếu không queue nào nhận được message và không có alternate route xử lý message, broker gửi **Basic.Return** về publisher. Publisher phải có return handler để nhận và xử lý message.

Publisher returns vì vậy là cơ chế phát hiện message không có đích nhận. Nó không giống publisher NACK: return nói rằng message không được route tới queue nào, còn NACK nói broker không thể xử lý thành công message.

### Thông tin trong một returned message

Khi binder chuyển một returned message thành error, payload **ReturnedAmqpMessageException** cung cấp:

| Thuộc tính | Ý nghĩa |
|---|---|
| **failedMessage** | Spring Messaging Message ban đầu được gửi nhưng bị trả lại. |
| **amqpMessage** | Message AMQP thô do Spring AMQP nhận về. |
| **replyCode** | Mã phản hồi của broker, ví dụ 312. |
| **replyText** | Mô tả ngắn, thường là NO_ROUTE. |
| **exchange** | Exchange mà publisher đã gửi message tới. |
| **routingKey** | Routing key được sử dụng khi publish. |

Mã **312 - NO_ROUTE** thường chỉ ra không có queue nào nhận message theo cấu hình routing hiện tại.

### Return không nhất thiết đồng nghĩa exchange không tồn tại

Nếu exchange không tồn tại, RabbitMQ phát channel-level exception và đóng channel; đây không phải tình huống Basic.Return thông thường. Return chủ yếu phản ánh exchange tồn tại nhưng không có queue nào được định tuyến nhận message.

Nếu exchange có Alternate Exchange và alternate exchange định tuyến được message, message được chuyển sang alternate exchange. Trong trường hợp đó, message đã có route và publisher thường không nhận returned message cho lần publish đó. Vì vậy, cần kiểm tra cả cấu hình alternate exchange khi điều tra message không xuất hiện ở queue chính.

## 4. Vì sao chỉ kiểm tra confirm ACK là chưa đủ?

Khi message không định tuyến được nhưng publisher gửi ở chế độ **mandatory=true**, RabbitMQ gửi Basic.Return trước, sau đó gửi publisher confirm ACK cho lần publish. ACK ở đây cho biết broker đã xử lý lần publish; nó không khẳng định message đã tới queue nghiệp vụ.

Nếu ứng dụng chỉ kiểm tra ACK, nó có thể đánh dấu message là đã gửi thành công dù message vừa bị trả về.

| Kết quả | Confirm | Return | Cách diễn giải |
|---|---|---|---|
| Message được route | ACK | Không có | Broker đã chấp nhận message và route tới ít nhất một queue. |
| Không có queue phù hợp, mandatory=true | ACK có thể vẫn được gửi sau return | Có | Broker xử lý publish nhưng message không tới queue nào. |
| Broker không thể xử lý message | NACK | Thường không có return | Broker từ chối trách nhiệm; cần điều tra lỗi broker/queue. |
| Không nhận confirm trước timeout | Chưa rõ | Có thể chưa rõ | Kết quả chưa xác định; không kết luận message chắc chắn mất hoặc chắc chắn đã nhận. |

Để kết luận message đã được route, hãy kết hợp publisher confirm với publisher return. Khi dùng correlation data của Spring AMQP, returned message được gắn vào correlation object trước khi Future confirm hoàn tất.

## 5. Bật confirms và returns cho Spring Cloud Stream Rabbit binder

RabbitMQ binder mặc định dùng Spring Boot ConnectionFactory. Có thể cấu hình publisher confirms và publisher returns bằng các thuộc tính Spring Boot.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              use-confirm-header: true
~~~

Ý nghĩa từng thuộc tính:

- **spring.rabbitmq.publisher-confirm-type: correlated** bật publisher confirms theo kiểu tương quan. Đây là cấu hình cần thiết để Spring AMQP gắn kết quả confirm với CorrelationData.
- **spring.rabbitmq.publisher-returns: true** bật khả năng nhận returned messages của ConnectionFactory.
- **producer.error-channel-enabled: true** yêu cầu Spring Cloud Stream chuyển các lỗi gửi bất đồng bộ mà binder hỗ trợ vào error channel.
- **use-confirm-header: true** chọn cơ chế correlation data header để lấy kết quả confirm theo từng message.

Trong các phiên bản Spring Boot cũ hơn, tên thuộc tính bật confirms có thể là **spring.rabbitmq.publisher-confirms**. Hãy dùng tên property phù hợp với phiên bản Spring Boot/Spring AMQP mà BOM của dự án quản lý; với cấu hình hiện hành, ưu tiên publisher-confirm-type.

Không chỉ bật publisher returns rồi cho rằng mọi message đều được trả về khi không có route. AMQP yêu cầu message được publish với **mandatory=true** để broker gửi Basic.Return. Khi dùng RabbitTemplate trực tiếp, cần đặt mandatory hoặc mandatory-expression phù hợp. Với producer của Rabbit binder, hãy dùng đường tích hợp return handling của binder và kiểm thử bằng một routing key không khớp để xác nhận hành vi trên phiên bản đang triển khai.

## 6. Cách nhận lỗi qua producer error channel

Spring Cloud Stream có thể tạo error channel cho các kết quả gửi bất đồng bộ. Với RabbitMQ binder, hai loại lỗi publish chính là:

1. Returned message do message không được định tuyến.
2. Negative publisher confirm do broker từ chối xử lý message.

Để nhận các lỗi này qua error channel, cần đồng thời:

- Bật **producer.error-channel-enabled** cho output binding.
- Bật publisher confirms trên ConnectionFactory.
- Bật publisher returns trên ConnectionFactory nếu muốn nhận returned messages.

Ví dụ cấu hình đã trình bày ở phần trước. Sau đó, ứng dụng có thể đăng ký một handler ở global Spring Integration error channel:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.amqp.support.NackedAmqpMessageException;
import org.springframework.integration.amqp.support.ReturnedAmqpMessageException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class RabbitPublishErrorHandler {

    private static final Logger log =
            LoggerFactory.getLogger(RabbitPublishErrorHandler.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();

        if (cause instanceof ReturnedAmqpMessageException returned) {
            log.error(
                    "Message không có queue nhận: exchange={}, routingKey={}, code={}, reason={}",
                    returned.getExchange(),
                    returned.getRoutingKey(),
                    returned.getReplyCode(),
                    returned.getReplyText()
            );
            return;
        }

        if (cause instanceof NackedAmqpMessageException nacked) {
            log.error(
                    "RabbitMQ NACK khi publish: {}",
                    nacked.getNackReason(),
                    nacked
            );
            return;
        }

        log.error("Lỗi gửi message bất đồng bộ", cause);
    }
}
~~~

Ví dụ trên dùng global error channel để minh họa. ErrorMessage của returned message có payload **ReturnedAmqpMessageException**; với negative confirm, payload là **NackedAmqpMessageException**. Cả hai chứa **failedMessage** để ứng dụng biết message gốc đã gặp lỗi.

Error channel không tự động lưu message vào DLQ. Ứng dụng phải quyết định cách xử lý: ghi audit, lưu outbox/retry store, cảnh báo vận hành, sửa routing rồi gửi lại hoặc chuyển sang parking-lot destination.

## 7. Xử lý theo từng binding và phân biệt error channel

Nếu nhiều output binding cùng bật producer error channel, global **errorChannel** có thể nhận lỗi từ nhiều nơi. Khi xử lý, hãy lấy failedMessage và metadata để xác định binding, exchange, routing key, correlation ID và event ID.

Spring Cloud Stream cũng có error channel gắn với destination/group cho các luồng inbound. Quy tắc đặt tên thường là **<destination>.<group>.errors**. Producer send failures là lỗi bất đồng bộ của output binding; không nên nhầm với lỗi do consumer function ném exception khi xử lý message đầu vào.

Một cách triển khai thực tế:

- Dùng correlation header khi cần kết quả chính xác cho từng message.
- Dùng producer error channel để tập trung quan sát lỗi bất đồng bộ.
- Gắn binding name, event ID và correlation ID vào log/metric.
- Không đăng ký nhiều handler cùng tiêu thụ một error channel nếu chưa chủ động thiết kế fan-out.

## 8. Publisher confirms qua confirmAckChannel

Rabbit binder hỗ trợ cơ chế cũ hơn để nhận positive publisher confirms qua **confirmAckChannel**. Giá trị thuộc tính là tên Spring MessageChannel nhận xác nhận. Nếu channel chưa tồn tại, binder có thể đăng ký một DirectChannel theo tên đó.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              confirm-ack-channel: orderPublisherConfirms
~~~

Ứng dụng đăng ký handler cho channel **orderPublisherConfirms** để nhận các positive confirm:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class RabbitConfirmChannelHandler {

    private static final Logger log =
            LoggerFactory.getLogger(RabbitConfirmChannelHandler.class);

    @ServiceActivator(inputChannel = "orderPublisherConfirms")
    public void onConfirm(Message<?> message) {
        log.info("RabbitMQ publisher confirm: {}", message);
    }
}
~~~

Đây là cơ chế legacy. Positive confirms được chuyển tới confirmAckChannel; negative confirms được chuyển tới error channel nếu đã bật. Mặc định confirmAckChannel là **nullChannel**, vì vậy positive confirms bị loại bỏ nếu không chỉ định channel.

Không cấu hình đồng thời **confirm-ack-channel** và **use-confirm-header** trên cùng producer binding. Hai cơ chế này loại trừ lẫn nhau. Với code mới, correlation data header và Future thường thuận tiện hơn vì có thể gắn kết quả với đúng message.

## 9. Cơ chế được ưu tiên: useConfirmHeader và CorrelationData

Từ Rabbit binder 3.1, có thể đặt một đối tượng **CorrelationData** vào header **AmqpHeaders.PUBLISH_CONFIRM_CORRELATION**. Sau khi publish, ứng dụng đọc kết quả từ **CorrelationData.getFuture()**. Đây là cơ chế được tài liệu Rabbit binder ưu tiên.

CorrelationData có:

- ID dùng để liên kết kết quả với message. Khi publisher returns được bật, ID phải duy nhất để framework tương quan returned message.
- Future hoàn tất khi broker gửi confirm.
- Returned message nếu broker không route được message.

Ví dụ gửi một message qua StreamBridge:

~~~java
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.core.AmqpHeaders;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.connection.CorrelationData.Confirm;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(OrderCreated event) {
        CorrelationData correlation =
                new CorrelationData(UUID.randomUUID().toString());

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(
                        AmqpHeaders.PUBLISH_CONFIRM_CORRELATION,
                        correlation
                )
                .build();

        boolean sent = streamBridge.send("orderPublisher-out-0", message);
        if (!sent) {
            throw new IllegalStateException(
                    "Không gửi được message tới output binding");
        }

        try {
            Confirm confirm = correlation.getFuture()
                    .get(10, TimeUnit.SECONDS);

            ReturnedMessage returned = correlation.getReturned();
            if (returned != null) {
                throw new IllegalStateException(
                        "Message không có queue nhận: exchange="
                                + returned.getExchange()
                                + ", routingKey="
                                + returned.getRoutingKey()
                                + ", reason="
                                + returned.getReplyText()
                );
            }

            if (!confirm.isAck()) {
                throw new IllegalStateException(
                        "RabbitMQ NACK: " + confirm.getReason());
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Bị ngắt khi chờ publisher confirm", ex);
        }
        catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException(
                    "Không nhận được publisher confirm đúng hạn", ex);
        }
    }
}
~~~

Thứ tự kiểm tra có chủ đích:

1. Chờ Future confirm hoàn tất.
2. Kiểm tra **correlation.getReturned()**. Nếu có returned message, message đã không được định tuyến tới queue nào.
3. Nếu không có return, kiểm tra **confirm.isAck()**. NACK nghĩa là broker từ chối trách nhiệm.
4. Chỉ coi publish đã được broker chấp nhận và route thành công khi có ACK và không có returned message.

Trong các phiên bản Spring AMQP mới, dùng **getReturned()** để nhận ReturnedMessage kèm reply code, reply text, exchange và routing key. Một số phiên bản cũ có **getReturnedMessage()**; phương thức này đã được thay bằng getReturned() trong các phiên bản mới hơn.

Ví dụ chờ tối đa 10 giây để minh họa. Trong hệ thống tải cao, không nên chặn một thread nghiệp vụ cho từng message nếu có thể gửi theo lô hoặc xử lý Future bất đồng bộ. Tài liệu binder minh họa việc gửi nhiều message trước rồi mới chờ các Future, phù hợp với batch listener.

## 10. Tại sao CorrelationData cần ID duy nhất?

Publisher confirms và returns được gửi bất đồng bộ. Một ứng dụng có thể publish hàng trăm message trước khi nhận kết quả. Nếu không có correlation ID, ứng dụng khó xác định ACK, NACK hoặc returned message thuộc message nào.

Khi returns được bật, Spring AMQP dùng ID của CorrelationData để liên kết Basic.Return với message đang chờ confirm. ID trùng nhau có thể khiến kết quả tương quan sai hoặc không thể gắn returned message đúng với lần publish.

Nên dùng:

- UUID hoặc event ID duy nhất cho từng lần publish.
- Event ID ổn định ở payload để chống trùng nghiệp vụ.
- Correlation ID duy nhất cho từng attempt publish để phân biệt các lần gửi lại.

Nếu gửi lại cùng một event, có thể giữ nguyên event ID nghiệp vụ nhưng tạo correlation ID mới cho attempt mới. Như vậy log có thể liên kết các lần thử của cùng event mà không làm nhầm lẫn kết quả confirm.

## 11. Xử lý message không có route bằng Alternate Exchange

RabbitMQ hỗ trợ **Alternate Exchange (AE)**. Khi exchange chính không thể định tuyến message tới queue, broker có thể thử định tuyến message qua alternate exchange đã gắn với exchange chính.

AE phù hợp khi muốn giữ message không khớp routing key trong một queue riêng để kiểm tra, thay vì trả message về publisher. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              alternate-exchange:
                name: unrouted-orders
                type: topic
                exists: false
                binding:
                  queue: unrouted-orders-audit
                  routing-key: "#"
~~~

Ví dụ minh họa binder khai báo alternate exchange và queue binding đơn giản. Nếu cần queue arguments, durability hoặc topology phức tạp, hãy tạo và bind tài nguyên bằng hạ tầng quản trị riêng rồi cấu hình binder dùng tài nguyên đã có.

Khi AE nhận được message, message đã được định tuyến vào một queue ở nhánh alternate. Vì vậy, publisher return không xuất hiện như trường hợp không có bất kỳ route nào. Hãy phân biệt hai mục tiêu:

- **Publisher return:** báo publisher biết message không được route tới queue.
- **Alternate Exchange:** giữ/định tuyến message không khớp vào một nhánh khác.

AE không tự sửa routing key và cũng không bảo đảm queue đích nghiệp vụ đã xử lý message. Queue alternate nên được theo dõi và có quy trình xử lý riêng.

## 12. Returned message không phải Dead Letter Queue

Publisher return xảy ra ở phía publish, khi message không được route tới queue. Dead Letter Queue (DLQ) là queue nhận message bị dead-letter từ một queue nguồn, thường do consumer reject, message hết TTL hoặc queue vượt giới hạn theo policy.

| Tiêu chí | Publisher return | Dead Letter Queue |
|---|---|---|
| Thời điểm | Ngay khi exchange không tìm được route phù hợp. | Sau khi message đã vào queue và bị dead-letter. |
| Nơi phát hiện | Publisher. | Broker/queue topology hoặc consumer. |
| Nguyên nhân ví dụ | Không có binding hoặc routing key không khớp. | Consumer reject, TTL hết hạn, queue length/overflow policy. |
| Nơi nhận | Return callback hoặc error/correlation channel của publisher. | DLQ đã được bind vào DLX. |
| Có tự động vào DLQ không? | Không. | Có nếu queue/DLX được cấu hình phù hợp. |

Rabbit binder không tự động đưa ReturnedAmqpMessageException hoặc NackedAmqpMessageException vào DLQ. Error channel chỉ là nơi ứng dụng nhận lỗi trong tiến trình. Nếu muốn lưu message lỗi, cần tự publish message gốc sang một queue lỗi/parking-lot hoặc lưu vào database/outbox với cơ chế retry phù hợp.

## 13. Negative confirm và returned message cần xử lý khác nhau

Hai loại lỗi có nguyên nhân và hướng khắc phục khác nhau:

| Lỗi | Nguyên nhân có thể | Hành động phù hợp |
|---|---|---|
| Returned message, NO_ROUTE | Sai routing key, thiếu binding, queue chưa được provision. | Kiểm tra exchange, queue, binding và routing key; sau khi sửa route, gửi lại message theo chính sách. |
| NACK | Lỗi nội bộ khi xử lý queue hoặc queue overflow reject-publish. | Kiểm tra broker log, queue policy, dung lượng và tình trạng node; retry có giới hạn nếu phù hợp. |
| Channel exception, exchange không tồn tại | Publish tới exchange chưa được khai báo hoặc sai tên. | Sửa topology/tên exchange; kiểm tra channel và connection đã được phục hồi. |
| Confirm timeout | Broker/connection chậm hoặc confirm bị mất trên đường về. | Đánh dấu kết quả chưa xác định; đối soát hoặc retry với idempotency. |
| StreamBridge.send trả false | Không gửi được vào binding theo kết quả API tại thời điểm gọi. | Kiểm tra binding, destination và lỗi cục bộ; chưa có broker confirm để kết luận. |

Không retry vô hạn một returned message nếu routing chưa được sửa. Mỗi lần retry sẽ tiếp tục không có route, tạo tải và log lặp. NACK cũng không nên được retry không giới hạn khi broker đang quá tải hoặc queue đang áp dụng reject-publish.

## 14. Xử lý kết quả không rõ sau timeout hoặc mất kết nối

Một tình huống khó là publisher gửi message, broker nhận và lưu message, nhưng connection bị đứt trước khi ACK đến client. Publisher không biết message đã được nhận hay chưa.

Nếu publisher gửi lại, broker có thể nhận một bản sao thứ hai. Nếu publisher không gửi lại, message có thể đã được broker nhận, nhưng ứng dụng chưa ghi nhận xác nhận.

Đây là lý do publisher confirms không tạo exactly-once delivery. Một chiến lược thường dùng:

1. Gắn event ID duy nhất vào payload hoặc header nghiệp vụ.
2. Lưu trạng thái publish vào outbox trước khi gửi.
3. Chờ confirm/return và cập nhật trạng thái outbox.
4. Nếu timeout, đánh dấu trạng thái chưa xác định và retry có kiểm soát.
5. Consumer dùng event ID làm khóa idempotency để bỏ qua bản sao đã xử lý.
6. Có quy trình đối soát cho các event bị timeout kéo dài.

Với dữ liệu tài chính hoặc nghiệp vụ quan trọng, cần lưu cả event ID, correlation ID, exchange, routing key, thời điểm gửi, trạng thái confirm, returned metadata và số lần retry. Nhờ đó, đội vận hành có thể điều tra một lần publish mà không dựa vào log rời rạc.

## 15. Kiểm thử publisher confirms và returns

Unit test một hàm gọi StreamBridge không thể chứng minh RabbitMQ đã nhận hoặc định tuyến message. Cần integration test với RabbitMQ broker thử nghiệm, ví dụ Testcontainers, để kiểm tra confirm và return thực tế.

### Kịch bản message được route thành công

1. Tạo exchange và queue.
2. Bind queue vào exchange bằng routing key phù hợp.
3. Bật correlated publisher confirms và publisher returns.
4. Publish message mandatory.
5. Chờ Future confirm.
6. Xác nhận ACK và không có returned message.
7. Đọc queue để xác nhận message thực sự có mặt.

### Kịch bản không có queue phù hợp

1. Tạo exchange nhưng không bind queue, hoặc dùng routing key không khớp.
2. Bật publisher returns và publish mandatory.
3. Nhận returned message.
4. Xác nhận reply code, reply text, exchange và routing key.
5. Chờ confirm và xác nhận returned message đã được gắn vào CorrelationData trước khi Future hoàn tất.
6. Kiểm tra ứng dụng không đánh dấu message là đã route chỉ vì confirm ACK.

### Ma trận kiểm thử

| Tình huống | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| Route thành công | Exchange, queue và binding hợp lệ. | Confirm ACK, không có return. |
| Không có binding | Exchange tồn tại nhưng không có queue phù hợp; mandatory=true. | Returned message, thường có reply code 312 và NO_ROUTE. |
| Routing key sai | Queue có binding nhưng key không khớp; mandatory=true. | Returned message chứa exchange và routing key đã dùng. |
| Không mandatory | Message không route và mandatory=false. | Message có thể bị discard hoặc chuyển AE; không có return. |
| Alternate Exchange | Exchange chính không route nhưng AE có queue phù hợp. | Message được AE nhận; không xử lý như một return không có route. |
| Negative confirm | Cấu hình queue overflow reject-publish hoặc mô phỏng lỗi broker phù hợp. | NACK hoặc lỗi publish được nhận và ghi nhận. |
| Exchange không tồn tại | Publish tới tên exchange không được khai báo. | Channel-level exception, không nhầm với NO_ROUTE return. |
| Confirm timeout | Giảm timeout hoặc ngắt kết nối trong test. | Ứng dụng đánh dấu kết quả chưa xác định, không kết luận message chắc chắn mất. |
| Nhiều message | Gửi nhiều message với correlation ID riêng. | Mỗi confirm/return được ghép đúng message. |
| Producer error channel | Bật error-channel-enabled và cấu hình confirms/returns. | ErrorMessage chứa đúng exception và failedMessage. |
| Consumer chưa hoạt động | Queue durable đã tồn tại nhưng chưa có consumer. | Publisher vẫn có thể nhận ACK vì broker đã nhận message vào queue. |
| Consumer xử lý lỗi | Consumer nhận message rồi reject hoặc gửi DLQ. | Không nhầm consumer failure với publisher return. |

### Các metric nên theo dõi

- Số publisher ACK và NACK.
- Số returned messages theo exchange và routing key.
- Tỷ lệ NO_ROUTE trên tổng số publish.
- Số lần timeout chờ confirm.
- Số confirm đang chờ và độ trễ confirm.
- Số message được chuyển sang Alternate Exchange.
- Số lần retry sau lỗi publish.
- Số event đang ở trạng thái outbox chưa xác nhận.

Không ghi toàn bộ payload vào log nếu có dữ liệu cá nhân hoặc bí mật. Ghi event ID, correlation ID và metadata routing thường đủ để truy vết.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không nhận confirm | ConnectionFactory chưa bật correlated confirms hoặc đang dùng sai cấu hình phiên bản. | Kiểm tra publisher-confirm-type và ConnectionFactory thực tế. |
| Không nhận returned message | Publisher returns chưa bật hoặc message không được gửi mandatory. | Bật publisher-returns và xác nhận return handling/mandatory trên producer. |
| Confirm ACK nhưng message không thấy ở queue chính | Message có thể không route và mandatory=false, hoặc đã đi qua Alternate Exchange. | Kết hợp return với confirm; kiểm tra AE và routing. |
| NACK bị nhầm với NO_ROUTE | Hai loại phản hồi có ý nghĩa khác nhau. | Đọc NackedAmqpMessageException và ReturnedAmqpMessageException riêng. |
| Error channel không nhận lỗi | Producer chưa bật error-channel-enabled hoặc ConnectionFactory thiếu confirms/returns. | Kiểm tra cả ba cấu hình. |
| Positive confirm không tới channel | confirmAckChannel vẫn là nullChannel hoặc chưa khai báo channel. | Đặt confirm-ack-channel; hoặc dùng use-confirm-header. |
| Cấu hình cả hai cơ chế confirm | useConfirmHeader và confirmAckChannel loại trừ lẫn nhau. | Chọn một cơ chế cho từng binding. |
| Returned message không gắn được correlation | CorrelationData ID không duy nhất hoặc không có ID khi returns bật. | Tạo correlation ID duy nhất cho mỗi lần publish. |
| Retry làm message bị trùng | Timeout khiến kết quả publish không rõ nhưng ứng dụng gửi lại. | Dùng outbox, event ID và idempotent consumer. |
| Đẩy return vào DLQ nhưng không thấy message | Rabbit binder không tự chuyển producer errors sang DLQ. | Tự xử lý error channel và publish/lưu message lỗi. |

Khi điều tra, kiểm tra theo thứ tự: exchange tồn tại, queue tồn tại, binding/routing key, mandatory, publisher returns, correlated confirms, error-channel-enabled, correlation ID và trạng thái broker. Đọc cả reply code/reply text lẫn confirm result để xác định chính xác message đã được route hay chưa.

## 17. Checklist trước khi triển khai

- [ ] ConnectionFactory bật publisher confirms ở chế độ correlated.
- [ ] Publisher returns được bật nếu cần phát hiện message không có route.
- [ ] Producer gửi mandatory khi yêu cầu phát hiện unroutable message.
- [ ] Output binding bật error-channel-enabled nếu muốn nhận lỗi gửi bất đồng bộ qua error channel.
- [ ] Chọn use-confirm-header hoặc confirm-ack-channel; không cấu hình đồng thời.
- [ ] CorrelationData có ID duy nhất cho từng lần publish.
- [ ] Ứng dụng kiểm tra cả ACK/NACK và returned message.
- [ ] Không xem StreamBridge.send trả true là broker confirm.
- [ ] Có timeout và xử lý trạng thái publish chưa xác định.
- [ ] Có event ID và idempotency để xử lý duplicate khi retry.
- [ ] Có quy trình cho returned message, NACK và channel exception.
- [ ] Không giả định producer errors tự động được đưa vào DLQ.
- [ ] Integration test đã kiểm tra route thành công, NO_ROUTE, AE và NACK.
- [ ] Metric theo dõi confirm latency, returns, NACK và retry.

Publisher confirms cho biết RabbitMQ đã chấp nhận trách nhiệm với message; publisher returns báo message không được định tuyến tới queue khi publisher gửi ở chế độ mandatory. Hai kết quả phải được kiểm tra cùng nhau: một message không có route vẫn có thể nhận confirm ACK sau khi broker gửi return. Spring Cloud Stream Rabbit binder hỗ trợ nhận kết quả qua producer error channel hoặc cơ chế correlation data header với Future<Confirm>. Khi kết hợp confirms, returns, routing test, outbox và idempotent consumer, ứng dụng có thể phát hiện sớm message không có đích nhận và xử lý trạng thái gửi một cách có kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Stream — RabbitMQ Binder Reference Guide: Publisher Confirms](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Binding Properties: errorChannelEnabled](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring AMQP — Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Publishers and Unroutable Message Handling](https://www.rabbitmq.com/docs/publishers)
