# Delivery tag, redelivered và consumer tag ở phía nhận

Trong hệ thống xử lý bất đồng bộ bằng RabbitMQ, một message có thể được gửi thành công nhưng consumer gặp lỗi trước khi xác nhận đã nhận xong. Broker có thể giao lại message đó, đôi khi trên một channel khác hoặc cho một consumer khác. Nếu ứng dụng hiểu sai các giá trị đi kèm lần giao message, nó có thể **ACK nhầm**, lặp nghiệp vụ hoặc đánh giá sai nguyên nhân message xuất hiện nhiều lần.

Ở phía nhận, ba thông tin cần phân biệt là **delivery tag**, **redelivered** và **consumer tag**. Chúng gắn với **lần broker giao message cho consumer**, không phải ba mã định danh vĩnh viễn của nội dung message. Bài học thuộc chương **Cấu trúc thông điệp** của module **SPRING_AMQP**, kết hợp `@RabbitListener`, `RabbitTemplate`, exchange, queue và binding để giải thích ý nghĩa của các trường này, cách ACK/NACK/requeue, xử lý trùng, dead-letter, giao dịch và quan sát hệ thống.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích phạm vi của `deliveryTag` và dùng nó để ACK/NACK **trên đúng AMQP channel**.
2. Hiểu ý nghĩa thực tế cùng giới hạn của cờ `redelivered`; tránh dùng cờ này thay cho idempotency.
3. Phân biệt `consumerTag` với `deliveryTag`, `messageId`, `correlationId` và ID của listener.
4. Đọc metadata của lần giao message bằng `MessageProperties` trong Spring AMQP.
5. Viết `@RabbitListener` dùng acknowledgment thủ công (`MANUAL`) và quan sát một lần NACK/requeue.
6. Thiết kế đường xử lý lỗi phù hợp với retry có giới hạn, dead-letter và ghi nhận nghiệp vụ bền vững.

## 2. Ba thông tin này xuất hiện ở đâu?

Trong giao thức AMQP 0-9-1, khi broker đẩy một message cho consumer, nó gửi phương thức **`basic.deliver`** với những thông tin như *consumer tag*, *delivery tag* và cờ *redelivered*, cùng các frame nội dung/properties của message. Spring AMQP nhận chúng qua client RabbitMQ rồi đưa một số trường vào `MessageProperties` trước khi gọi listener.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer / RabbitTemplate
    participant E as Exchange
    participant Q as Queue
    participant C as Consumer / @RabbitListener
    P->>E: Publish message + properties
    E->>Q: Route theo binding
    C->>Q: Đăng ký basic.consume
    Q-->>C: basic.deliver (consumerTag, deliveryTag, redelivered)
    C->>C: Đọc metadata và xử lý nghiệp vụ
    C-->>Q: basic.ack / basic.nack / basic.reject
~~~

Để đọc sơ đồ chính xác: message có **body** và các **properties do producer đặt**, còn `deliveryTag`, `redelivered` và `consumerTag` mô tả **việc giao message**. Cùng một message được giao lại có thể giữ nguyên body và `messageId` nhưng xuất hiện với `deliveryTag` khác. Khi consumer kết nối lại, `consumerTag` cũng có thể đổi.

| Trường | Tầng giao thức / phía tạo | Phạm vi và ý nghĩa | Truy cập trong Spring AMQP |
|---|---|---|---|
| **Delivery tag** | Broker cấp khi giao message trên channel | Số thứ tự nhận diện **lần giao trên một channel**; dùng khi ACK/NACK/reject | `message.getMessageProperties().getDeliveryTag()` |
| **Redelivered** | Broker gắn trên lần giao | Cờ chỉ broker nhận biết message **đã từng được giao** trước đó và đang được giao lại | `message.getMessageProperties().isRedelivered()` |
| **Consumer tag** | Được thiết lập khi đăng ký consumer (broker tạo hoặc client đề nghị) | Nhận diện **consumer subscription trên channel**, không định danh message | `message.getMessageProperties().getConsumerTag()` |
| **Message ID** | Thường do producer đặt trong AMQP properties | ID ứng dụng dùng theo dõi message; có thể vắng mặt hoặc bị đặt trùng | `message.getMessageProperties().getMessageId()` |
| **Correlation ID** | Thường do producer/ứng dụng đặt | Liên kết request–reply hoặc một chuỗi xử lý nghiệp vụ | `message.getMessageProperties().getCorrelationId()` |
| **Consumer queue** | Spring AMQP gắn thông tin queue của listener | Cho biết queue mà listener đã nhận message | `message.getMessageProperties().getConsumerQueue()` |

