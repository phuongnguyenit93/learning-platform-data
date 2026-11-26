# Tham số payload, Message, Channel, @Header và @Headers

Trong **Spring AMQP**, cách đơn giản nhất để nhận thông điệp từ RabbitMQ là khai báo phương thức có **@RabbitListener**. Phương thức này không bắt buộc chỉ nhận một **String** hoặc DTO; Spring có thể cung cấp thêm **Message** gốc, **MessageProperties**, **Channel**, một header riêng bằng **@Header** hoặc tập header bằng **@Headers**. Việc chọn đúng tham số giúp mã nghiệp vụ gọn, đồng thời giữ khả năng kiểm soát routing, ACK/NACK, retry và thông tin quan sát.

Bài học nằm trong chương **Listener khai báo** của module **SPRING_AMQP**, nơi sử dụng **RabbitTemplate**, **@RabbitListener**, exchange, queue và binding để xây dựng xử lý bất đồng bộ đáng tin cậy. Chủ đề trọng tâm là **chữ ký phương thức listener**: một message được biến đổi thành những đối số Java nào, tại sao có hai lớp cùng tên `Message`, và khi nào nên chạm tới RabbitMQ `Channel`.

Sau bài này, bạn có thể:

1. Chọn giữa **@Payload** và tham số payload không chú thích.
2. Phân biệt **org.springframework.amqp.core.Message** với **org.springframework.messaging.Message<T>**.
3. Đọc **MessageProperties**, **@Header** và **@Headers** đúng với header tùy chỉnh và metadata do broker cung cấp.
4. Dùng **com.rabbitmq.client.Channel** cùng delivery tag để ACK/NACK đúng chế độ.
5. Thiết kế listener có kiểm tra dữ liệu, idempotency, retry, dead-letter và logs an toàn.

## 1. Từ một delivery của RabbitMQ tới tham số Java

Khi message đã được exchange định tuyến vào queue, listener container đăng ký consumer trên queue, nhận delivery và chuyển nó tới phương thức **@RabbitListener** qua listener adapter:

~~~mermaid
flowchart LR
    P["RabbitTemplate<br/>publish"] --> E{"Exchange"}
    E --> Q[("Queue")]
    Q --> C["Listener container<br/>nhận delivery"]
    C --> M["AMQP Message<br/>body + MessageProperties"]
    M --> V["Message conversion<br/>argument resolution"]
    V --> L["@RabbitListener<br/>payload / Message / Channel / headers"]
    L --> A["ACK / NACK theo<br/>acknowledge mode"]
~~~

