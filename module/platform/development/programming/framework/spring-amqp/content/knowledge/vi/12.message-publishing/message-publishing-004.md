# Before-publish và after-receive post processor

Khi tích hợp RabbitMQ qua **Spring AMQP**, một ứng dụng không chỉ gửi và nhận body của message. Trước lúc publish, ta có thể cần bổ sung metadata, kiểm tra định dạng, nén dữ liệu hoặc áp dụng cơ chế bảo vệ payload. Sau khi nhận, ta có thể cần giải nén, kiểm tra những thuộc tính đã thống nhất hoặc ghi thông tin phục vụ quan sát trước khi chuyển dữ liệu cho nghiệp vụ. Spring AMQP hỗ trợ những thao tác này thông qua **MessagePostProcessor** và các điểm gắn xử lý trong **RabbitTemplate** cũng như **listener container**.

Bài học thuộc chương **Gửi thông điệp**, tập trung vào hai điểm mở rộng:

- **Before-publish post processor:** xử lý đối tượng **Message** ngay trước khi RabbitTemplate publish lên RabbitMQ.
- **After-receive post processor:** xử lý **Message** sau khi nhận từ broker nhưng trước giai đoạn xử lý tiếp theo, như message conversion hoặc lời gọi listener, tùy thành phần nhận.

Mục tiêu là hiểu **đặt processor ở đâu**, phân biệt các biến thể xử lý và tránh biến post processor thành nguồn gây lỗi lặp, phá metadata hoặc vô tình tạo thông điệp trùng.

Sau bài học, bạn có thể cấu hình Spring AMQP để bổ sung header trước khi gửi, theo dõi thông tin sau khi nhận, thực hành nén/giải nén, hiểu luồng convert/receive và biết cách kiểm chứng bằng RabbitMQ Management, publisher confirm, ACK, retry và dead-letter.

## 1. MessagePostProcessor là gì?

Spring AMQP định nghĩa giao diện **org.springframework.amqp.core.MessagePostProcessor**. Phương thức chính nhận một đối tượng **Message** và trả lại một đối tượng **Message**, cho phép chỉnh sửa payload bytes và/hoặc **MessageProperties**.

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessagePostProcessor;

MessagePostProcessor tagSource = message -> {
    message.getMessageProperties()
           .setHeader("x-source-app", "order-service");
    return message;
};
~~~

Một **Message** trong Spring AMQP có hai thành phần chính:

~~~text
Message
├── body: byte[]
└── MessageProperties
    ├── contentType / contentEncoding
    ├── messageId / correlationId / type
    ├── deliveryMode / priority / expiration
    └── headers (metadata mở rộng)
~~~

Post processor có thể thay đổi cả hai, nhưng cần hiểu rằng **MessagePostProcessor không phải MessageConverter**:

| Thành phần | Vai trò |
| --- | --- |
| **MessageConverter** | Chuyển đổi object Java thành Message khi gửi và Message thành dữ liệu Java khi nhận |
| **MessagePostProcessor** | Can thiệp Message và MessageProperties ở một điểm trong pipeline |
| **RabbitTemplate** | API gửi/nhận, chịu trách nhiệm gọi converter và processor tương ứng |
| **Listener container** | Nhận delivery, gọi after-receive processor rồi chuyển message đến listener adapter |
| **RabbitAdmin** | Khai báo exchange, queue và binding, không phải nơi xử lý body message |

Ví dụ: nếu cần chuyển DTO Java sang JSON, bạn ưu tiên cấu hình **Jackson message converter**. Nếu cần gắn **messageId**, **contentEncoding** hoặc nén dữ liệu sau khi đã convert thành bytes, **MessagePostProcessor** là một điểm mở rộng phù hợp.

## 2. Luồng gửi và luồng nhận

### 2.1. Trước lúc publish

~~~mermaid
flowchart LR
    A["Object Java<br/>hoặc byte payload"] --> B["MessageConverter<br/>nếu dùng convertAndSend"]
    B --> C["Message + MessageProperties"]
    C --> D["Post processor theo lần gửi<br/>nếu có"]
    D --> E["RabbitTemplate<br/>beforePublishPostProcessors"]
    E --> F["AMQP publish<br/>Exchange + routing key"]
    F --> G[("RabbitMQ queue<br/>qua binding")]
~~~

Với **RabbitTemplate.convertAndSend(...)**, converter tạo **Message** trước; processor được gọi **trên Message**, không trực tiếp trên DTO. Một overload của convertAndSend cho phép cung cấp processor riêng của **một lần gửi**. Ngoài ra, template có danh sách processor **beforePublishPostProcessors** áp dụng trên các hoạt động publish của template đó.

