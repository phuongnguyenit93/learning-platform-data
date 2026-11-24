# Chế độ xác nhận AUTO, MANUAL và NONE

RabbitMQ giao message cho consumer theo cơ chế push. Sau khi nhận message, consumer cần cho broker biết message đã được xử lý, cần giao lại hay có thể loại khỏi queue. Tín hiệu đó gọi là acknowledgement (ack). Chế độ xác nhận quyết định ai gửi ack và thời điểm broker được phép xóa message khỏi queue.

Spring Cloud Stream Rabbit binder hỗ trợ ba chế độ: `AUTO`, `MANUAL` và `NONE`. `AUTO` để listener container xác nhận sau khi xử lý thành công; `MANUAL` giao quyền xác nhận cho code ứng dụng thông qua Rabbit channel và delivery tag; `NONE` không gửi ack vì broker xem message đã được xác nhận ngay khi giao. Mặc định của Rabbit binder là `AUTO`.

Chọn sai chế độ có thể gây mất message hoặc giao lại nhiều lần. Bài học này giải thích vòng đời ack, cách cấu hình từng chế độ trong Spring Cloud Stream, cách dùng `basicAck`, `basicNack`, `basicReject`, và cách phối hợp acknowledgement với retry, dead-letter queue (DLQ), prefetch và idempotency.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt acknowledgement ở RabbitMQ với publisher confirm.
- Mô tả thời điểm xác nhận của AUTO, MANUAL và NONE.
- Cấu hình `acknowledgeMode` trên Rabbit consumer binding.
- Dùng `AmqpHeaders.CHANNEL` và `AmqpHeaders.DELIVERY_TAG` trong MANUAL mode.
- Chọn giữa `basicAck`, `basicNack` và `basicReject`.
- Hiểu tác động của requeue, retry và DLQ.
- Tránh mất message, vòng lặp redelivery và xác nhận trùng.
- Điều chỉnh prefetch theo số message chưa được xác nhận.
- Kiểm thử các tình huống consumer hoàn tất, lỗi và dừng đột ngột.

## 1. Acknowledgement trong RabbitMQ là gì?

Khi consumer đăng ký nhận message từ queue, RabbitMQ chuyển message tới consumer. Với acknowledgement thủ công hoặc do container quản lý, message vẫn ở trạng thái chưa xác nhận (unacked) cho tới khi broker nhận được ack hợp lệ.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ queue
    participant C as Consumer
    Q->>C: Deliver message (deliveryTag=42)
    Note over Q: Message ở trạng thái unacked
    C->>C: Xử lý nghiệp vụ
    C->>Q: basicAck(42, false)
    Note over Q: Broker loại message khỏi queue
~~~

Ack cho broker biết consumer đã nhận trách nhiệm xử lý xong message. Nếu consumer mất kết nối trước khi ack, RabbitMQ có thể đưa message chưa ack trở lại trạng thái ready để giao cho consumer khác. Vì vậy, consumer có thể nhận lại message dù lần xử lý trước đã thực hiện một phần hoặc thậm chí đã commit database.

Các khái niệm cần phân biệt:

- **Delivery:** broker chuyển message cho consumer.
- **Acknowledgement:** consumer xác nhận đã xử lý hoặc quyết định loại/giao lại message.
- **Publisher confirm:** broker xác nhận kết quả publish cho producer.
- **Message durability:** message và queue được cấu hình để tồn tại qua sự cố/restart theo các điều kiện tương ứng.

Consumer ack không thay thế publisher confirm. Ack cũng không tự bảo đảm message được lưu bền vững trước khi consumer nhận; durability phụ thuộc queue type, message delivery mode, replication và cấu hình broker.

## 2. Ba chế độ xác nhận

