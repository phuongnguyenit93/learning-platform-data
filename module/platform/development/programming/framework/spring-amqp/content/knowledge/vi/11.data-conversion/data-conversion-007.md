# Type headers, DefaultClassMapper và trusted packages

## Mục tiêu bài học

Trong module **SPRING_AMQP**, ứng dụng có thể dùng **RabbitTemplate** gửi một đối tượng Java và **@RabbitListener** nhận một DTO thay vì tự đọc byte array. Spring AMQP thực hiện chuyển đổi thông qua **MessageConverter**. Với JSON, chuyển đổi từ byte thành đối tượng còn cần biết **kiểu Java đích**. Đây là lý do xuất hiện các **type headers**, **DefaultClassMapper** và cấu hình **trusted packages**.

Sau bài học thuộc chương **Chuyển đổi dữ liệu**, bạn có thể:

1. Phân biệt JSON body, AMQP properties, **__TypeId__**, **__ContentTypeId__**, **__KeyTypeId__** và trường **eventType** của nghiệp vụ.
2. Hiểu cách Spring AMQP ghi/đọc type headers trong JSON converter và vì sao không nên phụ thuộc vào tên package Java giữa các service.
3. Dùng **DefaultClassMapper** để ánh xạ alias sang DTO, khai báo **defaultType** và **trustedPackages**.
4. Phân biệt **DefaultClassMapper** với **DefaultJackson2JavaTypeMapper** (nhánh Jackson 2) hoặc **DefaultJacksonJavaTypeMapper** (nhánh Jackson 3), đặc biệt khi có generic và type precedence.
5. Cấu hình nhất quán producer **RabbitTemplate** và consumer **@RabbitListener**, đồng thời thiết kế xử lý an toàn cho message sai kiểu hoặc không đáng tin cậy.
6. Gắn chuyển đổi JSON với retry, dead-letter và idempotency khi xây hệ thống xử lý bất đồng bộ đáng tin cậy.

## 1. Type headers nằm ở đâu trong một AMQP message?

Trong Spring AMQP, **org.springframework.amqp.core.Message** gồm **byte[] body** và **MessageProperties**. Khi gửi bằng JSON converter, body chứa JSON, còn MessageProperties thường chứa:

- **contentType**: ví dụ **application/json**; cho biết định dạng body.
- **contentEncoding** hoặc charset của contentType: ví dụ **UTF-8**.
- **headers**: các key/value phụ trợ như **__TypeId__**, **__ContentTypeId__**, **__KeyTypeId__**, cùng custom header của ứng dụng.
- **messageId**, **correlationId**, **deliveryMode** và các thuộc tính khác nếu được đặt.

Ví dụ:

~~~text
RabbitMQ delivery
├── body (byte[])
│   └── {"eventId":"evt-101","orderId":"ORD-9","total":150000}
└── MessageProperties
    ├── contentType: application/json
    ├── contentEncoding: UTF-8
    ├── messageId: evt-101
    ├── correlationId: checkout-9
    └── headers
        ├── __TypeId__: order.created.v1
        └── schemaVersion: 1
~~~

**__TypeId__ không phải thuộc tính bắt buộc của RabbitMQ broker.** Đây là quy ước metadata của **Spring AMQP JSON converter** giúp consumer chọn kiểu Java. RabbitMQ không dùng header ấy để tự deserialize JSON và cũng không tự bảo đảm nội dung header chính xác.

~~~mermaid
flowchart LR
    D["OrderCreatedV1 object"] --> C["JSON MessageConverter"]
    C --> M["AMQP Message<br/>body JSON + __TypeId__"]
    M --> T["RabbitTemplate"]
    T --> X{"Exchange"}
    X -->|"routing key + binding"| Q[("Queue")]
    Q --> L["@RabbitListener<br/>JSON converter"]
    L --> O["OrderCreatedV1 object"]
~~~

**Exchange, routing key và binding** giải quyết **message tới queue nào**. **Type headers và converter** giải quyết **byte[] được hiểu thành kiểu dữ liệu nào**. Hai cơ chế thuộc các tầng khác nhau.

## 2. Ba type headers quan trọng

Spring AMQP có quy ước tên header cho type mapper:

| Header | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| **__TypeId__** | Kiểu tổng thể của payload (hoặc container) | **order.created.v1**, **com.example.events.OrderCreatedV1**, **java.util.ArrayList** |
| **__ContentTypeId__** | Kiểu phần tử bên trong một collection hoặc kiểu value của map, khi mapper có đủ thông tin | **com.example.events.OrderCreatedV1** |
| **__KeyTypeId__** | Kiểu key của map, khi cần mô tả | **java.lang.String** |

**Không phải mọi message JSON đều có đủ ba header.** Message của một DTO đơn thường chỉ cần **__TypeId__**; type mapper cho collection/map có thể dùng thêm **__ContentTypeId__** và **__KeyTypeId__**. Một số generic type không được thể hiện đầy đủ nếu producer chỉ có object đã bị mất thông tin generic khi chạy.

Ví dụ mô phỏng metadata, không phải wire format bắt buộc cho mọi converter:

~~~text
Payload OrderCreatedV1:
  __TypeId__: order.created.v1

