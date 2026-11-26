# receiveAndConvert() và chuyển kiểu dữ liệu phía nhận

## Mục tiêu bài học

Trong **Spring AMQP**, producer thường dùng **RabbitTemplate.convertAndSend()** để biến một đối tượng Java thành thông điệp gửi tới RabbitMQ. Ở chiều ngược lại, ứng dụng có thể **chủ động lấy một message từ queue** và chuyển nó thành dữ liệu Java bằng **RabbitTemplate.receiveAndConvert()**. Đây là cách tiêu thụ **đồng bộ theo yêu cầu (polling)**, khác với cơ chế listener chạy liên tục của **@RabbitListener**.

Bài này thuộc chương **Nhận thông điệp** của module **SPRING_AMQP**. Ngoài việc chuyển đổi dữ liệu, ta sẽ gắn kiến thức với exchange, queue, binding, xác nhận giao nhận, retry, dead-letter và quan sát hệ thống để xây xử lý bất đồng bộ đáng tin cậy.

Sau bài học, bạn có thể:

1. Giải thích **receive()**, **receiveAndConvert()**, **receiveAndConvert(queue, timeout)** và cách chúng nhận dữ liệu.
2. Phân biệt **message không có**, **lỗi kết nối**, **lỗi conversion** và **lỗi nghiệp vụ**.
3. Hiểu **MessageConverter** xử lý **body byte[]**, **contentType**, **contentEncoding**, type headers và kiểu Java đích.
4. Nhận **String**, **byte[]**, **DTO JSON** và dữ liệu generic bằng converter phù hợp.
5. Quyết định khi nào nên polling bằng RabbitTemplate, khi nào nên dùng **@RabbitListener**.
6. Tránh mất message khi conversion lỗi và xử lý trùng bằng **idempotency**.

## 1. Đường đi từ RabbitMQ message đến Java object

RabbitMQ lưu và giao message dưới dạng body bytes cùng các thuộc tính AMQP. Nó **không tự biết class Java nào sẽ đại diện cho body đó**.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate.convertAndSend"] --> X{"Exchange<br/>orders.events"}
    X -->|"routing key + binding"| Q[("Queue<br/>orders.created.receive")]
    Q --> R["RabbitTemplate.receiveAndConvert"]
    R --> M["AMQP Message<br/>byte[] + MessageProperties"]
    M --> C["MessageConverter<br/>fromMessage"]
    C --> O["String / byte[] / DTO"]
~~~

Về mặt chức năng, **receiveAndConvert()** bao gồm hai công việc:

1. **Receive:** lấy một message từ queue RabbitMQ qua giao thức AMQP.
2. **Convert:** gọi converter để biến **org.springframework.amqp.core.Message** thành đối tượng Java.

Có thể hình dung:

~~~java
Message message = rabbitTemplate.receive("orders.created.receive");
Object value = message == null
        ? null
        : rabbitTemplate.getMessageConverter().fromMessage(message);
~~~

Đây là **mô phỏng logic**, không phải cách cài đặt nội bộ chính xác của mọi phiên bản. Nó cho thấy vì sao phải tách **lấy message** khỏi **giải mã body** khi chẩn đoán lỗi.

### Những kiểu message dễ nhầm

| Kiểu | Thuộc thư viện | Dữ liệu chính |
| --- | --- | --- |
| **org.springframework.amqp.core.Message** | Spring AMQP | **byte[] body** và **MessageProperties** |
| **org.springframework.messaging.Message&lt;T&gt;** | Spring Messaging | **payload T** và MessageHeaders |
| **OrderCreatedEvent** | DTO do ứng dụng định nghĩa | Dữ liệu nghiệp vụ như eventId, orderId |
| **com.rabbitmq.client.GetResponse** | RabbitMQ Java Client | Kết quả low-level của một lệnh basic.get |

**receive()** trả về AMQP Message thô. **receiveAndConvert()** trả về kết quả do converter tạo ra; **không** mặc định trả về một DTO chỉ vì JSON trông giống DTO đó.

## 2. API receiveAndConvert() trong RabbitTemplate

Các lời gọi thường gặp:

~~~java
// Đọc từ default receive queue đã cấu hình trên RabbitTemplate.
Object a = rabbitTemplate.receiveAndConvert();

// Đọc từ queue đích được chỉ định tường minh.
Object b = rabbitTemplate.receiveAndConvert("orders.created.receive");

// Đọc queue và có thể chờ tối đa khoảng 2 giây.
Object c = rabbitTemplate.receiveAndConvert(
        "orders.created.receive", 2_000L);
~~~

**receiveAndConvert() không nhận tên exchange/routing key** giống **convertAndSend()**. Nó nhận từ **một queue đã tồn tại**. Exchange và binding quyết định message đã vào queue nào **trước khi** consumer gọi receive.

| Lời gọi | Cách chọn queue | Hành vi |
| --- | --- | --- |
| **receiveAndConvert()** | Dùng default receive queue trên RabbitTemplate | Phù hợp khi template phục vụ một queue cụ thể |
| **receiveAndConvert(queueName)** | Tên queue truyền vào | Lấy một message từ queue đó theo timeout được cấu hình |
| **receiveAndConvert(queueName, timeoutMillis)** | Tên queue + timeout | Cho phép chờ message đến trong khoảng thời gian chỉ định |
| **receive(queueName)** | Tên queue | Trả về Message thô, không convert |
| **receiveAndConvert(queueName, ParameterizedTypeReference&lt;T&gt;)** | Queue + kiểu đích | Trả kiểu T khi converter hỗ trợ **SmartMessageConverter** |