Nếu sử dụng **RabbitTemplate.send(...)** với **Message** tự tạo, không cần bước chuyển đổi Java object thành Message; điểm before-publish vẫn là nơi can thiệp trước publish.

### 2.2. Sau khi nhận

~~~mermaid
flowchart LR
    R[("RabbitMQ queue")] --> A["AMQP delivery"]
    A --> B["Message bytes<br/>và properties"]
    B --> C["afterReceivePostProcessors<br/>ở đúng thành phần nhận"]
    C --> D["MessageConverter / listener adapter"]
    D --> E["Business handler"]
    E --> F["ACK / NACK / retry<br/>theo cấu hình"]
~~~

**Điểm cần phân biệt:** RabbitTemplate và **@RabbitListener** không phải cùng một đường nhận.

- **RabbitTemplate.setAfterReceivePostProcessors(...)** tác động đến các thao tác nhận qua **RabbitTemplate** (ví dụ receive/receiveAndConvert; các đường reply khi thích hợp).
- Listener tạo từ **@RabbitListener** nhận message thông qua **listener container**. Muốn post-process message trước listener, cần cấu hình **afterReceivePostProcessors cho container/factory** mà listener sử dụng.

Chỉ cấu hình after-receive ở RabbitTemplate **không có nghĩa tất cả @RabbitListener tự sử dụng processor ấy**.

## 3. Ba cách gắn post processor và phạm vi áp dụng

| API hoặc cấu hình | Vị trí | Phạm vi điển hình |
| --- | --- | --- |
| **convertAndSend(..., MessagePostProcessor)** | Tham số lần gửi | Chỉ message của lời gọi convertAndSend đó |
| **RabbitTemplate.setBeforePublishPostProcessors(...)** | Template publisher | Những message được publish qua template đó |
| **RabbitTemplate.setAfterReceivePostProcessors(...)** | Template receiver | Message nhận bằng các API receive của template |
| **SimpleRabbitListenerContainerFactory.setAfterReceivePostProcessors(...)** | Factory tạo listener container | Các listener container do factory đó tạo |
| **SimpleMessageListenerContainer.setAfterReceivePostProcessors(...)** | Một container cụ thể | Những delivery của container đó |

Các điểm gắn này giúp phân biệt **chính sách chung** với **thông tin của sự kiện cụ thể**.

**Chính sách chung:** gắn header tên dịch vụ, đo kích thước message, nén body của toàn bộ kênh publisher đã thống nhất hợp đồng.

**Thông tin riêng theo lần gửi:** đặt **eventId** đã tạo khi nghiệp vụ phát sinh, correlationId, loại sự kiện hoặc một header chỉ áp dụng cho sự kiện đó.

## 4. Post processor theo từng lần convertAndSend

Giả sử một sự kiện tạo đơn đã có định danh ổn định. Ta muốn gửi nội dung chuỗi, đồng thời đặt **messageId** và **correlationId** trước publish.

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        String correlationId
) {}
~~~

~~~java
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        String body = "order.created:" + event.orderId();

        rabbitTemplate.convertAndSend(
                "lab.order.events",
                "order.created",
                body,
                message -> {
                    MessageProperties props = message.getMessageProperties();
                    props.setMessageId(event.eventId());
                    if (event.correlationId() != null) {
                        props.setCorrelationId(event.correlationId());
                    }
                    props.setType("order.created");
                    props.setHeader("x-event-schema", 1);
                    return message;
                }
        );
    }
}
~~~

**Lý do đặt ID ở đây:** processor dùng **event.eventId()** đã có. Nếu publisher timeout và gửi lại cùng event, ta gọi **publish(event)** lần nữa, vẫn dùng đúng messageId. Không nên gọi **UUID.randomUUID()** bên trong processor này mỗi khi retry cùng một sự kiện.

**Lưu ý:** **messageId** trong AMQP properties là thông tin do publisher quản lý; RabbitMQ không dùng nó như một bảo đảm chống phát trùng. Consumer muốn idempotent phải dựa vào định danh ổn định đã thống nhất và trạng thái xử lý riêng.

## 5. Before-publish post processor dùng chung cho RabbitTemplate

Một template có thể gửi nhiều loại message. Để áp dụng một quy tắc chung, đặt processor qua **setBeforePublishPostProcessors**.

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessagePostProcessor;

public final class SourceHeaderProcessor implements MessagePostProcessor {
    private final String source;

    public SourceHeaderProcessor(String source) {
        this.source = source;
    }

    @Override
    public Message postProcessMessage(Message message) {
        message.getMessageProperties().setHeader("x-source-app", source);
        return message;
    }
}
~~~