Payload List<OrderCreatedV1>:
  __TypeId__: java.util.ArrayList
  __ContentTypeId__: com.example.events.OrderCreatedV1

Payload Map<String, OrderCreatedV1>:
  __TypeId__: java.util.HashMap
  __KeyTypeId__: java.lang.String
  __ContentTypeId__: com.example.events.OrderCreatedV1
~~~

Type headers **khác** các thông tin sau:

| Thông tin | Mục đích |
| --- | --- |
| **eventType: order.created** | Ý nghĩa sự kiện theo hợp đồng nghiệp vụ; có thể nằm trong body/header |
| **schemaVersion: 1** | Phiên bản của cấu trúc dữ liệu; giúp tương thích khi nâng cấp |
| **__TypeId__: order.created.v1** | Token mà type mapper có thể ánh xạ thành lớp Java |
| **routingKey: order.created** | Chuỗi producer gửi cho exchange để định tuyến message |
| **messageId: evt-101** | Định danh message/event phục vụ truy vết và xử lý trùng |
| **deliveryTag** | Định danh của một lần giao trên channel hiện tại, dùng ACK/NACK |

Một sự kiện có thể dùng cùng chuỗi cho eventType và alias type, nhưng đó là **quyết định thiết kế** chứ không phải quy tắc mà RabbitMQ tự áp dụng.

## 3. Type headers xuất hiện như thế nào?

### 3.1. Producer dùng JSON converter

Với JSON converter phù hợp, lời gọi sau có thể serialize Java object thành JSON và gắn metadata xác định kiểu:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events",        // exchange
        "order.created",        // routing key
        new OrderCreatedV1("evt-101", "ORD-9", 150_000));
~~~

Nếu dùng type mapper mặc định, header **__TypeId__** thường là **tên lớp Java đầy đủ** (fully qualified class name), ví dụ **com.shop.orders.dto.OrderCreatedV1**. Nếu cấu hình ánh xạ alias, converter có thể dùng token ổn định như **order.created.v1**.

Điều này xảy ra trong **MessageConverter**, không phải một tính năng của RabbitTemplate đơn lẻ. Nếu RabbitTemplate vẫn dùng **SimpleMessageConverter** mặc định, bạn không thể mặc nhiên kỳ vọng DTO bất kỳ được serialize thành JSON hoặc type header được gắn đúng.

### 3.2. Consumer giải mã

Khi nhận message, JSON converter kết hợp:

1. **contentType** và encoding để giải mã byte thành JSON;
2. **kiểu đã suy ra từ tham số listener** nếu có và đủ điều kiện ưu tiên;
3. **type headers** cùng cấu hình class/type mapper nếu cần;
4. **defaultType** hoặc cách xử lý fallback phù hợp khi thiếu thông tin kiểu.

Lớp được chọn phải có thể được JSON library deserialize theo cấu hình. Có type header hợp lệ vẫn có thể lỗi nếu body thiếu trường bắt buộc, tên trường không khớp, schema version chưa hỗ trợ hoặc constructor/creator không phù hợp.

## 4. DefaultClassMapper làm gì?

**org.springframework.amqp.support.converter.DefaultClassMapper** triển khai interface **ClassMapper** và ánh xạ giữa **Class&lt;?&gt;** và type ID trong **MessageProperties**.

| API | Hướng tác động | Mục đích |
| --- | --- | --- |
| **fromClass(clazz, properties)** | Java → metadata | Ghi type ID cho class khi publish |
| **toClass(properties)** | Metadata → Java | Tìm class đích từ type header lúc nhận |
| **setIdClassMapping(map)** | Hai chiều | Ánh xạ alias ổn định ↔ lớp Java |
| **setDefaultType(clazz)** | Khi thiếu type ID | Chọn kiểu mặc định nếu inbound không có thông tin kiểu |
| **setTrustedPackages(packages...)** | Kiểm tra class resolution | Giới hạn package được phép dùng khi diễn giải class name từ message |
| **afterPropertiesSet()** | Khởi tạo mapper | Dựng reverse mapping khi mapper không được Spring quản lý |

Nếu **không khai báo alias**, mapper có thể ghi tên class đầy đủ vào **__TypeId__**. Nếu **setIdClassMapping** có entry cho class cụ thể, khi publish class ấy, converter dùng token tương ứng; khi nhận token ấy, mapper tra lại class đã đăng ký.

~~~text
     Class ở producer             __TypeId__              Class ở consumer
  OrderCreatedV1.class  --->   order.created.v1   --->   OrderCreatedV1.class

  package producer có thể khác tên package consumer,
  miễn hai phía thống nhất hợp đồng alias và body JSON.
~~~

### 4.1. Ánh xạ alias thay vì gửi tên class Java

Giả sử producer có class **com.shop.producer.events.OrderCreatedV1** và consumer có class **com.shop.audit.contract.OrderCreatedV1**. Nếu để **__TypeId__** là tên class của producer, consumer có thể không có class ấy và báo lỗi.

Thay vào đó, hai ứng dụng cùng thống nhất:

~~~text
__TypeId__: order.created.v1
contentType: application/json
~~~

Producer ánh xạ token sang class **của producer**, consumer ánh xạ cùng token sang DTO **của consumer**. Hai class không bắt buộc cùng package hoặc cùng tên, nhưng body JSON cần tương thích về trường và ngữ nghĩa.