### 2.1. Không có message thì nhận gì?

Nếu queue không có message để giao trong khoảng chờ, các phương thức receive/receiveAndConvert thường trả **null**.

~~~java
Object result = rabbitTemplate.receiveAndConvert(
        "orders.created.receive");

if (result == null) {
    // Không nhận được message trong thời gian chờ.
    return;
}

System.out.println(result);
~~~

**null không đồng nghĩa lỗi kết nối**. Lỗi authentication, broker không sẵn sàng hoặc queue không tồn tại thường dẫn tới exception, không đơn thuần trả null. Không nên viết catch(Exception) rồi trả null vì sẽ che mất sự cố.

Nếu ứng dụng có một converter đặc biệt có thể trả null từ một message hợp lệ, cần đọc hợp đồng converter đó. Trong ví dụ học tập dùng converter chuẩn, null nên được xem là tín hiệu không nhận được message.

### 2.2. Timeout: không chờ và chờ có hạn

Theo cách sử dụng thông thường, **receiveTimeout=0** có nghĩa không chờ message khi queue đang trống. Có thể cấu hình:

~~~java
rabbitTemplate.setReceiveTimeout(2_000L);
Object received =
        rabbitTemplate.receiveAndConvert("orders.created.receive");
~~~

Hoặc truyền timeout riêng cho một lần đọc:

~~~java
Object received = rabbitTemplate.receiveAndConvert(
        "orders.created.receive", 2_000L);
~~~

Các tham số timeout được tính bằng **mili-giây**. Khi dùng timeout dương, một thao tác receive có thể phải **giữ thread chờ** đến khi message tới hoặc hết hạn. **Đây không phải cơ chế scheduler**: ứng dụng vẫn phải chủ động gọi lại nếu muốn polling theo chu kỳ.

Một số API/nhánh hỗ trợ giá trị timeout đặc biệt để chờ không giới hạn; trong ứng dụng production, ưu tiên **timeout hữu hạn** và quản lý deadline tổng thể thay vì giữ thread vô thời hạn.

### 2.3. receiveAndConvert() không phải peek

Quan trọng nhất: **receiveAndConvert là một thao tác tiêu thụ message**, không phải xem bản sao trong queue. Khi một message được lấy thành công, nó không còn là message ready để một worker khác lấy y nguyên theo cách polling thông thường.

Đừng dùng receiveAndConvert trên queue production chỉ để “xem thử payload”. Nếu cần kiểm tra, hãy dùng queue thử nghiệm, một bản sao gửi sang audit queue, hoặc công cụ quản trị phù hợp với chế độ requeue/thận trọng về ACK.

## 3. Converter mặc định: SimpleMessageConverter

Nếu không cấu hình loại khác, RabbitTemplate thường dùng **SimpleMessageConverter**. Converter này nhìn vào **contentType** và **contentEncoding** của message để quyết định cách giải mã.

| Body/properties lúc nhận | Kết quả thường gặp của SimpleMessageConverter | Cần lưu ý |
| --- | --- | --- |
| **text/plain** cùng charset phù hợp | **String** | Cần producer/consumer thống nhất encoding |
| **byte[]** với contentType không phải text/serialization | **byte[]** | Không tự biến JSON thành DTO |
| **application/json** nhưng không có JSON converter | Thường **byte[]** | ContentType JSON không làm SimpleMessageConverter tự dùng Jackson |
| **application/x-java-serialized-object** | Có thể giải mã Java serialized object nếu cho phép theo cấu hình | Không nên dùng native Java serialization làm hợp đồng liên dịch vụ |

### 3.1. Ví dụ gửi và nhận String

~~~java
// Producer.
rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        "Order ORD-1001 created");

// Consumer polling.
Object value = rabbitTemplate.receiveAndConvert(
        "orders.created.receive");

if (value instanceof String text) {
    System.out.println("Received text: " + text);
}
~~~

Ví dụ giả định exchange **orders.events** đã bind routing key **order.created** tới queue **orders.created.receive**, và hai phía đều dùng converter mặc định phù hợp.

### 3.2. Vì sao nhận byte[] dù producer gửi JSON?

Producer có thể tự tạo AMQP Message với body JSON và contentType **application/json**:

~~~java
String json = "{\"eventId\":\"e-101\",\"orderId\":\"ORD-1001\"}";
MessageProperties props = new MessageProperties();
props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
props.setContentEncoding("UTF-8");

Message message = new Message(
        json.getBytes(StandardCharsets.UTF_8), props);

rabbitTemplate.send("orders.events", "order.created", message);
~~~

Nếu phía nhận chỉ có **SimpleMessageConverter**, kết quả của receiveAndConvert có thể vẫn là **byte[]**. Khi đó:

~~~java
Object value = rabbitTemplate.receiveAndConvert(
        "orders.created.receive");

if (value instanceof byte[] bytes) {
    String jsonText = new String(bytes, StandardCharsets.UTF_8);
    // Parse JSON bằng thư viện JSON đã chọn và validate schema.
}
~~~

