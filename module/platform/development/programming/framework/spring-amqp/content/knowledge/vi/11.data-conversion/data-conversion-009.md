# ParameterizedTypeReference và payload có kiểu generic

## 1. Vấn đề: JSON đúng nhưng phần tử lại thành LinkedHashMap

Trong hệ thống **Spring AMQP** kết nối RabbitMQ, producer thường dùng `RabbitTemplate.convertAndSend(...)` để chuyển object Java thành message, đi qua exchange, binding và queue; consumer dùng `@RabbitListener` hoặc `RabbitTemplate.receiveAndConvert(...)` để đọc và chuyển bytes trở lại object. Với payload kiểu đơn giản như `OrderCreated`, người học thường chỉ cần một JSON message converter.

Khó khăn xuất hiện khi payload mang **kiểu generic**, chẳng hạn:

~~~java
List<OrderCreated>
EventEnvelope<List<OrderCreated>>
Map<String, List<OrderCreated>>
PageResult<EventEnvelope<OrderCreated>>
~~~

Một JSON array không mang tên Java class của từng phần tử. Nếu chỉ yêu cầu converter giải mã về `List.class` hoặc `EventEnvelope.class`, kết quả có thể là `List<LinkedHashMap>` thay vì `List<OrderCreated>`. Chương trình nhìn qua có vẻ hoạt động nhưng lỗi khi thao tác với phần tử:

~~~java
// Cách dễ sai: chỉ cung cấp raw class.
EventEnvelope raw = (EventEnvelope) rabbitTemplate.receiveAndConvert("orders.poll.q");
Object first = ((List<?>) raw.data()).get(0);
// first có thể là LinkedHashMap, không phải OrderCreated.
~~~

**`ParameterizedTypeReference<T>`** của Spring Framework cho phép khai báo kiểu đích **đầy đủ**, kể cả các generic lồng nhau. Khi đi cùng `SmartMessageConverter` hỗ trợ chuyển đổi theo type hint (chẳng hạn Jackson JSON converter của Spring AMQP), converter biết cần tạo `EventEnvelope<List<OrderCreated>>`.

Mục tiêu của bài **Chuyển đổi dữ liệu** này là:

1. Hiểu nguyên nhân Java type erasure làm mất `List<OrderCreated>` ở runtime.
2. Phân biệt `Class<T>` với `ParameterizedTypeReference<T>` và vai trò của `SmartMessageConverter`.
3. Đọc generic payload bằng `RabbitTemplate.receiveAndConvert(...)` và generic response bằng `convertSendAndReceiveAsType(...)`.
4. Xử lý generic payload trong `@RabbitListener` nhờ kiểu tham số suy luận.
5. Chẩn đoán lỗi chuyển đổi JSON mà vẫn giữ được retry, dead-letter, xác nhận giao nhận và tính idempotent của nghiệp vụ.

## 2. Cơ chế chuyển đổi trong Spring AMQP

Một AMQP message có **body bytes** và **message properties/headers**. Khi gửi object, converter chuyển object sang bytes, có thể thêm `contentType=application/json` và metadata kiểu. Khi nhận, converter dùng bytes cùng thông tin về kiểu đích để tạo object Java.

~~~mermaid
flowchart LR
    A["Producer<br/>EventEnvelope&lt;List&lt;OrderCreated&gt;&gt;"]
    B["JSON MessageConverter"]
    M["AMQP message<br/>body bytes + properties"]
    Q["RabbitMQ<br/>exchange → queue"]
    C["SmartMessageConverter"]
    D["Consumer<br/>EventEnvelope&lt;List&lt;OrderCreated&gt;&gt;"]
    T["ParameterizedTypeReference<br/>hoặc inferred listener type"]
    A --> B --> M --> Q --> C --> D
    T --> C
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| `Message` | Biểu diễn AMQP message của Spring: `byte[] body` và `MessageProperties`. |
| `MessageConverter` | Chuyển object sang `Message` và ngược lại; không phải converter nào cũng hiểu generic type hint. |
| `SmartMessageConverter` | Mở rộng khả năng chuyển đổi với **conversion hint**; các API nhận `ParameterizedTypeReference` yêu cầu converter thuộc loại này. |
| `Jackson2JsonMessageConverter` | JSON converter của Spring AMQP 3.x dựa trên Jackson 2, triển khai `SmartMessageConverter`. |
| `JacksonJsonMessageConverter` | JSON converter của Spring AMQP 4.x dựa trên Jackson 3, thay thế API Jackson 2 đã deprecated. |
| `ParameterizedTypeReference<T>` | **Type token ở phía Java caller** chứa thông tin đầy đủ của generic `T`. Nó không tự serialize hoặc thay đổi routing. |
| `@RabbitListener` | Có thể cung cấp kiểu đích suy luận từ tham số method cho JSON converter, không nhất thiết phải tạo `ParameterizedTypeReference` thủ công. |

