# Nhận đồng bộ bằng RabbitTemplate.receive() trong Spring AMQP

Khi tích hợp RabbitMQ với Spring AMQP, phần lớn ứng dụng xử lý thông điệp liên tục bằng `@RabbitListener`. Tuy nhiên, một số tác vụ cần **chủ động lấy một message tại thời điểm xác định**: công cụ kiểm tra queue, lệnh quản trị, bước chạy theo lịch hoặc tác vụ xử lý ít dữ liệu. Trong các trường hợp ấy, `RabbitTemplate.receive()` và các overload của nó cho phép ứng dụng **nhận đồng bộ (synchronous polling)** từ một queue.

Bài này thuộc chương **Nhận thông điệp** của module **SPRING_AMQP** — học tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding; thực hành định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống để xây các xử lý bất đồng bộ đáng tin cậy. Trọng tâm là hiểu đúng thời điểm `receive()` trả về, cấu hình queue/timeout, cách nhận body hoặc object, đặc biệt là **ý nghĩa acknowledgement** trước khi dùng polling cho nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `RabbitTemplate.receive()` khác `@RabbitListener` ở điểm nào và khi nào nên chọn polling.
2. Phân biệt `receive()`, `receive(queueName)`, `receive(timeoutMillis)` và `receive(queueName, timeoutMillis)`.
3. Xử lý đúng `null` khi queue trống, đọc `Message` body/properties, hoặc dùng `receiveAndConvert(...)` để nhận object.
4. Hiểu `basic.get` của đường nhận tức thời và consumer tạm của đường nhận có timeout, cùng chi phí tài nguyên tương ứng.
5. Đánh giá rủi ro message đã được ack trước khi nghiệp vụ xử lý xong; phân biệt polling thông thường với consumer acknowledgement được kiểm soát.
6. Thiết kế vòng poll có giới hạn, backoff, log và phép thử RabbitMQ thực tế, không làm queue mất message âm thầm.

## 2. Nhận đồng bộ là gì?

Với cơ chế nhận đồng bộ, **thread của ứng dụng chủ động gọi phương thức lấy message**, rồi tiếp tục xử lý kết quả trả về. Nếu không có message, API có thể trả `null` ngay hoặc đợi đến timeout do bạn chỉ định. Điều này khác với `@RabbitListener`: listener container duy trì consumer và gọi callback khi broker giao message.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] --> E["Exchange"]
    E -->|"Binding / routing key"| Q["Queue"]
    Q -->|"Lấy khi ứng dụng gọi receive()"| T["Thread tác vụ<br/>RabbitTemplate.receive()"]
    T --> B{"Có Message?"}
    B -->|"Có"| H["Đọc body/properties<br/>xử lý dữ liệu"]
    B -->|"Không"| N["null<br/>không có message sẵn có"]
~~~

Một queue có thể đang có **nhiều consumer cạnh tranh**: `@RabbitListener`, ứng dụng polling và consumer từ service khác. Mỗi message chỉ được giao cho **một lần nhận** tại một thời điểm, theo cơ chế broker; không thể giả định `receive()` sẽ lấy được message chỉ vì producer vừa publish khi consumer khác có thể lấy trước.

| Tiêu chí | `RabbitTemplate.receive()` | `@RabbitListener` |
|---|---|---|
| Ai khởi tạo nhận? | Code chủ động gọi vào thời điểm cần | Listener container đăng ký consumer và chờ delivery |
| Kiểu thực thi | Đồng bộ trên thread gọi | Callback được container điều phối |
| Queue rỗng | Trả `null` ngay hoặc chờ theo timeout | Consumer vẫn đăng ký, đợi message đến |
| Mô hình tải | Thường cho ít message hoặc tác vụ theo yêu cầu | Thường phù hợp xử lý liên tục, throughput cao |
| Xử lý ack/retry | Cần đặc biệt hiểu semantics của template nhận | Container có ack mode, retry và error handling riêng |
| Chi phí lặp lại | Gọi thường xuyên có overhead polling | Consumer lâu dài tránh tạo consumer tạm theo từng lần chờ |

**Nhận đồng bộ không đồng nghĩa request/reply.** `receive()` chỉ lấy message từ queue; nó không tự gửi request hay chờ câu trả lời của một RPC. `convertSendAndReceive(...)` và `sendAndReceive(...)` là các API khác.

## 3. Bốn overload receive cơ bản

Spring AMQP hỗ trợ các overload thường gặp:

~~~java
Message receive();
Message receive(String queueName);
Message receive(long timeoutMillis);
Message receive(String queueName, long timeoutMillis);
~~~

Các chữ ký trên là **trích yếu API để học**, không phải phương thức cần tự khai báo trong ứng dụng. `Message` ở đây là `org.springframework.amqp.core.Message` chứ không phải `jakarta.jms.Message` hay `org.springframework.messaging.Message`.

| Lời gọi | Queue đích | Cách chờ |
|---|---|---|
| `receive()` | Default receive queue của template | Theo `receiveTimeout` trên template (mặc định 0) |
| `receive("orders.pull.q")` | Queue truyền trực tiếp | Theo `receiveTimeout` trên template (mặc định 0) |
| `receive(1500)` | Default receive queue | Chờ tối đa 1.500 ms |
| `receive("orders.pull.q", 1500)` | Queue truyền trực tiếp | Chờ tối đa 1.500 ms |
| `receive("orders.pull.q", 0)` | Queue truyền trực tiếp | Không đợi; không có message thì trả `null` |
| `receive("orders.pull.q", -1)` | Queue truyền trực tiếp | Chờ vô hạn theo hợp đồng API, trừ khi kết nối bị mất hoặc có lỗi |