Mỗi phương thức có thể chọn những đối số được framework hỗ trợ, thay vì tự đọc mọi trường từ byte array.

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BasicOrderListener {

    @RabbitListener(queues = "lab.orders.created")
    public void onOrder(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Với chữ ký này, **String** là tham số payload. Dù không có **@Payload**, framework vẫn hiểu một tham số hợp lệ không phải kiểu đặc biệt là payload và áp dụng **MessageConverter** tương ứng.

### Bảng đối chiếu các loại tham số

| Tham số trong method | Nhận được gì? | Dùng khi |
| --- | --- | --- |
| `String payload`, `OrderCreated payload` | Body đã chuyển đổi sang kiểu Java phù hợp | Nghiệp vụ chỉ cần dữ liệu |
| `@Payload String payload` | Payload được chỉ định tường minh | Muốn rõ ý định, kết hợp validation |
| `org.springframework.amqp.core.Message` | **AMQP Message gốc**: bytes + MessageProperties | Cần raw body/metadata giao nhận |
| `org.springframework.amqp.core.MessageProperties` | Thuộc tính từ AMQP Message gốc | Cần thuộc tính message mà không cần toàn bộ raw body |
| `org.springframework.messaging.Message<T>` | Spring Messaging Message: payload đã convert + headers | Muốn dùng abstraction độc lập tương đối với transport |
| `com.rabbitmq.client.Channel` | Channel của delivery đang xử lý | Manual ACK/NACK hoặc thao tác AMQP có kiểm soát |
| `@Header("tenant-id") String tenant` | Giá trị của **một** header | Chỉ cần một metadata cụ thể |
| `@Headers Map<String,Object> headers` | Các headers mà Spring đã ánh xạ | Cần xem nhiều trường để quan sát/xử lý |

Các tham số raw `Message`, `MessageProperties`, Spring Messaging `Message<?>` và `Channel` được xử lý đặc biệt. Tham số payload nên có **kiểu xác định**, nhất là khi dùng nhiều handler hoặc cần JSON converter.

## 2. @Payload: tập trung vào dữ liệu nghiệp vụ

**@Payload** là annotation của Spring Messaging:

~~~java
import org.springframework.messaging.handler.annotation.Payload;
~~~

Ví dụ nhận một thông điệp text:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(queues = "lab.orders.created")
public void onOrder(@Payload String payload) {
    System.out.println(payload);
}
~~~

Với listener đơn giản, hai cách `onOrder(String payload)` và `onOrder(@Payload String payload)` thường tương đương. Gắn annotation giúp phương thức rõ ràng khi có nhiều tham số như `Channel`, `@Header` hoặc `@Headers`.

### MessageConverter quyết định kiểu payload

Khi delivery đến, Spring AMQP thường trải qua hai bước khái niệm:

1. **Spring AMQP MessageConverter** chuyển raw AMQP Message sang payload trong Spring Messaging Message.
2. **Argument converter / resolver** chuyển payload sang kiểu tham số của phương thức nếu cần.

`SimpleMessageConverter` mặc định có thể giải mã **String** khi content type phù hợp, xử lý Java-serialized content ở một số trường hợp và giữ **byte[]** với các body khác. Nó **không tự động hiểu một JSON object bất kỳ thành DTO của bạn**. Nếu muốn `OrderCreated` nhận JSON, cần cấu hình JSON MessageConverter tương thích phiên bản Spring AMQP.

Ví dụ DTO:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long totalMinor,
        String currency
) {}
~~~

Với Spring AMQP 3.x, một cách cấu hình JSON converter cho `@RabbitListener`:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JsonListenerConversionConfig {

    @Bean
    Jackson2JsonMessageConverter orderJsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(
    queues = "lab.orders.json",
    messageConverter = "orderJsonMessageConverter"
)
public void onOrderJson(@Payload OrderCreated event) {
    System.out.println("orderId=" + event.orderId());
}
~~~

Ví dụ trên **giả định queue lab.orders.json đã tồn tại**, publisher gửi JSON hợp lệ với `contentType=application/json`, và phiên bản Spring AMQP hỗ trợ `Jackson2JsonMessageConverter`. Ở các bản mới hơn có thể dùng một lớp Jackson converter tên khác; cần đối chiếu API đúng phiên bản và cấu hình Jackson tương ứng. Không dùng **Java serialization** của payload không tin cậy làm giải pháp thay JSON.

### @Valid áp dụng ở đâu?

Có thể kết hợp validation:

~~~java
@RabbitListener(
    queues = "lab.orders.json",
    messageConverter = "orderJsonMessageConverter"
)
public void onOrderJson(@Payload @jakarta.validation.Valid OrderCreated event) {
    // Xử lý nếu payload đã được convert và validation thành công.
}
~~~

Để **@Valid** phát huy tác dụng, cần validator và tích hợp validation cho handler factory tương ứng, cùng dependency như `spring-boot-starter-validation` khi dùng Spring Boot 3.x. Không nên cho rằng chỉ thêm annotation sẽ tự bảo đảm mọi schema JSON được kiểm tra. Lỗi parse/validation xảy ra trước khi mã nghiệp vụ chạy; hãy cấu hình error handler và dead-letter hợp lý để tránh poison message bị requeue vô hạn.

## 3. Hai lớp Message cùng tên nhưng khác mục đích

Đây là điểm rất dễ import nhầm:

| Lớp | Nội dung | Đặc trưng |
| --- | --- | --- |
| `org.springframework.amqp.core.Message` | Raw **byte[]** cùng `MessageProperties` | Gắn trực tiếp với biểu diễn AMQP, hữu ích khi debug/routing/ACK |
| `org.springframework.messaging.Message<T>` | `T getPayload()` và `MessageHeaders getHeaders()` | Abstraction Spring Messaging, thuận tiện cho code dùng payload và metadata đã ánh xạ |

Vì cùng tên `Message`, các ví dụ ở đây sẽ dùng **fully qualified name** khi hai kiểu xuất hiện cùng lúc.

### 3.1. Raw AMQP Message

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(queues = "lab.orders.created")
public void inspectRaw(org.springframework.amqp.core.Message raw) {
    byte[] body = raw.getBody();
    var props = raw.getMessageProperties();

    System.out.println("body=" +
            new String(body, StandardCharsets.UTF_8));
    System.out.println("messageId=" + props.getMessageId());
    System.out.println("exchange=" + props.getReceivedExchange());
    System.out.println("routingKey=" + props.getReceivedRoutingKey());
    System.out.println("consumerQueue=" + props.getConsumerQueue());
    System.out.println("redelivered=" + props.isRedelivered());
}
~~~

Ưu điểm: bạn nhìn thấy **body bytes nguyên bản** và **MessageProperties** của delivery. Nhược điểm: handler tự chịu trách nhiệm decode bytes và phân tích định dạng. **Không** dùng `new String(body, UTF_8)` khi body là bytes nén hoặc JSON có encoding khác mà chưa giải mã/giải nén phù hợp.

### 3.2. Spring Messaging Message<T>

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.Message;

@RabbitListener(queues = "lab.orders.created")
public void inspectConverted(Message<String> springMessage) {
    String payload = springMessage.getPayload();
    Object routingKey = springMessage.getHeaders()
            .get(AmqpHeaders.RECEIVED_ROUTING_KEY);

    System.out.printf("payload=%s routingKey=%s%n",
            payload, routingKey);
}
~~~

Ở đây generic `Message<String>` biểu thị payload đã chuyển sang String. Nếu converter trả về bytes hoặc kiểu khác mà không convert được, listener có thể ném lỗi chuyển đổi; không nên viết `Message<String>` với giả định mọi content type đều là text.

### 3.3. Nhận MessageProperties trực tiếp

~~~java
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(queues = "lab.orders.created")
public void propertiesOnly(MessageProperties properties) {
    System.out.printf(
            "id=%s key=%s queue=%s%n",
            properties.getMessageId(),
            properties.getReceivedRoutingKey(),
            properties.getConsumerQueue()
    );
}
~~~

Bạn không cần nhận toàn bộ raw Message nếu chỉ quan tâm đến các properties. Tuy vậy, khi payload là dữ liệu chính, dùng **@Payload** hoặc Message với generic cho rõ ý định.

## 4. @Header: lấy đúng một thông tin

**@Header** nằm trong package `org.springframework.messaging.handler.annotation`, không phải annotation riêng của RabbitMQ.

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(queues = "lab.orders.created")
public void handle(
        @Payload String body,
        @Header("tenant-id") String tenantId,
        @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String routingKey) {

    System.out.printf("tenant=%s routingKey=%s body=%s%n",
            tenantId, routingKey, body);
}
~~~

Nếu publisher gửi message có header tùy chỉnh **tenant-id**, Spring ánh xạ giá trị này vào headers của message đưa cho listener. Cùng lúc, `AmqpHeaders.RECEIVED_ROUTING_KEY` là một **metadata nhận** được Spring ánh xạ từ AMQP delivery, không phải header custom do publisher nhất thiết phải đặt.

### Thiếu @Header thì sao?

Mặc định `@Header` có `required=true`. Nếu broker message không có header bắt buộc, bước resolve tham số có thể thất bại **trước khi handler được gọi**. Để header có thể thiếu:

~~~java
import org.springframework.messaging.handler.annotation.Header;

public void onOrder(
        @Header(name = "trace-id", required = false) String traceId) {
    // traceId có thể null khi publisher không gửi.
}
~~~

Đây là **mảnh chữ ký phương thức**; đặt trong phương thức được gắn `@RabbitListener` của ví dụ thực tế. Nên chọn kiểu reference như `String` hoặc `Long` cho header tùy chọn, tránh unboxing `null` vào primitive `long`/`boolean`.

**Dữ liệu header cần được validate.** RabbitMQ không bảo đảm custom header `tenant-id` có đúng định dạng, đúng kiểu Java hoặc được gửi từ bên đáng tin cậy. Không dùng một header do publisher tùy ý đặt làm bằng chứng cấp quyền; cần xác thực/ủy quyền theo kiến trúc bảo mật ứng dụng.

### Các header chuẩn hữu ích

Spring AMQP cung cấp `org.springframework.amqp.support.AmqpHeaders`, giúp tránh hardcode chuỗi `amqp_...`:

| Constant | Ý nghĩa khi nhận | Mục đích |
| --- | --- | --- |
| `AmqpHeaders.MESSAGE_ID` | `messageId` từ MessageProperties nếu có | Trace hoặc tham chiếu eventId theo hợp đồng |
| `AmqpHeaders.CORRELATION_ID` | Tương quan message nếu publisher đặt | Truy vết workflow/request |
| `AmqpHeaders.RECEIVED_EXCHANGE` | Exchange mà delivery đến qua routing | Debug topology |
| `AmqpHeaders.RECEIVED_ROUTING_KEY` | Routing key nhận được | Debug routing và dispatch |
| `AmqpHeaders.CONSUMER_QUEUE` | Queue consumer đang nhận | Quan sát nhiều queue |
| `AmqpHeaders.CONSUMER_TAG` | Tag của consumer subscription | Quan sát consumer |
| `AmqpHeaders.DELIVERY_TAG` | Delivery tag trong channel | Manual ACK/NACK đúng delivery |
| `AmqpHeaders.REDELIVERED` | Cờ broker cho biết redelivery | Chẩn đoán, không thay thế dedupe |
| `AmqpHeaders.CONTENT_TYPE` | Content type theo MessageProperties | Chọn/kiểm tra converter phù hợp |

Các field như `CONSUMER_QUEUE`, `RECEIVED_ROUTING_KEY` và `DELIVERY_TAG` là **metadata của lần nhận**. Chúng không nên được hiểu như header ứng dụng đã phát từ publisher và có thể thay đổi theo queue/consumer/redelivery.

## 5. @Headers: nhận cả map header

Nếu handler cần nhiều metadata, dùng **@Headers** trên một tham số gán được cho `java.util.Map`:

~~~java
import java.util.Map;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(queues = "lab.orders.created")
public void inspectHeaders(
        @Payload String payload,
        @Headers Map<String, Object> headers) {

    Object tenantId = headers.get("tenant-id");
    Object routingKey = headers.get("amqp_receivedRoutingKey");

    System.out.printf("tenant=%s key=%s payload=%s%n",
            tenantId, routingKey, payload);
}
~~~

Tốt hơn nữa, thay tên chuẩn hardcode bằng `AmqpHeaders.RECEIVED_ROUTING_KEY` khi sử dụng trong mã. Map này chứa **headers được ánh xạ** sang Spring Messaging, bao gồm cả custom headers và một số metadata AMQP; không nên cho rằng mọi thuộc tính raw của RabbitMQ đều luôn có mặt như một entry tương ứng.

### @Header hay @Headers?

| Tiêu chí | @Header | @Headers |
| --- | --- | --- |
| Số giá trị lấy | Một | Nhiều |
| Kiểu tham số | Kiểu cần chuyển đổi, ví dụ String/Long | Kiểu tương thích `Map` |
| Header bắt buộc | Có thể `required=true/false` | Tự kiểm tra `containsKey`, kiểu và giá trị |
| Tính rõ ràng | Rất tốt khi cần vài trường đã biết | Tốt cho quan sát hoặc xử lý metadata động |
| Rủi ro | Missing header/conversion error | Ép kiểu sai, log lộ dữ liệu, thiếu contract |

Nếu chỉ cần `tenant-id` và routing key, dùng **hai @Header** làm hợp đồng rõ hơn. Dùng **@Headers** khi xử lý một tập metadata biến đổi hoặc viết diagnostics. Tránh log trọn map ở production vì có thể chứa thông tin nhạy cảm hoặc dữ liệu người dùng.

## 6. Channel: khi nào thực sự cần truy cập?

`com.rabbitmq.client.Channel` đại diện cho **channel AMQP thực tế đang nhận delivery**. Spring có thể inject nó vào method `@RabbitListener`:

~~~java
import com.rabbitmq.client.Channel;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(queues = "lab.orders.created")
public void inspectChannel(@Payload String body, Channel channel) {
    System.out.printf("channel=%d body=%s%n",
            channel.getChannelNumber(), body);
}
~~~

Những trường hợp hợp lý để nhận Channel:

- Cần **ACK/NACK thủ công** bằng `basicAck`, `basicNack` hoặc `basicReject`.
- Cần truy cập một thuộc tính đặc thù của AMQP channel trong phạm vi delivery hiện tại.
- Tích hợp với thư viện chuyên biệt yêu cầu RabbitMQ Java client Channel và đã quản lý vòng đời/thao tác an toàn.

**Không cần Channel** nếu listener chỉ parse payload và lưu dữ liệu, khi container đang ở **AUTO acknowledge mode**. Đưa Channel vào mọi method làm code gắn chặt với RabbitMQ hơn mà thường không mang lại lợi ích.

### Channel không phải connection

~~~text
RabbitMQ Connection (TCP)
    |
    +-- Channel 1: consumer của orders.queue
    +-- Channel 2: publisher RabbitTemplate
    +-- Channel 3: consumer khác
~~~

Delivery tag và thao tác ACK/NACK thuộc **channel được cấp cho consumer**. Không lấy delivery tag của channel này rồi ACK trên channel khác, cũng không lưu Channel trong singleton để dùng lại tùy tiện ở thread khác. Một Channel được container quản lý; ứng dụng không nên tự đóng nó sau khi xử lý một message.

## 7. Manual ACK: kết hợp Channel với @Header(AmqpHeaders.DELIVERY_TAG)

Đây là trường hợp phổ biến nhất cần cả `Channel` và `@Header`. Broker cấp **delivery tag** cho mỗi delivery trên channel; Spring ánh xạ nó vào header `AmqpHeaders.DELIVERY_TAG`.

### 7.1. Ba acknowledge mode phải phân biệt

| Chế độ container | Ai xác nhận message? | Có nên gọi Channel.basicAck trong listener? |
| --- | --- | --- |
| **AUTO** | Spring listener container ACK sau khi handler trả về thành công; xử lý lỗi theo cấu hình | **Không**; có thể gây ACK trùng và đóng channel |
| **MANUAL** | Mã listener phải ACK/NACK/REJECT phù hợp | **Có**, với delivery tag của message vừa nhận |
| **NONE** | Broker xem delivery đã được xác nhận khi gửi (*auto-ack/no-ack*) | **Không**; không còn manual ack để gửi |

Trong Spring Boot, `acknowledge-mode: auto` là chế độ container tự quản lý ACK **sau khi listener thành công**. Đây **không phải** `basic.consume(autoAck=true)` của RabbitMQ; `NONE` mới tương ứng không yêu cầu ACK.

### 7.2. Bật MANUAL ở listener container

Nếu toàn bộ simple listeners của ứng dụng sử dụng manual ACK:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 1
        concurrency: 1
~~~

Nếu chỉ **một listener** cần MANUAL, hãy tạo factory chuyên dụng thay vì bật manual cho tất cả listener:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManualListenerFactoryConfig {

    @Bean("manualAckFactory")
    SimpleRabbitListenerContainerFactory manualAckFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        configurer.configure(factory, connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setPrefetchCount(1);
        return factory;
    }
}
~~~

Ví dụ này dành cho **Spring Boot 3.x**; package/configurer có thể khác giữa các thế hệ Boot. `configurer.configure(...)` giúp giữ các thiết lập container được Boot quản lý trước khi đổi acknowledge mode riêng cho factory này.

### 7.3. Listener thực hiện ACK hoặc REJECT

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderListener {

    @RabbitListener(
        queues = "lab.orders.manual",
        containerFactory = "manualAckFactory"
    )
    public void process(
            @Payload String payload,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
            throws IOException {

        if (!payload.startsWith("order.created:")) {
            // Không thể xử lý payload này bằng contract hiện tại.
            channel.basicReject(deliveryTag, false);
            return;
        }

        try {
            // Minh họa; thay bằng logic nghiệp vụ có idempotency.
            System.out.println("Processed " + payload);

            // ACK đúng một delivery sau khi xử lý thành công.
            channel.basicAck(deliveryTag, false);
        } catch (RuntimeException ex) {
            // false: không requeue. Có DLX phù hợp mới vào DLQ.
            channel.basicNack(deliveryTag, false, false);
        }
    }
}
~~~

**Lưu ý:** Queue `lab.orders.manual` ở ví dụ này phải tồn tại và được bind phù hợp. Nó tách khỏi queue `lab.orders.created` để người học không vô tình chạy hai kiểu acknowledge mode trên cùng queue.

Ý nghĩa API:

| Lệnh | Ý nghĩa |
| --- | --- |
| `channel.basicAck(tag, false)` | Xác nhận **chính delivery có tag đó** |
| `channel.basicNack(tag, false, true)` | Từ chối và đề nghị **requeue** |
| `channel.basicNack(tag, false, false)` | Từ chối **không requeue**; có thể dead-letter nếu queue cấu hình DLX |
| `channel.basicReject(tag, false)` | Reject một delivery không requeue |
| `multiple=true` ở basicAck/basicNack | Áp dụng lên các delivery tag phù hợp **tới tag đó trên cùng channel**, có thể ảnh hưởng message khác |

Trong listener xử lý từng message, thường dùng **multiple=false**. Nếu `multiple=true` mà channel đang giữ nhiều delivery chưa ACK, bạn có thể xác nhận nhầm message vẫn đang xử lý.

**Quan trọng về mã minh họa:** `System.out.println` không phải side effect nghiệp vụ cần transaction. Với database, service nên commit transaction/idempotency trước khi ACK. Nếu publish tiếp một event, cần đánh giá outbox hoặc giao dịch phù hợp; manual ACK một mình không bảo đảm DB và RabbitMQ có exactly-once transaction chung.

### Những lỗi dễ gây mất message hoặc đóng channel

- **Gọi ACK trong AUTO mode:** container cũng ACK, có nguy cơ double-ack; broker có thể đóng channel vì unknown delivery tag.
- **MANUAL nhưng quên ACK/NACK:** message nằm **Unacked**, prefetch bị chiếm và throughput giảm hoặc dừng.
- **Gọi ACK hai lần cho cùng tag:** không hợp lệ; broker có thể trả `PRECONDITION_FAILED - unknown delivery tag`.
- **Lưu deliveryTag làm định danh sự kiện:** tag chỉ có ý nghĩa với một channel, không ổn định qua redelivery.
- **REJECT requeue=false nhưng không có DLX:** message có thể bị loại, **không tự tạo DLQ**.
- **NACK requeue=true mọi lỗi:** poison message có thể lặp vô hạn; cần retry có giới hạn và dead-letter policy.
- **Truyền Channel tới thread khác để ACK sau:** cần cơ chế quản lý async acknowledgement đúng chuẩn thay vì sử dụng Channel tùy tiện ngoài vòng đời container.

Nếu phương thức dùng MANUAL và đã **basicNack** một delivery, không nên tiếp tục ném cùng lỗi để khiến container/error handler xử lý lại chính delivery đó theo cách khó dự đoán. Tránh nhánh xử lý nào đó vừa ACK rồi lại NACK khi có exception phát sinh sau ACK.

## 8. Kết hợp payload, MessageProperties, @Header, @Headers và Channel

Spring AMQP cho phép listener có nhiều tham số hỗ trợ trong cùng chữ ký:

~~~java
import com.rabbitmq.client.Channel;
import java.util.Map;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(queues = "lab.orders.created")
public void auditDelivery(
        @Payload String payload,
        MessageProperties properties,
        Channel channel,
        @Header("tenant-id") String tenantId,
        @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String routingKey,
        @Headers Map<String, Object> headers) {

    System.out.printf(
            "tenant=%s key=%s id=%s channel=%d body=%s headerCount=%d%n",
            tenantId,
            routingKey,
            properties.getMessageId(),
            channel.getChannelNumber(),
            payload,
            headers.size()
    );

    // Chế độ AUTO: không tự gọi basicAck/basicNack ở đây.
}
~~~

Đây là **ví dụ chữ ký**, không phải khuyến nghị bắt mọi listener nhận đủ sáu tham số. Handler nghiệp vụ tốt thường chỉ yêu cầu dữ liệu thực sự dùng, chẳng hạn `@Payload OrderCreated` và `@Header("tenant-id")`. Khi cần debug routing hoặc manual ACK mới thêm raw Message/MessageProperties/Channel.

**Lưu ý thực hành:** các ví dụ @RabbitListener trong các mục trước là **những cách triển khai thay thế**, không phải tất cả được bật cùng lúc. Nếu bạn khai báo nhiều listener trên **cùng queue**, RabbitMQ sẽ phân phối message cho các consumer cạnh tranh; mỗi listener không mặc nhiên nhận một bản sao. Muốn tất cả nhóm chức năng cùng nhận sự kiện, hãy dùng **queue riêng** và exchange/binding phù hợp.

## 9. Ví dụ chạy được: publisher đặt header, listener nhận các tham số

Ví dụ này dùng **Spring Boot 3.x**, Java 17, RabbitMQ AMQP 0-9-1 và **spring-boot-starter-amqp**. Để tránh phụ thuộc JSON converter, payload là `String`; sau khi hiểu parameter resolution, bạn có thể đổi sang DTO với cấu hình JSON ở phần 2.

### 9.1. Dependency và kết nối

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

`application.yml` cho một RabbitMQ local có tài khoản lab tương ứng:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 1
        max-concurrency: 1
        prefetch: 5
~~~

Credentials trên chỉ mang tính minh họa; cần thay bằng user thật của broker. Trong production, cung cấp thông tin đăng nhập qua biến môi trường hoặc secret manager, không commit mật khẩu vào source control.

### 9.2. Exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class DemoTopology {
    public static final String EXCHANGE = "lab.orders.exchange";
    public static final String QUEUE = "lab.orders.created";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange demoExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue demoQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding demoBinding(Queue demoQueue, DirectExchange demoExchange) {
        return BindingBuilder.bind(demoQueue)
                .to(demoExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Với `RabbitAdmin` hoạt động và đủ quyền khai báo, Spring AMQP có thể tạo những tài nguyên này khi connection được mở. **Tạo bean không tự đảm bảo queue đã có** nếu broker chưa kết nối hoặc auto-declare bị tắt. Kiểm tra exchange/queue/binding trong RabbitMQ Management.

### 9.3. Publisher tạo payload và header

~~~java
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class DemoOrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public DemoOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendOrderCreated(String orderId, String tenantId) {
        String eventId = UUID.randomUUID().toString();
        String body = "order.created:" + orderId;

        rabbitTemplate.convertAndSend(
                DemoTopology.EXCHANGE,
                DemoTopology.ROUTING_KEY,
                body,
                message -> {
                    var p = message.getMessageProperties();
                    p.setMessageId(eventId);
                    p.setCorrelationId("checkout-123");
                    p.setType("order.created");
                    p.setHeader("tenant-id", tenantId);
                    p.setHeader("schema-version", 1);
                    return message;
                }
        );
    }
}
~~~

Ví dụ tạo eventId khi **tạo sự kiện mới**. Nếu hệ thống có publisher retry của cùng một sự kiện, phải tạo và lưu eventId **trước lần gửi đầu tiên**, rồi tái sử dụng nó; không gọi lại phương thức tạo event mới để gửi lại vì như thế mỗi attempt nhận UUID khác.

### 9.4. Listener đọc body và metadata

~~~java
import java.util.Map;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class DemoOrderListener {

    @RabbitListener(queues = DemoTopology.QUEUE)
    public void handle(
            @Payload String body,
            @Header("tenant-id") String tenantId,
            @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String routingKey,
            @Header(name = "trace-id", required = false) String traceId,
            @Headers Map<String, Object> headers,
            MessageProperties properties) {

        System.out.printf(
                "messageId=%s tenant=%s routingKey=%s body=%s " +
                "traceId=%s headerCount=%d%n",
                properties.getMessageId(),
                tenantId,
                routingKey,
                body,
                traceId,
                headers.size()
        );
    }
}
~~~

Trong ví dụ này:

- `body` được convert thành String theo content type do RabbitTemplate gửi.
- `tenant-id` là **custom header** có giá trị được publisher đặt.
- `RECEIVED_ROUTING_KEY` là metadata của delivery.
- `trace-id` được đánh dấu **required=false**, nên có thể là null vì publisher ví dụ không đặt nó.
- `headers` là tập thông tin đã được ánh xạ, còn `properties` là các thuộc tính raw.
- Với **AUTO ACK**, container sẽ ACK khi handler hoàn thành thành công. Không cần `Channel` nếu chỉ muốn log những trường này.

Để phát một message khi khởi động lab, thêm bean:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class DemoSenderConfig {

    @Bean
    ApplicationRunner sendDemo(DemoOrderPublisher publisher) {
        return args -> publisher.sendOrderCreated("O-1001", "store-a");
    }
}
~~~

Sau khi chạy ứng dụng, log có thể tương tự:

~~~text
messageId=7b77... tenant=store-a routingKey=order.created
body=order.created:O-1001 traceId=null headerCount=...
~~~

Đừng giả định giá trị **headerCount** cố định vì framework có thể ánh xạ thêm những metadata khác. Nếu muốn quan sát body/header trong RabbitMQ Management, dừng consumer trước khi publish; message có thể được xử lý/ACK rất nhanh khiến queue Ready về 0.

## 10. Metadata của producer và metadata của delivery khác nhau

Khi publisher dùng **RabbitTemplate**:

~~~java
rabbitTemplate.convertAndSend(
        "lab.orders.exchange",
        "order.created",
        "order.created:O-1001",
        message -> {
            message.getMessageProperties()
                    .setHeader("tenant-id", "store-a");
            message.getMessageProperties()
                    .setMessageId("evt-order-1001-created");
            return message;
        }
);
~~~

Consumer có thể nhận cả header **tenant-id**, **messageId** và metadata nhận như **consumerQueue** hoặc **receivedRoutingKey**. Nhưng nguồn gốc của chúng khác nhau:

~~~mermaid
flowchart TD
    P["Publisher"] --> H["Custom headers, messageId,<br/>correlationId, contentType"]
    H --> E["Exchange định tuyến"]
    E --> Q[("Queue")]
    Q --> D["Delivery metadata:<br/>deliveryTag, receivedRoutingKey,<br/>consumerQueue, redelivered"]
    D --> R["@RabbitListener<br/>@Header / @Headers / MessageProperties"]
~~~

| Trường | Ai quyết định? | Có thể thay đổi giữa các lần giao? |
| --- | --- | --- |
| **tenant-id** custom | Publisher/ứng dụng | Giữ nguyên nếu message không bị thay đổi khi republish |
| **messageId** | Thường do publisher đặt | Giữ nguyên nếu ứng dụng tuân thủ quy ước ID ổn định |
| **receivedRoutingKey** | Giao thức/broker chuyển vào delivery; Spring ánh xạ | Có thể khác nếu message được republish với key khác |
| **consumerQueue** | Container/queue nhận | Có thể khác giữa các queue nhận cùng sự kiện |
| **deliveryTag** | Broker cấp theo channel | **Có**; không phải ID của message logic |
| **redelivered** | Broker đánh dấu | Có thể đổi khi message bị giao lại |

**Kết quả thiết kế:** dùng eventId hoặc một ID nghiệp vụ ổn định làm khóa chống trùng; không lấy delivery tag, queue name hoặc consumer tag làm danh tính sự kiện. Header custom có thể hữu ích để định tuyến nghiệp vụ trong consumer, nhưng phải validate dữ liệu và kiểm soát quyền gửi.

## 11. Khi listener có nhiều loại payload và nhiều handler

Spring AMQP hỗ trợ class-level **@RabbitListener** kết hợp nhiều **@RabbitHandler** để dispatch dựa trên kiểu payload sau conversion:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
@RabbitListener(queues = "lab.orders.mixed")
public class OrderEventHandlers {

    @RabbitHandler
    public void created(
            @Payload OrderCreated event,
            @Header("tenant-id") String tenantId) {
        System.out.println("Created order for " + tenantId);
    }

    @RabbitHandler(isDefault = true)
    public void unexpected(Object payload) {
        System.out.println("Unhandled payload type: " + payload.getClass());
    }
}
~~~

Đây là ví dụ bổ sung: giả định queue **lab.orders.mixed** đã tồn tại và có JSON converter ánh xạ payload tới đúng DTO **OrderCreated**. Nếu converter chỉ trả **byte[]** hoặc **String**, handler cho OrderCreated có thể không được chọn. Dispatch trong **@RabbitHandler** dựa trên **kiểu payload sau conversion**, không chỉ dựa vào tên `eventType` hay routing key.

Khi cần truy cập trực tiếp raw **org.springframework.amqp.core.Message** làm nội dung xử lý chính, hãy dùng **@RabbitListener trên phương thức** thay vì trông đợi chọn handler theo raw message trong mô hình multi-method. Tránh để nhiều handler nhận kiểu payload mơ hồ gây lỗi chọn method.

## 12. Lỗi parse, missing header và exception đi về đâu?

Không phải mọi lỗi đều xảy ra bên trong phần thân phương thức listener.

~~~mermaid
flowchart TD
    A["Delivery từ RabbitMQ"] --> B{"MessageConverter<br/>parse được?"}
    B -->|"Không"| ERR["Conversion error"]
    B -->|"Có"| H{"Đủ @Header bắt buộc?<br/>Payload hợp lệ?"}
    H -->|"Không"| ERR
    H -->|"Có"| L["Gọi business handler"]
    L -->|"Exception"| ERR2["Listener exception"]
    L -->|"Hoàn thành"| OK["Container ACK nếu AUTO"]
    ERR --> POLICY["Container error handling<br/>requeue/reject/retry/DLQ"]
    ERR2 --> POLICY
~~~

Một số tình huống tiêu biểu:

| Hiện tượng | Lỗi xảy ra tại đâu? | Điều cần xem |
| --- | --- | --- |
| **JSON không đúng cấu trúc** | Message conversion hoặc argument conversion | Converter, content type, schema, error handler |
| **@Header bắt buộc không có** | Argument resolution | `required=false` nếu tùy chọn, sửa producer contract |
| **Header type không thể convert** | Argument conversion | Kiểu producer gửi, `String` vs `Long`, validate |
| **Ném IllegalArgumentException trong handler** | Business logic | Retry có hợp lý không hay phải dead-letter |
| **MANUAL mà không ACK/NACK** | Logic điều khiển delivery | Kiểm tra Unacked và mọi nhánh xử lý |
| **ACK nhầm channel/tag** | RabbitMQ protocol | Có thể đóng channel vì unknown delivery tag |
| **Requeue vô hạn một poison message** | Error policy | Retry giới hạn, DLX/DLQ, giám sát |

### Chọn AUTO hay MANUAL?

**AUTO** thường là lựa chọn đơn giản và an toàn khi handler đồng bộ, thành công thì hoàn thành, lỗi thì ném exception để container áp dụng chính sách. Khi cần kiểm soát chi tiết thời điểm ACK/NACK, hoặc integration với side effect đặc thù, có thể chọn **MANUAL** nhưng phải chịu trách nhiệm về **mọi đường thoát của handler**.

Chế độ `AUTO` không đồng nghĩa **exactly once**. Sau khi DB commit nhưng trước khi broker nhận ACK, connection có thể mất và message được redeliver. Vì vậy vẫn cần **idempotency**, thường bằng `eventId`/messageId ổn định, khóa unique và transaction với trạng thái nghiệp vụ.

### DLQ không tự xuất hiện chỉ vì basicReject(false)

Nếu dùng:

~~~java
channel.basicReject(deliveryTag, false);
~~~

Broker **không requeue**. Message chỉ được **dead-letter** nếu queue/policy có cơ chế DLX phù hợp; nếu không, message có thể bị loại. Dưới đây là topology ví dụ cho một queue manual có DLQ:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ManualOrderDeadLetterTopology {

    @Bean
    DirectExchange demoDlx() {
        return new DirectExchange("lab.orders.dlx", true, false);
    }

    @Bean
    Queue manualOrdersQueue() {
        return QueueBuilder.durable("lab.orders.manual")
                .deadLetterExchange("lab.orders.dlx")
                .deadLetterRoutingKey("order.failed")
                .build();
    }

    @Bean
    Queue manualOrderDlq() {
        return QueueBuilder.durable("lab.orders.manual.dlq").build();
    }

    @Bean
    Binding manualOrderDlqBinding(
            Queue manualOrderDlq, DirectExchange demoDlx) {
        return BindingBuilder.bind(manualOrderDlq)
                .to(demoDlx)
                .with("order.failed");
    }
}
~~~

Ví dụ này cho thấy queue **lab.orders.manual** có DLX. Để gửi message thực sự vào queue đó trong lab, có thể publish qua **default exchange** với routing key bằng tên queue, hoặc thêm binding từ một exchange nghiệp vụ khác. Khi message reject/nack với requeue=false và DLX hợp lệ, hãy kiểm tra DLQ bằng RabbitMQ Management; không giả định dead-letter chắc chắn thành công nếu cấu hình/đích bị lỗi.

Trong production, có thể cân nhắc thiết lập DLX qua policy thay vì hardcode arguments vì việc thay đổi argument của queue đang tồn tại có hạn chế; lựa chọn phụ thuộc cách quản lý topology của hệ thống.

## 13. Quan sát header và Channel an toàn

Với **RabbitMQ Management**, mở queue và kiểm tra số **Ready**, **Unacked**, số **Consumers** và tốc độ delivery/ack. Nếu consumer dùng manual ACK mà bỏ quên ACK, **Unacked** có thể tăng tới giới hạn prefetch.

Nếu RabbitMQ chạy trong Docker Compose service tên **rabbitmq**, dùng:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Khi phân tích lỗi, log các trường có giá trị truy vết:

~~~text
eventId=evt-1001 tenant=store-a
queue=lab.orders.created routingKey=order.created
redelivered=false outcome=PROCESSED
~~~

Những việc nên làm:

- Đặt **messageId/eventId** ổn định ở publisher, giữ nguyên khi retry cùng sự kiện.
- Log **consumerQueue, receivedRoutingKey, eventType, outcome**, không cần log toàn bộ body hoặc headers nhạy cảm.
- Khi dùng `@Headers`, không đưa tất cả giá trị header vào metric labels; giá trị tùy ý như eventId sẽ gây **cardinality cao**.
- Theo dõi lỗi conversion/missing header riêng với lỗi nghiệp vụ: một số lỗi xảy ra **trước khi handler được gọi**.
- Theo dõi publisher confirms/returns để biết message vào broker/routing; những tín hiệu đó **không thay thế consumer ACK**.
- Nếu dùng Channel để manual ACK, không truyền channel hoặc delivery tag cho một thread khác rồi tự ý thao tác sau khi listener đã kết thúc.

**Lưu ý bảo mật:** `tenant-id`, `user-id` hay `source-service` do producer tự đặt **không phải bằng chứng xác thực**. Dùng quyền trên RabbitMQ, TLS, xác thực ở lớp ứng dụng và các biện pháp chống giả mạo phù hợp. Không cấp quyền truy cập dữ liệu của tenant chỉ dựa vào một header không đáng tin.

## 14. Bài thực hành và kết quả mong đợi

Làm theo thứ tự để tránh những listener minh họa cạnh tranh nhau trên cùng queue:

1. Chạy RabbitMQ cục bộ, tạo tài khoản phù hợp và bật Management UI.
2. Chỉ bật **DemoOrderListener** của phần 9 cùng topology/publisher tương ứng; giữ các listener ví dụ khác ở trạng thái không đăng ký.
3. Publish `order.created:O-1001` với header **tenant-id=store-a**.
4. Kiểm tra log chứa **body**, **tenant**, **receivedRoutingKey=order.created**, **messageId** và giá trị `traceId=null`.
5. Thêm `trace-id` ở producer rồi publish sự kiện mới; kiểm tra optional header trở thành giá trị có thật.
6. Thử xóa `tenant-id` khi nó đang là `@Header` bắt buộc; quan sát lỗi resolve trước handler và policy container, sau đó khôi phục.
7. Chạy thử một listener raw `org.springframework.amqp.core.Message` **thay thế** demo listener để kiểm tra `body` bytes và `MessageProperties`.
8. Đặt cấu hình `manualAckFactory` cho **lab.orders.manual** và publish một message vào queue đó; theo dõi **Unacked** giảm sau `basicAck`.
9. Gửi payload lỗi vào queue manual; kiểm tra `basicReject(tag,false)` và queue **lab.orders.manual.dlq** nếu DLX được cấu hình đúng.
10. Mô phỏng lỗi handler và redelivery trong môi trường lab; xác nhận **deliveryTag có thể thay đổi** nhưng ID sự kiện logic không thay đổi.

### Checklist cho từng tham số

| Muốn kiểm chứng | Cách kiểm chứng |
| --- | --- |
| **@Payload String** | Log payload đã decode đúng nội dung |
| **Raw Message** | So sánh raw body bytes và MessageProperties với message gửi đi |
| **Spring Messaging Message<T>** | Dùng `getPayload()`, `getHeaders()` thay vì decode byte[] thủ công |
| **MessageProperties** | Đọc messageId, consumerQueue, receivedExchange/routingKey |
| **@Header** | Thử header bắt buộc, header tùy chọn và kiểu không phù hợp |
| **@Headers Map** | Quan sát custom headers và metadata đã ánh xạ, không giả định mọi property luôn hiện diện |
| **Channel** | Trong MANUAL, ACK/NACK đúng delivery tag, quan sát Unacked và DLQ |

## 15. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Không có @Payload thì Spring không biết body” | Một tham số payload phù hợp có thể được nhận diện **không cần @Payload** |
| “Message trong mọi ví dụ là cùng một class” | **org.springframework.amqp.core.Message** và **org.springframework.messaging.Message<T>** là hai kiểu khác nhau |
| “JSON luôn tự thành DTO” | Cần converter và hợp đồng kiểu dữ liệu phù hợp |
| “@Headers là raw MessageProperties” | Đây là **Map headers đã được ánh xạ**; MessageProperties là đối tượng khác |
| “Mọi header đều do publisher gửi” | **receivedRoutingKey, consumerQueue, deliveryTag** là metadata phía nhận |
| “Có @Header thì thiếu giá trị tự thành null” | Mặc định **required=true**; chỉ dùng `required=false` khi phù hợp |
| “Có Channel thì nên tự ACK” | Chỉ tự ACK/NACK khi container ở **MANUAL** |
| “basicAck(tag,true) chỉ ACK message hiện tại” | `multiple=true` có thể ACK **nhiều delivery** trước đó trên cùng channel |
| “Delivery tag là event ID” | Tag thuộc **channel/delivery**, thay đổi khi giao lại |
| “Reject không requeue sẽ tự có DLQ” | Cần queue được cấu hình DLX và route đích hợp lệ |
| “Hai @RabbitListener cùng queue đều nhận mọi message” | Chúng thường là **competing consumers**, chia delivery |
| “Handler không throw tức là exactly once” | ACK và side effect có thể bị gián đoạn; vẫn cần idempotency |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Trong `@RabbitListener`, sự khác nhau giữa `@Payload OrderCreated` và `org.springframework.amqp.core.Message` là gì?

**Câu 2.** Một method nhận `@Header("tenant-id") String tenantId`. Message không có header này. Vì sao method có thể chưa được gọi? Sửa thế nào nếu header không bắt buộc?

**Câu 3.** Muốn đọc tên queue, routing key và delivery tag, nên dùng **@Header** với constant nào? Có nhất thiết dùng Channel không?

**Câu 4.** Bạn có `@Headers Map<String,Object>`. Có nên coi mọi field trong map là header custom đáng tin do producer cung cấp không?

**Câu 5.** Vì sao manual ACK bằng `channel.basicAck(tag,false)` phải thực hiện trên channel gắn với delivery hiện tại?

**Câu 6.** Listener đặt `acknowledge-mode=auto` rồi gọi `channel.basicAck(tag,false)` bên trong. Rủi ro là gì?

**Câu 7.** Consumer NACK với `requeue=false`. Message có chắc chắn ở DLQ không? Điều kiện nào cần có?

**Câu 8.** Hai phương thức `@RabbitListener(queues="same.queue")` hoạt động cùng lúc; có chắc mỗi message được gọi vào cả hai method không?

**Đáp án gợi ý:**

1. **@Payload DTO** nhận dữ liệu nghiệp vụ **sau conversion**; raw AMQP **Message** cho body bytes và MessageProperties gốc.
2. **@Header** mặc định `required=true`; dùng `@Header(name="tenant-id", required=false)` trên kiểu có thể null và validate tùy hợp đồng.
3. **AmqpHeaders.CONSUMER_QUEUE**, **RECEIVED_ROUTING_KEY**, **DELIVERY_TAG**; không cần Channel nếu chỉ muốn đọc/log, nhưng cần Channel khi manual ACK/NACK.
4. **Không.** Map chứa cả header tùy chỉnh lẫn metadata Spring đã ánh xạ; cần validate và phân quyền độc lập.
5. Delivery tag chỉ có ý nghĩa **trên đúng channel**; ACK ở channel khác hoặc ACK hai lần có thể gây lỗi.
6. Container sẽ cố ACK thêm, có thể double ACK/unknown delivery tag và đóng channel.
7. **Không chắc.** Queue cần DLX và routing tới DLQ phù hợp; nếu không message có thể bị loại.
8. **Không.** Chúng là competing consumers trên một queue; muốn mỗi nghiệp vụ nhận một bản, dùng queue riêng có binding thích hợp.

## 17. Checklist trước khi đưa listener vào production

Một chữ ký listener tốt cần rõ trách nhiệm:

1. **Payload:** xác định kiểu dữ liệu và MessageConverter; validate schema và phiên bản.
2. **Message:** chỉ lấy raw AMQP Message khi cần body bytes/properties; tránh import nhầm Spring Messaging Message.
3. **@Header:** chỉ lấy các metadata cần thiết; khai báo optional chính xác và kiểm tra kiểu.
4. **@Headers:** không log nhạy cảm, không tin tưởng mọi giá trị và không sử dụng eventId làm metric label.
5. **Channel:** chỉ thao tác manual ACK khi cần; không giữ qua thread/channel khác hoặc ACK trùng.
6. **Delivery tag:** không dùng làm định danh sự kiện; ACK/NACK đúng tag, đúng chế độ container.
7. **Failure path:** phân loại lỗi parse, validation, business và I/O; có retry giới hạn, dead-letter và observability.
8. **Reliability:** sử dụng eventId ổn định, idempotency, transaction và publisher confirms/returns khi luồng nghiệp vụ yêu cầu.
9. **Topology:** bảo đảm exchange/queue/binding tồn tại; xác minh consumer kết nối đúng broker/vhost và queue.

**Kết luận:** `@RabbitListener` hỗ trợ linh hoạt từ **@Payload** đơn giản tới **raw AMQP Message**, **Spring Messaging Message**, **Channel**, **@Header** và **@Headers**. Hãy chọn **ít tham số nhất đáp ứng nghiệp vụ**, chỉ truy cập Channel khi cần quyền điều khiển giao nhận, và kết hợp converter, validation, ACK/NACK, retry/dead-letter cùng idempotency để tạo consumer Spring AMQP đáng tin cậy.

### Tài liệu tham khảo

- [Spring AMQP – Annotated Endpoint Method Signature](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable-signature.html)
- [Spring AMQP – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Spring AMQP – Message Conversion for Annotated Methods](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html)
- [Spring AMQP – Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring AMQP – AmqpHeaders API](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/support/AmqpHeaders.html)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