| Chế độ | Ai xác nhận? | Thời điểm | Hành vi khi consumer chết trước xử lý |
|---|---|---|---|
| `AUTO` | Listener container của Spring | Sau khi listener xử lý hoàn tất bình thường | Message chưa ack được giao lại |
| `MANUAL` | Code ứng dụng | Khi ứng dụng gọi `basicAck`, `basicNack` hoặc `basicReject` | Message chưa ack được giao lại khi channel/connection đóng |
| `NONE` | Không có ack frame từ consumer; RabbitMQ auto-ack khi giao | Ngay lúc broker gửi message | Message có thể đã bị loại khỏi queue dù ứng dụng chưa xử lý xong |

Tên gọi dễ gây nhầm: `AUTO` của Spring AMQP nghĩa là container tự gửi ack sau khi listener hoàn tất. RabbitMQ gọi chế độ không dùng acknowledgement là *auto-ack*; trong Spring, chế độ đó tương ứng với `NONE`.

Spring Cloud Stream Rabbit binder mặc định dùng `AUTO`. Chỉ đổi sang `MANUAL` khi ứng dụng thực sự cần quyết định ack/nack ở mức từng message. `NONE` phù hợp với dữ liệu có thể mất và cần ưu tiên tốc độ hơn bảo đảm giao nhận.

## 3. Cấu hình acknowledgeMode trong Spring Cloud Stream

Thuộc tính này thuộc riêng Rabbit binder và đặt dưới prefix:

`spring.cloud.stream.rabbit.bindings.<bindingName>.consumer.`

Ví dụ binding nhận đơn hàng:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: AUTO
~~~

Có thể đặt giá trị mặc định cho nhiều Rabbit binding bằng:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        default:
          consumer:
            acknowledgeMode: AUTO
~~~

Cấu hình riêng của binding sẽ ghi đè cấu hình mặc định. Đừng nhầm prefix này với `spring.cloud.stream.bindings.<bindingName>.consumer`, vốn chứa các thuộc tính consumer chung như concurrency và retry.

Các giá trị hợp lệ là `AUTO`, `MANUAL` và `NONE`. Nếu không khai báo, binder sử dụng `AUTO`.

## 4. AUTO: container xác nhận sau khi xử lý thành công

Với `AUTO`, listener container quản lý acknowledgement. Khi handler hoàn tất bình thường, container gửi ack cho RabbitMQ. Nếu handler ném exception, container/error handler xử lý thất bại theo retry, requeue và DLQ configuration.