**Không dùng alias để che giấu thiếu tương thích schema.** Nếu một phía hiểu **order.created.v1** là số tiền theo VND còn phía kia hiểu theo cent, message vẫn sai nghiệp vụ dù giải mã thành công.

### 4.2. defaultType: dành cho một loại message đã biết

Một queue chỉ nhận **OrderCreatedV1** từ hệ thống ngoài đôi khi có JSON body nhưng **không có __TypeId__**. Có thể cấu hình:

~~~java
DefaultClassMapper mapper = new DefaultClassMapper();
mapper.setDefaultType(OrderCreatedV1.class);
~~~

Khi **không có type header**, mapper dùng **OrderCreatedV1.class** làm lựa chọn mặc định. **defaultType không tự sửa type header sai hoặc không đáng tin**. Trên queue chứa nhiều loại event, ép tất cả về một kiểu có thể gây lỗi hoặc diễn giải sai dữ liệu; nên dùng hợp đồng rõ ràng và ánh xạ alias.

### 4.3. Giới hạn của DefaultClassMapper

DefaultClassMapper tập trung vào ánh xạ **một Class** qua type ID. Với **generic** như **List&lt;OrderCreatedV1&gt;**, **Map&lt;String, OrderCreatedV1&gt;** hoặc yêu cầu phân biệt **kiểu suy ra** từ listener với **kiểu ghi trên header**, Spring AMQP còn có type mapper dành riêng cho Jackson:

- **Spring AMQP 3.x / Jackson 2:** **DefaultJackson2JavaTypeMapper** và **Jackson2JavaTypeMapper**.
- **Spring AMQP 4.x / Jackson 3:** **DefaultJacksonJavaTypeMapper** và **JacksonJavaTypeMapper**.

Các mapper này có thể dựng thông tin **JavaType** chi tiết hơn và điều khiển **TypePrecedence**. Không nên nghĩ rằng chỉ cấu hình DefaultClassMapper sẽ tự giải quyết mọi generic, collection và polymorphic DTO.

## 5. trusted packages: giới hạn việc chọn kiểu khi deserialize

**Type headers là dữ liệu do phía gửi cung cấp.** Nếu một publisher không đáng tin có thể đặt **__TypeId__** thành tên class bất kỳ, converter cố giải mã vào kiểu đó có thể mở ra rủi ro bảo mật. Spring AMQP cung cấp **trustedPackages** trên JSON class/type mapper để hạn chế các package được phép ánh xạ từ type metadata.

### 5.1. Cấu hình tối thiểu theo danh sách cho phép

~~~java
DefaultClassMapper mapper = new DefaultClassMapper();
mapper.setTrustedPackages(
        "com.example.contracts.orders",
        "java.lang",
        "java.util");
~~~

Trong đó:

- **com.example.contracts.orders**: package chứa DTO hợp đồng mà ứng dụng dự kiến nhận.
- **java.lang** và **java.util**: các package nền tảng cần thiết cho những kiểu tương ứng nếu có; kiểm tra nhu cầu thực tế và cách mapper xử lý chúng.
- **setTrustedPackages("*")**: cho phép **mọi package**, làm mất ý nghĩa ràng buộc package; **không nên dùng** để chữa lỗi chuyển đổi trên môi trường thật.

**Defaults và cách xử lý được phép có thể khác theo converter/constructor/nhánh thư viện.** Tài liệu mô tả converter thường giới hạn type resolution ở **java.lang** và **java.util**, nhưng một số constructor/API có cấu hình trust khác. Hãy đặt allowlist **tường minh** cho converter/type mapper đang sử dụng và kiểm tra đúng artifact phiên bản.

### 5.2. Trusted package không phải xác thực người gửi

Ngay cả khi class thuộc package được tin cậy, payload vẫn có thể chứa:

- dữ liệu sai nghiệp vụ hoặc trường bắt buộc bị thiếu;
- JSON quá lớn hoặc lồng sâu gây tốn tài nguyên;
- giá trị giả mạo eventId, tenantId hoặc correlationId;
- schemaVersion chưa được consumer hỗ trợ;
- nội dung khiến tầng nghiệp vụ gọi API ngoài không mong muốn.

Vì vậy, **trustedPackages là một lớp phòng vệ cho type resolution, không phải kiểm soát truy cập, chữ ký số hay xác thực nghiệp vụ**. Cần giới hạn quyền publish của vhost/exchange, dùng TLS khi thích hợp, validate body, bảo vệ parser và đặt giới hạn kích thước message.

### 5.3. Alias mapping không đồng nghĩa khóa kín mọi type ID

**setIdClassMapping** cung cấp các token đã biết. Tuy nhiên, không nên mặc định rằng **mọi token không có trong map sẽ tự bị từ chối**: một mapper có thể tiếp tục thử diễn giải token thành tên class, tùy cấu hình trustedPackages.

Nếu yêu cầu hợp đồng nghiêm ngặt **chỉ nhận một tập alias**, ứng dụng nên kiểm tra **__TypeId__** so với allowlist nghiệp vụ (hoặc tự viết mapper/validator từ chối token lạ) trước khi deserialize hoặc trước khi xử lý. Không dựa duy nhất vào map alias để khẳng định bên ngoài không gửi được kiểu khác.