Sử dụng trong cấu hình Spring Boot **3.x** với template do Boot auto-configure:

~~~java
import org.springframework.boot.autoconfigure.amqp.RabbitTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OutgoingProcessorConfig {

    @Bean
    RabbitTemplateCustomizer outgoingCustomizer() {
        return template -> template.setBeforePublishPostProcessors(
                new SourceHeaderProcessor("order-service")
        );
    }
}
~~~

Đối với dự án Spring Boot có API customizer khác giữa các phiên bản, hoặc khi chủ động tạo RabbitTemplate, có thể cấu hình trực tiếp:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

RabbitTemplate template = new RabbitTemplate(connectionFactory);
template.setBeforePublishPostProcessors(
        new SourceHeaderProcessor("order-service")
);
~~~

Đoạn cuối minh họa API trong phần cấu hình có sẵn **connectionFactory**; nếu dùng Spring Boot tự khai báo **@Bean RabbitTemplate**, cần chú ý các cấu hình khác mà Boot thường đặt cho template như converter, retry, publisher returns và observation. Không nên vô tình mất chúng chỉ để thêm processor.

### Khi nào before-publish chạy?

Với **convertAndSend**, trình tự khái niệm là chuyển payload Java thành **Message**, áp dụng processor của lời gọi (nếu có), rồi chạy các processor before-publish đã đăng ký trước khi chuyển message đến broker. Chi tiết thứ tự giữa nhiều processor cùng loại có thể chịu ảnh hưởng của cấu hình thứ tự; đừng thiết kế ngầm rằng một phép biến đổi nhạy cảm về thứ tự sẽ luôn chạy trước phép khác nếu chưa kiểm tra.

Với ví dụ hiện tại, message rời publisher có các thông tin:

~~~text
Body: order.created:O-1001
MessageProperties:
  messageId: <eventId đã có>
  type: order.created
  correlationId: <nếu có>
  headers:
    x-event-schema: 1
    x-source-app: order-service
~~~

Trong môi trường có nhiều publisher, giá trị **x-source-app** là metadata do ứng dụng tự khai báo, không phải chứng thực danh tính. Consumer không nên xem một header tùy ý là bằng chứng bảo mật.

## 6. After-receive trên RabbitTemplate

RabbitTemplate cũng có những API chủ động lấy message khỏi queue, ví dụ **receive(...)** và **receiveAndConvert(...)**. Có thể cấu hình xử lý ngay sau khi template nhận được Message:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessagePostProcessor;

public final class IncomingObservationProcessor
        implements MessagePostProcessor {

    private static final Logger log =
            LoggerFactory.getLogger(IncomingObservationProcessor.class);

    @Override
    public Message postProcessMessage(Message message) {
        var props = message.getMessageProperties();
        log.info(
                "AMQP receive messageId={} type={} bytes={}",
                props.getMessageId(),
                props.getType(),
                message.getBody().length
        );
        return message;
    }
}
~~~

Đăng ký với template:

~~~java
rabbitTemplate.setAfterReceivePostProcessors(
        new IncomingObservationProcessor()
);

// Lấy message qua chính RabbitTemplate:
Object payload = rabbitTemplate.receiveAndConvert(
        "lab.order.handlers"
);
~~~

Processor sẽ nhìn thấy **Message và MessageProperties** trước khi template thực hiện chuyển đổi body thành object, khi thao tác nhận có message. Nếu không có message, receive có thể trả **null**; không có đối tượng nào để processor xử lý. Cần xử lý tình huống rỗng khi viết code gọi receive.

**Không nhầm:** một @RabbitListener cùng sử dụng ConnectionFactory với RabbitTemplate vẫn **không tự chạy** after-receive processor được cài trên template. Listener có pipeline độc lập.

## 7. After-receive trước @RabbitListener

Để tác động đến message đến một **@RabbitListener**, cần cấu hình trên listener container hoặc **factory** tạo container.

Ví dụ Spring Boot **3.x** với **SimpleRabbitListenerContainerFactoryConfigurer**:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class IncomingListenerConfig {

    @Bean(name = "rabbitListenerContainerFactory")
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        // Giữ cấu hình listener mặc định của Spring Boot:
        configurer.configure(factory, connectionFactory);

        // Chạy trước bước gọi handler/convert của listener:
        factory.setAfterReceivePostProcessors(
                new IncomingObservationProcessor()
        );
        return factory;
    }
}
~~~

Với một listener:

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
import java.nio.charset.StandardCharsets;

@Component
public class OrderEventListener {