**Phạm vi phiên bản:** ví dụ Java chính bên dưới dùng **Spring Boot 3.x / Spring AMQP 3.x / RabbitMQ AMQP 0-9-1** với `Jackson2JsonMessageConverter`. Đối với **Spring AMQP 4.x**, dùng `JacksonJsonMessageConverter` dựa trên Jackson 3 và cấu hình starter tương thích theo phiên bản dự án; ý tưởng type token và các overload của `RabbitTemplate` vẫn áp dụng. Không trộn package của Jackson 2 và Jackson 3 tùy tiện trong cùng ví dụ.

## 3. Vì sao Class<T> không diễn đạt được generic lồng nhau?

### 3.1. Java type erasure

Trong Java, generic chủ yếu giúp kiểm tra kiểu lúc biên dịch. Khi runtime chỉ cầm một `Class<?>`, nhiều chi tiết type argument đã bị xóa:

~~~java
Class<?> a = List.class;
Class<?> b = EventEnvelope.class;

// Không thể viết:
// List<OrderCreated>.class
// EventEnvelope<List<OrderCreated>>.class
~~~

`List.class` không nói phần tử là `OrderCreated` hay `PaymentCreated`. `EventEnvelope.class` cũng không nói kiểu của `data` là `String` hay `List<OrderCreated>`.

Khi Jackson deserialize JSON với một raw type, các object lồng trong map/list có thể được biểu diễn bằng `LinkedHashMap` hoặc các cấu trúc Java chung khác. Ép kiểu ngoài cùng không biến phần tử bên trong thành DTO:

~~~java
// Ví dụ minh họa raw type: không có type argument lúc deserialize.
List<?> list = (List<?>) someConvertedObject;
Object element = list.get(0);
// element có thể là java.util.LinkedHashMap.
~~~

Nguy cơ lớn nhất không phải lúc tạo list, mà khi gọi method của DTO, chẳng hạn `((OrderCreated) element).orderId()`, dẫn tới `ClassCastException`.

### 3.2. ParameterizedTypeReference giữ thông tin kiểu đầy đủ

Spring Framework cung cấp `org.springframework.core.ParameterizedTypeReference`. Cách thông dụng là tạo anonymous subclass:

~~~java
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<OrderCreated>> listType =
        new ParameterizedTypeReference<List<OrderCreated>>() {};

ParameterizedTypeReference<EventEnvelope<List<OrderCreated>>> envelopeType =
        new ParameterizedTypeReference<EventEnvelope<List<OrderCreated>>>() {};
~~~

`{}` ở cuối là **anonymous subclass**, nhờ đó đối tượng token có thể giữ thông tin generic superclass trong reflection. Không thể thay bằng `new ParameterizedTypeReference<...>()` vì lớp được dùng theo mẫu type token và constructor của nó không phải API tạo instance trực tiếp.

| Mục tiêu deserialize | Type token cần thiết |
| --- | --- |
| Một DTO cụ thể | Có thể suy luận từ `OrderCreated.class` hoặc listener parameter. |
| `List<OrderCreated>` | `new ParameterizedTypeReference<List<OrderCreated>>() {}` |
| `Map<String, List<OrderCreated>>` | `new ParameterizedTypeReference<Map<String, List<OrderCreated>>>() {}` |
| `EventEnvelope<List<OrderCreated>>` | `new ParameterizedTypeReference<EventEnvelope<List<OrderCreated>>>() {}` |
| `EventEnvelope<Map<String, List<OrderCreated>>>` | Type token bao trọn cấu trúc lồng nhau. |

Khai báo token chỉ là bước **mô tả kiểu mong muốn**. Converter phải dùng type hint đó để deserialize; `SimpleMessageConverter` mặc định của `RabbitTemplate` không đáp ứng nhu cầu JSON generic kiểu này.

### 3.3. Tạo Java DTO và JSON minh họa

Dùng Java 17+ với record:

~~~java
public record OrderCreated(String orderId, long amount) {}

public record EventEnvelope<T>(
        String eventId,
        String schemaVersion,
        T data
) {}
~~~

Producer có thể gửi giá trị:

~~~java
EventEnvelope<List<OrderCreated>> batch = new EventEnvelope<>(
        "evt-1001",
        "1",
        List.of(
                new OrderCreated("ORD-1001", 250_000L),
                new OrderCreated("ORD-1002", 500_000L)
        )
);
~~~

JSON tương ứng:

~~~json
{
  "eventId": "evt-1001",
  "schemaVersion": "1",
  "data": [
    { "orderId": "ORD-1001", "amount": 250000 },
    { "orderId": "ORD-1002", "amount": 500000 }
  ]
}
~~~

Trong JSON không có tên class `OrderCreated`. Converter chỉ có thể tái tạo record này một cách đáng tin khi nó biết kiểu đích từ **type hint ở caller, inferred listener type hoặc type metadata được tin cậy**.

## 4. Cấu hình Jackson JSON converter trong Spring AMQP

### 4.1. Dependency và broker

Với **Spring Boot 3.x**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-json'
}
~~~