### 5.4. Không bật polymorphic default typing rộng

Nếu tự cấp **ObjectMapper** cho converter, không nên tùy tiện bật **Jackson default typing** trên dữ liệu từ RabbitMQ. Đây là một cơ chế chọn type khác, có nguy cơ mở rộng bề mặt deserialization không cần thiết. Với event nghiệp vụ, ưu tiên DTO đã biết, alias rõ ràng, schema version và allowlist; chỉ sử dụng polymorphism khi thật sự cần và có kiểm soát.

## 6. Ví dụ hoàn chỉnh: alias + trusted packages + RabbitTemplate + @RabbitListener

Ví dụ dùng **Java 17**, **Spring Boot 3.x**, **Spring AMQP 3.x** với **Jackson2JsonMessageConverter**. Các ví dụ Java dưới đây là những phần của cùng ứng dụng, giả định RabbitMQ đang chạy, đã cấu hình connection và user có quyền declare exchange/queue/binding.

### 6.1. Định nghĩa DTO dùng làm contract

~~~java
// OrderCreatedV1.java
package com.example.contracts.orders;

public record OrderCreatedV1(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

Event thực tế có thể cần thêm **occurredAt**, **currency**, **schemaVersion**, **aggregateVersion** và các field tùy hợp đồng. Ví dụ để ngắn gọn chỉ giữ ba thuộc tính. Record cần môi trường Java hỗ trợ và JSON converter đủ khả năng xử lý record.

### 6.2. Topology và converter sử dụng cùng một class mapper

~~~java
package com.example;

import com.example.contracts.orders.OrderCreatedV1;
import java.util.Map;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class OrderAmqpConfig {

    @Bean
    public TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    public Queue auditQueue() {
        return QueueBuilder.durable("orders.audit").build();
    }

    @Bean
    public Binding auditBinding(Queue auditQueue,
                                TopicExchange ordersExchange) {
        return BindingBuilder.bind(auditQueue)
                .to(ordersExchange)
                .with("order.created");
    }

    @Bean
    public DefaultClassMapper eventClassMapper() {
        DefaultClassMapper mapper = new DefaultClassMapper();
        mapper.setIdClassMapping(
                Map.of("order.created.v1", OrderCreatedV1.class));
        mapper.setTrustedPackages(
                "com.example.contracts.orders",
                "java.lang",
                "java.util");
        // Spring gọi afterPropertiesSet() vì đây là @Bean.
        return mapper;
    }

    @Bean
    public Jackson2JsonMessageConverter jsonEventConverter(
            DefaultClassMapper eventClassMapper) {
        Jackson2JsonMessageConverter converter =
                new Jackson2JsonMessageConverter();
        converter.setClassMapper(eventClassMapper);
        return converter;
    }

    @Bean
    public RabbitTemplate eventRabbitTemplate(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter jsonEventConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(jsonEventConverter);
        return template;
    }

    @Bean
    public SimpleRabbitListenerContainerFactory orderListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter jsonEventConverter) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jsonEventConverter);
        return factory;
    }
}
~~~

**Cần chú ý:**

- **setIdClassMapping(...)** ánh xạ **order.created.v1 → OrderCreatedV1.class**.
- **setTrustedPackages(...)** chỉ cho phép các package dự kiến; ví dụ này không dùng wildcard.
- **Spring quản lý bean DefaultClassMapper**, nên gọi lifecycle **afterPropertiesSet()** để khởi tạo chiều reverse mapping. Nếu tự tạo mapper ngoài Spring, phải gọi **afterPropertiesSet()** theo yêu cầu API.
- Producer template và consumer factory đều được cấu hình **cùng converter**, tránh hai phía dùng cách hiểu type header khác nhau.
- Để giữ riêng ví dụ, **eventRabbitTemplate** là bean được đặt tên. Nếu ứng dụng đã có RabbitTemplate hoặc listener factory khác, cần chọn bean/cấu hình phù hợp thay vì giả định cấu hình tự động sẽ luôn lấy đúng converter.

### 6.3. Producer gửi event

~~~java
package com.example;

import com.example.contracts.orders.OrderCreatedV1;
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Qualifier;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate template;

    public OrderEventPublisher(
            @Qualifier("eventRabbitTemplate") RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String orderId, long totalAmount) {
        String eventId = UUID.randomUUID().toString();
        OrderCreatedV1 event =
                new OrderCreatedV1(eventId, orderId, totalAmount);

        template.convertAndSend(
                "orders.events",
                "order.created",
                event,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    message.getMessageProperties().setHeader(
                            "schemaVersion", 1);
                    return message;
                });
    }
}
~~~

Converter serialize **OrderCreatedV1** thành JSON và dùng class mapper để gắn **__TypeId__=order.created.v1**. MessagePostProcessor thêm **messageId** và **schemaVersion**. **Routing key** vẫn là **order.created** do lời gọi convertAndSend quyết định; nó không tự lấy từ **__TypeId__**.

Khi phát lại cùng một event do timeout hoặc lỗi mạng, **eventId phải giữ nguyên** để consumer có thể nhận diện bản trùng. Ví dụ sinh UUID trong publish() nhằm minh họa, nhưng khi ứng dụng đã có event trong outbox thì cần lấy ID từ bản ghi outbox thay vì tạo UUID mới mỗi lần retry.