**Không dùng `deliveryTag` làm `eventId` trong database.** Delivery tag là số trong phạm vi một channel; cùng số ấy có thể xuất hiện trên channel khác, và một event được giao lại có thể có tag mới.

## 3. Delivery tag: số thứ tự giao message trên channel

### 3.1. Một channel có chuỗi tag riêng

Khi RabbitMQ giao message trên một channel, nó gán **delivery tag tăng dần trong phạm vi channel đó**. Ví dụ:

~~~text
Channel A:
  message M1 -> deliveryTag=1
  message M2 -> deliveryTag=2
  message M3 -> deliveryTag=3

Channel B:
  message N1 -> deliveryTag=1
  message N2 -> deliveryTag=2
~~~

Tag `1` trên Channel A **không phải** cùng một định danh với tag `1` trên Channel B. Khi một connection/channel bị đóng và message chưa được ACK được giao lại trên một channel mới, broker sẽ gán tag theo **chuỗi của channel mới**. Một message có thể mang `deliveryTag=8` ở lần giao đầu và `deliveryTag=1` ở lần giao sau; đây là hiện tượng hợp lệ.

Trong RabbitMQ Java client, ACK/NACK áp dụng lên **channel đang sở hữu lần giao**:

~~~java
// channel là com.rabbitmq.client.Channel của chính lần giao này
channel.basicAck(deliveryTag, false);
channel.basicNack(deliveryTag, false, true);
channel.basicReject(deliveryTag, false);
~~~

Ba thao tác khác nhau:

- `basicAck(tag, false)`: xác nhận **một delivery** với tag đó.
- `basicNack(tag, false, true)`: từ chối delivery và **yêu cầu requeue**; broker có thể giao lại.
- `basicReject(tag, false)`: từ chối delivery và **không requeue**; message có thể được dead-letter nếu queue có DLX phù hợp, hoặc bị loại.

### 3.2. Tham số `multiple` thay đổi phạm vi ACK

`basicAck(tag, true)` xác nhận **tất cả các delivery chưa ACK có tag tới và bao gồm tag được chỉ định trên cùng channel**, không chỉ riêng một message.

| Lệnh gọi khi có tag 4, 5, 6 chưa ACK trên cùng channel | Tác động |
|---|---|
| `basicAck(5, false)` | ACK delivery tag 5 |
| `basicAck(5, true)` | ACK mọi delivery chưa ACK với tag ≤ 5 trên channel đó, gồm 4 và 5 |
| `basicNack(6, false, true)` | NACK delivery tag 6, yêu cầu requeue |
| `basicNack(6, true, false)` | NACK các delivery chưa ACK đến tag 6 trên channel đó, không requeue |

Trong mã xử lý đồng thời, dùng `multiple=true` thiếu kiểm soát có thể ACK những công việc **chưa hoàn tất** trên cùng channel. Với các listener thông thường, bắt đầu từ **`multiple=false`** để thao tác đúng một delivery, trừ khi ứng dụng có thiết kế batch ACK rõ ràng.

### 3.3. ACK sai tag hoặc sai channel

Delivery tag **phải được ACK/NACK trên chính channel đã nhận delivery**. Gửi ACK một tag không hợp lệ (chẳng hạn đã ACK rồi, hoặc thuộc channel khác) có thể khiến RabbitMQ đóng channel với lỗi giao thức như **`PRECONDITION_FAILED - unknown delivery tag`**. Các delivery khác chưa ACK trên channel bị đóng có thể được broker đưa trở lại trạng thái chờ và giao lại.

Vì vậy:

1. Không lưu `deliveryTag` vào database rồi dùng một connection/channel mới để ACK sau.
2. Không gọi ACK hai lần cho cùng delivery.
3. Không kết hợp `acknowledge-mode: auto` với việc tự gọi `basicAck` trên cùng delivery.
4. Khi xử lý bất đồng bộ tách luồng, phải quản lý vòng đời channel/consumer rất cẩn thận; listener thủ công đơn giản nhất là ACK/NACK ngay trong phạm vi xử lý và trên channel được cung cấp.

## 4. Redelivered: tín hiệu giao lại, không phải bộ đếm lỗi

### 4.1. Khi nào broker đánh dấu `redelivered=true`?

Lần giao đầu thông thường có cờ `redelivered=false`. Nếu message đã được giao nhưng chưa được xác nhận hoàn tất và broker phải giao lại, cờ thường là **`true`**. Những tình huống thường gặp:

- Listener gọi `basicNack(tag, false, true)` hoặc `basicReject(tag, true)` để **requeue**.
- Consumer mất kết nối hoặc channel bị đóng khi còn delivery chưa ACK.
- Consumer bị hủy và các message chưa xác nhận quay lại queue.