    @RabbitListener(queues = "lab.order.handlers")
    public void onOrder(Message message) {
        String payload = new String(
                message.getBody(),
                StandardCharsets.UTF_8
        );
        System.out.println("Business received: " + payload);
    }
}
~~~

Khi có message, log từ **IncomingObservationProcessor** sẽ xuất hiện trước log của **onOrder** trong cùng lượt xử lý:

~~~text
AMQP receive messageId=evt-001 type=order.created bytes=20
Business received: order.created:O-1001
~~~

Con số bytes trong ví dụ chỉ minh họa. Với listener method nhận **String/DTO** thay vì **Message**, conversion xảy ra sau processor tại lớp listener adapter.

### Nếu có nhiều listener container factory

Một ứng dụng có thể định nghĩa factory khác nhau, ví dụ:

~~~java
@RabbitListener(
    queues = "lab.order.handlers",
    containerFactory = "observedListenerFactory"
)
public void onOrder(String payload) {
    // ...
}
~~~

Khi đó cần gắn after-receive processor vào **observedListenerFactory**, không phải vào factory mặc định rồi mong mọi listener đều nhận. Tương tự, nếu dùng **DirectRabbitListenerContainerFactory**, hãy cấu hình processor trên factory thực sự được listener sử dụng.

## 8. Ví dụ đầy đủ: topology, publish và quan sát

Để chạy hai ví dụ processor ở trên, cần một exchange, queue và binding tương ứng.

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
public class LabTopology {

    @Bean
    DirectExchange orderExchange() {
        return new DirectExchange("lab.order.events", true, false);
    }

    @Bean
    Queue orderQueue() {
        return QueueBuilder.durable("lab.order.handlers").build();
    }

    @Bean
    Binding orderBinding(Queue orderQueue,
                         DirectExchange orderExchange) {
        return BindingBuilder.bind(orderQueue)
                .to(orderExchange)
                .with("order.created");
    }
}
~~~

Tài khoản RabbitMQ và địa chỉ broker đặt trong **application.yml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
~~~

Đây là credential ví dụ cho lab, không dùng cố định trong production. Cần RabbitMQ broker đã chạy và dependency **spring-boot-starter-amqp**:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Spring AMQP thường dùng RabbitAdmin để tự khai báo các bean Queue/Exchange/Binding khi có kết nối phù hợp; nếu bạn tắt auto-declare hoặc dùng tài nguyên do bên khác quản lý, hãy tạo topology trước.

Chạy thử publish với **eventId** được tạo đúng một lần:

~~~java
OrderCreatedEvent event = new OrderCreatedEvent(
        "e5b8a51a-50fa-4c38-a7d7-67dc9318c7fd",
        "O-1001",
        "request-abc"
);

orderEventPublisher.publish(event);

// Nếu cần thử gửi lại chính event đó:
orderEventPublisher.publish(event);
~~~

Hai lần gọi trên chủ ý publish **hai bản vận chuyển của cùng một sự kiện logic**. Consumer sẽ nhận hai message nếu cả hai lần đều được broker chấp nhận; việc cùng messageId **không khiến RabbitMQ tự loại trùng**. Nếu nghiệp vụ không cho phép xử lý side effect hai lần, consumer cần cơ chế **idempotency** riêng.

Trong RabbitMQ Management, mở queue **lab.order.handlers** để kiểm tra **Ready**, **Unacked**, **Consumers** và message rates. Nếu listener đang chạy, message có thể được nhận/ACK quá nhanh khiến Ready bằng 0; quan sát log và biểu đồ rates thay vì suy luận rằng message chưa được publish.

## 9. Nén trước publish và giải nén sau receive

Một ví dụ nổi bật của post processor là **compression**. Khi publisher nén body bytes bằng GZIP, consumer phải giải nén **trước khi** message converter cố diễn giải dữ liệu như text/JSON.

Spring AMQP cung cấp các processor nén/giải nén, ví dụ:

~~~java
import org.springframework.amqp.support.postprocessor.GZipPostProcessor;
import org.springframework.amqp.support.postprocessor.GUnzipPostProcessor;
~~~

Ở publisher:

~~~java
rabbitTemplate.setBeforePublishPostProcessors(
        new GZipPostProcessor()
);
~~~

Nếu nhận bằng **RabbitTemplate.receiveAndConvert(...)**:

~~~java
rabbitTemplate.setAfterReceivePostProcessors(
        new GUnzipPostProcessor()
);
~~~

Nếu nhận bằng **@RabbitListener**, cấu hình giải nén trên listener factory:

~~~java
factory.setAfterReceivePostProcessors(
        new GUnzipPostProcessor()
);
~~~