### 6.4. Consumer nhận DTO đã chuyển đổi

~~~java
package com.example;

import com.example.contracts.orders.OrderCreatedV1;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AuditOrderConsumer {

    @RabbitListener(
            queues = "orders.audit",
            containerFactory = "orderListenerFactory")
    public void onOrderCreated(OrderCreatedV1 event) {
        // Validate eventId/orderId/totalAmount trước khi lưu.
        // Ghi eventId vào DB cùng giao dịch với bản ghi audit
        // để chống xử lý trùng nếu broker redeliver.
        System.out.println("Audit order " + event.orderId());
    }
}
~~~

Ở đây **@RabbitListener** suy ra kiểu tham số **OrderCreatedV1**. Spring JSON converter cũng có alias mapping trùng kiểu nên việc giải mã nhất quán. **Không cần method tự parse JSON byte[]**.

Nếu ứng dụng có hai listener cùng nghe **orders.audit**, chúng là competing consumers; mỗi message được giao cho một consumer, không mặc nhiên cho cả hai. Muốn nhiều chức năng đều nhận một event, thiết kế queue riêng và binding phù hợp.

### 6.5. Quan sát type headers ở mức message thô

Khi cần chẩn đoán, có thể gọi converter trực tiếp:

~~~java
import com.example.contracts.orders.OrderCreatedV1;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;

OrderCreatedV1 event = new OrderCreatedV1(
        "evt-101", "ORD-9", 150_000);

Message raw = jsonEventConverter.toMessage(
        event, new MessageProperties());

System.out.println(raw.getMessageProperties().getContentType());
System.out.println(raw.getMessageProperties().getHeader("__TypeId__"));
System.out.println(raw.getBody().length);
~~~

Với cấu hình alias ở trên, header **__TypeId__** dự kiến có giá trị **order.created.v1**. Để kiểm tra dữ liệu nhận thực tế, có thể dùng **@RabbitListener** nhận **org.springframework.amqp.core.Message** hoặc RabbitMQ Management trong môi trường thử nghiệm. Tránh in raw body và headers nhạy cảm ra log production.

## 7. Type precedence: lúc nào header không được dùng?

Một điểm dễ gây nhầm lẫn: listener khai báo kiểu tham số cụ thể có thể khiến Spring **suy ra kiểu đích từ method signature**, và mặc định kiểu suy ra có thể được **ưu tiên hơn __TypeId__ do producer gửi**.

Giả sử producer gửi:

~~~text
body:       {"eventId":"evt-101","orderId":"ORD-9","totalAmount":150000}
__TypeId__: order.created.v1
~~~

Consumer có:

~~~java
@RabbitListener(queues = "orders.audit",
                containerFactory = "orderListenerFactory")
public void handle(OrderCreatedV1 event) {
    // Type có thể được suy ra từ tham số của method.
}
~~~

Trong trường hợp này, Spring biết trước **OrderCreatedV1** là kiểu đích. Vì thế **message thiếu __TypeId__ vẫn có thể được giải mã đúng**, nếu converter và JSON tương thích. Ngược lại, khi listener nhận **Object**, interface/abstract class hoặc dùng class-level listener với nhiều handler, việc lựa chọn type có thể phụ thuộc vào header và cấu hình bổ sung.

### 7.1. INFERRED so với TYPE_ID

| Chế độ | Ưu tiên chính | Khi phù hợp |
| --- | --- | --- |
| **TypePrecedence.INFERRED** (mặc định) | Kiểu suy ra từ method argument khi kiểu này concrete hoặc thuộc nhóm được hỗ trợ | Consumer có DTO đích cố định; giảm phụ thuộc vào tên class do producer phát |
| **TypePrecedence.TYPE_ID** | Type header khi cả header và inferred type đều có | Có nhu cầu polymorphic rõ ràng, ví dụ listener nhận base type nhưng muốn tạo subclass cụ thể |

**Ngoại lệ cần nhớ:** inferred type không phải lúc nào cũng thắng. Khi listener dùng interface/abstract type hoặc gặp giới hạn suy luận generic, converter có thể quay lại dùng type headers. Hành vi còn phụ thuộc API và converter phiên bản.

Với Spring AMQP **3.x**, type precedence được đặt trên **Jackson2JsonMessageConverter** hoặc **DefaultJackson2JavaTypeMapper**, ví dụ:

~~~java
import org.springframework.amqp.support.converter.Jackson2JavaTypeMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

Jackson2JsonMessageConverter converter =
        new Jackson2JsonMessageConverter();
converter.setTypePrecedence(
        Jackson2JavaTypeMapper.TypePrecedence.TYPE_ID);
~~~

**Không dùng cấu hình TYPE_ID toàn cục chỉ để “bắt converter đọc header”.** Nó tăng sự phụ thuộc vào nội dung header từ phía gửi. Với message không đáng tin, trước tiên cần xác minh allowlist type, trusted packages và hợp đồng polymorphic. Nếu ứng dụng đã tự cung cấp JavaTypeMapper, thiết lập precedence trên chính mapper đó theo API tương ứng.