~~~mermaid
sequenceDiagram
    autonumber
    participant Q as RabbitMQ queue
    participant C as Consumer
    Q-->>C: Deliver M (tag=1, redelivered=false)
    C-->>Q: basic.nack(1, requeue=true)
    Note over Q: Đặt M trở lại queue
    Q-->>C: Deliver M (tag=2, redelivered=true)
    C-->>Q: basic.ack(2)
~~~

Con số tag chỉ để minh họa trường hợp **cùng channel**; nếu lần giao thứ hai diễn ra trên channel khác, delivery tag có thể bắt đầu lại từ đầu. Không có quy tắc nói tag bắt buộc tăng đúng 1 sau khi requeue vì các message khác cũng có thể được giao xen kẽ.

### 4.2. Tại sao `redelivered` không đủ để chống xử lý trùng?

`redelivered=true` gợi ý message **có thể đã được consumer trước đó xử lý một phần hoặc toàn bộ**, nhưng không chứng minh consumer đã chạy nghiệp vụ. Chẳng hạn broker giao message rồi connection đứt trước khi listener bắt đầu.

Ngược lại, **`redelivered=false` cũng không bảo đảm message chưa từng gây hiệu ứng nghiệp vụ**:

- Producer gửi lại cùng một sự kiện sau timeout publisher confirm.
- Hai publication có cùng `eventId` nhưng là hai message mới.
- Ứng dụng retry bằng cách **publish message mới** thay vì requeue delivery cũ.
- Message được chuyển qua dead-letter hoặc một luồng trung gian, rồi xuất hiện như một lần giao mới.

**Quy tắc thiết kế:** coi `redelivered` là thông tin chẩn đoán, **không phải khóa chống trùng** và không phải số lần retry. Consumer cần **idempotency** dựa trên `eventId`/khóa nghiệp vụ được lưu bền vững, thường đặt trong body hoặc message properties do producer kiểm soát.

### 4.3. Muốn biết đã retry bao nhiêu lần thì sao?

Cờ `redelivered` chỉ có hai trạng thái; nó **không chứa số lần giao**. Nếu yêu cầu giới hạn retry, bạn cần cơ chế riêng:

- Retry có giới hạn trong ứng dụng/Spring Retry và lưu hoặc xuất metadata phù hợp.
- Xử lý NACK không requeue hoặc dead-letter sau khi hết chính sách retry.
- Khi message đi qua DLX, kiểm tra metadata lịch sử dead-letter như `x-death` nếu có; **`x-death` không tương đương số lần `basic.nack(..., requeue=true)`**.
- Với queue type/chính sách có tính năng đếm lượt giao của broker, kiểm tra metadata và cấu hình **đặc thù queue/phiên bản** thay vì suy số lần từ cờ `redelivered`.

NACK requeue liên tục không có giới hạn có thể tạo **vòng lặp nóng**, tăng CPU, traffic và log mà nghiệp vụ không tiến triển.

## 5. Consumer tag: nhận diện một lần đăng ký tiêu thụ

Consumer nhận message sau khi client gửi `basic.consume` lên broker. Khi đăng ký, consumer được gắn một **consumer tag**. Broker có thể tạo tag tự động nếu client không đề nghị giá trị riêng; tag được dùng trong `basic.deliver` và các thao tác như hủy consumer (`basic.cancel`).

~~~text
Queue orders.created
  Channel A:
    Consumer tag = ctag-A
    Delivery tag = 1, 2, 3, ...

  Channel B:
    Consumer tag = ctag-B
    Delivery tag = 1, 2, 3, ...
~~~

| Câu hỏi | Consumer tag trả lời? |
|---|---|
| Message được giao cho **consumer subscription** nào? | **Có** |
| Lần giao nào phải được ACK? | Không; dùng **delivery tag cùng channel** |
| Message có phải sự kiện mới hay trùng? | Không; dùng **event ID/idempotency** |
| Consumer đang đọc từ queue nào? | Cần thêm **consumer queue** |
| Sau reconnect có giữ nguyên consumer tag không? | **Không nên giả định**; subscription có thể được tạo lại với tag mới |

Một `@RabbitListener` với `concurrency > 1` có thể tạo nhiều consumer thực tế, mỗi consumer có tag riêng. **ID của phương thức/listener container không đồng nghĩa với consumer tag**. Consumer tag có phạm vi định danh gắn với subscription trên channel; không nên dùng nó làm định danh nghiệp vụ toàn cục hoặc khóa lưu trữ lâu dài.

Trong log, kết hợp **consumer tag + queue + connection/channel + thời điểm** giúp truy vết instance/consumer nào nhận delivery. Tuy nhiên, để lần theo cùng một sự kiện qua producer, exchange, DLQ và consumer khác, vẫn cần `eventId` hoặc correlation ID được tạo ở tầng ứng dụng.