**Phân biệt các giá trị timeout:**

- `0`: kiểm tra queue hiện tại và trả kết quả ngay theo hành vi không-blocking của API (vẫn có thể tốn thời gian cho I/O mạng và RPC).
- **Dương**: đợi message xuất hiện trong khoảng thời gian tối đa, ví dụ `2000` là **2 giây**.
- **Âm**: yêu cầu đợi vô hạn; tránh dùng trực tiếp trên request thread, scheduler có khả năng bị dừng hoặc tài nguyên có hạn.

Timeout của `receive` đo khoảng đợi **message**, không đồng nghĩa toàn lời gọi sẽ kết thúc chính xác tại mili giây đó nếu còn overhead kết nối, handshake, channel hay lỗi mạng.

### Default receive queue

Các overload **không truyền tên queue** yêu cầu template được thiết lập `defaultReceiveQueue`. Bạn có thể đặt:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

// rabbitTemplate là bean đã được inject và cấu hình phù hợp.
rabbitTemplate.setDefaultReceiveQueue("orders.pull.q");

Message message = rabbitTemplate.receive();
~~~

Nếu chưa thiết lập default receive queue, `receive()` không thể tự suy ra tên queue từ exchange hoặc routing key; nó có thể báo lỗi cấu hình. Trong code nhiều nghiệp vụ, `receive("orders.pull.q")` thường rõ ràng hơn. Đừng nhầm `defaultReceiveQueue` với **default exchange** của RabbitMQ: một bên là tên queue dùng khi nhận, một bên là exchange có tên rỗng dùng khi publish.

## 4. Không chờ: receive() và basic.get

Mặc định `RabbitTemplate` dùng `receiveTimeout = 0`. Khi đó, đường nhận tức thời sử dụng thao tác AMQP **`basic.get`** để hỏi broker về một message trong queue.

~~~mermaid
sequenceDiagram
    participant APP as Application thread
    participant RT as RabbitTemplate
    participant B as RabbitMQ broker
    APP->>RT: receive("orders.pull.q", 0)
    RT->>B: basic.get(queue)
    alt Queue có message sẵn
        B-->>RT: basic.get-ok + body/properties
        RT-->>APP: Message
    else Queue trống
        B-->>RT: basic.get-empty
        RT-->>APP: null
    end
~~~

Đây là dạng **pull một lần**: không có consumer được giữ lâu dài chỉ vì bạn đã gọi `receive()`. Gọi hai lần nghĩa là hai lần chủ động hỏi broker; một lần nhận chỉ trả **tối đa một** message.

Những điều dễ bị hiểu sai:

1. `receive()` **không tự tạo queue**. Queue phải tồn tại trong đúng virtual host, tài khoản phải có quyền cần thiết.
2. `null` nghĩa là không có message sẵn **ở thời điểm nhận và trong phạm vi chờ**, không chứng minh queue sẽ luôn trống hoặc producer chưa từng gửi.
3. Vì cần giao tiếp với broker, `receive(..., 0)` vẫn là thao tác I/O; “không đợi message” không có nghĩa phương thức chắc chắn chạy xong ngay trong 0 ms.
4. Message có thể bị consumer khác lấy trước; không coi kết quả `null` là lỗi routing khi chưa kiểm tra binding, queue, producer và các consumer khác.

## 5. Có chờ: receive(queue, timeout) dùng consumer tạm

Khi timeout **khác 0**, Spring AMQP dùng cơ chế nhận có chờ, trong đó một consumer tạm được đăng ký qua `basic.consume` trong lúc đợi delivery. Sau khi nhận được một message hoặc hết thời gian chờ, consumer tạm được hủy/thu dọn theo lifecycle của template. Đây là khác biệt quan trọng so với `basic.get` tức thời.

~~~mermaid
sequenceDiagram
    participant APP as Application thread
    participant RT as RabbitTemplate
    participant B as RabbitMQ broker
    APP->>RT: receive("orders.pull.q", 2000)
    RT->>B: basic.consume (consumer tạm)
    B-->>RT: consumer registered
    alt Có delivery trong khoảng chờ
        B-->>RT: deliver Message
        RT-->>APP: Message
    else Hết 2 giây chưa có delivery
        RT-->>APP: null
    end
    RT->>B: Hủy / thu dọn consumer tạm
~~~