`spring-boot-starter-json` bảo đảm các thành phần Jackson 2 cần thiết có trên classpath của ví dụ; nhiều dự án có sẵn qua web starter. Trong `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    listener:
      simple:
        acknowledge-mode: auto
~~~

Đây là thông số demo với RabbitMQ cục bộ. Môi trường triển khai thật nên dùng user/vhost, credentials và TLS riêng; mặc định tài khoản `guest` thường bị giới hạn đăng nhập từ loopback.

### 4.2. Định nghĩa một JSON converter nhất quán cho gửi và nhận

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonConversionConfiguration {
    @Bean
    Jackson2JsonMessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Trong Spring Boot 3.x có auto-configuration tương ứng, bean `MessageConverter` có thể được áp dụng cho `RabbitTemplate` và listener container factory do Boot tạo. Khi ứng dụng định nghĩa custom `RabbitTemplate` hoặc container factory, **hãy cấu hình converter trên các bean đó một cách tường minh** và kiểm tra đừng để producer dùng JSON còn consumer dùng `SimpleMessageConverter`.

Ví dụ cấu hình thủ công nếu không dựa vào cơ chế Boot:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExplicitConverterWiring {

    @Bean
    RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter converter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(converter);
        return template;
    }

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter converter) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        return factory;
    }
}
~~~

Đây là **phương án thay thế** wiring tự động; không cần thêm cả `ExplicitConverterWiring` nếu đã dùng Boot auto-config và xác minh nó chọn đúng bean converter. Trong cùng application context, tránh tạo nhiều `RabbitTemplate` cạnh tranh hoặc hai container factory cùng tên.

### 4.3. Lưu ý khi dùng Spring AMQP 4.x

Trong Spring AMQP 4.x, chuyển sang converter dựa trên Jackson 3:

~~~java
// Spring AMQP 4.x: thay import và bean khi dự án dùng Jackson 3.
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;

@Bean
JacksonJsonMessageConverter jsonMessageConverter() {
    return new JacksonJsonMessageConverter();
}
~~~

**Chỉ dùng ví dụ của một phiên bản tương thích.** Các class `Jackson2JsonMessageConverter`/`AbstractJackson2MessageConverter` thuộc nhánh Jackson 2 đã deprecated để thay thế bằng API Jackson 3 trong Spring AMQP 4.x; build cần đồng bộ phiên bản Spring Framework, Boot và Jackson.

## 5. Khai báo queue và publish generic payload

Để nhìn rõ từng luồng, ví dụ sử dụng **hai queue riêng**:

- `orders.generic.listener.q`: có `@RabbitListener` nhận.
- `orders.generic.poll.q`: không gắn listener, phục vụ thử nghiệm `RabbitTemplate.receiveAndConvert(...)`.

Hai queue cùng nhận message qua **direct exchange** với routing key riêng. Không dùng cùng một queue cho polling và listener khi muốn quan sát kết quả chắc chắn: chúng sẽ **cạnh tranh tiêu thụ**, khiến kết quả phụ thuộc thời điểm.

### 5.1. Topology

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GenericPayloadTopology {
    public static final String EXCHANGE = "orders.generic.events";
    public static final String LISTENER_QUEUE = "orders.generic.listener.q";
    public static final String POLL_QUEUE = "orders.generic.poll.q";

    @Bean
    DirectExchange genericExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue genericListenerQueue() {
        return QueueBuilder.durable(LISTENER_QUEUE).build();
    }

    @Bean
    Queue genericPollQueue() {
        return QueueBuilder.durable(POLL_QUEUE).build();
    }

    @Bean
    Binding listenerBinding(
            Queue genericListenerQueue, DirectExchange genericExchange) {
        return BindingBuilder.bind(genericListenerQueue)
                .to(genericExchange)
                .with("orders.batch.listener");
    }

    @Bean
    Binding pollBinding(
            Queue genericPollQueue, DirectExchange genericExchange) {
        return BindingBuilder.bind(genericPollQueue)
                .to(genericExchange)
                .with("orders.batch.poll");
    }
}
~~~

`RabbitAdmin` có thể khai báo bean topology khi kết nối RabbitMQ được thiết lập. Với direct exchange, routing key `orders.batch.poll` sẽ tới queue poll, không tự tạo queue khác và không đi tới listener queue.

### 5.2. Producer gửi object chứa generic data

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class GenericBatchPublisher {

    private final RabbitTemplate template;

    public GenericBatchPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publishToPollQueue() {
        EventEnvelope<List<OrderCreated>> envelope = new EventEnvelope<>(
                "evt-1001",
                "1",
                List.of(
                        new OrderCreated("ORD-1001", 250_000L),
                        new OrderCreated("ORD-1002", 500_000L)
                )
        );

        template.convertAndSend(
                GenericPayloadTopology.EXCHANGE,
                "orders.batch.poll",
                envelope
        );
    }

    public void publishToListenerQueue() {
        EventEnvelope<List<OrderCreated>> envelope = new EventEnvelope<>(
                "evt-1002",
                "1",
                List.of(new OrderCreated("ORD-1003", 750_000L))
        );

        template.convertAndSend(
                GenericPayloadTopology.EXCHANGE,
                "orders.batch.listener",
                envelope
        );
    }
}
~~~

Jackson JSON converter chuyển payload sang bytes và khai báo content type JSON. Việc gọi `convertAndSend(...)` **không tự tạo `ParameterizedTypeReference` trên wire**: type token là cách người đọc **chỉ định kiểu đích**. Nếu producer và consumer có các phiên bản DTO khác nhau, hãy thống nhất JSON schema/contract, không lệ thuộc hoàn toàn vào tên Java class trong headers.

## 6. Dùng ParameterizedTypeReference với RabbitTemplate.receiveAndConvert

### 6.1. Đọc kiểu generic chính xác

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;

@Service
public class GenericBatchPoller {
    private final RabbitTemplate template;

    private static final ParameterizedTypeReference<
            EventEnvelope<List<OrderCreated>>> ENVELOPE_TYPE =
            new ParameterizedTypeReference<
                    EventEnvelope<List<OrderCreated>>>() {};

    public GenericBatchPoller(RabbitTemplate template) {
        this.template = template;
    }

    public EventEnvelope<List<OrderCreated>> receiveOnce() {
        return template.receiveAndConvert(
                GenericPayloadTopology.POLL_QUEUE,
                ENVELOPE_TYPE
        );
    }
}
~~~

Cách thử:

1. Gọi `GenericBatchPublisher.publishToPollQueue()`.
2. Gọi `GenericBatchPoller.receiveOnce()`.
3. Nếu nhận được giá trị khác `null`, đọc `result.data().get(0).orderId()`: phần tử phải là `OrderCreated` với cấu hình converter phù hợp.

`receiveAndConvert(...)` có thể trả **`null`** nếu không có message đang sẵn sàng trong queue. Đây là API **chủ động lấy message** (*poll*), không phải listener chạy liên tục. Không đặt `@RabbitListener` khác trên `orders.generic.poll.q` nếu bài thực hành cần poll nhận đúng message vừa gửi.

### 6.2. Đọc với timeout

Nếu muốn chờ một khoảng thời gian thay vì trả về ngay:

~~~java
EventEnvelope<List<OrderCreated>> result = template.receiveAndConvert(
        GenericPayloadTopology.POLL_QUEUE,
        3_000L, // chờ tối đa 3 giây
        ENVELOPE_TYPE
);

if (result == null) {
    System.out.println("Khong co message phu hop trong thoi gian cho");
} else {
    for (OrderCreated order : result.data()) {
        System.out.println(order.orderId() + " = " + order.amount());
    }
}
~~~

Đây là đoạn minh họa **trong class đã có biến `template` và `ENVELOPE_TYPE`**. Với `receiveAndConvert` có type token, phải có `SmartMessageConverter` đã gắn vào `RabbitTemplate`; nếu để `SimpleMessageConverter` mặc định, thao tác không có khả năng chuyển JSON phức tạp thành DTO đúng type.

### 6.3. So sánh với cách đọc thiếu type hint

~~~java
// Khi converter không có đủ metadata kiểu,
// kết quả của raw conversion có thể chứa LinkedHashMap.
Object raw = template.receiveAndConvert(GenericPayloadTopology.POLL_QUEUE);

// Đây KHÔNG phải cách bảo đảm phần tử là OrderCreated:
@SuppressWarnings("unchecked")
EventEnvelope<List<OrderCreated>> castOnly =
        (EventEnvelope<List<OrderCreated>>) raw;
~~~

Phép cast chỉ giúp compiler tạm chấp nhận một tên kiểu; nó **không deserialize lại** các phần tử vốn đã thành `Map`. Muốn thấy rõ sự khác biệt, cần publish **hai message tương đương**, một message đọc bằng cách raw, một message đọc với type reference; mỗi lần `receiveAndConvert` tiêu thụ một message khỏi queue.

Lưu ý vận hành: `RabbitTemplate.receiveAndConvert` dùng cơ chế polling/basic-get của RabbitMQ; khi cần kiểm soát thất bại chuyển đổi, requeue và retry/ack theo nghiệp vụ, mô hình **`@RabbitListener` với error handler và dead-letter** thường phù hợp hơn. Không nên giả định đọc polling thất bại sẽ tự động đưa message vào DLQ.

## 7. Dùng ParameterizedTypeReference cho RPC response có generic

`RabbitTemplate.convertSendAndReceiveAsType(...)` phục vụ mô hình **request/reply**: gửi request, đợi response và yêu cầu converter tạo đúng kiểu response. Ví dụ dịch vụ client yêu cầu danh sách đơn hàng:

~~~java
public record OrderQuery(String customerId) {}
~~~

Server có listener ở queue `orders.generic.rpc.q`, trả về object generic:

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersQueryHandler {

    @RabbitListener(queues = "orders.generic.rpc.q")
    public EventEnvelope<List<OrderCreated>> lookup(OrderQuery query) {
        return new EventEnvelope<>(
                "reply-" + query.customerId(),
                "1",
                List.of(
                        new OrderCreated("ORD-9001", 350_000L),
                        new OrderCreated("ORD-9002", 200_000L)
                )
        );
    }
}
~~~

Khai báo thêm queue cho RPC (đặt bean này trong một class `@Configuration` thích hợp):

~~~java
@Bean
Queue genericRpcQueue() {
    return QueueBuilder.durable("orders.generic.rpc.q").build();
}
~~~

Đối với RPC, ví dụ dùng **default exchange `""`** và routing key là chính tên queue, nên không cần bean binding riêng cho RPC queue. Producer/client:

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;

@Service
public class OrdersQueryClient {
    private final RabbitTemplate template;

    private static final ParameterizedTypeReference<
            EventEnvelope<List<OrderCreated>>> RESPONSE_TYPE =
            new ParameterizedTypeReference<
                    EventEnvelope<List<OrderCreated>>>() {};

    public OrdersQueryClient(RabbitTemplate template) {
        this.template = template;
    }

    public EventEnvelope<List<OrderCreated>> find(String customerId) {
        return template.convertSendAndReceiveAsType(
                "",
                "orders.generic.rpc.q",
                new OrderQuery(customerId),
                RESPONSE_TYPE
        );
    }
}
~~~

RPC server trả lời tới reply destination do Spring/RabbitMQ sử dụng. `RESPONSE_TYPE` **áp dụng cho response**, không phải type của request. Cả phía xử lý request và phía nhận response cần converter tương thích với các DTO.

**Trường hợp trả `null`:** không có reply trong thời gian `replyTimeout`, message không định tuyến được hoặc service không trả response như mong đợi. Cần phân biệt timeout với response nghiệp vụ hợp lệ. Spring `RabbitTemplate` hỗ trợ correlation cho request/reply; correlation này không làm cho kết quả RPC tự có semantics **exactly once**.

Khi lỗi mạng xảy ra sau khi server đã xử lý nhưng trước khi client nhận reply, client có thể thử lại và tạo request trùng. Với thao tác nghiệp vụ có side effect, cần request ID/idempotency ở server, cùng publisher confirms/returns và timeout phù hợp.

## 8. @RabbitListener có cần ParameterizedTypeReference không?

**Không nhất thiết.** Listener được khai báo bằng method có kiểu tham số cụ thể; Spring AMQP có thể **suy luận kiểu đích** từ tham số payload và cung cấp thông tin này cho Jackson converter. Ví dụ listener xử lý chính queue `orders.generic.listener.q`:

~~~java
import java.util.List;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class GenericBatchListener {

    @RabbitListener(queues = GenericPayloadTopology.LISTENER_QUEUE)
    public void handle(EventEnvelope<List<OrderCreated>> envelope) {
        for (OrderCreated order : envelope.data()) {
            System.out.println(
                    "Processed " + envelope.eventId()
                            + " / " + order.orderId()
            );
        }
    }
}
~~~

Trong trường hợp converter và listener factory được cấu hình đúng, method signature `EventEnvelope<List<OrderCreated>>` là **kiểu đích được suy luận**, giúp converter tạo `OrderCreated` bên trong `List`.

Điều kiện cần chú ý:

- Suy luận kiểu hoạt động rõ nhất với **một tham số payload** (hoặc một tham số `@Payload`), trong khi các tham số hệ thống như raw `Message` có quy tắc xử lý riêng.
- Inferred type thường được ưu tiên hơn type headers từ producer khi kiểu đích là concrete type hoặc thuộc `java.util`; cấu hình `TypePrecedence.TYPE_ID` có thể thay đổi thứ tự ưu tiên.
- Khi listener nhận `Object`, `Map<String, Object>`, raw `List`, wildcard hoặc kiểu quá trừu tượng, thông tin kiểu của phần tử có thể không đủ.
- Generic method/DTO phải có contract JSON tương thích: field names, constructors, record component names, enum values và version.
- Với multi-method listener (`@RabbitHandler`) việc chọn handler khác với listener một method; không suy luận rằng mọi chữ ký generic luôn phân phối chính xác khi type headers không đủ.

Nếu dùng listener như trên, không cần tự gọi `receiveAndConvert(...)` để nhận cùng queue. Listener container chịu trách nhiệm nhận delivery và ACK/NACK theo chính sách; việc dùng polling song song tạo **competing consumers**.

### Listener trả về generic response

Trong request/reply như `OrdersQueryHandler` ở mục 7, Spring chuyển return value sang reply message. Client vẫn có thể dùng `ParameterizedTypeReference` để mô tả **kiểu response mong muốn**. Hai hướng không đối lập: **server suy luận theo method signature**, còn **client truyền type token** khi gọi `convertSendAndReceiveAsType(...)`.

## 9. Message type headers và độ tin cậy của thông tin kiểu

Spring Jackson converter có thể thêm metadata như `__TypeId__` và các type headers liên quan để hỗ trợ deserialize ở phía nhận. Cần phân biệt:

| Thông tin | Ai cung cấp? | Công dụng |
| --- | --- | --- |
| `__TypeId__` (và headers kiểu liên quan) | Converter/producer | Gợi ý Java type hoặc type mapping cho message. |
| `ParameterizedTypeReference<EventEnvelope<List<OrderCreated>>>` | **Caller phía đọc** | Chỉ rõ kiểu đích đầy đủ, kể cả generic lồng nhau. |
| Inferred parameter type | Chữ ký method `@RabbitListener` | Cho listener converter biết kiểu đích. |
| `contentType=application/json` | Message converter/producer | Cho biết body có định dạng JSON; không nói các generic arguments là gì. |
| `type` (AMQP standard property, nếu dùng) | Producer ứng dụng | Nhãn nghiệp vụ; không tự thay thế Java type headers. |

Nếu publisher và consumer là các service viết bằng các ngôn ngữ khác nhau, **không nên phụ thuộc vào Java class name trong `__TypeId__`** làm contract liên dịch vụ. Thống nhất JSON schema, version và mapping type an toàn sẽ giúp bảo trì dễ hơn.

Đồng thời, **đừng tin mặc định class name do message bên ngoài khai báo**. Converter Jackson có cơ chế trusted packages/type mapper; cần cấu hình giới hạn loại class chấp nhận khi đọc từ nguồn không tin cậy. Phản xạ tạo object từ một type header không kiểm soát có thể dẫn đến vấn đề bảo mật và lỗi triển khai.

### Nếu type headers khác kiểu của listener

Một service phát `EventEnvelope<LegacyOrder>` nhưng listener yêu cầu `EventEnvelope<List<OrderCreated>>` có thể gặp lỗi chuyển đổi. Đặt type reference không “sửa” được JSON thiếu field, sai kiểu giá trị, hoặc schema thay đổi không tương thích.

Trong một số trường hợp, Spring AMQP dùng inferred type của listener thay cho type ID headers. Nếu cần ưu tiên dữ liệu type ID từ producer, converter cho phép điều chỉnh type precedence. Hãy chỉ đổi chính sách này sau khi đánh giá type mapping và tính an toàn của nguồn dữ liệu; mặc định thường phù hợp hơn khi consumer nắm contract.

## 10. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `List<LinkedHashMap>` thay cho `List<OrderCreated>` | Chuyển về raw `List.class` hoặc không có đủ thông tin generic. | Dùng `ParameterizedTypeReference<List<OrderCreated>>` hoặc listener parameter cụ thể. |
| `ClassCastException` khi lấy phần tử của `EventEnvelope.data` | Chỉ ép kiểu raw object mà không deserialize lại phần tử. | Đưa type hint vào bước **conversion**, không chỉ cast sau conversion. |
| `IllegalStateException`/lỗi yêu cầu `SmartMessageConverter` | Template vẫn đang dùng converter không hỗ trợ conversion hint. | Gắn Jackson JSON converter phù hợp vào `RabbitTemplate`. |
| Listener nhận `byte[]` thay vì DTO | `contentType` không phải JSON hoặc converter không hỗ trợ format đang nhận. | Kiểm tra producer content type, JSON converter, setting `assumeSupportedContentType` và logs. |
| `MessageConversionException` | JSON sai cú pháp, field không phù hợp constructor/record, type headers không hợp lệ, giá trị không thể deserialize. | Lưu thông tin message ID và nguyên nhân; đối chiếu schema và converter version. |
| `receiveAndConvert(...)` trả `null` | Queue không có message sẵn sàng hoặc hết timeout. | Kiểm tra queue, routing key, consumer count, message ready và timeout. |
| RPC trả `null` hoặc timeout | Request chưa đến worker, worker lỗi hoặc reply không về đúng nơi. | Kiểm tra reply queue, reply timeout, correlation, publisher returns/confirm, listener log. |
| DTO đúng nhưng dữ liệu nghiệp vụ bị lặp | Message được redeliver/retry sau sự cố. | Dùng event ID ổn định và idempotency; type reference không chống trùng. |

Đừng cố giải quyết lỗi **schema không tương thích** bằng cách tăng retry vô hạn. Nếu message có JSON sai định dạng hoặc field không hợp lệ vĩnh viễn, việc giao lại message đó ngay lập tức thường không làm nó trở nên hợp lệ.

## 11. Retry, dead-letter và xác nhận giao nhận khi chuyển đổi generic lỗi

Sử dụng generic type an toàn giúp tránh lỗi dữ liệu khi deserialize nhưng **không thay thế** các lớp bảo đảm message:

~~~mermaid
sequenceDiagram
    autonumber
    participant P as RabbitTemplate producer
    participant B as RabbitMQ
    participant L as @RabbitListener + JSON converter
    participant DB as Database
    P->>B: Publish JSON + contentType + eventId
    B-->>P: Publisher confirm (nếu bật)
    B->>L: Delivery từ queue
    alt JSON hợp lệ, type đúng
        L->>L: Convert generic payload
        L->>DB: Ghi nghiệp vụ + processedEventId
        DB-->>L: Commit
        L-->>B: Consumer ACK
    else JSON/type không hợp lệ
        L-->>B: Reject/NACK theo error handler
        B->>B: Requeue hoặc DLX/DLQ theo cấu hình
    end
~~~

### 11.1. Phân loại lỗi

- **Lỗi serialization/conversion vĩnh viễn:** JSON sai cú pháp, schema thiếu trường bắt buộc, type header không an toàn. Không nên retry nóng; dùng error handler và dead-letter để điều tra.
- **Lỗi nghiệp vụ tạm thời:** database timeout, dịch vụ phụ thuộc gián đoạn. Có thể retry hữu hạn với backoff; sau giới hạn thì dead-letter.
- **Kết quả publish chưa rõ:** producer chưa nhận confirm do mất kết nối. Không đồng nghĩa converter đã sai hoặc consumer chưa nhận; cần đối soát và phát lại có kiểm soát.
- **Consumer ACK thất lạc:** message có thể được giao lại sau khi DB đã commit. Đặt event ID cố định, kiểm tra dấu đã xử lý trong transaction và ACK sau khi hoàn thành.

### 11.2. Dùng metadata để quan sát

Khi gửi `EventEnvelope<List<OrderCreated>>`, nên log `eventId`, `schemaVersion`, `contentType`, exchange, routing key và correlation ID. Khi listener lỗi, log **loại lỗi chuyển đổi** cùng ID, tránh ghi toàn bộ payload nếu chứa dữ liệu riêng tư.

Khi listener chuyển đổi thất bại **trước khi method được gọi**, exception thường đi qua cơ chế error handler của listener container. Tùy cấu hình và loại lỗi, Spring AMQP có thể reject không requeue hoặc requeue; cần kiểm tra chính sách của phiên bản đang dùng. Muốn DLQ nhận message bị reject, phải khai báo DLX/DLQ phù hợp. Một `@RabbitListener` không bắt được mọi exception conversion bằng khối `try/catch` trong method nếu việc conversion thất bại trước khi method được gọi.

### 11.3. Transaction và outbox

Một message được deserialize chính xác vẫn có thể thất bại trong transaction database. Nếu producer cần ghi DB và phát event như một bước nghiệp vụ nhất quán, xem xét **transactional outbox**: ghi record nghiệp vụ và event vào cùng DB transaction, sau đó worker phát event từ outbox. Khi retry publish cùng event, giữ ID ổn định.

RabbitMQ publisher confirm không tự biến hai hệ thống DB và RabbitMQ thành một transaction phân tán; consumer acknowledgment cũng không đảm bảo side effect xảy ra đúng một lần.

## 12. Khi nào nên dùng ParameterizedTypeReference?

| Tình huống | Có cần tạo type reference thủ công? | Giải thích |
| --- | --- | --- |
| `RabbitTemplate.receiveAndConvert` trả `EventEnvelope<List<OrderCreated>>` | **Nên dùng** | Caller phải chỉ rõ cấu trúc generic khi đọc. |
| `RabbitTemplate.convertSendAndReceiveAsType` nhận RPC response generic | **Nên dùng** | Cho phép deserialize response theo kiểu đầy đủ. |
| `@RabbitListener void handle(EventEnvelope<List<OrderCreated>> body)` | **Thường không cần** | Listener method cung cấp inferred type cho JSON converter. |
| Producer gọi `convertAndSend` với một object generic | **Không cần chỉ để gửi** | Jackson serialize giá trị thực thành JSON; bên nhận vẫn cần biết contract/type thích hợp. |
| Consumer nhận `byte[]` và tự parse JSON | Không dùng trực tiếp với `RabbitTemplate` | Có thể dùng Jackson `TypeReference`/`JavaType` nhưng đó là API khác; chỉ cần khi chủ động tự deserialize. |
| Payload chỉ là `String` hoặc DTO cụ thể | Thường không cần | Không có generic lồng nhau cần bảo toàn. |
| Event streaming đa ngôn ngữ | Dùng contract/schema thay vì chỉ dựa vào Java token | Token không đi qua wire như một schema chung. |

**Đặc biệt:** `org.springframework.core.ParameterizedTypeReference` của Spring và `com.fasterxml.jackson.core.type.TypeReference` của Jackson là **hai API khác nhau**. Với các overload của `RabbitTemplate`, dùng **Spring `ParameterizedTypeReference`**; nếu bạn trực tiếp gọi `ObjectMapper.readValue`, Jackson có các cách chỉ kiểu khác.

## 13. Bài thực hành có thể kiểm chứng

Thử nghiệm trên RabbitMQ cục bộ có Management UI và dự án Spring Boot 3.x đã cấu hình Jackson 2 JSON converter.

1. **Chuẩn bị:** khai báo hai queue và exchange ở mục 5; chạy listener ở mục 8. Xác nhận cả hai queue tồn tại trước khi publish.
2. **Gửi generic envelope:** gọi `publishToPollQueue()`. Kiểm tra message ready trong `orders.generic.poll.q` tăng lên 1 nếu chưa poll.
3. **Đọc với type token:** gọi `receiveOnce()`, xác minh `data().get(0)` là `OrderCreated` và `orderId()` trả về `ORD-1001`.
4. **Thử raw conversion:** publish thêm một message mới rồi dùng overload không có type reference; quan sát kiểu runtime của phần tử. Nếu converter đã có type headers đủ chi tiết, kết quả có thể khác; thí nghiệm cần ghi lại headers và converter config thay vì mặc định mọi raw conversion đều thành map.
5. **Thử @RabbitListener:** gọi `publishToListenerQueue()`; listener phải đọc được `EventEnvelope<List<OrderCreated>>` mà không dùng type reference trực tiếp.
6. **Thử RPC:** thêm `orders.generic.rpc.q`, chạy `OrdersQueryHandler` và gọi `OrdersQueryClient.find("CUST-1001")`. Ghi kết quả khi có reply và khi server không phản hồi trước timeout.
7. **Tạo lỗi schema:** sửa payload JSON thành giá trị `"amount": "not-a-number"` trong môi trường thử nghiệm; quan sát lỗi chuyển đổi, requeue/reject và DLQ theo cấu hình.
8. **Kiểm tra độ tin cậy:** gửi lại cùng một `eventId` và bổ sung bảng chống trùng trong listener; xác minh side effect nghiệp vụ không lặp lại dù message được delivery nhiều lần.

### Mẫu ghi nhận

~~~text
Spring Boot / Spring AMQP version:
RabbitMQ version:
JSON converter:
Payload JSON:
contentType:
Type headers (nếu có):
Đích nhận: listener / poll / RPC:
ParameterizedTypeReference được dùng:
Kiểu runtime của data:
Kiểu runtime của phần tử trong List:
Conversion exception:
Publisher confirm / returned message:
Consumer ACK / reject / requeue / DLQ:
Idempotency result:
~~~

Nếu thấy `ClassCastException`, ghi **kiểu thực** của phần tử trước khi cast. Nếu thấy `MessageConversionException`, ghi phiên bản schema, content type, converter và type headers trước khi đổi mã xử lý lỗi.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `List<OrderCreated>.class` không hợp lệ trong Java?

**Trả lời:** Java không có class literal cho parameterized generic type; type arguments bị xóa ở mức runtime `Class`. Dùng `ParameterizedTypeReference<List<OrderCreated>>` để cung cấp type token.

**Câu 2.** Ép một `List<LinkedHashMap>` thành `List<OrderCreated>` có deserialize lại các phần tử không?

**Trả lời:** Không. Ép kiểu không chuyển đổi từng phần tử; cần converter có type hint khi đọc bytes.

**Câu 3.** Vì sao `ParameterizedTypeReference` vẫn không đủ nếu `RabbitTemplate` dùng `SimpleMessageConverter`?

**Trả lời:** Các overload nhận type token yêu cầu `SmartMessageConverter` biết dùng conversion hint. `SimpleMessageConverter` mặc định không xử lý JSON generic theo cơ chế này.

**Câu 4.** Listener `handle(EventEnvelope<List<OrderCreated>> data)` có bắt buộc tự tạo type reference?

**Trả lời:** Thường không. Spring AMQP có thể suy luận generic type từ method parameter và truyền cho Jackson converter; điều này phụ thuộc chữ ký, converter và cấu hình listener.

**Câu 5.** Type reference của `convertSendAndReceiveAsType` áp dụng cho request hay reply?

**Trả lời:** Cho **reply** mà client muốn deserialize. Phần gửi request vẫn dùng converter đã cấu hình.

**Câu 6.** Khi message JSON bị lỗi conversion trước khi vào method `@RabbitListener`, đặt `try/catch` trong method có xử lý được không?

**Trả lời:** Không đảm bảo, vì method có thể chưa được gọi. Phải kiểm tra converter, listener container error handler và DLQ.

**Câu 7.** Dùng type token đã đảm bảo xử lý đúng một lần chưa?

**Trả lời:** Chưa. Type token chỉ hỗ trợ giải mã dữ liệu. Publisher confirm, consumer acknowledgment, retry/DLQ, idempotency và giao dịch vẫn phải được thiết kế độc lập.

## 15. Tài liệu tham khảo

- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): `SmartMessageConverter`, Jackson JSON converter và cách chuyển generic bằng `ParameterizedTypeReference`.
- [Spring AMQP 3.2 — Message Converters](https://docs.spring.io/spring-amqp/reference/3.2/amqp/message-converters.html): `Jackson2JsonMessageConverter` cho các dự án dùng Spring AMQP 3.x.
- [Spring AMQP — Annotation-driven Listener Conversion](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): suy luận kiểu từ method của `@RabbitListener`.
- [Spring AMQP — RabbitTemplate API](https://docs.spring.io/spring-amqp/docs/3.2.8/api/org/springframework/amqp/rabbit/core/RabbitTemplate.html): các overload `receiveAndConvert(...)` và `convertSendAndReceiveAsType(...)`.
- [Spring Framework — ParameterizedTypeReference](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ParameterizedTypeReference.html): mẫu type token và cách giữ thông tin generic qua reflection.
- [RabbitMQ — Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): phân biệt kết quả publish với delivery và ACK/NACK ở consumer.

**Ghi nhớ:** `ParameterizedTypeReference<T>` giúp **Spring AMQP deserialize đúng cấu trúc generic** như `EventEnvelope<List<OrderCreated>>` khi `RabbitTemplate` làm việc với một `SmartMessageConverter` phù hợp. Với `@RabbitListener`, kiểu tham số method thường cung cấp cùng thông tin mà không cần tạo type token thủ công. Kiểu dữ liệu được chuyển đổi chính xác vẫn cần được đặt trong một luồng RabbitMQ có routing/binding rõ ràng, xử lý lỗi conversion, retry/dead-letter, publisher confirms, consumer acknowledgments và idempotency để nghiệp vụ bất đồng bộ đáng tin cậy.