**Phân biệt:** **DefaultClassMapper** chỉ ánh xạ class ID; **TypePrecedence** là cơ chế của **Jackson Java type mapper/converter**. Hai khái niệm liên quan nhưng không phải cùng một cài đặt.

## 8. Collection, Map và generic: dùng type mapper đúng lớp

Trên Java, generic có thể bị mất thông tin tại runtime. Nếu converter nhận **List** hoặc **Map** chỉ với type header của container, nó có thể tạo ra **List&lt;Map&lt;String,Object&gt;&gt;** thay vì **List&lt;OrderCreatedV1&gt;**.

Để mô tả kiểu phần tử hoặc map key/value, **DefaultJackson2JavaTypeMapper** (Jackson 2) hoặc **DefaultJacksonJavaTypeMapper** (Jackson 3) hỗ trợ metadata tương ứng:

~~~text
__TypeId__         = java.util.ArrayList
__ContentTypeId__  = order.created.v1

__TypeId__         = java.util.HashMap
__KeyTypeId__      = java.lang.String
__ContentTypeId__  = order.created.v1
~~~

Đây là minh họa ý nghĩa header; khi serialize object thực, các header được sinh ra phụ thuộc **JavaType mà converter biết được**, cách gửi và version đang dùng.

Trong Spring AMQP 3.x có thể cấu hình mapper chi tiết:

~~~java
import com.example.contracts.orders.OrderCreatedV1;
import java.util.Map;
import org.springframework.amqp.support.converter.DefaultJackson2JavaTypeMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

DefaultJackson2JavaTypeMapper mapper =
        new DefaultJackson2JavaTypeMapper();
mapper.setIdClassMapping(
        Map.of("order.created.v1", OrderCreatedV1.class));
mapper.setTrustedPackages(
        "com.example.contracts.orders", "java.lang", "java.util");

Jackson2JsonMessageConverter converter =
        new Jackson2JsonMessageConverter();
converter.setJavaTypeMapper(mapper);
~~~

Đây là **hướng cấu hình thay thế** cho việc dùng **setClassMapper(DefaultClassMapper)** ở mục 6 khi bạn thực sự cần JavaType mapping; không cấu hình hai mapper độc lập rồi mặc định chúng sẽ kết hợp như ý.

Nếu consumer biết trước kiểu generic cần nhận khi gọi RabbitTemplate, dùng API hỗ trợ **ParameterizedTypeReference** (với SmartMessageConverter) là một cách khác để cung cấp kiểu đích tường minh:

~~~java
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;

// Dùng với RabbitTemplate đã cấu hình JSON SmartMessageConverter.
List<OrderCreatedV1> events = rabbitTemplate.receiveAndConvert(
        "orders.audit",
        new ParameterizedTypeReference<List<OrderCreatedV1>>() {});
~~~

Ví dụ chỉ minh họa cú pháp với phiên bản hỗ trợ; **receiveAndConvert** kéo message khỏi queue, nên không dùng nó để tự ý đọc kiểm thử trên queue nghiệp vụ đang có consumer khác. Trong thiết kế production, tốt hơn là thống nhất **một event/message** cho mỗi publish nếu không có lý do cần gói cả collection.

## 9. Khi message thiếu hoặc sai type header

Các tình huống cần phân biệt:

| Tình huống | Hành vi khả dĩ | Hướng xử lý |
| --- | --- | --- |
| **Không có __TypeId__**, listener nhận DTO concrete | Converter có thể suy ra kiểu từ tham số | Kiểm tra JSON schema và cấu hình converter |
| **Không có __TypeId__**, không có kiểu đích | Jackson có thể trả **Map/List** thay vì DTO | Đặt defaultType trên queue có đúng một contract, hoặc cung cấp kiểu đích |
| **__TypeId__ là alias đã map** | Mapper tạo DTO đã đăng ký | Vẫn validate body và schemaVersion |
| **__TypeId__ là tên class của producer nhưng consumer không có class đó** | Class resolution thất bại | Dùng alias ổn định, không sao chép classpath producer |
| **__TypeId__ thuộc package không tin cậy** | Converter có thể từ chối resolution | Kiểm tra allowlist; không chữa bằng trustedPackages("*") |
| **__TypeId__ đúng, JSON sai cấu trúc** | Lỗi parse/bind/validation | Phân loại message lỗi, chuyển sang kênh phục hồi phù hợp |
| **contentType không tương thích JSON** | Converter có thể giữ body dưới dạng byte[] hoặc báo lỗi chuyển đổi | Đặt application/json đúng, kiểm tra charset và converter |
| **TypePrecedence.INFERRED ghi đè header** | Kết quả là DTO của listener dù header khác | Xem method signature, type mapper và loại listener |
| **Aliased header đúng nhưng schemaVersion chưa được hỗ trợ** | Deserialize có thể thành công nhưng ý nghĩa dữ liệu sai | Từ chối version chưa hỗ trợ, không chỉ tin vào header |

**Lưu ý về contentType:** trong một số phiên bản Spring AMQP, JSON converter mặc định **giả định application/json** nếu contentType không có hoặc để giá trị mặc định **application/octet-stream**. Có thể đổi behavior bằng **assumeSupportedContentType**. Không nên lấy fallback này làm hợp đồng giữa các service; producer cần gắn **application/json** rõ ràng.