Ba đoạn trên là các phần cấu hình **tại những vị trí khác nhau**, không phải một chương trình Java hoàn chỉnh đứng độc lập. Khi áp dụng vào ví dụ lab, hãy quyết định **receiver nào thực sự sử dụng pipeline nén** và cấu hình đúng receiver đó.

~~~mermaid
flowchart LR
    A["Object Java"] --> B["MessageConverter"]
    B --> C["GZipPostProcessor<br/>trước publish"]
    C --> Q[("RabbitMQ queue<br/>body nén")]
    Q --> U["GUnzipPostProcessor<br/>sau receive"]
    U --> D["MessageConverter"]
    D --> L["Listener / business"]
~~~

### Những điều cần chú ý khi nén

- **Thỏa thuận giao thức giữa producer và consumer:** nếu publisher nén nhưng consumer không giải nén, listener có thể nhận bytes không đọc được hoặc lỗi conversion.
- **Content encoding:** processor nén/giải nén thường sử dụng metadata để mô tả thuật toán và quản lý nội dung gốc. Không tự gán **contentEncoding** tùy tiện sau khi nén vì có thể khiến bên nhận giải mã sai.
- **Thứ tự xử lý:** nếu vừa nén vừa mã hóa, thông thường nén trước rồi mã hóa; lúc nhận phải giải mã trước rồi giải nén. Cần cấu hình và kiểm thử thứ tự processor thực tế.
- **Payload nhỏ:** nén có thể không giảm kích thước đáng kể, thậm chí tăng overhead và CPU; hãy đo với dữ liệu thật.
- **Bảo vệ tài nguyên:** giới hạn kích thước message và kích thước sau giải nén; dữ liệu nén không tin cậy có thể gây rủi ro tiêu thụ bộ nhớ quá lớn.
- **Thay đổi hợp đồng:** trước khi bật nén cho queue có consumer cũ, cần kiểm tra khả năng tương thích, đặc biệt khi DLQ còn chứa message với định dạng cũ.

**Nén không phải mã hóa và không thay thế TLS**. Nếu yêu cầu bảo mật dữ liệu trên đường truyền, cấu hình AMQPS/TLS, phân quyền broker và bảo vệ thông tin nhạy cảm trong logging.

## 10. Nhiều post processor: thứ tự và tính an toàn

Đôi khi ứng dụng cần kết hợp:

1. Gắn **eventId**, type và các header tương quan.
2. Validate hợp đồng MessageProperties.
3. Ghi metadata quan sát (không in toàn bộ dữ liệu nhạy cảm).
4. Nén body.
5. Mã hóa hoặc ký message theo cơ chế riêng nếu yêu cầu.

Nếu phép biến đổi thứ hai phụ thuộc kết quả của phép thứ nhất, **thứ tự là một phần của hợp đồng**. Spring AMQP hỗ trợ nhiều processor trong các danh sách before-publish và after-receive; việc sắp xếp có thể dựa trên cơ chế ordering của framework ở phiên bản sử dụng. Khi thứ tự bắt buộc, hãy thể hiện ưu tiên rõ ràng và viết **integration test** kiểm tra body/properties cuối cùng thay vì phó mặc cho thứ tự đăng ký tình cờ.

Ví dụ về khác biệt:

~~~text
Đúng cho hợp đồng nén rồi mã hóa:
  JSON bytes -> gzip -> encrypt -> broker
  broker -> decrypt -> gunzip -> JSON decode

Sai nếu receiver đảo thứ tự:
  broker -> gunzip ciphertext -> lỗi xử lý
~~~

### Processor nên stateless và thread-safe

Một bean **MessagePostProcessor** có thể được dùng đồng thời bởi nhiều thread publish/consume. Nên:

- Tránh lưu **eventId cuối cùng** hoặc body hiện tại vào field chia sẻ có thể thay đổi.
- Nếu cần bộ đếm, dùng metric registry/thread-safe structure thay vì biến toàn cục không đồng bộ.
- Tránh chặn network/database trong processor cho mọi message; những thao tác nặng gây tăng latency hoặc nghẽn consumer.
- Nếu tạo Message mới, bảo toàn metadata cần thiết (messageId, correlationId, deliveryMode, headers) và không làm hỏng body.
- Không sửa định danh sự kiện ở **after-receive** để che dữ liệu đầu vào sai.
- Không đặt bí mật như token hoặc số thẻ vào header, trace hoặc log.

### Có thể return Message khác không?