## 6. Truy cập metadata trong Spring AMQP

### 6.1. Đọc từ `MessageProperties`

Spring AMQP thường truyền vào listener một `org.springframework.amqp.core.Message`. Lấy các trường phía nhận như sau:

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class DeliveryMetadataListener {

    @RabbitListener(queues = "orders.created")
    public void receive(Message message) {
        MessageProperties p = message.getMessageProperties();

        long deliveryTag = p.getDeliveryTag();
        boolean redelivered = Boolean.TRUE.equals(p.isRedelivered());
        String consumerTag = p.getConsumerTag();
        String consumerQueue = p.getConsumerQueue();
        String messageId = p.getMessageId();

        System.out.printf(
                "tag=%d, redelivered=%s, consumer=%s, queue=%s, messageId=%s%n",
                deliveryTag, redelivered, consumerTag, consumerQueue, messageId);

        // Xử lý nghiệp vụ; container ở chế độ AUTO có thể ACK sau khi
        // listener hoàn tất bình thường.
    }
}
~~~

Ví dụ này **chỉ quan sát**, không tự gọi `basicAck`. Nếu listener container ở chế độ **`AUTO` của Spring AMQP**, container thường ACK sau khi phương thức hoàn tất không lỗi. Lưu ý `AUTO` này khác với `autoAck=true` của RabbitMQ client (ack ngay khi giao).

### 6.2. Đọc từ `@Header`

Khi listener sử dụng Spring Messaging argument resolution, các metadata có thể được truy cập qua tên `AmqpHeaders`:

~~~java
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;

@RabbitListener(queues = "orders.created")
public void handle(
        String body,
        @Header(AmqpHeaders.DELIVERY_TAG) long tag,
        @Header(AmqpHeaders.REDELIVERED) boolean redelivered,
        @Header(AmqpHeaders.CONSUMER_TAG) String consumerTag) {
    // Các header ở đây là thông tin giao message do listener mapping cung cấp.
}
~~~

Đây là một **ví dụ thay thế** cho cách đọc trực tiếp `MessageProperties`; không khai báo đồng thời hai listener trên cùng queue nếu bạn muốn mọi message đều đi qua một handler duy nhất. Khi cần manual ack, nhận thêm tham số `com.rabbitmq.client.Channel` và cấu hình `MANUAL`.

## 7. Bài thực hành: NACK một lần, sau đó ACK

Ví dụ tiếp theo minh họa cách một message thay đổi `redelivered` và `deliveryTag` qua hai lần giao. Sử dụng một listener **manual acknowledgment**, một producer `RabbitTemplate` và topology có dead-letter queue để có thể mở rộng bài thực hành khi xử lý lỗi.

### 7.1. Chuẩn bị RabbitMQ và Spring Boot

Nếu chưa có broker ở máy học tập, một cách khởi chạy RabbitMQ có Management là:

~~~bash
docker run -d --name rabbitmq-delivery-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

Mở `http://localhost:15672` với tài khoản **lab / lab123456**. Đây là thông tin minh họa cho môi trường local, không sử dụng trên hệ thống công khai. Nếu đã có broker trên các cổng này, dùng broker hiện có với cấu hình kết nối phù hợp.

Trong ứng dụng Spring Boot có Maven dependency management, thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      simple:
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
~~~

**`prefetch: 1`** giúp phòng lab có tối đa một delivery chưa ACK trên mỗi consumer, thuận tiện quan sát. Listener dưới đây khai báo `ackMode = "MANUAL"` riêng, vì vậy chính listener sẽ gọi ACK/NACK.

### 7.2. Tạo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DeliveryLabTopology {

    @Bean
    DirectExchange deliveryExchange() {
        return new DirectExchange("demo.delivery.events", true, false);
    }

    @Bean
    DirectExchange deliveryDlx() {
        return new DirectExchange("demo.delivery.dlx", true, false);
    }

    @Bean
    Queue deliveryQueue() {
        return QueueBuilder.durable("demo.delivery.work")
                .deadLetterExchange("demo.delivery.dlx")
                .deadLetterRoutingKey("demo.delivery.dead")
                .build();
    }

    @Bean
    Queue deliveryDlq() {
        return QueueBuilder.durable("demo.delivery.dlq").build();
    }

    @Bean
    Binding deliveryBinding(Queue deliveryQueue,
                            DirectExchange deliveryExchange) {
        return BindingBuilder.bind(deliveryQueue)
                .to(deliveryExchange)
                .with("demo.delivery.created");
    }

    @Bean
    Binding deadBinding(Queue deliveryDlq,
                        DirectExchange deliveryDlx) {
        return BindingBuilder.bind(deliveryDlq)
                .to(deliveryDlx)
                .with("demo.delivery.dead");
    }
}
~~~