**Không ép kiểu trực tiếp** như **(OrderCreatedEvent) value** khi chưa biết converter trả kiểu gì. Java sẽ ném **ClassCastException**, trong khi message có thể đã được lấy khỏi queue.

### 3.3. Java native serialization: không dùng làm định dạng sự kiện

SimpleMessageConverter có hỗ trợ các kiểu Serializable và cơ chế Java serialization/deserialization trong những điều kiện nhất định. Cách này ràng buộc chặt với Java class và có nguy cơ bảo mật khi đọc dữ liệu không đáng tin.

Trong hệ thống nhiều service, ưu tiên **JSON, Protobuf, Avro** hoặc một định dạng có contract và schema rõ ràng. Không mở rộng danh sách class được deserialize một cách tùy tiện để chữa lỗi conversion.

## 4. Ví dụ hoàn chỉnh: JSON DTO với Spring AMQP 3.x

Đây là ví dụ sử dụng **Spring Boot 3.x**, **Spring AMQP 3.x** và **Jackson2JsonMessageConverter**. Nếu dự án dùng nhánh Spring AMQP 4.x/Jackson 3, API converter có tên khác; hãy chọn đúng phiên bản thay vì trộn code.

### 4.1. Dependency

~~~xml
<!-- Ví dụ Spring Boot 3.x: phiên bản được BOM của Boot quản lý. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Môi trường chạy cần RabbitMQ AMQP 0.9.1, thường ở cổng **5672**, và một tài khoản có quyền tương ứng. Dự án cũng cần Jackson JSON trên classpath; trong Spring Boot Web thường đã có, còn ứng dụng tối giản cần kiểm tra dependencies thực tế.

### 4.2. Hợp đồng DTO

~~~java
// OrderCreatedEvent.java
package com.example.contracts.orders;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

Body JSON tương ứng:

~~~json
{
  "eventId": "evt-101",
  "orderId": "ORD-1001",
  "totalAmount": 150000
}
~~~

Trong hệ thống thật, hãy bổ sung **schemaVersion**, **occurredAt**, **currency** và validation theo nghiệp vụ. **eventId** phải đủ ổn định để nhận diện sự kiện khi publisher retry hoặc consumer nhận lại.

### 4.3. Khai báo queue, exchange, binding, converter và template

~~~java
package com.example;

import com.example.contracts.orders.OrderCreatedEvent;
import java.util.Map;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderReceiveConfig {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    Queue orderReceiveQueue() {
        return QueueBuilder.durable("orders.created.receive").build();
    }

    @Bean
    Binding orderReceiveBinding(
            Queue orderReceiveQueue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(orderReceiveQueue)
                .to(ordersExchange)
                .with("order.created");
    }

    @Bean
    DefaultClassMapper orderClassMapper() {
        DefaultClassMapper mapper = new DefaultClassMapper();
        mapper.setIdClassMapping(
                Map.of("order.created.v1", OrderCreatedEvent.class));
        mapper.setTrustedPackages(
                "com.example.contracts.orders",
                "java.lang",
                "java.util");
        // Với @Bean, Spring gọi afterPropertiesSet() khi cần.
        return mapper;
    }

    @Bean
    Jackson2JsonMessageConverter orderJsonConverter(
            DefaultClassMapper orderClassMapper) {
        Jackson2JsonMessageConverter converter =
                new Jackson2JsonMessageConverter();
        converter.setClassMapper(orderClassMapper);
        return converter;
    }

    @Bean
    RabbitTemplate orderRabbitTemplate(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter orderJsonConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(orderJsonConverter);
        template.setReceiveTimeout(2_000);
        return template;
    }
}
~~~

**Ý nghĩa các bean:**

- **ordersExchange** và **orderReceiveQueue** là tài nguyên RabbitMQ, được liên kết bởi **orderReceiveBinding**.
- **orderClassMapper** chuyển alias **order.created.v1** sang **OrderCreatedEvent.class** và hạn chế package dùng khi đọc type metadata.
- **orderJsonConverter** biến đối tượng thành JSON lúc gửi và giải mã JSON lúc nhận.
- **orderRabbitTemplate** dùng converter đó cho cả **convertAndSend** và **receiveAndConvert**, với khoảng chờ polling 2 giây mặc định.

Ứng dụng giả định **RabbitAdmin** hoặc công cụ provisioning khai báo topology. Nếu đã có RabbitTemplate khác do Boot tạo, hãy **chọn đúng bean bằng @Qualifier**, không giả định mọi template trong ApplicationContext tự dùng converter mới.

### 4.4. Producer publish DTO

~~~java
package com.example;

import com.example.contracts.orders.OrderCreatedEvent;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class OrderProducer {
    private final RabbitTemplate template;

    public OrderProducer(
            @Qualifier("orderRabbitTemplate") RabbitTemplate template) {
        this.template = template;
    }

    public void send(OrderCreatedEvent event) {
        template.convertAndSend(
                "orders.events",
                "order.created",
                event,
                message -> {
                    message.getMessageProperties()
                            .setMessageId(event.eventId());
                    message.getMessageProperties()
                            .setHeader("schemaVersion", 1);
                    return message;
                });
    }
}
~~~