### Header giả mạo không phải lỗi định tuyến

Nếu một message có **__TypeId__** không tin cậy, nó có thể **đã được RabbitMQ định tuyến vào queue thành công** nhưng lỗi xảy ra khi consumer chuyển byte thành Java object. Đây là **conversion failure**, không phải lỗi **exchange/routing key**.

Do đó cần quan sát hai nhóm chỉ số riêng: **publisher confirms/returns** cho publish/routing và **message conversion exceptions/retry/dead-letter** cho consumer.

## 10. Kết hợp với retry, dead-letter và idempotency

Type header sai, class không nằm trong trusted packages hoặc JSON không hợp lệ thường là **lỗi dữ liệu không tự phục hồi**. Retry ngay cùng một message nhiều lần không làm header hoặc body tự thay đổi.

Một luồng xử lý hợp lý:

~~~mermaid
flowchart TD
    P["RabbitTemplate publish JSON event"] --> B["Exchange + queue"]
    B --> C["JSON converter<br/>type header → DTO"]
    C --> D{"Chuyển đổi hợp lệ?"}
    D -->|"Không"| E["Ghi eventId / lý do lỗi<br/>DLQ hoặc error queue"]
    D -->|"Có"| V["Validate schemaVersion<br/>và dữ liệu nghiệp vụ"]
    V --> R{"Hợp lệ?"}
    R -->|"Không"| E
    R -->|"Có"| H["Xử lý idempotent<br/>transaction nghiệp vụ"]
    H --> A{"Thành công?"}
    A -->|"Có"| K["Consumer ACK"]
    A -->|"Lỗi tạm thời"| T["Retry có giới hạn<br/>và backoff"]
    T --> H
    T -->|"Hết lượt"| E
~~~

**Không có nghĩa Spring tự động tạo toàn bộ luồng này.** Cần cấu hình listener error handler, retry interceptor/recoverer, DLX/DLQ (hoặc kênh lỗi riêng), acknowledgement và giám sát theo nhu cầu.

Với **@RabbitListener**, lỗi chuyển đổi có thể xảy ra **trước khi method được gọi**, nên try/catch đặt trong method không nhất thiết bắt được. Cần xử lý ở **container/error handler** và chính sách reject/dead-letter phù hợp. Không để message poison liên tục requeue gây vòng lặp nóng.

**Idempotency không được giải quyết bằng type headers.** Khi Order Service publish cùng event hai lần hoặc consumer nhận lại do ACK thất lạc, cả hai message có thể có **__TypeId__** đúng. Consumer phải dùng **eventId ổn định** và cơ chế chống trùng trong DB hoặc hệ thống ngoài.

### Các bước bảo vệ tối thiểu khi nhận message

1. **Phân quyền publisher:** tách vhost/user, hạn chế quyền gửi vào exchange và bảo vệ connection phù hợp.
2. **Định nghĩa contract:** thống nhất contentType, alias type, schemaVersion, required fields và max payload size.
3. **Giới hạn type resolution:** trustedPackages tường minh, ánh xạ alias và từ chối alias lạ nếu yêu cầu strict.
4. **Validate body:** không tin rằng class đúng thì dữ liệu nghiệp vụ đúng; kiểm tra schema, null, kích thước và range.
5. **Xử lý lỗi có giới hạn:** classify permanent/transient, retry có backoff, chuyển kênh lỗi theo chính sách.
6. **Idempotency và quan sát:** eventId/correlationId, trạng thái đã xử lý, số lỗi converter, DLQ và duplicate count.

## 11. Khác biệt phiên bản Spring AMQP

API chuyển đổi JSON đã thay đổi giữa các nhánh:

| Nhánh | JSON converter | Mapper phục vụ JavaType |
| --- | --- | --- |
| **Spring AMQP 3.x** | **Jackson2JsonMessageConverter** (Jackson 2) | **DefaultJackson2JavaTypeMapper**, **Jackson2JavaTypeMapper.TypePrecedence** |
| **Spring AMQP 4.x** | **JacksonJsonMessageConverter** (Jackson 3) | **DefaultJacksonJavaTypeMapper**, **JacksonJavaTypeMapper.TypePrecedence** |
| **Dùng ClassMapper đơn giản** | **DefaultClassMapper** (khi API converter hỗ trợ) | Type ID ↔ Class, alias map, defaultType, trustedPackages |

Mã ví dụ chính của bài chọn **Spring AMQP 3.x** để nhất quán với các API **Jackson2JsonMessageConverter**, **DefaultClassMapper** và **DefaultJackson2JavaTypeMapper**. Nếu ứng dụng chạy **Spring AMQP 4.x**, hãy dùng tài liệu API của đúng phiên bản; không đổi duy nhất tên converter trong code mà bỏ qua khác biệt Jackson 2/Jackson 3.

**Không ghim version thư viện tùy tiện:** Spring Boot thường quản lý Spring AMQP qua BOM. Kiểm tra **dependency tree** để biết chính xác version của **spring-rabbit**, **spring-amqp**, Jackson và các starter trước khi sao chép ví dụ.

## 12. Bài tập thực hành

### Bài 1 — Quan sát type headers