Các bean trên tạo luồng:

~~~text
RabbitTemplate
    -> demo.delivery.events (direct exchange)
    -> routing key: demo.delivery.created
    -> demo.delivery.work (queue)
    -> @RabbitListener

Khi reject không requeue:
    -> demo.delivery.dlx
    -> routing key: demo.delivery.dead
    -> demo.delivery.dlq
~~~

### 7.3. Producer gắn `messageId`

Một endpoint HTTP để tạo một sự kiện mới và publish:

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab/delivery")
public class DeliveryLabPublisher {
    private final RabbitTemplate rabbitTemplate;

    public DeliveryLabPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @PostMapping("/send")
    public ResponseEntity<Map<String, String>> send(
            @RequestParam(defaultValue = "ORD-1001") String orderId) {
        String eventId = UUID.randomUUID().toString();

        rabbitTemplate.convertAndSend(
                "demo.delivery.events",
                "demo.delivery.created",
                orderId,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    message.getMessageProperties()
                            .setHeader("eventId", eventId);
                    return message;
                });

        return ResponseEntity.accepted()
                .body(Map.of("eventId", eventId, "orderId", orderId));
    }
}
~~~

`messageId` và `eventId` do **ứng dụng đặt**, khác với `deliveryTag` do **broker cấp lúc giao**. HTTP `202 Accepted` ở endpoint này chỉ cho biết lời gọi publish phía ứng dụng đã thực hiện mà không ném lỗi ngay; nó không thay cho **publisher confirm** hay bằng chứng consumer hoàn tất nghiệp vụ.

### 7.4. Listener dùng `MANUAL` để tạo redelivery

Listener sau cố ý **NACK và requeue lần đầu** đối với mỗi `messageId`, rồi ACK ở lần nhận tiếp theo. `Set` trong bộ nhớ chỉ dùng để minh họa, **không phải cơ chế retry/idempotency an toàn trong production**.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import com.rabbitmq.client.Channel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class DeliveryLabListener {
    private static final Logger log =
            LoggerFactory.getLogger(DeliveryLabListener.class);

    // Chỉ phục vụ demo: dữ liệu mất khi restart; không dùng để chống trùng thực tế.
    private final Set<String> seenOnce = ConcurrentHashMap.newKeySet();

    @RabbitListener(queues = "demo.delivery.work", ackMode = "MANUAL")
    public void receive(Message message, Channel channel) throws IOException {
        MessageProperties properties = message.getMessageProperties();
        long deliveryTag = properties.getDeliveryTag();
        boolean redelivered =
                Boolean.TRUE.equals(properties.isRedelivered());
        String consumerTag = properties.getConsumerTag();
        String messageId = properties.getMessageId();
        String orderId = new String(
                message.getBody(), StandardCharsets.UTF_8);

        log.info(
                "RECEIVED orderId={}, messageId={}, deliveryTag={}, "
                        + "redelivered={}, consumerTag={}",
                orderId, messageId, deliveryTag, redelivered, consumerTag);

        if (messageId != null && seenOnce.add(messageId)) {
            log.warn("Demo: NACK + requeue lần đầu cho {}", messageId);
            channel.basicNack(deliveryTag, false, true);
            return;
        }

        // Tại đây chỉ mô phỏng xử lý; trong thực tế phải thực hiện
        // nghiệp vụ idempotent và ghi trạng thái bền vững trước khi ACK.
        log.info("Demo: xử lý xong {}, ACK deliveryTag={}",
                messageId, deliveryTag);
        channel.basicAck(deliveryTag, false);
    }
}
~~~

Lưu ý để kết quả dễ theo dõi: chỉ chạy **một listener** nhận `demo.delivery.work` và cấu hình `concurrency=1, prefetch=1`. Nếu bạn giữ thêm một listener khác đọc cùng queue, RabbitMQ có thể chia message sang consumer đó và luồng log sẽ không giống dự đoán.

### 7.5. Gửi và quan sát

Khởi động RabbitMQ và ứng dụng, sau đó chạy:

~~~bash
curl -X POST "http://localhost:8080/lab/delivery/send?orderId=ORD-1001"
~~~

Trong Windows PowerShell, dùng `curl.exe` nếu lệnh `curl` là alias không tương thích với cú pháp mẫu.

Kỳ vọng log **tương tự**:

~~~text
RECEIVED orderId=ORD-1001, messageId=E-1,
         deliveryTag=1, redelivered=false, consumerTag=ctag-A
Demo: NACK + requeue lần đầu cho E-1