Vì converter sử dụng **DefaultClassMapper**, khi gửi **OrderCreatedEvent**, message JSON có thể kèm header **__TypeId__=order.created.v1**. **messageId** và custom header **schemaVersion** là thông tin bổ sung; chúng không tự biến một DTO thành hợp đồng tương thích nếu schema thay đổi sai cách.

**Điểm về độ tin cậy:** **convertAndSend** không trả về kết quả xử lý của consumer. Muốn biết broker xác nhận publish và có route thành công, cần xử lý **publisher confirms, mandatory returns** và topology đúng.

### 4.5. Consumer polling bằng receiveAndConvert

~~~java
package com.example;

import com.example.contracts.orders.OrderCreatedEvent;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class OrderPollingConsumer {
    private final RabbitTemplate template;

    public OrderPollingConsumer(
            @Qualifier("orderRabbitTemplate") RabbitTemplate template) {
        this.template = template;
    }

    public void pollOnce() {
        Object converted = template.receiveAndConvert(
                "orders.created.receive", 2_000);

        if (converted == null) {
            System.out.println("No message available");
            return;
        }

        if (!(converted instanceof OrderCreatedEvent event)) {
            throw new IllegalStateException(
                    "Unexpected converted type: "
                    + converted.getClass().getName());
        }

        validate(event);
        System.out.println("Received order " + event.orderId());
        // Production: ghi DB idempotently theo event.eventId().
    }

    private void validate(OrderCreatedEvent event) {
        if (event.eventId() == null
                || event.orderId() == null
                || event.totalAmount() < 0) {
            throw new IllegalArgumentException("Invalid event");
        }
    }
}
~~~

Phương thức này **chủ động polling một lần**; nó không tự chạy liên tục. Ứng dụng có thể gọi nó từ một job hoặc một thao tác bảo trì có điều phối. Để chạy nhiều lần, cần scheduler, giới hạn tần suất và quản lý lỗi riêng; một vòng **while(true)** không có backoff, shutdown signal hay giới hạn số thread dễ gây lãng phí tài nguyên.

**Cảnh báo quan trọng về ví dụ polling:** với RabbitTemplate.receiveAndConvert() theo cách dùng phổ biến, việc lấy/ACK message được thực hiện bởi template theo lifecycle nhận, **không gắn nguyên tử** với validate() hoặc lưu DB sau khi method trả về. Nếu validate() thất bại sau khi converter đã trả object, message có thể **đã bị lấy khỏi queue**; không được mong RabbitMQ tự giao lại như khi @RabbitListener ném exception trong container.

## 5. Nhận kiểu generic bằng ParameterizedTypeReference

Một DTO đơn thường có thể xác định bằng type header **__TypeId__**. Với JSON array hoặc object có generic, chỉ nhận **Object** có thể tạo cấu trúc **List/Map** chứa những phần tử không phải DTO.

Ví dụ body:

~~~json
[
  {"eventId": "evt-201", "orderId": "ORD-201", "totalAmount": 1000},
  {"eventId": "evt-202", "orderId": "ORD-202", "totalAmount": 2000}
]
~~~

Để cung cấp kiểu đích **List&lt;OrderCreatedEvent&gt;**, có thể dùng **ParameterizedTypeReference** khi **MessageConverter** hỗ trợ **SmartMessageConverter**:

~~~java
import com.example.contracts.orders.OrderCreatedEvent;
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<OrderCreatedEvent>> type =
        new ParameterizedTypeReference<>() {};

List<OrderCreatedEvent> events =
        rabbitTemplate.receiveAndConvert(
                "orders.created.receive", type);

if (events != null) {
    for (OrderCreatedEvent event : events) {
        System.out.println(event.orderId());
    }
}
~~~

**Điều kiện sử dụng:**

- Converter của RabbitTemplate phải hỗ trợ **SmartMessageConverter** và hiểu type hint (chẳng hạn Jackson JSON converter tương ứng).
- Body phải thực sự là **JSON array** của event phù hợp; không dùng type List cho message chứa một object JSON đơn.
- Nếu converter không hỗ trợ typed conversion, API có thể báo lỗi thay vì tự suy ra generic an toàn.
- Type hint do caller cung cấp không thay thế việc kiểm tra **schemaVersion, contentType, field bắt buộc và giới hạn kích thước**.

**Lựa chọn kiến trúc:** trong RabbitMQ, phần lớn event nên publish **mỗi message chứa một event** để ACK/retry độc lập. Gói một list lớn trong một message khiến một phần tử lỗi có thể buộc xử lý lại cả batch và làm message nặng hơn.

## 6. contentType, contentEncoding và type headers

Chuyển kiểu JSON không chỉ nhìn body. Với converter, ba nguồn thông tin thường quan trọng:

| Metadata | Mục đích | Ví dụ |
| --- | --- | --- |
| **contentType** | Xác định dữ liệu có phải JSON hoặc format phù hợp | **application/json** |
| **contentEncoding** / charset | Biết cách giải mã chuỗi byte | **UTF-8** |
| **__TypeId__** | Gợi ý kiểu Java/alias theo quy ước Spring AMQP | **order.created.v1** |
| **__ContentTypeId__**, **__KeyTypeId__** | Gợi ý kiểu phần tử của collection/map | Alias hoặc class name |
| **schemaVersion** | Hợp đồng nghiệp vụ để validation/evolution | **1**, **2** |