Tạo **OrderCreatedV1**, cấu hình JSON converter và publish qua **RabbitTemplate.convertAndSend**. Kiểm tra message raw trong môi trường test: contentType, **__TypeId__**, messageId, schemaVersion và body. So sánh khi dùng converter không có alias với converter ánh xạ **order.created.v1**.

### Bài 2 — Đổi package phía consumer

Tạo một consumer có DTO thuộc package **com.example.audit.contract**, không trùng package DTO của producer. Dùng cùng alias **order.created.v1** nhưng class mapping riêng. Chứng minh consumer vẫn deserialize được khi JSON contract tương thích.

### Bài 3 — Trusted package và alias lạ

Gửi message test với:

- type ID là alias đã đăng ký;
- type ID là tên class ngoài trusted packages;
- type ID là một alias chưa đăng ký.

Quan sát kết quả với **DefaultClassMapper**. Giải thích vì sao chỉ dùng setIdClassMapping không bảo đảm chặn mọi alias lạ nếu mapper còn cho phép tên class trong trusted packages; đề xuất một lớp kiểm tra strict alias.

### Bài 4 — TypePrecedence.INFERRED và TYPE_ID

Tạo DTO base **OrderEvent** và subclass **OrderCreatedV1** trong môi trường test. Đặt @RabbitListener nhận concrete base class, rồi thử hai chế độ precedence. Ghi lại kiểu object nhận được, đối chiếu type headers, sau đó giải thích tại sao TYPE_ID cần đi kèm allowlist.

### Bài 5 — Collection và JavaType

Đặt message JSON array cho **List&lt;OrderCreatedV1&gt;**. Thử deserialize bằng mapper chỉ biết class container, rồi dùng **DefaultJackson2JavaTypeMapper** hoặc **ParameterizedTypeReference**. So sánh phần tử là **Map** hay DTO và giải thích giới hạn generic type erasure.

### Bài 6 — Poison message

Gửi event có **__TypeId__** hợp lệ nhưng body JSON lỗi hoặc **schemaVersion=999**. Thiết kế chính sách xử lý lỗi tại container để không requeue vô hạn, ghi lại **eventId/correlationId** nếu đọc được và chuyển message lỗi tới DLQ/error queue. Kiểm tra rằng consumer tiếp tục xử lý các message hợp lệ sau đó.

### Câu hỏi tự đánh giá

1. Header **__TypeId__** do RabbitMQ tự tạo hay do Spring converter/producer đặt?
2. **__TypeId__**, **eventType**, **schemaVersion** và **routing key** khác nhau ra sao?
3. **DefaultClassMapper.setIdClassMapping** giải quyết sự phụ thuộc tên package giữa các service như thế nào?
4. Khi nào dùng **setDefaultType**? Nó có sửa được header sai không?
5. Vì sao **trustedPackages("*")** là lựa chọn nguy hiểm trên message không đáng tin?
6. Vì sao listener có DTO concrete có thể bỏ qua **__TypeId__** trong chế độ INFERRED?
7. DefaultClassMapper và DefaultJackson2JavaTypeMapper khác nhau ở nhu cầu generic và type precedence nào?
8. Một lỗi conversion xảy ra trước khi listener chạy sẽ được xử lý ở tầng nào?
9. Nếu hai lần publish cùng eventId đều có header hợp lệ, converter có giúp ngăn xử lý trùng không?

## 13. Tài liệu tham khảo chính thức

- [Spring AMQP 3.2 — Message Converters](https://docs.spring.io/spring-amqp/reference/3.2/amqp/message-converters.html): Jackson2JsonMessageConverter, DefaultClassMapper, alias mapping, inference và trustedPackages.
- [Spring AMQP 4.x — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): JacksonJsonMessageConverter, thay đổi sang Jackson 3 và loại mapper tương ứng.
- [Spring AMQP API — DefaultClassMapper](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/support/converter/DefaultClassMapper.html): setIdClassMapping, setDefaultType, setTrustedPackages, afterPropertiesSet.
- [Spring AMQP API — DefaultJackson2JavaTypeMapper](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/support/converter/DefaultJackson2JavaTypeMapper.html): JavaType, TypePrecedence, trusted packages.
- [Spring AMQP API — AbstractJackson2MessageConverter](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/support/converter/AbstractJackson2MessageConverter.html): setClassMapper, setJavaTypeMapper, setTypePrecedence.
- [Spring AMQP — Message Conversion for Annotated Methods](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): inference từ @RabbitListener, conversion với annotation và method signature.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): phạm vi xác nhận giao nhận, khác với chuyển đổi dữ liệu.

---

**Ghi nhớ:** **Type headers** hỗ trợ Spring AMQP chuyển JSON thành kiểu Java; **__TypeId__** mô tả class/alias, còn **__ContentTypeId__** và **__KeyTypeId__** phục vụ một số cấu trúc collection/map. **DefaultClassMapper** quản lý alias, defaultType và trusted packages; **DefaultJackson2JavaTypeMapper** hoặc **DefaultJacksonJavaTypeMapper** hỗ trợ JavaType và type precedence theo phiên bản. Với message từ nhiều service, nên dùng **alias ổn định, trusted packages tường minh, schema version, validation, error handling và idempotency**. Type header đúng không có nghĩa message đã định tuyến thành công, có nguồn đáng tin hoặc được xử lý đúng một lần.