Ví dụ function consumer:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumer {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
~~~

Cấu hình AUTO:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: AUTO
~~~

Nếu `orderService.process` hoàn tất bình thường, container xác nhận message. Nếu nó ném exception, Spring Cloud Stream có thể thực hiện retry theo `maxAttempts` trước khi chuyển sang failure handling. Hành vi cuối cùng còn phụ thuộc `requeueRejected`, DLQ topology và cấu hình binder.

### Khi nào AUTO phù hợp?

AUTO thường là lựa chọn tốt cho phần lớn consumer nghiệp vụ vì:

- Code nghiệp vụ không phải tự quản lý delivery tag.
- Ack chỉ được gửi sau khi handler hoàn tất bình thường.
- Retry và DLQ có thể phối hợp với error handling của framework.
- Giảm nguy cơ quên ack hoặc ack sai message.

Cần lưu ý: “handler hoàn tất bình thường” là tín hiệu của framework, không tự chứng minh mọi side effect bên ngoài đã bền vững. Nếu handler bắt exception rồi chỉ ghi log và trả về bình thường, container có thể ack message. Không nuốt lỗi nếu muốn framework retry hoặc chuyển message sang failure path.

### AUTO và xử lý bất đồng bộ

Nếu handler đẩy công việc sang một thread hoặc queue nội bộ rồi trả về ngay, container có thể xem listener đã hoàn tất và ack message trước khi công việc nền hoàn tất. Hãy bảo đảm ranh giới hoàn tất của listener phản ánh đúng lúc nghiệp vụ đã xử lý bền vững. Với xử lý async, dùng mô hình hỗ trợ async đúng cách hoặc cân nhắc manual acknowledgement sau khi hiểu rõ vòng đời channel.

## 5. MANUAL: ứng dụng tự xác nhận

Với `MANUAL`, container không tự ack khi listener trả về. Code ứng dụng phải quyết định message đã thành công, cần giao lại hay cần reject. Spring AMQP đưa Rabbit channel và delivery tag vào message headers:

- `AmqpHeaders.CHANNEL` (header `amqp_channel`) chứa `com.rabbitmq.client.Channel`.
- `AmqpHeaders.DELIVERY_TAG` (header `amqp_deliveryTag`) chứa delivery tag của message.

Cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: MANUAL
              autoBindDlq: true
~~~

### Xác nhận message thành công

Khi nghiệp vụ đã hoàn tất và dữ liệu đã được ghi bền vững, gọi:

~~~java
channel.basicAck(deliveryTag, false);
~~~

Tham số thứ hai là `multiple`:
- `false`: chỉ xác nhận delivery tag này.
- `true`: xác nhận tất cả delivery tag chưa ack trên channel có giá trị nhỏ hơn hoặc bằng tag hiện tại.

Với xử lý từng message độc lập, thường dùng `false`. Chỉ dùng `true` khi ứng dụng quản lý chính xác thứ tự hoàn tất của mọi delivery trước đó trên channel. Nếu một message trước vẫn đang xử lý, ack multiple có thể xác nhận nhầm message đó.

### Nack và reject

Nếu không thể xử lý message, ứng dụng có thể chọn:

~~~java
channel.basicNack(deliveryTag, false, true);
~~~

`basicNack` cho phép:
- Chỉ định một delivery hoặc nhiều delivery bằng `multiple`.
- Chọn `requeue=true` để đưa message trở lại queue.
- Chọn `requeue=false` để reject; nếu queue có dead-letter exchange phù hợp, message được dead-letter theo cấu hình broker.

`basicReject` áp dụng cho một delivery tag:

~~~java
channel.basicReject(deliveryTag, false);
~~~

Bảng so sánh:

| API | Phạm vi | Có requeue? | Mục đích |
|---|---|---|---|
| `basicAck(tag, multiple)` | Một hoặc nhiều delivery chưa ack | Không | Xác nhận xử lý thành công |
| `basicNack(tag, multiple, requeue)` | Một hoặc nhiều delivery chưa ack | Có | Giao lại hoặc reject |
| `basicReject(tag, requeue)` | Một delivery | Có | Reject một message |

Khi dùng `requeue=false`, message chỉ được chuyển sang DLQ nếu queue có dead-letter exchange được cấu hình; nếu không, RabbitMQ có thể loại bỏ message. Không mặc định rằng reject luôn tạo DLQ.

### Ví dụ MANUAL với Spring Cloud Stream

~~~java
import java.io.IOException;
import java.util.function.Consumer;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class ManualAckOrderConsumer {

    @Bean
    Consumer<Message<OrderCreated>> processOrderManually(
            OrderService orderService) {

        return message -> {
            Channel channel = message.getHeaders().get(
                AmqpHeaders.CHANNEL, Channel.class
            );
            Long deliveryTag = message.getHeaders().get(
                AmqpHeaders.DELIVERY_TAG, Long.class
            );

            try {
                orderService.process(message.getPayload());
            }
            catch (TemporaryOrderException ex) {
                try {
                    channel.basicNack(deliveryTag, false, true);
                }
                catch (IOException ackError) {
                    throw new AmqpException(
                        "Không thể yêu cầu RabbitMQ giao lại message", ackError
                    );
                }
                return;
            }
            catch (InvalidOrderException ex) {
                try {
                    channel.basicReject(deliveryTag, false);
                }
                catch (IOException ackError) {
                    throw new AmqpException(
                        "Không thể reject message", ackError
                    );
                }
                return;
            }
            catch (RuntimeException ex) {
                try {
                    // Cần có DLX/DLQ để cách ly lỗi chưa được phân loại.
                    channel.basicNack(deliveryTag, false, false);
                }
                catch (IOException ackError) {
                    throw new AmqpException(
                        "Không thể cách ly message lỗi", ackError
                    );
                }
                return;
            }

            try {
                channel.basicAck(deliveryTag, false);
            }
            catch (IOException ackError) {
                throw new AmqpException(
                    "Không thể xác nhận message", ackError
                );
            }
        };
    }
}
~~~

Đây là ví dụ minh họa quyết định ack trong cùng ngữ cảnh xử lý message. Trong ứng dụng thực tế, cần:
- Bảo đảm `channel` và `deliveryTag` tồn tại khi binding chạy ở MANUAL mode.
- Chỉ ack một lần cho mỗi delivery.
- Không ack trước khi thay đổi nghiệp vụ đã được commit.
- Không giữ channel để dùng tùy ý sau khi handler kết thúc.
- Xử lý lỗi I/O khi gửi ack/nack vì kết nối có thể đã đóng.
- Dùng idempotency vì broker có thể giao lại nếu ack bị mất hoặc không tới broker.

Channel là đối tượng kết nối đang hoạt động, không thể serialize an toàn hoặc lưu vào database để xử lý sau. Chỉ dùng channel trong phạm vi delivery hiện tại. Nếu xử lý bất đồng bộ, phải thiết kế rõ vòng đời channel, thread và thời điểm xác nhận; không chuyển channel tùy tiện sang thread pool.

## 6. NONE: broker xác nhận ngay khi giao

Với `NONE`, consumer không gửi acknowledgement. RabbitMQ xem message đã được xác nhận ngay khi gửi tới consumer (còn gọi là auto-ack). Nếu process chết ngay sau khi nhận nhưng trước khi xử lý, message có thể đã bị loại khỏi queue và không được giao lại.

Cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        metricsConsumer-in-0:
          destination: telemetry
          group: metrics-reader
      rabbit:
        bindings:
          metricsConsumer-in-0:
            consumer:
              acknowledgeMode: NONE
~~~

NONE có thể phù hợp với dữ liệu:
- Có thể mất một phần mà không ảnh hưởng nghiệp vụ.
- Có thể được tái tạo từ nguồn khác.
- Là telemetry hoặc số liệu tạm thời mà tốc độ quan trọng hơn việc xử lý từng message.
- Không kích hoạt tác dụng phụ không thể hoàn tác.

Không dùng NONE cho thanh toán, đơn hàng, tồn kho hoặc sự kiện cần bảo đảm xử lý. Khi message được giao, broker không còn chờ consumer xác nhận. Restart ứng dụng không khôi phục các message đã được auto-ack.

`NONE` không tương thích với Rabbit channel transaction (`transacted: true` / `channelTransacted=true`). Nếu cần giao dịch channel, hãy chọn AUTO hoặc MANUAL và kiểm thử commit/rollback cùng acknowledgement.

### NONE không phải là chế độ AUTO nhanh hơn

AUTO vẫn đợi listener hoàn tất trước khi container gửi ack. NONE bỏ qua bước đó. Sự khác nhau là bảo đảm giao nhận, không chỉ hiệu năng. Khi chọn NONE, ứng dụng chấp nhận nguy cơ mất message trong cửa sổ từ lúc broker giao đến lúc ứng dụng hoàn tất xử lý.

## 7. So sánh độ tin cậy và lựa chọn theo nghiệp vụ

| Nhu cầu | Chế độ gợi ý | Lý do |
|---|---|---|
| Xử lý đơn hàng và thanh toán | AUTO | Container ack sau xử lý; retry/DLQ tích hợp thuận tiện |
| Chỉ ack sau khi ghi database hoặc hoàn tất bước tùy chỉnh | MANUAL | Ứng dụng điều khiển thời điểm ack |
| Phân loại lỗi để requeue hoặc reject ngay | MANUAL | Code quyết định disposition của message |
| Đếm telemetry có thể mất | NONE | Không cần chờ ack, ưu tiên throughput |
| Consumer có logic phức tạp, cần quản lý nhiều delivery | MANUAL có kiểm soát | Có thể ack theo nhóm nhưng cần theo dõi tag và thứ tự |
| Consumer nghiệp vụ thông thường | AUTO | Ít code vận hành thủ công và ít lỗi ack |

Không có chế độ nào tự tạo exactly-once processing. AUTO và MANUAL có thể dẫn đến redelivery nếu consumer chết sau khi commit nghiệp vụ nhưng trước khi broker nhận ack. Consumer vẫn cần idempotent.

## 8. Delivery tag và channel cần được quản lý đúng

Delivery tag là số định danh delivery do RabbitMQ cấp trên một channel. Nó không phải message ID toàn cục và không dùng được trên channel khác.

Các quy tắc quan trọng:

1. Dùng đúng channel đi kèm delivery.
2. Không lấy delivery tag của message này để ack message khác.
3. Không dùng tag sau khi channel đã đóng.
4. Không ack cùng một tag hai lần.
5. Cẩn thận với `multiple=true` khi xử lý song song.
6. Không lưu channel trong entity hoặc database.
7. Không coi delivery tag là khóa deduplication nghiệp vụ.

Nếu consumer nhận cùng message lần nữa, delivery tag mới có thể khác. Để nhận diện sự kiện trùng, dùng event ID hoặc business key trong payload/header, không dùng delivery tag.

## 9. Requeue, retry và nguy cơ vòng lặp

`basicNack(tag, false, true)` yêu cầu RabbitMQ đưa message trở lại queue. Nếu message lỗi vẫn được consumer nhận ngay và lỗi lần nữa, nó có thể tạo vòng lặp redelivery liên tục:

~~~mermaid
flowchart TD
    A["Queue giao message"] --> B["Consumer xử lý"]
    B --> C{"Thành công?"}
    C -->|Có| D["Ack"]
    C -->|Không| E["Nack requeue=true"]
    E --> A
~~~

Vòng lặp nóng có thể:
- Tạo tải CPU và network cao.
- Làm một message lỗi chiếm phần lớn thời gian consumer.
- Làm tăng số lần xử lý và log.
- Ngăn các message khác tiến triển.
- Làm broker và downstream quá tải.

Với lỗi tạm thời, dùng retry có backoff hoặc delayed retry thay vì requeue liên tục. Với lỗi dữ liệu không thể phục hồi, reject với `requeue=false` và chuyển tới DLQ nếu topology được cấu hình.

### Retry của Spring Cloud Stream

Consumer property chung `maxAttempts` quy định số lần xử lý tối đa, bao gồm lần đầu; mặc định thường là 3. Có thể cấu hình backoff:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            maxAttempts: 4
            backOffInitialInterval: 1000
            backOffMaxInterval: 10000
            backOffMultiplier: 2.0
~~~

Với AUTO, để exception thoát khỏi handler để framework áp dụng retry. Không bắt exception rồi trả về bình thường nếu muốn retry. Khi hết retry, Rabbit binder xử lý failure theo các thuộc tính như `requeueRejected`, `autoBindDlq` và `republishToDlq`.

Với MANUAL, ứng dụng đã tự quyết định ack/nack. Hãy xác định rõ tầng nào sở hữu retry và kiểm thử tương tác giữa retry của framework với lệnh ack/nack do ứng dụng gọi. Tránh cấu hình hai cơ chế retry độc lập khiến số lần thử tăng ngoài dự kiến.

## 10. Kết hợp AUTO với DLQ

Rabbit binder có thể tự khai báo dead-letter queue và bind queue đó vào dead-letter exchange khi bật `autoBindDlq`. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: AUTO
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
~~~

Các điểm cần hiểu:

- `autoBindDlq` mặc định là `false`; bật nó để binder khai báo DLQ và bind với DLX theo cấu hình.
- `republishToDlq` mặc định là `true` khi binder republish message thất bại tới DLQ; binder có thể thêm exception message và stack trace vào headers.
- `requeueRejected` quyết định có requeue delivery failure trong trường hợp retry bị tắt hoặc `republishToDlq=false`; mặc định hiện hành là `false`.
- Tên DLQ, DLX và routing key có thể cấu hình riêng.
- DLQ không tự sửa payload; cần quy trình điều tra và replay.

Không nhầm việc binder republish message sau khi retry cạn với lệnh `basicReject(..., false)` do ứng dụng gọi trong MANUAL mode. Lệnh reject thủ công dựa vào dead-letter exchange/topology của queue; đường republish có thể không thêm cùng bộ headers lỗi như binder retry recovery.

## 11. Prefetch và số message chưa ack

Prefetch giới hạn số message RabbitMQ có thể giao trước mà chưa nhận ack từ consumer. Đây là cơ chế điều tiết lượng message in-flight.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: MANUAL
              prefetch: 20
~~~

Với prefetch 20, broker có thể giao tối đa khoảng 20 message chưa ack cho mỗi consumer theo QoS cấu hình. Khi consumer ack message, broker có thể giao thêm message để duy trì lượng in-flight.

Prefetch quá cao:
- Tăng bộ nhớ và số message đang nằm trong ứng dụng.
- Có thể làm một consumer giữ nhiều message trong khi consumer khác rảnh.
- Khi consumer chết, nhiều message cùng được requeue.
- Làm tăng độ trễ của message chờ nếu một consumer xử lý chậm.

Prefetch quá thấp:
- Có thể giảm throughput vì consumer thường xuyên chờ broker giao thêm message.
- Không tận dụng hết khả năng xử lý song song khi tác vụ có thời gian chờ.

Chọn prefetch dựa trên thời gian xử lý, kích thước message, concurrency, memory và mục tiêu latency. Với manual ack, theo dõi số unacked messages và bảo đảm ứng dụng không giữ message quá lâu.

## 12. Acknowledgement không thay thế transaction và idempotency

Một tình huống phổ biến:

1. Consumer ghi database thành công.
2. Consumer gọi `basicAck`.
3. Kết nối bị ngắt trước khi RabbitMQ nhận ack.
4. RabbitMQ giao lại message.
5. Consumer ghi database lần nữa.

Dù ứng dụng đã gọi ack, nó không biết chắc broker đã nhận được ack nếu connection mất ngay sau đó. Vì vậy, xử lý nghiệp vụ cần chịu được redelivery.

Các biện pháp:

- Dùng event ID ổn định để nhận diện message.
- Tạo unique constraint hoặc inbox table để deduplicate.
- Gộp inbox record và thay đổi database trong cùng transaction.
- Dùng idempotency key cho API bên ngoài.
- Ack sau khi thay đổi nghiệp vụ đã commit.
- Không coi việc gọi ack là transaction phân tán giữa RabbitMQ và database.

Nếu cần phát message tiếp theo sau khi ghi database, dùng transactional outbox. Outbox bảo đảm yêu cầu publish được lưu cùng thay đổi nghiệp vụ; consumer phía sau vẫn cần idempotency vì relay có thể publish lại.

## 13. Xử lý lỗi trong từng chế độ

| Tình huống | AUTO | MANUAL | NONE |
|---|---|---|---|
| Handler thành công | Container ack | Ứng dụng gọi basicAck | Broker đã coi là ack khi giao |
| Handler ném exception | Container/error handler xử lý retry/reject | Cần bảo đảm delivery được ack/nack; chưa ack sẽ được requeue khi channel đóng | Message có thể đã bị loại khỏi queue |
| Ứng dụng muốn requeue | Dùng failure/requeue configuration | Gọi basicNack/basicReject với requeue=true | Không thể yêu cầu redelivery bằng ack |
| Ứng dụng muốn DLQ | Cấu hình binder DLQ và failure path | Reject/nack requeue=false với DLX đã cấu hình | Không còn delivery để chuyển DLQ sau khi đã auto-ack |
| Process chết giữa xử lý | Message chưa ack được giao lại | Message chưa ack được giao lại | Có thể mất message |
| Quên ack | Không áp dụng cho code handler | Message giữ unacked đến khi channel đóng hoặc bị timeout/connection recovery | Không áp dụng |

Với MANUAL, nếu code không gọi ack hoặc nack, message ở trạng thái unacked. Nó có thể giữ tài nguyên và không được giao cho consumer khác cho đến khi channel đóng hoặc broker xử lý connection failure. Đây là lý do mọi nhánh logic phải có quyết định rõ ràng.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Message bị mất khi consumer crash | Dùng NONE | Chuyển sang AUTO hoặc MANUAL |
| Message được giao lại dù database đã commit | Broker chưa nhận ack | Dùng inbox/idempotency |
| Message lặp vô hạn | Nack với requeue=true cho lỗi vĩnh viễn | Phân loại lỗi, dùng DLQ hoặc retry có backoff |
| Consumer giữ nhiều unacked messages | Quên ack trong MANUAL | Kiểm tra mọi nhánh và channel lifecycle |
| Ack sai message | Dùng nhầm delivery tag hoặc channel | Lấy header từ chính message hiện tại |
| Ack multiple làm mất message chưa xử lý | Dùng multiple=true khi xử lý song song | Dùng false hoặc quản lý thứ tự hoàn tất |
| DLQ không nhận message | Chưa có DLX hoặc autoBindDlq chưa bật | Kiểm tra queue arguments và binder topology |
| AUTO ack dù nghiệp vụ lỗi | Handler bắt exception rồi trả về bình thường | Ném lại exception để failure handling hoạt động |
| Retry quá nhiều | Retry lồng giữa framework và code MANUAL | Chỉ định một tầng sở hữu retry |
| Unacked tăng liên tục | Consumer xử lý chậm hoặc thiếu ack | Điều chỉnh prefetch/concurrency và xử lý lỗi |
| Dùng channel sau khi message kết thúc | Lưu channel để ack từ công việc nền | Giữ thao tác ack trong vòng đời delivery |

## 15. Kiểm thử AUTO, MANUAL và NONE

Nên chạy integration test với RabbitMQ thực tế hoặc Testcontainers. Test binder có thể kiểm tra logic function nhưng không mô phỏng đầy đủ acknowledgement protocol và redelivery của broker.

### Kiểm thử AUTO

1. Tạo queue và binding có group ổn định.
2. Gửi một message hợp lệ.
3. Xác minh handler xử lý thành công và message biến mất khỏi ready/unacked.
4. Gửi message làm handler ném exception.
5. Xác minh retry và failure path đúng cấu hình.
6. Dừng consumer trước khi xử lý hoàn tất và xác minh message được giao lại.

### Kiểm thử MANUAL

1. Cấu hình `acknowledgeMode: MANUAL`.
2. Xác minh message có headers channel và delivery tag.
3. Gửi message hợp lệ; gọi basicAck sau khi database commit.
4. Xác minh message được loại khỏi queue.
5. Gửi message lỗi tạm thời; gọi basicNack với requeue=true và quan sát redelivery.
6. Gửi message lỗi vĩnh viễn; gọi basicReject với requeue=false và xác minh DLQ nhận message nếu đã cấu hình.
7. Mô phỏng channel đóng trước ack và xác minh message chưa ack được giao lại.
8. Xác minh không ack cùng delivery tag hai lần.

### Kiểm thử NONE

1. Cấu hình `acknowledgeMode: NONE`.
2. Gửi message và xác minh broker xem delivery đã được xác nhận ngay.
3. Dừng consumer sau khi nhận nhưng trước khi xử lý xong.
4. Xác minh message không được giao lại như chế độ ack thủ công.
5. Đánh giá dữ liệu nghiệp vụ nào có thể chấp nhận rủi ro mất message.

### Quan sát trên RabbitMQ

Dùng RabbitMQ Management UI hoặc metrics để theo dõi:
- Ready messages.
- Unacked messages.
- Consumer count.
- Redelivery rate.
- Queue ingress/egress.
- DLQ depth.
- Consumer processing latency.

Một test chỉ xác minh function đã được gọi không đủ chứng minh ack hoạt động đúng. Cần quan sát trạng thái queue và hành vi redelivery của broker.

## 16. Bài thực hành: consumer xử lý đơn hàng

Xây dựng consumer `processOrder` đọc destination `orders` với group `order-processor`:

1. Khởi đầu với `AUTO`, viết function chỉ trả về bình thường sau khi service commit database.
2. Gửi message hợp lệ và xác minh broker nhận ack.
3. Làm service ném exception tạm thời; xác minh retry theo `maxAttempts`.
4. Bật DLQ và kiểm tra message sau khi hết retry.
5. Chuyển sang `MANUAL`, lấy channel và delivery tag từ headers.
6. Gọi basicAck sau khi transaction nghiệp vụ thành công.
7. Với lỗi tạm thời, thử basicNack requeue=true trong môi trường test.
8. Với lỗi vĩnh viễn, dùng basicReject requeue=false và xác minh DLX/DLQ.
9. Mô phỏng process chết sau database commit nhưng trước ack; xác minh redelivery không tạo tác dụng phụ trùng.
10. Thử `NONE` với telemetry có thể mất và quan sát khác biệt khi consumer dừng đột ngột.
11. Điều chỉnh prefetch và theo dõi số unacked messages.
12. Ghi nhận lựa chọn acknowledgement mode cùng lý do nghiệp vụ.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| AUTO | Container ack sau listener thành công |
| MANUAL | Ứng dụng ack/nack đúng delivery tag và channel |
| NONE | Hiểu và chấp nhận rủi ro mất message |
| Exception | Failure path không bị nuốt |
| Retry | Có giới hạn và backoff phù hợp |
| DLQ | Reject/failure đi đúng dead-letter topology |
| Prefetch | Unacked messages nằm trong giới hạn |
| Idempotency | Redelivery không lặp side effect |
| Channel lifecycle | Không giữ hoặc dùng channel sau delivery |
| Observability | Theo dõi ready, unacked, redelivery và DLQ |

## Kết luận

`AUTO`, `MANUAL` và `NONE` xác định thời điểm và chủ thể xác nhận message trong RabbitMQ. AUTO là mặc định phù hợp với phần lớn consumer Spring Cloud Stream: container ack sau khi listener hoàn tất bình thường. MANUAL cho phép ứng dụng điều khiển từng delivery bằng `basicAck`, `basicNack` hoặc `basicReject`. NONE dùng auto-ack ở broker và có thể làm mất message nếu consumer dừng sau khi nhận.

Hãy chọn chế độ theo mức độ quan trọng của dữ liệu, phối hợp retry/DLQ và prefetch, đồng thời thiết kế consumer idempotent để chịu được redelivery. Ack chỉ xác nhận giao nhận ở phía consumer; publisher confirms, queue durability và transaction là các cơ chế riêng cần được cấu hình và kiểm thử phù hợp.

## Tài liệu tham khảo

- [Spring Cloud Stream – RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring AMQP – Message Listener Container Acknowledge Mode](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring Integration – Inbound Endpoint Acknowledge Mode](https://docs.spring.io/spring-integration/reference/amqp/inbound-ack.html)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)