### 6.1. RabbitMQ không tự sinh type header Java

Header **__TypeId__** thường do **Spring JSON converter phía publisher** tạo. Nếu producer là Go, Node.js, Python hoặc một hệ thống không dùng Spring, message có thể chỉ chứa JSON và **không có __TypeId__**.

Khi ấy, receiveAndConvert() không có DTO đích tường minh có thể chuyển thành **Map** hoặc gặp khó khăn chọn class. Giải pháp:

1. Cấu hình **defaultType** nếu queue chỉ nhận một contract rõ ràng.
2. Sử dụng overload với **ParameterizedTypeReference** khi converter hỗ trợ.
3. Nhận raw **Message** và parse bằng schema registry/serializer thống nhất.
4. Dùng **alias mapping** được hai phía thỏa thuận, không phụ thuộc tên class producer.

### 6.2. Alias ổn định hơn tên package Java

Nếu producer gửi **__TypeId__=com.producer.internal.OrderCreatedEvent**, consumer chưa chắc có class tương ứng. Alias **order.created.v1** có thể được ánh xạ sang DTO nội bộ của từng service, dù package khác nhau.

**DefaultClassMapper** cho phép **setIdClassMapping**, **setDefaultType**, **setTrustedPackages**. Các header Java type nằm ở tầng chuyển đổi, không nên nhầm với **eventType** và **schemaVersion** của hợp đồng nghiệp vụ.

### 6.3. Trusted packages và dữ liệu từ publisher

**Type headers là dữ liệu có thể do người gửi điều khiển.** Với JSON class mapping, chỉ cho phép package dự kiến, không khắc phục lỗi bằng cách mở rộng **trustedPackages("*")** trong môi trường không kiểm soát nguồn gửi.

Allowlist package **không phải** xác thực người gửi. Vẫn phải kiểm soát quyền publish trên vhost/exchange, dùng TLS khi thích hợp, giới hạn kích thước message và validate DTO trước khi ghi DB hay gọi API bên ngoài.

### 6.4. Vì sao @RabbitListener có thể hoạt động nhưng receiveAndConvert lại không?

~~~java
@RabbitListener(queues = "orders.created.receive")
public void onEvent(OrderCreatedEvent event) {
    // Spring có thể suy ra type từ chữ ký method này.
}
~~~

Với listener method, Spring có thể **suy ra kiểu đích OrderCreatedEvent từ tham số method**, tùy converter và cấu hình TypePrecedence. Trong khi đó, **receiveAndConvert("orders.created.receive")** không có method argument để suy luận; nó chủ yếu dựa vào converter, type headers, defaultType hoặc kiểu do caller cung cấp.

Vì vậy đừng chẩn đoán “converter hỏng” chỉ bằng việc thấy một phương pháp nhận được DTO còn phương pháp kia trả Map/byte[]: **bối cảnh lựa chọn kiểu đích khác nhau**.

## 7. Lỗi chuyển đổi và thời điểm ACK: nguy cơ mất message

Trong quá trình receiveAndConvert, có thể gặp:

- JSON sai cú pháp.
- **contentType** không khớp body hoặc converter không phù hợp.
- Type header trỏ đến alias/class không được phép hoặc không có trên classpath.
- DTO thiếu constructor/creator hoặc có trường bắt buộc sai định dạng.
- Dữ liệu JSON parse được nhưng vi phạm quy tắc nghiệp vụ.

### 7.1. Phân biệt các loại lỗi

| Tình huống | Kết quả | Có nên retry ngay cùng message? |
| --- | --- | --- |
| Queue trống trong thời gian chờ | **null** | Không phải lỗi; quay lại chu kỳ polling |
| Broker tạm mất kết nối | **AmqpException** hoặc lỗi connection | Retry kết nối có backoff và giới hạn |
| Body sai JSON, converter báo lỗi | **MessageConversionException** hoặc lỗi chuyển đổi tương ứng | Không retry vô hạn cùng payload |
| Deserialize thành kiểu không mong đợi | Có thể là Map/byte[] hoặc lỗi cast | Sửa converter/contract, không coi là lỗi mạng |
| DTO hợp lệ nhưng DB tạm thời offline | Lỗi nghiệp vụ/hạ tầng | Cần retry có kiểm soát **và giữ được message** |
| Publisher gửi event trùng | Hai message hợp lệ cùng eventId | Idempotent consumer, không dựa vào redelivered |

### 7.2. Tại sao try/catch trong pollOnce chưa đủ?

Với đường nhận không giao dịch thông thường, **RabbitTemplate có thể ACK/lấy message khỏi queue trong bước receive, trước khi code ứng dụng hoàn tất conversion và xử lý nghiệp vụ**. Nếu converter hoặc handler ném exception, một vòng retry chỉ gọi lại receiveAndConvert **không bảo đảm lấy lại chính message lỗi**.

~~~text
T0  RabbitTemplate nhận message M từ queue
T1  Message M được xác nhận/lấy khỏi queue theo cơ chế của template
T2  MessageConverter cố parse body của M
T3  Lỗi JSON / type mapping
T4  Ứng dụng catch exception
T5  Poll tiếp: không bảo đảm M còn trên queue
~~~

**Đừng nhầm nhận một message với xử lý thành công về mặt nghiệp vụ.** Để hệ thống đáng tin cậy, cần thiết kế **acknowledgement gắn với kết quả xử lý** hoặc kênh xử lý lỗi bền vững.