Ví dụ:

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class PullOnce {
    private final RabbitTemplate rabbitTemplate;

    public PullOnce(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public boolean tryReceiveOnce() {
        Message message = rabbitTemplate.receive("orders.pull.q", 2_000);
        if (message == null) {
            return false;
        }

        System.out.println("Message bytes: " + message.getBody().length);
        return true;
    }
}
~~~

Khi workload thấp, timeout dương có thể giúp một tác vụ chờ message đến thay vì liên tục hỏi broker. Nhưng vì **mỗi lần chờ có overhead đăng ký consumer tạm**, phương pháp này thường không tối ưu cho hệ thống nhận liên tục với throughput cao. Nếu mục tiêu là xử lý mọi message ngay khi đến, dùng `@RabbitListener` với consumer lâu dài sẽ phù hợp hơn.

**Phụ thuộc phiên bản:** từ Spring AMQP 2.4.8, với non-zero timeout, template hỗ trợ thêm consumer arguments cho `basic.consume` (ví dụ consumer priority). Cần kiểm tra Reference/Javadoc của **đúng phiên bản** trước khi sao chép ví dụ dùng `addConsumerArg(...)`.

## 6. Thiết lập môi trường thực hành tối thiểu

Giả sử một ứng dụng Spring Boot có dependency `spring-boot-starter-amqp` và có thể kết nối RabbitMQ. Ta tạo một direct exchange, một durable queue và binding để chủ động gửi/nhận.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PullDemoTopology {

    @Bean
    DirectExchange pullExchange() {
        return new DirectExchange("orders.pull.x", true, false);
    }

    @Bean
    Queue pullQueue() {
        return QueueBuilder.durable("orders.pull.q").build();
    }

    @Bean
    Binding pullBinding(DirectExchange pullExchange, Queue pullQueue) {
        return BindingBuilder.bind(pullQueue)
                .to(pullExchange)
                .with("order.created");
    }
}
~~~

Nếu Spring Boot/Spring AMQP auto-configure `RabbitAdmin` phù hợp, các bean này có thể được khai báo lên broker khi có kết nối và quyền `configure`. Trong một môi trường đã quản lý topology bằng IaC, không nên khai báo trùng với cấu hình mâu thuẫn. Cần xác nhận queue/exchange/binding tồn tại trong **cùng virtual host** của producer và polling consumer.

Publisher tạo message:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class PullDemoPublisher {
    private final RabbitTemplate rabbitTemplate;

    public PullDemoPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String orderId) {
        rabbitTemplate.convertAndSend(
                "orders.pull.x",
                "order.created",
                "OrderCreated:" + orderId
        );
    }
}
~~~

Điều kiện nhận được là message **đã được định tuyến vào queue** và chưa bị consumer khác lấy hoặc bị chính sách queue loại. `RabbitTemplate.receive("orders.pull.q")` không lấy trực tiếp từ exchange `orders.pull.x`.

## 7. Nhận Message thô và đọc message properties