RECEIVED orderId=ORD-1001, messageId=E-1,
         deliveryTag=2, redelivered=true, consumerTag=ctag-A
Demo: xử lý xong E-1, ACK deliveryTag=2
~~~

`E-1`, `ctag-A` và các delivery tag là **giá trị minh họa**, không phải output chính xác. Giá trị `eventId/messageId` thực tế là UUID; delivery tag có thể khác nếu channel trước đó đã nhận message, còn consumer tag thường do broker/container sinh ra.

Đối chiếu:

| Thuộc tính | Lần giao đầu | Lần giao lại cùng channel |
|---|---|---|
| Body / `messageId` | Giữ nguyên | Thường giữ nguyên |
| `deliveryTag` | Một số trên channel | Một số delivery **mới** trên channel |
| `redelivered` | Thường `false` | `true` khi broker giao lại |
| `consumerTag` | Tag của consumer nhận | Có thể giữ nguyên nếu cùng consumer; có thể khác nếu chuyển consumer |
| ACK/NACK cần gửi | NACK tag của lần đầu | ACK tag **của lần giao lại** |

Trong RabbitMQ Management, mở **Queues and Streams → demo.delivery.work**. Với listener xử lý rất nhanh, các cột `Ready` và `Unacked` có thể về 0 trước khi giao diện kịp cập nhật; **log có `messageId` và delivery metadata** đáng tin cậy hơn cho thí nghiệm này. Management hỗ trợ xem queue, consumers và connections nhưng không phải kho lưu lịch sử mọi lần `basic.deliver`.

## 8. Khác nhau giữa ACK, NACK, reject và AUTO

| Hành vi | Lệnh / cấu hình | Sau đó broker có thể làm gì? |
|---|---|---|
| Đã xử lý thành công | `basicAck(tag, false)` | Gỡ delivery khỏi trạng thái chờ ACK; không giao lại chỉ vì ACK đó |
| Lỗi tạm thời, yêu cầu giao lại | `basicNack(tag, false, true)` | Đưa message trở lại queue; có thể giao cho cùng hoặc consumer khác |
| Lỗi không thể xử lý, không requeue | `basicReject(tag, false)` | Dead-letter nếu có DLX phù hợp, nếu không thì loại message |
| NACK nhiều delivery không requeue | `basicNack(tag, true, false)` | Tác động tới các delivery chưa ACK đến tag đó trên channel |
| `@RabbitListener` chế độ Spring `AUTO` | Container quyết định ACK khi listener thành công | Không tự gọi `basicAck` trong handler thông thường |
| `@RabbitListener` chế độ `MANUAL` | Ứng dụng tự ACK/NACK đúng channel/tag | Quên xác nhận khiến message ở trạng thái Unacked cho tới khi có điều kiện xử lý khác |

**Cần phân loại lỗi trước khi requeue.** Với lỗi mạng tạm thời, có thể retry có giới hạn và delay; với lỗi dữ liệu không hợp lệ, NACK rồi requeue liên tục chỉ gây vòng lặp. Hệ thống thực tế nên có retry policy, backoff, dead-letter queue, cảnh báo và thao tác kiểm tra/replay có kiểm soát.

Một mẫu xử lý rõ ba kết quả:

~~~java
@RabbitListener(queues = "orders.created", ackMode = "MANUAL")
public void handle(Message message, Channel channel) throws IOException {
    long tag = message.getMessageProperties().getDeliveryTag();

    try {
        orderService.processIdempotently(message);
    } catch (TemporaryProcessingException e) {
        // Minh họa; production cần giới hạn retry và backoff.
        channel.basicNack(tag, false, true);
        return;
    } catch (InvalidMessageException e) {
        // Không requeue; nếu queue cấu hình DLX, message có thể vào DLQ.
        channel.basicReject(tag, false);
        return;
    }

    // Chỉ ACK sau khi side effect nghiệp vụ đã được ghi nhận phù hợp.
    channel.basicAck(tag, false);
}
~~~

Đây là **mẫu thuật toán**, trong đó `orderService` và hai loại exception là thành phần ứng dụng tự định nghĩa. Nếu một exception khác xảy ra hoặc ACK/NACK thất bại vì channel mất kết nối, ứng dụng/container phải có chiến lược lỗi riêng; không nên lặng lẽ nuốt exception rồi coi message đã hoàn thành.

## 9. Redelivery, retry, dead-letter và trùng nghiệp vụ

Đặt ba tình huống cạnh nhau:

| Tình huống | Điều có thể quan sát ở delivery | Nên theo dõi thêm |
|---|---|---|
| Consumer NACK với `requeue=true` | Có thể nhận lại cùng message với `redelivered=true`; tag mới | Số lần lỗi, thời gian retry, log và trạng thái nghiệp vụ |
| Consumer reject không requeue và queue có DLX | Message có thể sang DLQ; lần giao ở DLQ là delivery khác | Header lịch sử dead-letter `x-death`, queue nguồn, lý do xử lý lỗi |
| Producer gửi lại cùng `eventId` sau timeout confirm | Có thể là message mới, lần giao đầu có `redelivered=false` | Idempotency theo `eventId` và trạng thái outbox/publisher confirm |

**Không suy `redelivered=true` nghĩa là đã chạy nghiệp vụ một lần.** Broker chỉ biết đã giao message; nó không biết database đã commit hay chưa. Và **`redelivered=false` không có nghĩa message là sự kiện nghiệp vụ mới**: producer có thể đã phát lại cùng event.

Ví dụ xử lý giữ hàng:

1. Consumer nhận `eventId=E-42`, thực hiện `INSERT reservation` và commit database.
2. Consumer mất connection trước khi broker nhận ACK.
3. Broker giao lại message `E-42` với một delivery tag mới, có thể `redelivered=true`.
4. Nếu consumer không chống trùng, đơn có thể bị giữ hàng hai lần.

Một thiết kế idempotent thường đặt **ràng buộc duy nhất** trên `eventId`/khóa nghiệp vụ trong database và kiểm tra thay đổi trạng thái trong cùng giao dịch thích hợp. Khi nhận sự kiện đã hoàn tất, consumer có thể xác nhận delivery mới mà không lặp side effect. Cờ `redelivered` vẫn hữu ích để log, nhưng không thay thế ràng buộc dữ liệu.

### Publisher confirm không sử dụng delivery tag của consumer

`RabbitTemplate` ở producer có thể dùng **publisher confirms** để nhận ACK/NACK từ broker cho từng publication, chẳng hạn qua `CorrelationData`. Cơ chế đó dựa trên sequence number/confirm tracking của **channel publisher**. Nó **không phải `deliveryTag` của một message được giao cho consumer**. Cùng từ “ACK” nhưng hai phía nói về hai việc:

- **Publisher confirm ACK:** broker xác nhận publication phía producer; không có nghĩa một `@RabbitListener` đã chạy.
- **Consumer basic.ack:** consumer xác nhận delivery cụ thể trên channel của nó; không chứng minh producer đã nhận confirm hay mọi hiệu ứng nghiệp vụ đều đúng.

Nếu message không khớp exchange/binding để đến queue, publisher confirm có thể ACK publication nhưng message vẫn không được định tuyến; khi cần, kết hợp **mandatory publisher returns**. Khi message vào DLQ vì xử lý thất bại, consumer cần theo dõi DLQ chứ không giả định publish ban đầu đã thất bại.

## 10. Quan sát và chẩn đoán trên RabbitMQ Management

Khi RabbitMQ Management được bật, thường có các khu vực **Connections**, **Channels**, **Exchanges**, **Queues and Streams/Queues** và **Consumers** (có thể nằm trong trang chi tiết queue tùy phiên bản).

| Dấu hiệu | Điều cần kiểm tra | Lỗi thường gặp |
|---|---|---|
| `Ready` tăng và `Consumers=0` | Listener có kết nối đúng vhost/queue hay không | Listener chưa chạy, tên queue sai, sai thông tin kết nối |
| `Unacked` tồn đọng lâu | Listener có ACK/NACK đúng channel/tag không | Quên ACK ở `MANUAL`, xử lý bị treo, xử lý quá chậm |
| Channel liên tục đóng với `unknown delivery tag` | Log lỗi giao thức, cách dùng `multiple`, ACK hai lần | ACK sai tag/channel, ACK lặp, chồng `AUTO` và `MANUAL` |
| `redelivered=true` xuất hiện thường xuyên | Exception, requeue, channel/connection bị đóng | Lỗi tạm thời liên tục, vòng lặp NACK không giới hạn |
| Message đến DLQ | DLX binding, header `x-death`, lỗi ứng dụng | Poison message, reject không requeue, hết TTL hoặc chính sách queue |
| Mỗi lần khởi động có consumer tag khác | Listener/container có tạo subscription mới không | Reconnect, restart, thay đổi concurrency |
| Cùng `eventId` được xử lý hai lần | Dữ liệu idempotency và log từng message | Producer gửi trùng hoặc consumer được giao lại |

Khi ghi log ở consumer, ưu tiên đủ các trường:

~~~text
time, eventId/messageId, queue, consumerTag, deliveryTag,
redelivered, businessKey, processingResult, ackAction, exceptionType
~~~