### 7.3. Ba lựa chọn cho workload quan trọng

1. **Ưu tiên @RabbitListener** với acknowledge mode phù hợp. Container có thể ACK sau khi handler xử lý thành công, hoặc NACK/reject theo error handler và chính sách retry/DLQ.
2. **Dùng transaction/channel được quản lý phù hợp** cho polling trong các yêu cầu cần rollback theo phạm vi AMQP, hiểu rõ giới hạn đối với database transaction và hiệu năng. Không mặc nhiên coi **channelTransacted=true** là transaction phân tán nguyên tử với DB.
3. **Xây low-level consumption có manual ACK** nếu buộc phải kiểm soát trực tiếp từng bước. Phải ACK/NACK trên đúng channel và deliveryTag, xử lý lifecycle khi connection đứt, prefetch và exception. Cách này thường phức tạp hơn listener container.

**Không nên chỉ dùng receiveAndConvert + catch exception + RabbitTemplate retry rồi khẳng định có at-least-once processing.** Template retry chủ yếu giải quyết lỗi thao tác hạ tầng; nó không thể tự khôi phục một message đã được ACK và mất khỏi queue.

### 7.4. Trường hợp lỗi poison message

Một message chứa **schemaVersion=999** trong khi consumer chỉ hiểu phiên bản 1 và 2 là lỗi **không tự phục hồi**. Nếu cứ requeue liên tục, có thể hình thành hot loop.

Thiết kế đề xuất:

- Phân loại lỗi **permanent** (schema, JSON, quyền) so với **transient** (DB, API tạm lỗi).
- Retry transient với **số lần hữu hạn**, backoff và metric.
- Với lỗi permanent, lưu metadata và chuyển message tới **dead-letter queue** hoặc error queue được quản lý.
- Không log payload nhạy cảm; giữ **eventId**, **correlationId**, routing key, nguyên nhân lỗi để điều tra.

Việc lỗi conversion xảy ra **trước khi @RabbitListener method được gọi** cũng cần được xử lý ở tầng **container/error handler**, thay vì mong try/catch bên trong listener bắt được mọi lỗi.

## 8. Polling hay @RabbitListener?

| Yếu tố | **RabbitTemplate.receiveAndConvert()** | **@RabbitListener** |
| --- | --- | --- |
| Kiểu chạy | Ứng dụng **chủ động gọi**, thường từng lần | Container đăng ký consumer và gọi method khi có message |
| Cách lấy message | Polling/receive, có timeout tùy cấu hình | Push delivery qua consumer callback của broker |
| Độ đồng thời | Do code/scheduler của bạn tự quản lý | Container quản lý concurrent consumers |
| Chuyển đổi | MessageConverter của RabbitTemplate | Converter của listener container/adapter và type inference |
| Kiểu đích | Type header/defaultType/type hint; nếu không có có thể là Object | Có thể suy ra từ tham số listener |
| ACK/lỗi nghiệp vụ | Cần đặc biệt chú ý thời điểm message bị ACK và phần code chạy sau receive | Có AcknowledgeMode, error handler, reject/requeue, retry interceptor |
| Retry/DLQ | Phải thiết kế tường minh, tránh mất message đã lấy | Dễ tích hợp retry/recoverer/DLX theo container |
| Use case | Công cụ nội bộ, thao tác batch có kiểm soát, polling theo nhịp hoặc demo | Worker xử lý liên tục, workload nghiệp vụ cần tin cậy |

**Khuyến nghị:** dùng **@RabbitListener** cho một consumer sản xuất xử lý hàng đợi liên tục, cần quản lý ACK, retry, backpressure, concurrency và graceful shutdown. Dùng **receiveAndConvert()** khi ứng dụng thực sự muốn chủ động kéo một message, hiểu giới hạn về ACK và có phương án xử lý lỗi phù hợp.

### So sánh code

~~~java
// Polling: ứng dụng quyết định khi nào lấy một message.
Object value = rabbitTemplate.receiveAndConvert("orders.created.receive");
if (value != null) {
    // Tự chuyển sang workflow xử lý và điều phối polling tiếp.
}
~~~

~~~java
// Listener: container nhận và gọi method khi có message.
@RabbitListener(
        queues = "orders.created.receive",
        containerFactory = "orderListenerFactory")
public void onOrderCreated(OrderCreatedEvent event) {
    // Xử lý nghiệp vụ; ném exception nếu thất bại.
}
~~~

Ví dụ listener giả định **orderListenerFactory** đã được cấu hình với JSON converter và chính sách ACK phù hợp. **Không chạy polling consumer và @RabbitListener cùng queue rồi tưởng cả hai đều nhận mỗi event**: chúng là competing consumers; mỗi message thường được giao cho một trong các consumer.

### 8.1. Nếu có cả polling và listener cùng lúc

~~~mermaid
flowchart TB
    Q[("orders.created.receive")] --> P["Polling RabbitTemplate"]
    Q --> L["@RabbitListener container"]
    P --> A["Lấy một số message"]
    L --> B["Nhận các message khác"]
~~~

Tăng số consumer không tự biến queue thành một broadcast stream. Nếu mỗi service phải nhận **bản sao** của một event, cần **queue riêng cho mỗi nhóm** và các binding tương ứng với exchange.