Với `receive(...)`, kiểu trả về là `org.springframework.amqp.core.Message`, chứa body dạng `byte[]` và `MessageProperties`.

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class PullMessageInspector {
    private final RabbitTemplate rabbitTemplate;

    public PullMessageInspector(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void inspectOnce() {
        Message message = rabbitTemplate.receive("orders.pull.q", 0);
        if (message == null) {
            System.out.println("Queue hiện không có message sẵn.");
            return;
        }

        MessageProperties properties = message.getMessageProperties();
        String body = new String(
                message.getBody(), StandardCharsets.UTF_8
        );

        System.out.println("body=" + body);
        System.out.println("contentType=" + properties.getContentType());
        System.out.println("messageId=" + properties.getMessageId());
        System.out.println("receivedExchange=" + properties.getReceivedExchange());
        System.out.println("receivedKey=" + properties.getReceivedRoutingKey());
    }
}
~~~

Đoạn này **giả định** body thực sự là text UTF-8; không decode tùy tiện nếu producer gửi Avro, protobuf, dữ liệu nén hoặc JSON dùng charset khác. Trong ứng dụng thật, không log nguyên body khi có thông tin cá nhân, dữ liệu tài chính hoặc secret.

| Thuộc tính | Ý nghĩa thực hành |
|---|---|
| `getBody()` | Byte array của message được lấy ra |
| `getContentType()` | Gợi ý định dạng payload như `text/plain`, `application/json` |
| `getContentEncoding()` | Gợi ý charset/mã hóa nếu producer đặt |
| `getMessageId()` | ID message nếu có; có thể dùng để truy vết/idempotency |
| `getReceivedExchange()` | Exchange broker đã nhận publish ban đầu |
| `getReceivedRoutingKey()` | Routing key của delivery |
| `getHeaders()` | Application headers do producer/framework gắn |

**Chú ý:** Một message trả về từ `receive()` không kèm theo một channel đang mở để bạn tùy ý gọi `basicAck(deliveryTag)` sau khi phương thức đã kết thúc. Việc `MessageProperties` có metadata delivery không đồng nghĩa caller đang sở hữu AMQP channel của delivery đó.

## 8. Cấu hình receiveTimeout: đặt trên template hay từng lần gọi?

Trong các phiên bản Spring Boot hỗ trợ property tương ứng, có thể cấu hình:

~~~properties
spring.rabbitmq.template.receive-timeout=2s
~~~

Khi Spring Boot auto-configure `RabbitTemplate` và áp dụng thuộc tính đó, `rabbitTemplate.receive("orders.pull.q")` sẽ đợi message tối đa khoảng 2 giây thay vì trả `null` ngay khi không có message.

Hoặc cấu hình trực tiếp:

~~~java
// Chỉ minh họa cấu hình khi khởi tạo template.
rabbitTemplate.setReceiveTimeout(2_000L);
~~~

Lưu ý: đừng thay `setReceiveTimeout` của bean `RabbitTemplate` dùng chung liên tục trong các request đồng thời. Nếu mỗi tác vụ cần timeout khác nhau, hãy dùng overload:

~~~java
Message immediate = rabbitTemplate.receive("orders.pull.q", 0);
Message waitOneSecond = rabbitTemplate.receive("orders.pull.q", 1_000);
Message waitFiveSeconds = rabbitTemplate.receive("orders.pull.q", 5_000);
~~~

Các lời gọi trên là **ba lượt nhận khác nhau**, và mỗi lượt có thể lấy một message riêng; không được coi chúng là ba cách đọc lại cùng một message.

### Receive timeout không phải reply timeout

| Thuộc tính/API | Tình huống sử dụng |
|---|---|
| `spring.rabbitmq.template.receive-timeout` | `receive()` hoặc `receiveAndConvert()` lấy message chủ động từ queue |
| `spring.rabbitmq.template.reply-timeout` | `convertSendAndReceive()` đợi RPC reply |
| `spring.rabbitmq.connection-timeout` | Thiết lập kết nối mạng đến RabbitMQ |
| Listener container `receiveTimeout` | Điều tiết vòng nhận/batch nội bộ của listener container, khác timeout của template |

Nếu request HTTP chờ `receive(..., 30_000)` và broker không gửi message, bạn đã giữ một HTTP worker trong suốt khoảng chờ. Phải cân nhắc timeout ở tầng web, hủy tác vụ và nguồn thread trước khi dùng polling trong API.

## 9. receiveAndConvert(): lấy object thay vì Message

`receive()` trả **Message thô**. Nếu cần object Java, `receiveAndConvert(...)` dùng `MessageConverter` đã cấu hình của template để chuyển payload.

~~~java
Object result = rabbitTemplate.receiveAndConvert("orders.pull.q", 1_000);

if (result == null) {
    System.out.println("Không có message để chuyển đổi.");
} else if (result instanceof String text) {
    System.out.println("Text: " + text);
} else {
    System.out.println("Java payload type: " + result.getClass().getName());
}
~~~

Với `SimpleMessageConverter`, message text có thể chuyển thành `String`, các message khác có thể thành `byte[]` hoặc kiểu Java theo content type/serialization. **Không mặc định** `receiveAndConvert` sẽ trả DTO JSON nếu chưa gắn JSON converter phù hợp.

Ví dụ cấu hình JSON converter cho **Spring AMQP 3.x / Jackson 2**:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AmqpPollingConverterConfig {

    @Bean
    MessageConverter amqpMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Trên **Spring AMQP 4.0+ với Jackson 3**, class converter dành cho thế hệ mới là `JacksonJsonMessageConverter`. Hai class thuộc những nhánh Jackson khác nhau; không tự trộn Jackson 2 `com.fasterxml.jackson.databind.ObjectMapper` với mapper của Jackson 3. Hãy kiểm tra Javadoc, BOM và dependency tree của phiên bản thực tế. Việc tạo bean `MessageConverter` có thể được Boot áp dụng cho template auto-configured theo nhánh; nếu template được tạo thủ công, hãy kiểm tra wiring riêng.

### Typed receiveAndConvert với generic type

Với `SmartMessageConverter` hỗ trợ target type, có thể dùng `ParameterizedTypeReference`:

~~~java
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<OrderCreated>> type =
        new ParameterizedTypeReference<>() {};

List<OrderCreated> events = rabbitTemplate.receiveAndConvert(
        "orders.pull.q",
        2_000,
        type
);
~~~

`OrderCreated` ở đây là DTO của ứng dụng; ví dụ giả định producer đã gửi **một message với body là JSON array**. Phương thức **không tự lấy nhiều message từ queue rồi ghép chúng thành List**. Nếu queue không có message, kết quả có thể là `null`; nếu converter không hỗ trợ `SmartMessageConverter` hoặc payload khác schema dự kiến, có thể phát sinh lỗi conversion.

## 10. Điểm sống còn: acknowledgement của receive() thông thường

Với `RabbitTemplate` **không bật transaction**, đường `receive(..., 0)` sử dụng `basic.get` với **auto-ack**; đường `receive(queue, timeout khác 0)` dùng consumer tạm và template thực hiện acknowledgement khi nhận trước khi trả kết quả về caller.

Điều này có một hệ quả lớn: **message có thể đã bị broker coi là xử lý xong trước khi nghiệp vụ của bạn thực sự xử lý xong**.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ broker
    participant T as RabbitTemplate.receive()
    participant APP as Business code
    B-->>T: Delivery Message
    Note over B,T: Non-transactional receive được xác nhận ở tầng nhận
    T-->>APP: return Message
    APP->>APP: saveOrderToDatabase()
    Note over APP: Nếu throw exception tại đây,<br/>không có auto-nack cho message vừa lấy
~~~

Ví dụ có rủi ro:

~~~java
Message message = rabbitTemplate.receive("payments.tasks.q", 0);
if (message != null) {
    paymentService.charge(message.getBody()); // Có thể lỗi sau khi message đã ack.
}
~~~

Nếu `paymentService.charge(...)` ném exception, `receive()` không tự quay lại broker để `basicNack`/requeue message. Message có thể đã biến mất khỏi queue. Đây là lý do **không nên dùng polling thông thường cho workflow cần xử lý chắc chắn từng task**, đặc biệt thanh toán, lập hóa đơn hoặc nghiệp vụ không chấp nhận mất công việc.

### Khi bật channelTransacted thì sao?

`RabbitTemplate.setChannelTransacted(true)` cho phép thao tác AMQP đi qua **transactional channel**. Khi template thực hiện một `receive` riêng lẻ ngoài Spring transaction bao quanh, transaction AMQP cục bộ có thể được commit trước khi phương thức trả message cho caller. Vì vậy:

- **Không được suy** rằng chỉ bật `channelTransacted=true` là exception của business code *sau* `receive()` sẽ rollback được message.
- Nếu muốn commit/rollback của receive gắn với một phạm vi xử lý lớn hơn, phải cấu hình và kiểm chứng **Spring transaction/thread-bound channel** đúng cách, phân biệt RabbitMQ transaction với transaction database.
- Transaction AMQP không phải XA/atomic transaction xuyên RabbitMQ và database. Với nghiệp vụ quan trọng, ưu tiên mẫu consumer có ack rõ ràng, idempotency và/outbox theo yêu cầu.

| Cách nhận | Khi nào ack message? | Nếu business code thất bại? |
|---|---|---|
| `receive(queue, 0)` không giao dịch | Broker auto-ack khi basic.get thành công | Không còn message để auto-requeue |
| `receive(queue, timeout > 0)` không giao dịch | Template ack delivery trước khi trả message | Lỗi business sau đó không tự nack |
| `receive` với transactional channel | Theo scope transaction và cách framework commit/rollback | Phải kiểm tra transaction boundary thực tế |
| `@RabbitListener` với container `AUTO` | Container ack sau khi handler xử lý thành công theo chính sách | Có đường error handling/reject/requeue |
| `@RabbitListener` với `MANUAL` | Ứng dụng gọi `basicAck/basicNack` trên channel của delivery | Kiểm soát ack nhưng phải tự xử lý failure đúng |

Chữ **AUTO** của listener container (`AcknowledgeMode.AUTO`) **không giống** RabbitMQ **auto-ack/noAck** khi lấy bằng `basic.get`. Trong container, AUTO nghĩa là framework quyết định gửi ack dựa trên outcome handler; trong `basic.get(..., autoAck=true)`, broker coi message đã được ack ngay khi delivery.

## 11. Muốn manual ack thì không dùng receive() thông thường

Nếu cần **chỉ ack sau khi nghiệp vụ hoàn tất**, `RabbitTemplate.receive()` thông thường không phải API cho caller cầm delivery tag và trì hoãn ack tùy ý. Có hai cách phù hợp hơn:

1. **Ưu tiên:** `@RabbitListener` với `AcknowledgeMode.AUTO` hoặc `MANUAL`, retry và DLX được thiết kế rõ. Phù hợp xử lý liên tục và an toàn hơn.
2. Nếu bắt buộc đồng bộ/poll một lần: dùng API thấp hơn `RabbitTemplate.execute(ChannelCallback)` để gọi `Channel.basicGet(queue, false)`, xử lý trên **cùng channel**, rồi `basicAck` hoặc `basicReject/basicNack` một cách tường minh.

Ví dụ mức thấp, chỉ để thấy ranh giới ack:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;
import com.rabbitmq.client.GetResponse;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class ManualAckPoller {
    private final RabbitTemplate rabbitTemplate;

    public ManualAckPoller(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public boolean pollOne(Consumer<String> businessHandler) {
        return rabbitTemplate.execute(channel -> {
            GetResponse response = channel.basicGet("orders.pull.q", false);
            if (response == null) {
                return false;
            }

            long tag = response.getEnvelope().getDeliveryTag();
            String body = new String(
                    response.getBody(), StandardCharsets.UTF_8
            );

            try {
                businessHandler.accept(body);
                channel.basicAck(tag, false);
                return true;
            } catch (Exception failure) {
                channel.basicReject(tag, false); // Không requeue; có thể DLX.
                throw failure;
            }
        });
    }
}
~~~

Đoạn trên thực hiện acknowledgement **trên cùng channel** với `basicGet(queue, false)`, vì delivery tag chỉ có ý nghĩa trong channel đó. `basicReject(tag, false)` yêu cầu không requeue; message chỉ đến DLQ nếu broker có cấu hình DLX và binding phù hợp. Với lỗi tạm thời, một chính sách retry/backoff có giới hạn sẽ phù hợp hơn việc reject vô điều kiện. Nếu thao tác `basicAck` thất bại vì mất connection, kết quả xử lý có thể không chắc chắn và message có thể được giao lại.

Đây là ví dụ **nâng cao**: cần tự thiết kế transaction boundary, phân loại lỗi, retry, quan sát và kiểm tra bản Spring AMQP/RabbitMQ đang dùng. Không lưu `channel`/delivery tag để ack trên thread khác sau khi `execute` đã trả về. Đối với tác vụ quan trọng, `@RabbitListener` hoặc container consumer thường là lựa chọn dễ duy trì hơn.

## 12. Khi nào polling phù hợp, khi nào không?

| Tình huống | Polling bằng `receive()` | Khuyến nghị |
|---|---|---|
| Công cụ quản trị đọc thử một message trên queue test | Phù hợp | Nhớ thao tác này có thể **lấy mất message** khỏi queue |
| Job định kỳ tiêu thụ ít thông báo không trọng yếu | Có thể phù hợp | Dùng lịch chạy, timeout hữu hạn và theo dõi số message |
| Kiểm tra queue trống trong integration test | Phù hợp trong điều kiện cô lập | Assert `null` với queue test riêng |
| Worker thanh toán, tạo hóa đơn, xử lý task quan trọng | Không nên dùng receive không giao dịch đơn thuần | `@RabbitListener`, ack/retry/idempotency rõ ràng |
| Hệ thống hàng nghìn message/giây | Polling liên tục kém phù hợp | Consumer lâu dài với concurrency/prefetch phù hợp |
| Muốn chờ một RPC response từ service khác | API khác phù hợp hơn | Dùng `convertSendAndReceive`/replyTo/correlation |
| Muốn lấy “tất cả messages hiện có” | Phải lặp nhiều lần và có race | Đặt giới hạn, không coi snapshot của queue là ổn định |

**Tránh busy polling:** đoạn code `while(true) { rabbitTemplate.receive("q", 0); }` có thể gây nhiều round trip, tăng CPU/load broker và tạo lưu lượng vô ích khi queue trống. Dùng scheduler/backoff hoặc chuyển sang listener.

## 13. Thiết kế một polling job có giới hạn

Ví dụ một tác vụ theo lịch cần xử lý **tối đa 20 message trong một lần chạy**. Đoạn code dưới đây minh họa về mặt điều phối, **không thay đổi bản chất auto-ack** của `receive()`.

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class BoundedPollingJob {
    private final RabbitTemplate rabbitTemplate;

    public BoundedPollingJob(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Scheduled(fixedDelayString = "${app.poll.interval-ms:2000}")
    public void poll() {
        int count = 0;
        while (count < 20) {
            Message message = rabbitTemplate.receive("metrics.sample.q", 0);
            if (message == null) {
                break;
            }

            String text = new String(
                    message.getBody(), StandardCharsets.UTF_8
            );
            System.out.println("sample=" + text);
            count++;
        }
        System.out.println("receivedCount=" + count);
    }
}
~~~

Để `@Scheduled` hoạt động, ứng dụng phải bật scheduling, ví dụ `@EnableScheduling` trong cấu hình Spring. Thuộc tính `app.poll.interval-ms` ở đây là **property ứng dụng do bạn định nghĩa**, không phải cấu hình RabbitMQ chuẩn. Queue `metrics.sample.q` là tên minh họa và cần tồn tại.

Giải thích lựa chọn:

- `max 20` ngăn một lần chạy chiếm thread mãi nếu queue liên tục nhận thêm message.
- `receive(..., 0)` tránh tạo consumer chờ mới cho từng lần nhận trong vòng lặp.
- Nếu queue trống, job thoát sớm thay vì quay vòng liên tục.
- `fixedDelay` giúp kiểm soát khoảng cách giữa **kết thúc lần chạy** và **bắt đầu lần kế tiếp** trong môi trường scheduler thông thường.
- **Không phù hợp cho message bắt buộc phải xử lý chắc chắn**, vì exception ở phần in/ghi/đẩy ra ngoài sau `receive` không tự requeue message.

Nếu nhiều instance chạy cùng cron/scheduler, chúng có thể cạnh tranh lấy message; nếu nghiệp vụ không muốn concurrency, cần cơ chế phối hợp hoặc một consumer group theo đúng thiết kế. Nếu yêu cầu backpressure, có thể dừng polling hoặc giảm tốc độ thay vì dùng timeout âm vô hạn.

## 14. Những trường hợp cần phân biệt khi chẩn đoán

| Hiện tượng | Có thể là gì? | Hướng kiểm tra |
|---|---|---|
| `receive()` trả `null` ngay | Queue trống; default timeout = 0 | Kiểm tra queue ready count, tên queue, consumers khác |
| `receive(queue, 2000)` trả `null` sau khoảng 2 giây | Không có delivery trong khoảng chờ | Đừng nhầm timeout với connect failure |
| `receive()` không có tên queue báo lỗi | Chưa đặt `defaultReceiveQueue` | Dùng overload có queue hoặc cấu hình default |
| Broker báo `404 NOT_FOUND`, channel đóng | Queue không tồn tại ở virtual host hiện tại | Xác minh queue, quyền, topology và vhost |
| `receiveAndConvert` ném conversion exception | Body/contentType/DTO/type mapping không hợp lệ | Kiểm tra bytes, converter và schema; nhớ rủi ro message đã ack |
| `receive()` trả message nhưng nghiệp vụ lỗi, queue không thấy message | Template non-transacted đã ack khi nhận | Chọn listener/ack strategy phù hợp |
| Queue còn nhiều message nhưng poller thường xuyên nhận `null` | Consumer khác giành delivery, race, nhầm vhost/queue | Quan sát consumer count, ready/unacked |
| CPU/broker requests tăng khi queue trống | Busy-loop `receive(queue, 0)` | Thêm giới hạn/scheduler/backoff |
| Poller nhận chậm dù có message | Broker/network chậm, consumer tạm, channel/caching hoặc flow control | Đo latency, connections/channels, timeout và log hai phía |
| Message đến DLQ sau khi poller lỗi? | Chỉ xảy ra nếu có reject/nack/dead-letter phù hợp | Không giả định auto-ack nontransacted sẽ sinh DLQ |

### Không nhầm “queue trống” với “không có message trong hệ thống”

Một publish có thể thất bại vì exchange không tồn tại, route nhầm queue, bị trả `NO_ROUTE`, hoặc chờ ở một queue khác. Polling từ `orders.pull.q` chỉ trả lời câu hỏi **queue này có message có thể giao vào thời điểm đó không**. Muốn điều tra đường đi của message, cần kiểm tra publisher confirms/returns, exchange, binding, queue ready/unacked và các consumer khác.

## 15. Kết nối, channel và timeout khi nhận đồng bộ

`RabbitTemplate` lấy channel qua `ConnectionFactory`; với `CachingConnectionFactory`, các channel có thể được tái sử dụng sau thao tác. Khi nhiều thread đồng thời gọi `receive`, khả năng sử dụng channel sẽ ảnh hưởng đến latency/timeout của ứng dụng.

- **Connection timeout:** giới hạn thời gian thiết lập kết nối mạng; khác với thời gian đợi message.
- **Channel checkout timeout:** nếu cấu hình cache với giới hạn channel, người gọi có thể phải chờ channel rảnh trước khi nhận.
- **receive timeout:** khoảng đợi delivery khi đã thực hiện thao tác nhận phù hợp.
- **Heartbeat:** phát hiện mất kết nối AMQP; không chứng minh một job polling xử lý message thành công.

Một `receive(queue, -1)` có thể giữ thread/channel trong lúc chờ rất lâu. Nếu có ít channel, nhiều request cùng chờ âm vô hạn có thể gây cạn tài nguyên. Dùng timeout hữu hạn trong worker hoặc thiết kế consumer lâu dài khi cần chờ liên tục.

Không lưu `Message` rồi giả định một transaction/channel sẽ tự tồn tại cho đến khi logic nghiệp vụ hoàn tất. Đối với API có ack do template xử lý, việc giữ object trong Java lâu hơn không thay đổi trạng thái delivery đã được broker xác nhận.

## 16. Thực hành kiểm thử với RabbitMQ thật

Để tránh nhầm với các listener đang hoạt động, sử dụng **queue test riêng** và dừng mọi consumer khác đối với queue đó. Kiểm tra topology đã được tạo trước khi chạy.

### Thử nghiệm A — Queue trống

~~~java
Message empty = rabbitTemplate.receive("orders.pull.q", 0);
assert empty == null;
~~~

Điều kiện: queue test thực sự trống và không có producer đồng thời. Nếu cần assertion chuẩn trong JUnit, sử dụng AssertJ/JUnit thay cho từ khóa `assert` (vì Java assertion có thể bị tắt nếu không bật JVM option).

### Thử nghiệm B — Nhận một message

~~~java
rabbitTemplate.convertAndSend(
        "orders.pull.x", "order.created", "OrderCreated:O-1001");

Message received = rabbitTemplate.receive("orders.pull.q", 2_000);
if (received == null) {
    throw new AssertionError("Expected a message");
}
String payload = new String(
        received.getBody(), StandardCharsets.UTF_8);
if (!"OrderCreated:O-1001".equals(payload)) {
    throw new AssertionError("Unexpected payload: " + payload);
}
~~~

Điều kiện: không có consumer cạnh tranh, exchange/binding đúng, publisher thực sự gửi thành công. Để tránh flaky test, kiểm thử integration cần broker test hoạt động ổn định, queue test sạch và xác nhận phù hợp khi cần.

### Thử nghiệm C — Nhận lần thứ hai

Sau khi B nhận message duy nhất:

~~~java
Message second = rabbitTemplate.receive("orders.pull.q", 0);
if (second != null) {
    throw new AssertionError("Unexpected second message");
}
~~~

Lưu ý message được lấy ra khỏi queue; đây không phải API **peek** xem dữ liệu nhưng vẫn giữ nguyên message. Đừng dùng polling trên queue production nếu chỉ muốn kiểm tra nội dung bằng mắt.

### Thử nghiệm D — Timeout và đo thời gian

Queue trống, gọi `receive("orders.pull.q", 1_000)`. Đo thời gian bằng `System.nanoTime()` và kiểm tra kết quả `null`. Đừng assert thời gian chính xác tuyệt đối 1000 ms vì scheduling, network, JVM pause hoặc overhead tài nguyên có thể tạo sai lệch.

### Thử nghiệm E — Conversion lỗi

Đặt contentType JSON cho một message có body JSON hỏng hoặc không phù hợp DTO, rồi gọi `receiveAndConvert`. Ghi lại exception và xác minh message còn trong queue hay không. Trên template không transacted, **message thường đã được ack ở bước nhận**, nên không có bảo đảm redelivery sau lỗi conversion.

### Thử nghiệm F — Manual ack ở API mức thấp

Trên queue riêng, chạy một lần `basicGet(queue, false)` trong `execute(ChannelCallback)`; thử `basicReject(tag, false)` và theo dõi DLQ (nếu cấu hình) hoặc `basicNack(tag, false, true)` để kiểm chứng requeue. Không tạo poison-message loop vô hạn; dùng môi trường test, consumer count hạn chế và message ID ổn định.

### Ma trận kết quả kỳ vọng

| Kịch bản | Lời gọi | Kết quả API | Điều cần kiểm chứng thêm |
|---|---|---|---|
| A | `receive(queue, 0)` | `null` | Queue trống ở thời điểm thử |
| B | `receive(queue, 2000)` | `Message` | Payload và properties đúng |
| C | Nhận lần hai khi chỉ gửi một message | `null` | Không phải peek; đã lấy message |
| D | `receive(queue, 1000)` khi trống | `null` sau khoảng đợi | Timeout không tuyệt đối đến từng ms |
| E | `receiveAndConvert` với JSON sai | Lỗi converter có thể phát sinh | Message đã ack hay vẫn nằm trong transaction? |
| F | Raw `basicGet(queue, false)` + reject/nack | Theo cờ requeue và cấu hình broker | Không dùng `receive()` để trì hoãn ack |

## 17. Bài tập tự kiểm tra

### Bài 1 — Nhận 5 lần có chắc được 5 message?

Một queue chỉ có 3 message và không có producer mới. Thread gọi `receive("q", 0)` năm lần. Có chắc mọi lần đều trả `Message`?

**Đáp án:** không. Nếu không có consumer khác và không có chính sách loại message, ba lần đầu có thể lấy ba message, hai lần sau trả `null`. Thực tế, consumer khác hoặc queue policy có thể làm khác kết quả; không có cam kết luôn đủ năm message.

### Bài 2 — Timeout âm

`receive("q", -1)` có nghĩa là “thử một lần rồi bỏ qua lỗi” hay “đợi vô hạn”?

**Đáp án:** yêu cầu chờ vô hạn, trừ khi kết nối lỗi hoặc thao tác bị gián đoạn theo semantics của API. Không thích hợp cho HTTP request thread cần giới hạn thời gian đáp ứng.

### Bài 3 — Điểm khác giữa receive và receiveAndConvert

`receive("q")` trả gì, `receiveAndConvert("q")` trả gì?

**Đáp án:** API thứ nhất trả `org.springframework.amqp.core.Message` hoặc `null`; thứ hai trả object đã được `MessageConverter` xử lý hoặc `null`. Không đảm bảo object luôn là DTO JSON nếu converter không phù hợp.

### Bài 4 — Lỗi sau receive

Một service lấy được payment task bằng `receive()`, sau đó lỗi khi ghi database. Vì sao queue không tự giao lại message?

**Đáp án:** template ở chế độ nontransacted đã ack ở tầng nhận. Business exception xảy ra sau khi method return không tự biến thành consumer nack. Hãy chọn listener/ack strategy khác cho nghiệp vụ quan trọng.

### Bài 5 — basic.get với manual ack

Vì sao phải dùng `Channel.basicGet(queue, false)` và ack trên **cùng channel**, không dùng delivery tag lấy từ một `Message` rồi ack trên channel mới?

**Đáp án:** delivery tag chỉ hợp lệ trong channel đã giao message, còn `RabbitTemplate.receive()` không cung cấp quyền sở hữu channel đó cho caller sau lời gọi.

### Bài 6 — Polling hay listener?

Một hệ thống nhận 20.000 event/giây cần retry, DLQ và khả năng xử lý trùng. Bạn chọn vòng `receive(queue, 5000)` hay `@RabbitListener`?

**Gợi ý:** ưu tiên listener container lâu dài, quản lý concurrency/prefetch, ack/retry/DLX và idempotency. Polling với consumer tạm có overhead, khó kiểm soát outcome sau `receive` và không phù hợp throughput cao.

### Bài 7 — Queue trống nhưng producer có log “sent”

Producer gọi `convertAndSend` thành công nhưng `receive()` trả `null`. Hãy nêu tối thiểu bốn nguyên nhân.

**Gợi ý:** routing key/binding sai, exchange hoặc vhost khác, consumer khác đã nhận, producer chưa có confirm, message bị TTL/overflow, publish unroutable mà không bật returns. `receive()` không giải thích toàn bộ trạng thái publish.

### Bài 8 — Tạo job theo lịch

Viết một job chạy mỗi 5 giây, lấy tối đa 10 message không trọng yếu mỗi lần và thoát ngay khi queue trống. Với yêu cầu không được mất message quan trọng, cần đổi thiết kế thế nào?

**Gợi ý:** dùng `@Scheduled` + vòng `receive(queue, 0)` có giới hạn cho dữ liệu không trọng yếu. Nếu dữ liệu quan trọng, chuyển sang listener có ack sau xử lý hoặc raw channel có ack đúng và chiến lược lỗi, idempotency, DLQ.

## 18. Checklist áp dụng trong dự án

- [ ] Chọn đúng queue (và virtual host), xác nhận queue đã được tạo và có binding phù hợp.
- [ ] Khi dùng `receive()` không tham số, cấu hình `defaultReceiveQueue`; nếu không, dùng overload tên queue rõ ràng.
- [ ] Phân biệt `receiveTimeout = 0` (basic.get ngay), timeout dương (consumer tạm chờ) và timeout âm (đợi vô hạn).
- [ ] Xử lý `null` bình thường, không coi đây là exception hoặc chắc chắn producer không gửi.
- [ ] Không giải mã `byte[]` tùy tiện; dùng contentType/encoding và JSON converter tương thích khi cần.
- [ ] Hiểu `receiveAndConvert` không phải API lấy một batch nhiều message.
- [ ] Nhớ **nontransactional `receive()` xác nhận delivery ở tầng nhận**, không chờ business code thành công.
- [ ] Không dùng `receive()` đơn thuần cho task bắt buộc xử lý chắc chắn; chọn `@RabbitListener` và ack/error handler phù hợp.
- [ ] Nếu bắt buộc manual ack đồng bộ, dùng `basicGet(..., false)` trên channel được quản lý rõ ràng và kiểm thử lỗi.
- [ ] Tránh vòng polling sát không nghỉ; dùng scheduler/backoff, giới hạn số message/lượt và timeout hữu hạn.
- [ ] Theo dõi queue ready/unacked, lượng message đã nhận, lỗi conversion, consumer count và DLQ.
- [ ] Có test RabbitMQ thật về queue trống, message xuất hiện, timeout, conversion failure, consumer cạnh tranh và lost connection.
- [ ] Kiểm tra tài liệu API theo Spring AMQP version, nhất là các option liên quan timeout và consumer arguments.

## 19. Tài liệu tham khảo chính thức

- [Spring AMQP — Polling Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/polling-consumer.html): hành vi `receive`, overload, timeout và `receiveAndConvert`.
- [Spring AMQP — RabbitTemplate API](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/rabbit/core/RabbitTemplate.html): chữ ký `receive`, `setReceiveTimeout`, `setDefaultReceiveQueue`.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): `channelTransacted`, phạm vi Spring transaction và rollback.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): ack modes, concurrency, listener error handling.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ý nghĩa broker auto-ack và consumer manual acknowledgement.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers): consumer lifecycle, competing consumers và cách broker giao delivery.

**Ghi nhớ:** `RabbitTemplate.receive()` là API **chủ động lấy một message đồng bộ từ queue**, trả `Message` hoặc `null`. Mặc định nó kiểm tra ngay bằng `basic.get`; timeout dương dùng consumer tạm để chờ. Quan trọng nhất, trong chế độ không giao dịch, message được broker xác nhận ở bước nhận **trước khi business code xử lý xong**. Vì vậy, hãy dùng polling cho tình huống phù hợp và chọn consumer container/ack strategy khác khi bạn cần bảo đảm xử lý từng message có khả năng retry và quan sát đầy đủ.