**Có.** MessagePostProcessor nhận **Message** và trả về **Message**, do đó có thể tạo Message mới với body bytes sau biến đổi. Nhưng nếu thay body thì phải giữ **MessageProperties** thích hợp, đặc biệt **contentType**, **contentEncoding**, **messageId**, **deliveryMode**, correlation và headers. Với nén/giải nén, nên ưu tiên các processor có sẵn của Spring AMQP thay vì tự viết thao tác bytes khi không cần.

## 11. Phân biệt processor với interceptor, confirm và listener advice

Một hệ thống đáng tin cậy có thể dùng nhiều điểm mở rộng, nhưng chúng **không tương đương**:

| Cơ chế | Vấn đề giải quyết | Khác post processor ở đâu? |
| --- | --- | --- |
| **MessagePostProcessor** | Thay đổi/kiểm tra Message trước publish hoặc sau receive | Can thiệp trực tiếp body/properties tại một vị trí pipeline |
| **MessageConverter** | Java object ↔ AMQP Message | Chuyển kiểu và serialization, không phải chính sách xử lý message |
| **Publisher confirm** | Broker xác nhận publish ở phía producer | Không thay đổi body; không xác nhận consumer xử lý xong |
| **Publisher returns** | Thông báo message mandatory không được route đến queue | Không giải quyết lỗi parse/nén/deserialize ở consumer |
| **Listener advice/retry interceptor** | Retry, transaction hoặc cross-cutting logic khi xử lý listener | Can thiệp vòng gọi handler; khác bước biến đổi AMQP Message đầu vào |
| **Consumer ACK/NACK** | Xác nhận hoặc từ chối delivery | Không tự bổ sung metadata và không bảo đảm exactly-once |
| **Dead-letter exchange** | Route message bị dead-letter theo điều kiện queue | Dùng cho luồng message lỗi/hết hạn, không thay thế validation |

**Ví dụ:** gắn **messageId** bằng post processor và bật publisher confirm đều hữu ích, nhưng không bảo đảm một message chỉ được xử lý một lần. Nếu publish retry sau timeout hoặc consumer mất connection trước ACK, message có thể xuất hiện lại. Cần **idempotent consumer**, có thể dựa trên eventId lưu bền cùng side effect nghiệp vụ.

## 12. Nếu post processor lỗi thì chuyện gì xảy ra?

### Trước publish

Nếu before-publish processor ném exception, hoạt động publish có thể thất bại **trước khi message được gửi thành công**. Bên gọi phải phân biệt lỗi local serialization/validation với lỗi broker hoặc timeout. Đừng retry vô hạn một payload chắc chắn không hợp lệ. Nếu publisher không chắc message đã được gửi, retry phải **giữ eventId ổn định**.

### Sau receive

Nếu after-receive processor của listener ném exception, message không đi tiếp vào handler bình thường. Hệ quả ACK/NACK/requeue tùy **listener container**, acknowledge mode, error handler, advice, retry configuration và cài đặt DLQ. Nếu cấu hình requeue không giới hạn cho dữ liệu không thể giải nén, có thể tạo vòng lặp **poison message**.

Ví dụ:

~~~text
message có contentEncoding=gzip nhưng body hỏng
    |
    v
GUnzipPostProcessor ném lỗi
    |
    v
Listener method chưa được gọi
    |
    v
Container áp dụng xử lý exception/ACK/NACK theo cấu hình
    |
    +-- Requeue vô hạn -> nguy cơ lặp
    +-- Reject/nack không requeue -> DLQ nếu có cấu hình
~~~

Trong thiết kế hệ thống xử lý bất đồng bộ tin cậy, nên:

- **Phân loại lỗi không thể sửa bằng retry** (schema sai, payload nén hỏng, thiếu field bắt buộc).
- Cấu hình **retry giới hạn/backoff** cho lỗi có thể tạm thời, kèm **dead-letter** cho message phải chuyển ra luồng xử lý chính.
- Ghi **messageId/eventId**, queue, nguyên nhân lỗi và lần thử trong log (tránh log dữ liệu nhạy cảm).
- Kiểm chứng message lỗi có thực sự vào DLQ hay chỉ bị reject/bị mất theo chính sách queue.
- Quan sát **Ready/Unacked**, tần suất retry, DLQ backlog và độ trễ consumer.

## 13. Hiệu năng và quan sát hệ thống

Post processor chạy trên đường xử lý message, nên chi phí nhỏ **nhân với số message** có thể trở thành đáng kể.