## 9. Thiết kế xử lý idempotent sau khi chuyển đổi

Giả sử event **OrderCreated(eventId=evt-101)** bị publish hai lần do publisher mất confirm và retry. Consumer polling hoặc listener đều có thể thấy hai bản độc lập, ngay cả khi **redelivered=false**.

Một bảng chống trùng đơn giản (PostgreSQL):

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Đoạn xử lý nghiệp vụ minh họa:

~~~java
@Transactional
public void saveOrderProjection(OrderCreatedEvent event) {
    int inserted = jdbcTemplate.update(
        """
        INSERT INTO processed_events (consumer_name, event_id)
        VALUES (?, ?)
        ON CONFLICT DO NOTHING
        """,
        "order-projection", event.eventId());

    if (inserted == 0) {
        return; // Sự kiện này đã được xử lý ở consumer group này.
    }

    orderProjectionRepository.insertFromEvent(event);
}
~~~

Ở đây **jdbcTemplate** và **orderProjectionRepository** là các thành phần do ứng dụng định nghĩa. **Insert processed_events và cập nhật projection phải nằm trong cùng DB transaction** để tránh ghi nhận processed nhưng tác động nghiệp vụ thất bại.

Với tác động bên ngoài DB như gửi email hoặc gọi cổng thanh toán, transaction trên không tự bao trùm hệ thống ngoài; cân nhắc **notification outbox, idempotency key, reconciliation** và kết quả xử lý từng bước.

**Idempotency giúp chống tác động trùng**, nhưng **không khôi phục message bị ACK rồi mất do lỗi conversion**. Cần cả chính sách ACK/retry/DLQ phù hợp.

## 10. Observability: phân biệt không có message và nhận lỗi

Vì receiveAndConvert thường được gọi trong lịch polling, nên đo các chỉ số:

| Metric | Điều theo dõi | Ý nghĩa |
| --- | --- | --- |
| **poll_attempt_total** | Số lần cố đọc queue | Cho thấy nhịp polling |
| **poll_empty_total** | Số lần nhận null | Có thể bình thường khi queue vắng message |
| **receive_error_total** | Lỗi network, channel hoặc broker | Phát hiện vấn đề hạ tầng |
| **conversion_error_total** | JSON/type mapping không hợp lệ | Phát hiện poison message và lỗi schema |
| **business_error_total** | Logic nghiệp vụ/DB thất bại | Không được gộp thành conversion error |
| **poll_duration_seconds** | Thời gian chờ mỗi lần receive | Giám sát timeout và thread bị giữ |
| **queue_ready / unacked** | Backlog và message đang xử lý | Kiểm tra khả năng tiêu thụ |
| **duplicate_event_total** | EventId bị bỏ qua vì đã xử lý | Đo publisher retry/redelivery |
| **DLQ/error_queue_count** | Message lỗi chưa được xử lý | Hỗ trợ vận hành và replay có kiểm soát |

**Queue trống không phải sự cố** nếu polling theo nhịp và workload thưa. Ngược lại, nếu queue có backlog nhưng poll_empty_total vẫn tăng, cần kiểm tra **đúng queue/vhost**, consumer khác đang lấy message, trạng thái message unacked và quyền truy cập.

Log hữu ích nên có **queueName**, **eventId**, **schemaVersion**, **contentType**, loại converter, thời gian xử lý và correlationId khi có. Không log toàn bộ body nếu chứa dữ liệu người dùng nhạy cảm.

## 11. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi receiveAndConvert để “xem thử” queue production | Message có thể bị tiêu thụ | Dùng môi trường test, mirror/audit queue hoặc công cụ quản trị phù hợp |
| Nghĩ nhận **null** là broker lỗi | Báo động giả, retry quá mức | Phân biệt empty polling với exception |
| Ép kiểu trực tiếp **(OrderCreatedEvent)** khi đang dùng SimpleMessageConverter | **ClassCastException** | Dùng JSON converter hoặc kiểm tra kiểu trước |
| Chỉ gắn **contentType=application/json** mà mong DTO xuất hiện | Vẫn nhận byte[] với converter không hỗ trợ JSON | Cấu hình JSON converter ở phía nhận |
| Producer và consumer dùng type mapper khác nhau | Alias không resolve, Map hoặc conversion exception | Thống nhất alias, schemaVersion và trusted packages |
| Dùng **trustedPackages("*")** để chữa lỗi | Mở rộng type resolution không cần thiết | Dùng allowlist và contract rõ ràng |
| Quên rằng receiveAndConvert tiêu thụ message | Mất message khi validate/DB lỗi sau receive | Ưu tiên listener có ACK/error policy hoặc thiết kế transactional/manual ack |
| Vừa polling vừa chạy @RabbitListener cùng queue | Các consumer chia nhau message không đoán trước | Chọn một cách consume hoặc tách queue |
| Poll liên tục khi queue trống | Tốn CPU, connection/channel, tăng tải broker | Timeout hữu hạn, backoff, scheduler |
| Chỉ retry exception mà không kiểm tra ACK | Không bảo đảm lấy lại message cũ | Thiết kế lifecycle nhận và acknowledgement đúng |
| Cho rằng redelivered=false là message đầu tiên của event | Bỏ sót trùng do publisher retry | Dedupe theo eventId |
| Không đo conversion errors | Poison message âm thầm làm mất dữ liệu | Metric, cảnh báo và error queue/DLQ |