Thêm **correlation ID / trace ID** để nối producer, broker và các downstream services. Đừng dùng duy nhất `deliveryTag` làm khóa tìm kiếm toàn hệ thống: muốn phân biệt delivery an toàn trong log, phải đi cùng **channel/connection hoặc một định danh phiên**, còn muốn đối chiếu sự kiện nghiệp vụ phải dựa vào `eventId`.

Management không lưu lịch sử mọi message đã ACK. Một snapshot có `Ready=0, Unacked=0` chỉ cho biết queue không còn message ở hai trạng thái tại thời điểm thống kê, **không chứng minh tất cả các tác vụ nghiệp vụ đã thành công**.

## 11. Bài tập thực hành

**Bài tập A — Quan sát redelivery trên cùng consumer.** Dùng ví dụ `DeliveryLabListener`, gửi một event và ghi hai dòng `RECEIVED` có cùng `messageId`. Kiểm tra `deliveryTag` và `redelivered` giữa hai lần nhận. Giải thích vì sao ACK phải dùng tag của lần thứ hai.

**Bài tập B — Consumer reconnect.** Gửi message vào queue rồi cho listener chủ động ngừng trước khi ACK trong môi trường lab riêng. Khởi động lại listener, quan sát `consumerTag` và `deliveryTag` của lần giao lại. Vì sao không thể dùng tag trước reconnect để ACK trên channel mới?

**Bài tập C — Đổi NACK thành reject không requeue.** Trong một bản sao lab, thay `basicNack(tag, false, true)` bằng `basicReject(tag, false)`. Message nên xuất hiện ở `demo.delivery.dlq` khi DLX/binding chính xác. So sánh với vòng requeue và tìm metadata dead-letter nếu có.

**Bài tập D — Hai consumer cùng queue.** Tăng concurrency lên 2, gửi nhiều event và quan sát consumer tag khác nhau. Một message có xuất hiện trong cả hai listener cùng lúc không? Delivery tag có duy nhất trên toàn broker không? Ghi chú sự khác nhau giữa **chia tải một queue** và **fan-out đến nhiều queue**.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hai channel cùng nhận một delivery với `deliveryTag=1`. Hai tag này có xác định cùng một message không?

Không. Delivery tag chỉ có ý nghĩa **trên từng channel**; hai channel có thể cùng có tag 1 cho hai delivery độc lập.

**Câu 2.** `redelivered=false` có chứng minh message chưa bao giờ được xử lý nghiệp vụ trước đó không?

Không. Producer có thể gửi bản sao của cùng event hoặc một luồng trung gian republish message mới. Phải dùng ID nghiệp vụ và cơ chế idempotency.

**Câu 3.** `consumerTag` có giống `messageId` không?

Không. Consumer tag định danh **đăng ký consumer**, còn message ID là một property thường do ứng dụng gắn để nhận diện message.

**Câu 4.** Trong chế độ `MANUAL`, quên ACK khiến message ở trạng thái gì?

Nó có thể tồn tại ở trạng thái **Unacked** trong khi connection/channel và delivery còn hiệu lực; khi channel/connection đóng, broker có thể đưa message chưa ACK trở lại queue để giao lại.

**Câu 5.** Tại sao `basicAck(tag, true)` nguy hiểm nếu nhiều công việc đang xử lý trên cùng channel?

Vì `multiple=true` có thể ACK **tất cả delivery chưa ACK đến tag đó** trên channel, gồm những công việc còn đang xử lý.

**Câu 6.** Consumer gặp message lỗi cố định; có nên liên tục `basicNack(tag, false, true)` không?

Không. Requeue vô hạn có thể gây vòng lặp nóng. Nên dùng retry có giới hạn, backoff và DLQ hoặc một chiến lược xử lý lỗi khác phù hợp.

## 13. Ghi nhớ

- **`deliveryTag`** là định danh **của lần giao trên channel**; dùng ACK/NACK/reject **đúng tag và đúng channel**. Nó không phải message ID hoặc event ID.
- **`redelivered`** chỉ gợi ý broker đang **giao lại**; không nói message đã xử lý thành công hay số lần retry, và không thay thế idempotency.
- **`consumerTag`** định danh **consumer subscription**, có thể đổi khi reconnect/restart; hữu ích cho log và quan sát hơn là làm khóa nghiệp vụ.
- Với **`@RabbitListener`**, phân biệt `AUTO` của container với `MANUAL`. Một delivery cần được xác nhận một cách nhất quán; retry/requeue, dead-letter và lưu trữ bền vững phải được thiết kế cùng nhau.
- Hệ thống đáng tin cậy vẫn cần **publisher confirms/returns, kiểm soát giao dịch, idempotency, retry có giới hạn và giám sát queue/channel**, bên cạnh thông tin của từng lần giao message.