| Yếu tố | Ảnh hưởng | Gợi ý |
| --- | --- | --- |
| Nén/giải nén | Tăng CPU và allocation | Đo payload thật, bật khi thực sự có lợi |
| Logging mọi message | I/O, latency và chi phí lưu log | Dùng sampling hoặc log có mục đích |
| Sao chép body bytes | Tăng áp lực GC và bộ nhớ | Hạn chế copy không cần thiết |
| Gọi HTTP/DB trong processor | Có thể nghẽn luồng publish/consume | Đưa sang service nghiệp vụ hoặc pipeline async có kiểm soát |
| Quá nhiều processor theo chuỗi | Khó theo dõi thứ tự, lỗi và metadata | Chuẩn hóa hợp đồng, test từng stage |
| Retry lỗi parse vô hạn | Message chặn tiến trình xử lý | Error classification và DLQ |

Nên dùng **Micrometer Observation/Tracing** hoặc cơ chế tracing do ứng dụng cấu hình để đo send/receive, đồng thời dùng metadata như **eventType**, **queue**, **result** làm dimension có cardinality hợp lý. Không nên dùng **messageId duy nhất của từng message** làm metric label, vì tạo số lượng time series quá lớn. MessageId phù hợp cho **log/tracing** khi tuân thủ chính sách dữ liệu.

Trong **RabbitMQ Management**, theo dõi exchange, queue, binding, số consumers, Ready/Unacked, publish/deliver/ack rate. Không thể xác nhận processor đã chạy chỉ bằng việc queue có message; cần quan sát **headers/body/properties** hoặc log của ứng dụng.

## 14. Quy trình thực hành kiểm chứng

Một chuỗi thử nghiệm gợi ý:

1. Khởi động RabbitMQ với Management UI và một ứng dụng Spring Boot có **spring-boot-starter-amqp**.
2. Tạo exchange **lab.order.events**, queue **lab.order.handlers** và binding key **order.created** theo cấu hình ở phần 8.
3. Bật **SourceHeaderProcessor** tại **RabbitTemplate.setBeforePublishPostProcessors(...)** và publish một event.
4. Khi muốn xem message trên Management UI, tạm dừng consumer để message nằm trong queue; kiểm tra header **x-source-app** và **messageId**. Tránh thao tác **Get messages** với ACK/xóa nếu muốn giữ lại dữ liệu lab.
5. Bật **IncomingObservationProcessor** trên factory mà @RabbitListener sử dụng, chạy consumer và xem log messageId/type/body size.
6. Thử dùng **rabbitTemplate.receiveAndConvert(...)** trong một tình huống riêng; cấu hình processor qua **RabbitTemplate.setAfterReceivePostProcessors(...)** để thấy đường nhận của template độc lập với listener container.
7. Bật nén **GZipPostProcessor** trên publisher và giải nén **GUnzipPostProcessor** trên đúng phía nhận; kiểm tra handler vẫn đọc body gốc.
8. Cố ý thử một message nén sai **chỉ ở môi trường lab**; kiểm tra error handler và chính sách DLQ, không để vòng requeue vô hạn.
9. Nếu thử publish lại cùng event, giữ nguyên eventId; xác minh consumer cần idempotency riêng, không dựa vào messageId để broker tự loại trùng.

Khi kiểm chứng nén, **không** nên dùng một queue chứa hỗn hợp message cũ không nén và message mới có nén nếu receiver chỉ hỗ trợ một định dạng cố định. Nếu phải chuyển đổi dần, thiết kế một giai đoạn tương thích hoặc tách queue/version theo hợp đồng dữ liệu.

## 15. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ cấu hình afterReceive trên **RabbitTemplate**, mong @RabbitListener cũng chạy | Processor không được gọi trên listener | Đăng ký trên đúng listener container factory |
| Tưởng **MessagePostProcessor** tự deserialize JSON thành DTO | Sai trách nhiệm của pipeline | Dùng MessageConverter cho chuyển kiểu |
| Sinh UUID mới ở before-publish mỗi lần retry | Một event logic có nhiều ID | Tạo eventId ở nguồn, truyền vào processor theo lần gửi |
| Nén trước publish nhưng quên giải nén sau nhận | Lỗi parse hoặc dữ liệu không đọc được | Bật GUnzip đúng thành phần consumer |
| Giải nén sau message converter | Converter đọc bytes nén thay vì dữ liệu gốc | Xử lý after-receive trước conversion |
| Processor làm network I/O chậm | Nghẽn luồng publish/consume | Giữ processor nhẹ, tách logic nghiệp vụ |
| Dùng header **x-source-app** làm bằng chứng xác thực | Header có thể bị bên gửi tự khai báo | Dùng TLS, tài khoản và ACL broker |
| Ghi log body đầy đủ | Rủi ro lộ dữ liệu và tốn tài nguyên | Log metadata tối thiểu, che dữ liệu nhạy cảm |
| Nghĩ messageId giúp RabbitMQ tự khử trùng | Publish lại có thể tạo message trùng | Idempotency ở consumer |
| Processor ném lỗi parse nhưng không có DLQ | Message có thể retry vô hạn hoặc bị loại không mong muốn | Xác định chiến lược retry/nack/dead-letter |
| Đăng ký nhiều processor phụ thuộc thứ tự nhưng không kiểm thử | Nén/mã hóa/validation không nhất quán | Cấu hình order rõ và kiểm chứng integration |
| Thay body nhưng không cập nhật contentEncoding/contentType | Bên nhận giải mã sai | Giữ metadata phù hợp với bytes thực tế |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Trong một ứng dụng Spring Boot, bạn đã gọi **rabbitTemplate.setAfterReceivePostProcessors(new GUnzipPostProcessor())** nhưng @RabbitListener vẫn không đọc được message nén. Vì sao?