## 12. Bài tập thực hành

### Bài 1 — Nhận String và body bytes

Khai báo **orders.events** và queue **orders.created.receive** theo mục 4. Gửi một message String bằng **convertAndSend** với SimpleMessageConverter và đọc bằng **receiveAndConvert**. In class thực tế của object. Sau đó gửi một message JSON raw có contentType **application/json** và nhận bằng SimpleMessageConverter; giải thích vì sao kết quả có thể là byte[].

### Bài 2 — Timeout và null

Gọi **receiveAndConvert(queue, 0)** khi queue trống, đo thời gian trả về; tiếp theo dùng **receiveAndConvert(queue, 2000)**. So sánh thời gian chờ. Gửi một message khi đang chờ và xem kết quả. Thử tên queue không tồn tại để phân biệt **null** với exception.

### Bài 3 — DTO JSON và type alias

Cấu hình Jackson2JsonMessageConverter cùng DefaultClassMapper như mục 4. Gửi **OrderCreatedEvent**, nhận bằng receiveAndConvert, kiểm tra class thực tế và các trường. Quan sát **__TypeId__=order.created.v1** bằng cách đọc raw Message trong một lần gửi khác trên queue test.

### Bài 4 — Kiểu generic

Gửi một JSON array chứa hai order events, thử dùng **receiveAndConvert(queue)** rồi so sánh với overload có **ParameterizedTypeReference&lt;List&lt;OrderCreatedEvent&gt;&gt;**. Ghi lại điều kiện converter cần hỗ trợ và vì sao một event/message thường dễ retry độc lập hơn một danh sách.

### Bài 5 — Lỗi conversion và mất message

Trên queue thử nghiệm, gửi JSON sai cú pháp. Gọi receiveAndConvert bằng JSON converter, ghi lại exception. Kiểm tra queue còn message đó hay không sau lỗi, đối chiếu ACK/transaction configuration. **Không thực hiện thử nghiệm này trên queue dữ liệu thật.** Đề xuất cách bảo vệ bằng listener error handler và DLQ.

### Bài 6 — Polling so với listener

Tạo hai consumer đọc cùng queue: một dùng polling, một dùng @RabbitListener. Publish 20 event, ghi nhận consumer nào nhận từng event. Giải thích vì sao tổng số event được phân phối cho hai consumer thay vì mỗi consumer đều có 20 bản.

### Bài 7 — Chống xử lý trùng

Publish hai lần cùng **eventId** nhưng khác attempt ở producer; consumer ghi processed_events và projection trong một DB transaction. Xác minh chỉ có một thay đổi trạng thái nghiệp vụ. Giải thích vì sao cơ chế này không thay thế retry/DLQ khi conversion lỗi.

### Câu hỏi tự đánh giá

1. **receive()** khác **receiveAndConvert()** ở bước nào?
2. Vì sao **receiveAndConvert()** không nhận exchange/routing key?
3. Khi nào nhận **null**, khi nào nhận **AmqpException**?
4. SimpleMessageConverter có tự biến **application/json** thành DTO không?
5. Tại sao **@RabbitListener(OrderCreatedEvent event)** có thể chuyển kiểu được dù không có type header, còn receiveAndConvert không có type hint lại trả Map?
6. Khi nào nên dùng **ParameterizedTypeReference**? Converter cần có khả năng gì?
7. Vì sao một lỗi JSON trong polling không tự động được retry như exception từ method của @RabbitListener?
8. Nếu producer gửi hai bản cùng eventId nhưng redelivered=false, consumer chống trùng ra sao?
9. Nếu bạn cần bảo đảm việc xử lý DB hoàn tất trước ACK, bạn sẽ chọn polling đơn giản hay listener có cơ chế acknowledgement phù hợp?

## 13. Tài liệu tham khảo chính thức

- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages.html): RabbitTemplate.receive/receiveAndConvert, timeout, polling và listener.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): SimpleMessageConverter, JSON converter, contentType và type mapping.
- [Spring AMQP — Annotated Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): @RabbitListener, conversion và method arguments.
- [Spring AMQP API — RabbitTemplate](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/rabbit/core/RabbitTemplate.html): các overload receiveAndConvert, receiveTimeout và MessageConverter.
- [Spring AMQP API — MessageConverter](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/support/converter/MessageConverter.html): toMessage và fromMessage.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): consumer ACK/NACK, redelivery và publisher confirms.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): competing consumers, queue properties và đặc tính tiêu thụ.

---

**Ghi nhớ:** **RabbitTemplate.receiveAndConvert() là polling lấy message từ queue rồi chuyển body thành Java object bằng MessageConverter**. Khi queue trống có thể trả **null**; kiểu dữ liệu nhận được phụ thuộc **contentType, encoding, converter, type headers và type hint**. **SimpleMessageConverter không tự biến JSON thành DTO**; muốn typed JSON cần converter phù hợp. **Polling không phải peek** và lỗi conversion/DB sau khi message được lấy có thể gây mất dữ liệu nếu ACK không được thiết kế đúng. Với workload quan trọng, ưu tiên **@RabbitListener có acknowledgement, retry/DLQ và idempotency** rõ ràng.