**Câu 2.** Muốn đặt **messageId** bằng eventId đã tạo ở nghiệp vụ cho từng event, nên dùng processor theo từng lần gửi hay một processor chung tự sinh UUID mới?

**Câu 3.** Vì sao không thể thay thế Jackson MessageConverter bằng before-publish processor đơn giản gắn header?

**Câu 4.** Nếu publisher nén rồi mã hóa, listener cần biến đổi theo thứ tự nào trước khi convert JSON?

**Câu 5.** Message bị gửi lặp với cùng AMQP messageId. RabbitMQ có tự động loại một bản không?

**Câu 6.** Một after-receive processor ném exception do dữ liệu hỏng. Có thể chắc chắn message được chuyển vào DLQ chỉ vì đã cấu hình processor không?

**Đáp án gợi ý:**

1. Vì **@RabbitListener nhận qua listener container**, không đi qua đường receive của RabbitTemplate. Phải cấu hình **afterReceivePostProcessors** trên container/factory thực sự dùng.
2. Dùng **processor của convertAndSend theo lần gửi** để lấy eventId từ event có sẵn, hoặc bảo toàn ID đã lưu từ outbox. Không sinh ID mới ở mỗi lần publish retry.
3. Vì **MessageConverter** thực hiện chuyển đổi Java object ↔ bytes/message, còn processor can thiệp Message đã được tạo.
4. **Giải mã trước, giải nén sau, rồi mới convert JSON**, theo đúng thứ tự đảo ngược quá trình publish.
5. **Không.** messageId là metadata; consumer cần idempotency theo định danh logic.
6. **Không.** Còn phụ thuộc acknowledge mode, error handler, retry/requeue và cấu hình DLX/DLQ.

## 17. Checklist khi đưa vào production

Trước khi triển khai, hãy xác nhận:

- **Processor chạy ở đường nào:** per-send, RabbitTemplate before-publish, RabbitTemplate after-receive hay listener container after-receive?
- **MessageConverter** nào được dùng? Phép biến đổi bytes thực hiện **trước hay sau converter**?
- **Metadata nào phải giữ nguyên**, đặc biệt eventId/messageId, correlationId, contentType, encoding, deliveryMode và headers?
- **Retry publish** có bảo toàn eventId không? Consumer đã có idempotency chưa?
- **Nén/mã hóa** có được mọi producer/consumer trong queue hiểu đúng không?
- **Thứ tự processor** có được cấu hình và kiểm thử khi có nhiều bước?
- **Lỗi post processor** có được phân loại và xử lý bằng retry giới hạn, ACK/NACK, DLQ đúng chính sách?
- **Latency và tài nguyên** có được đo, log có tránh payload nhạy cảm và metric cardinality cao không?
- **Publisher confirms/returns và consumer acknowledgements** đã được cấu hình và giám sát khi cần độ tin cậy chưa?
- **RabbitMQ Management** có giúp kiểm chứng header, queue/backlog, kết nối và rates tương ứng không?

**Kết luận:** **before-publish** là điểm điều chỉnh Message ở **phía gửi**, còn **after-receive** là điểm điều chỉnh Message ở **phía nhận** trước xử lý tiếp theo. Với Spring AMQP, cần gắn đúng processor vào **RabbitTemplate** hoặc **listener container**; không mặc định một cấu hình bao trùm mọi đường gửi/nhận. Post processor giúp chuẩn hóa metadata và xử lý payload, nhưng độ tin cậy end-to-end vẫn cần exchange/queue/binding đúng, publisher confirm/returns, consumer ACK, retry, dead-letter, transaction, idempotency và observability.

### Tài liệu đọc thêm

- [Spring AMQP – RabbitTemplate: Message Post Processing](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [Spring AMQP – Asynchronous Consumer: Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html)
- [Spring AMQP – Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
