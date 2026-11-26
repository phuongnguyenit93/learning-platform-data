# @RabbitHandler và phân phối theo kiểu payload trong Spring AMQP

Một queue RabbitMQ có thể chứa nhiều **loại sự kiện**: `OrderCreated`, `OrderCancelled`, `OrderPaid`... Nếu viết một listener với tham số `Object` rồi tự kiểm tra hàng loạt `instanceof`, code sẽ nhanh chóng trở thành bộ định tuyến nghiệp vụ khó bảo trì. Spring AMQP cung cấp `@RabbitListener` đặt **trên class** kết hợp nhiều method `@RabbitHandler` để phân phối message theo **kiểu Java của payload sau chuyển đổi**.

Bài này thuộc chương **Listener khai báo** của module **SPRING_AMQP**: tích hợp RabbitMQ qua `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding và xây dựng xử lý bất đồng bộ có định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch, quan sát hệ thống. Bạn sẽ học cách chọn đúng handler, cấu hình message conversion để Spring nhận biết kiểu payload, xử lý trường hợp không khớp hoặc khớp mơ hồ, và tránh nhầm `@RabbitHandler` với routing của broker.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `@RabbitListener` ở cấp **method** với `@RabbitListener` ở cấp **class** cùng nhiều `@RabbitHandler`.
2. Giải thích **kiểu payload sau conversion** mới là căn cứ để Spring chọn handler; routing key và tên exchange không tự quyết định method.
3. Tạo listener cho nhiều DTO cụ thể, thêm `@Header`, `@Payload` và một default handler khi thích hợp.
4. Cấu hình JSON `MessageConverter` và type metadata để class-level listener biết payload là `OrderCreated` hay `OrderCancelled`.
5. Xử lý các lỗi không tìm thấy handler, nhiều handler cùng khớp, sai type headers, JSON không hợp lệ và fallback không mong muốn.
6. Kiểm chứng handler nào chạy, kết quả ack/retry/DLQ và tính idempotent của consumer.

## 2. Vị trí của @RabbitHandler trong đường đi của message

Message được producer publish tới exchange, RabbitMQ định tuyến tới queue bằng binding, sau đó listener container nhận **delivery**. Spring AMQP chuyển đổi body thành một object Java và lựa chọn method `@RabbitHandler` phù hợp với **kiểu object đó**.

~~~mermaid
flowchart LR
    P["RabbitTemplate<br/>publish JSON event"] --> E["Exchange<br/>orders.events"]
    E -->|"Binding key"| Q["Queue<br/>orders.events.q"]
    Q --> C["Listener container<br/>AMQP MessageConverter"]
    C --> S{"Payload type?"}
    S -->|"OrderCreated"| H1["@RabbitHandler<br/>onCreated"]
    S -->|"OrderCancelled"| H2["@RabbitHandler<br/>onCancelled"]
    S -->|"Không có handler phù hợp"| H3["@RabbitHandler(isDefault=true)<br/>onUnknown, nếu có"]
~~~

| Thành phần | Vai trò | Không đảm nhận |
|---|---|---|
| Exchange và binding | Chọn queue nhận message | Không chọn method `@RabbitHandler` |
| `@RabbitListener` trên class | Đăng ký một listener endpoint cho các queue được chỉ định | Không tự suy luận mọi kiểu DTO của các handler |
| AMQP `MessageConverter` | Biến body bytes/properties thành Java payload | Không tự tạo business handler |
| `@RabbitHandler` trên method | Xử lý payload có kiểu phù hợp | Không tạo thêm queue/consumer riêng cho từng method |
| Error handler/ack mode | Xử lý lỗi listener, ack/reject/requeue theo cấu hình | Không biến một payload lỗi thành schema đúng |

**Điểm trọng tâm:** Một class-level `@RabbitListener(queues = "orders.events.q")` là **một endpoint listener**, không phải mỗi `@RabbitHandler` là một subscription RabbitMQ riêng. Các method cùng nhận delivery từ endpoint đó; Spring quyết định method sau bước conversion. Với nhiều instance ứng dụng cùng nghe một queue, chúng vẫn là **competing consumers**, không phải mỗi method đều nhận một bản message.

## 3. Hai cách sử dụng @RabbitListener

### 3.1. Đặt trên method: một method là endpoint

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SingleOrderListener {

    @RabbitListener(queues = "orders.created.q")
    public void onCreated(OrderCreated event) {
        // Xử lý một loại message.
    }
}
~~~

Ở đây, framework biết method đích **trước khi** chuyển đổi message, nên có thể dùng kiểu tham số `OrderCreated` để hỗ trợ suy luận kiểu đích khi JSON không có type header, tùy converter và phiên bản.

### 3.2. Đặt trên class: nhiều @RabbitHandler

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
@RabbitListener(queues = "orders.events.q")
public class MultiOrderListener {

    @RabbitHandler
    public void onCreated(OrderCreated event) {
        // Xử lý OrderCreated.
    }

    @RabbitHandler
    public void onCancelled(OrderCancelled event) {
        // Xử lý OrderCancelled.
    }
}
~~~

Ở kiểu này, listener container **chưa biết** phải chọn `onCreated` hay `onCancelled` khi bắt đầu chuyển body. Vì vậy, message converter cần xác định được kiểu payload (ví dụ dựa vào type headers, class mapper hoặc metadata được thỏa thuận). Sau khi conversion thành object, framework mới chọn đúng handler.

| Tiêu chí | Method-level `@RabbitListener` | Class-level `@RabbitListener` + `@RabbitHandler` |
|---|---|---|
| Số method xử lý mỗi endpoint | Một method đích | Nhiều handler trong một class |
| Thời điểm biết method đích | Trước bước conversion | Sau conversion, dựa trên Java payload type |
| Suy ra target DTO từ method | Có thể, khi đủ điều kiện | **Không** dùng suy luận từ một method cụ thể trước conversion |
| Header kiểu JSON có vai trò | Có thể không bắt buộc với concrete DTO | Thường quan trọng để converter ra đúng các DTO khác nhau |
| Chọn theo routing key | Không, trừ khi code/endpoint thiết kế riêng | Không; handler chọn theo payload type |
| Dùng raw AMQP `Message` làm payload chính | Phù hợp | Với raw message nên dùng method-level listener |

Không trộn kiểu `@RabbitListener` đặt riêng trên **mỗi** `@RabbitHandler` chỉ để tạo “nhiều handler của một listener”. Nếu muốn những queue hoàn toàn độc lập, nên tạo các method-level listeners hoặc bean riêng cho mỗi endpoint.

## 4. Quy tắc chọn method @RabbitHandler

Theo cơ chế multi-method listeners của Spring AMQP, sau khi payload được chuyển đổi, hệ thống tìm **một method phù hợp duy nhất** với kiểu payload. Kiểu được so với **một tham số không có annotation**, hoặc **một tham số đánh dấu `@Payload`**. Những tham số metadata như `@Header` không phải là tiêu chí chọn method.

Ví dụ:

~~~java
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitHandler
public void onCreated(
        @Payload OrderCreated event,
        @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String routingKey) {
    System.out.println("Created " + event.orderId()
            + " via " + routingKey);
}
~~~

Handler ở đây vẫn được chọn vì payload là `OrderCreated`, **không phải** vì giá trị của `routingKey`. `@Header` bổ sung dữ liệu cho method sau khi method đã được chọn.

Những quy tắc cần nhớ:

1. **Kiểu của payload sau conversion** phải tương thích với tham số payload của handler.
2. **Một handler phù hợp duy nhất** mới có thể được gọi. Nhiều handler khớp mơ hồ là lỗi cần giải quyết ở thiết kế chữ ký.
3. Nếu không có handler phù hợp, một handler `@RabbitHandler(isDefault = true)` có thể được dùng làm fallback.
4. Nếu cả handler thông thường lẫn fallback đều không xử lý được message, lỗi đi qua cơ chế error handling của listener container.
5. Không dựa vào **thứ tự khai báo method** trong source Java để ưu tiên một handler.

### Không chọn theo routing key, eventType hoặc method name

Giả sử hai message có cùng kiểu Java `OrderEvent`, nhưng routing key lần lượt là `order.created` và `order.cancelled`. Viết hai method:

~~~java
@RabbitHandler
public void created(OrderEvent event) { /* ... */ }

@RabbitHandler
public void cancelled(OrderEvent event) { /* ... */ }
~~~

**Không phải** là cách phân luồng hợp lệ: cả hai cùng khai báo một payload type, dù tên method khác nhau. Spring không thể dựa vào tên method hay routing key để chọn. Bạn cần tạo **hai kiểu payload riêng** (`OrderCreated`, `OrderCancelled`) hoặc một handler duy nhất tự dispatch theo `eventType`, hoặc tách queue/listener ở tầng topology.

### Kiểu kế thừa và ambiguity

Ví dụ nếu payload là `String` mà một handler nhận `CharSequence`, handler khác nhận `java.io.Serializable`, cả hai interface đều có thể gán được từ String. Không nên kỳ vọng Spring tự chọn đúng ý nghiệp vụ. Thiết kế kiểu handler không chồng lấp, và kiểm thử payload thực tế để bảo đảm phương thức được chọn duy nhất.

## 5. Ví dụ hoàn chỉnh với hai DTO

Giả sử cùng queue `orders.events.q` nhận hai loại event. Một service dùng `RabbitTemplate` phát DTO, class-level listener xử lý tùy loại.

### 5.1. Định nghĩa hợp đồng event

Ví dụ dưới đây dùng Java `record`; có thể thay bằng POJO nếu phiên bản Java/Jackson của dự án chưa phù hợp. Đặt mỗi `public record` trong **một file Java riêng**.

~~~java
// OrderCreated.java
package com.example.orders.events;

import java.math.BigDecimal;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal totalAmount,
        int schemaVersion) {
}
~~~

~~~java
// OrderCancelled.java
package com.example.orders.events;

public record OrderCancelled(
        String eventId,
        String orderId,
        String reason,
        int schemaVersion) {
}
~~~

Lựa chọn hai Java types riêng có ý nghĩa quan trọng: **đây là thứ Spring dùng để phân phối tới `@RabbitHandler`** sau conversion. Trường `schemaVersion` giúp quản trị hợp đồng JSON, còn `eventId` giúp consumer xử lý trùng theo logic nghiệp vụ. Hai trường này **không tự thay thế** type mapping.

### 5.2. Định tuyến RabbitMQ: một queue, hai binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events", true, false);
    }

    @Bean
    Queue ordersEventsQueue() {
        return QueueBuilder.durable("orders.events.q").build();
    }

    @Bean
    Binding ordersCreatedBinding(Queue ordersEventsQueue,
                                 DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersEventsQueue)
                .to(ordersExchange)
                .with("order.created");
    }

    @Bean
    Binding ordersCancelledBinding(Queue ordersEventsQueue,
                                   DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersEventsQueue)
                .to(ordersExchange)
                .with("order.cancelled");
    }
}
~~~

Đây là **routing của broker**: direct exchange chọn queue khi routing key khớp một trong hai binding. Hai key đều dẫn vào **cùng** queue. Việc chọn `onCreated` hay `onCancelled` diễn ra **sau đó trong Java**, không xảy ra ở RabbitMQ.

Bean `Queue`, `DirectExchange`, `Binding` chỉ được khai báo lên broker khi có hạ tầng khai báo phù hợp như `RabbitAdmin`, cùng vhost và quyền cấu hình. Nếu topology đã có do IaC quản lý, không tạo các bean mâu thuẫn chỉ để listener khởi động.

### 5.3. JSON converter dùng chung cho producer và listener

Với **Spring AMQP 3.x / Jackson 2**, có thể khai báo converter:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AmqpMessageConfig {

    @Bean
    MessageConverter amqpJsonConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Trong ứng dụng Spring Boot được auto-configure theo cách thông thường, `MessageConverter` bean phù hợp có thể được gắn vào `RabbitTemplate` và listener factory. Nếu tự tạo `RabbitTemplate` hoặc listener factory, phải **kiểm tra converter thực tế trên cả hai phía**, tránh để publisher dùng JSON mà listener vẫn dùng `SimpleMessageConverter`.

Với **Spring AMQP 4.0+ / Jackson 3**, converter tương ứng là `JacksonJsonMessageConverter`; không copy import Jackson 2 hoặc constructor mapper Jackson 2 sang nhánh Jackson 3. Các ví dụ khác của bài dùng API `MessageConverter` chung, nhưng class cụ thể cần được chọn theo phiên bản Spring AMQP thực sự được resolve bởi BOM/dependency graph.

### 5.4. Producer phát hai kiểu object

~~~java
import com.example.orders.events.OrderCancelled;
import com.example.orders.events.OrderCreated;
import java.math.BigDecimal;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrdersPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendExamples() {
        rabbitTemplate.convertAndSend(
                "orders.events",
                "order.created",
                new OrderCreated("evt-101", "O-101",
                        new BigDecimal("199.00"), 1));

        rabbitTemplate.convertAndSend(
                "orders.events",
                "order.cancelled",
                new OrderCancelled("evt-102", "O-102",
                        "Customer request", 1));
    }
}
~~~

`convertAndSend` dùng converter của template để biến DTO thành JSON bytes/properties khi converter JSON được cấu hình. Spring JSON converter thường gửi metadata kiểu như `__TypeId__` theo cách mapper hoạt động; consumer dùng thông tin đó để dựng lại Java type **trước khi chọn handler**. Không coi tên DTO trong Java là một phần bắt buộc của giao thức RabbitMQ; đây là chi tiết thỏa thuận serialization phía ứng dụng.

### 5.5. Class-level listener và hai handler

~~~java
import com.example.orders.events.OrderCancelled;
import com.example.orders.events.OrderCreated;
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
@RabbitListener(id = "orders-multi", queues = "orders.events.q")
public class OrdersMultiHandler {

    @RabbitHandler
    public void onCreated(
            @Payload OrderCreated event,
            @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String key) {
        System.out.printf(
                "CREATED id=%s key=%s%n", event.eventId(), key);
        // Ghi nhận eventId để xử lý trùng trước khi tác động nghiệp vụ.
    }

    @RabbitHandler
    public void onCancelled(OrderCancelled event) {
        System.out.printf("CANCELLED id=%s%n", event.eventId());
        // Quy trình hủy đơn hàng.
    }
}
~~~

Với JSON converter đã xác định đúng `OrderCreated`, Spring gọi `onCreated`; với `OrderCancelled`, gọi `onCancelled`. `@Header(AmqpHeaders.RECEIVED_ROUTING_KEY)` lấy metadata của delivery để log/kiểm tra, **không phải** điều kiện Spring dùng để chọn handler.

**Vấn đề dễ bỏ qua:** `@RabbitListener(id = "orders-multi", queues = "orders.events.q")` chỉ đăng ký một listener endpoint. Nếu cần tăng throughput, có thể điều chỉnh concurrency của container theo yêu cầu, nhưng mỗi replica/consumer vẫn chỉ nhận từng delivery rồi phân phối tới **một** handler tương ứng.

## 6. Default handler: @RabbitHandler(isDefault = true)

Nếu không có method nào phù hợp với kiểu payload, bạn có thể khai báo **một** fallback handler:

~~~java
@RabbitHandler(isDefault = true)
public void onUnknown(Object payload) {
    throw new IllegalArgumentException(
            "Unsupported order event payload: "
                    + (payload == null
                    ? "null"
                    : payload.getClass().getName())
    );
}
~~~

Handler này có thể bổ sung vào class `OrdersMultiHandler`. Tính năng `isDefault` có từ Spring AMQP **2.0.3**; chỉ được khai báo **tối đa một default method** trong tập handler. Fallback chạy khi không tìm thấy method phù hợp từ các handler thông thường; đừng coi nó là giải pháp giải quyết **hai handler cùng khớp** một kiểu payload. Trường hợp mơ hồ cần sửa chữ ký hoặc conversion, không thể dựa vào default để chọn ngẫu nhiên.

### Chọn hành vi fallback theo nghiệp vụ

| Hành vi fallback | Tác động | Khi nào dùng? |
|---|---|---|
| Log ngắn rồi trả về bình thường | Container có thể ack delivery theo chế độ AUTO | Chỉ khi message lạ **được phép bỏ qua** theo hợp đồng |
| Ném exception | Đi vào error handler/requeue/retry/DLQ theo cấu hình | Khi cần báo lỗi dữ liệu/đưa vào quarantine |
| Ghi lại event lạ vào hệ thống riêng rồi trả về | Có thể lưu dấu vết nhưng phải thiết kế transaction/idempotency | Khi cần kiểm tra schema mới mà không làm nghẽn queue |
| Dispatch thủ công theo field `eventType` | Fallback trở thành bộ chọn nghiệp vụ thứ hai | Khi payload cố ý là envelope và không thể dùng typed handlers |

Trong ví dụ, ném `IllegalArgumentException` nhằm thể hiện lỗi dữ liệu không được hỗ trợ. **Không mặc định** exception này tự đi vào DLQ: việc requeue, retry, reject và dead-letter còn phụ thuộc `AcknowledgeMode`, error handler, retry interceptor, DLX/binding và policy thực tế. Với message “poison” có thể gây lỗi lặp đi lặp lại, hãy cấu hình điểm dừng rõ ràng.

Nếu muốn xử lý raw `org.springframework.amqp.core.Message` mà không convert body, tài liệu Spring AMQP khuyến nghị dùng **method-level `@RabbitListener`** thay vì dựa vào `@RabbitHandler` của class-level listener. Default handler nhận payload **đã chuyển đổi**, không phải một raw AMQP message được bảo đảm.

## 7. Tại sao JSON converter quyết định việc chọn handler?

Đây là phần khó nhất của multi-method listener. Khi một message đến, Spring thực hiện theo thứ tự:

~~~mermaid
flowchart TD
    M["AMQP Message<br/>JSON body + headers"] --> A{"AMQP MessageConverter"}
    A -->|"Tạo OrderCreated"| C["Payload type = OrderCreated"]
    A -->|"Tạo OrderCancelled"| D["Payload type = OrderCancelled"]
    A -->|"Thiếu type mapping<br/>tạo Map/byte[]/String"| U["Payload type khác"]
    C --> H1["@RabbitHandler(OrderCreated)"]
    D --> H2["@RabbitHandler(OrderCancelled)"]
    U --> F{"Có default handler?"}
    F -->|Có| HD["@RabbitHandler(isDefault=true)"]
    F -->|Không| ERR["Lỗi không tìm thấy handler phù hợp"]
~~~

### 7.1. Method-level listener có lợi thế suy luận type

Khi `@RabbitListener` đặt trực tiếp trên một method có **một** tham số payload kiểu cụ thể, framework có thể đưa inferred argument type cho converter. Khi `@RabbitListener` đặt trên class có nhiều `@RabbitHandler`, framework **không biết handler đích trước khi conversion**, nên không thể suy inferred type từ một method như trường hợp một handler.

Vì vậy, chỉ tạo DTO `OrderCreated` và viết:

~~~java
@RabbitHandler
public void handle(OrderCreated event) { /* ... */ }
~~~

không đủ nếu incoming body là JSON nhưng converter chỉ trả `LinkedHashMap` do **thiếu type header và không có type mapping**. Handler `OrderCreated` không được chọn chỉ vì JSON có các key `orderId` và `totalAmount`.

### 7.2. Tình huống JSON từ producer Spring

Một producer `RabbitTemplate` với Jackson JSON converter phù hợp có thể gửi:

~~~text
body: {"eventId":"evt-101","orderId":"O-101",...}
contentType: application/json
headers:
  __TypeId__: com.example.orders.events.OrderCreated
~~~

Đây là **ví dụ minh họa**, không phải yêu cầu bắt buộc mọi producer JSON phải gửi Java class name. Bên nhận cần có class tương ứng và quyền type mapping thích hợp. Nếu class/package khác nhau, hãy ánh xạ type alias thay vì phụ thuộc tên class Java.

### 7.3. Tình huống JSON từ producer không phải Java

Một producer viết bằng Node.js/Go/Python thường chỉ gửi JSON body và `contentType = application/json`:

~~~json
{
  "eventId": "evt-101",
  "eventType": "order.created",
  "orderId": "O-101",
  "schemaVersion": 1
}
~~~

Nếu không có type headers và converter không có thông tin khác, việc deserialize JSON thành `Map` thường là hành vi bình thường. Khi ấy không thể tự động chọn `@RabbitHandler(OrderCreated)` chỉ dựa trên `eventType` nằm trong JSON.

Các hướng thiết kế hợp lý:

1. **Thống nhất type alias trong AMQP headers** (ví dụ `__TypeId__ = order.created.v1`) và ánh xạ alias → DTO ở consumer.
2. **Dùng method-level listener** với DTO cụ thể trên các queue tách biệt, khi routing topology cho phép.
3. **Dùng một envelope type** (ví dụ `EventEnvelope`) và một handler phân nhánh bằng `eventType`, nếu chủ ý giữ một wire contract độc lập Java types.
4. **Dùng custom converter** có hợp đồng ánh xạ `eventType` hoặc application header đến DTO an toàn trước khi handler selection.

Không nên dựa vào class name do producer không tin cậy gửi để tự ý instantiate các class tùy ý trong JVM.

## 8. Ánh xạ logical type ID thay cho tên class Java

Nếu nhiều service triển khai bằng Java nhưng có package khác nhau, logical type IDs giúp giảm coupling. Ví dụ producer ghi `__TypeId__: order.created.v1`, consumer ánh xạ alias này thành `OrderCreated.class`.

Với nhánh **Spring AMQP 3.x / Jackson 2**, có thể cấu hình `DefaultClassMapper`:

~~~java
import com.example.orders.events.OrderCancelled;
import com.example.orders.events.OrderCreated;
import java.util.Map;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class EventTypeMappingConfig {

    @Bean
    MessageConverter amqpJsonConverter() {
        DefaultClassMapper mapper = new DefaultClassMapper();
        mapper.setIdClassMapping(Map.of(
                "order.created.v1", OrderCreated.class,
                "order.cancelled.v1", OrderCancelled.class
        ));
        mapper.setTrustedPackages("com.example.orders.events");

        Jackson2JsonMessageConverter converter =
                new Jackson2JsonMessageConverter();
        converter.setClassMapper(mapper);
        return converter;
    }
}
~~~

Đây là **phương án thay thế** bean converter đơn giản ở mục 5.3, **không** thêm cả hai bean cùng mục đích vào một cấu hình mà không xác định converter nào đang được dùng. Khi mapper được dùng ở producer và consumer, alias có thể được ghi/đọc tương ứng; với producer khác ngôn ngữ, cần bảo đảm header thực tế trùng alias đã định nghĩa.

**Cẩn trọng với version:** API cụ thể của class mapper, constructor, trusted packages và Jackson mapper thay đổi theo nhánh Spring AMQP. Với Spring AMQP 4.0+/Jackson 3, hãy dùng converter và type mapper tương thích, không gắn bừa `ObjectMapper` Jackson 2 vào class mới. Nếu muốn chuyển alias mapping sang nhánh 4.x, kiểm tra Javadoc cho `JacksonJsonMessageConverter`, `DefaultJacksonJavaTypeMapper` hoặc mapper tương ứng trong phiên bản thực tế.

### Trách nhiệm bảo mật của type mapping

- Dùng alias được quản lý tập trung và giới hạn class DTO có thể deserialize.
- Kiểm tra trusted packages/class mapper khi producer không tin cậy; tránh cho phép `*` một cách tùy tiện.
- `__TypeId__` chỉ là metadata do producer gửi, **không phải chứng minh danh tính producer**.
- Nếu dùng hai class khác nhau có cùng schema, thỏa thuận rõ `schemaVersion`, unknown fields và thời gian duy trì tương thích.

## 9. Tham số method: payload, headers và metadata

`@RabbitHandler` có thể nhận thêm metadata mà không thay đổi tiêu chí chọn handler.

~~~java
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitHandler
public void onCancelled(
        @Payload OrderCancelled event,
        @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String routingKey) {

    if (event.schemaVersion() != 1) {
        throw new IllegalArgumentException("Unsupported schema version");
    }
    System.out.println(event.orderId() + " routed with " + routingKey);
}
~~~

Lưu ý:

- Một tham số payload không có annotation thường được hiểu là payload; đặt `@Payload` giúp mã nguồn rõ ý định.
- `@Header` đọc application/AMQP metadata sau conversion và selection; header bị thiếu có thể gây lỗi binding argument nếu bạn khai báo nó là bắt buộc.
- Thêm **hai tham số không được đánh dấu rõ vai trò** có thể khiến framework không xác định được payload parameter.
- Không trộn `org.springframework.messaging.Message` với `org.springframework.amqp.core.Message`; các type phục vụ những tầng xử lý khác nhau.
- Nếu muốn kiểm tra route-specific business invariant, đọc received routing key **sau khi handler đã được chọn**.

Không cố sử dụng `@RabbitHandler` như annotation định tuyến động theo một header hoặc exchange name. Cần chọn một chiến lược rõ ràng: broker route tới queue; converter chọn Java type; handler xử lý nghiệp vụ.

## 10. Handler không khớp, ambiguity và exception

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có handler phù hợp | Converted payload là `Map` nhưng chỉ có handler DTO | Kiểm tra JSON converter, type header hoặc class mapper |
| Handler khác dự kiến được chọn | Payload thực tế khác kiểu kỳ vọng | Log class name/ID an toàn; kiểm tra serializer và alias |
| Có nhiều handler cùng khớp | Hai method nhận cùng type hoặc các interface/supertype chồng lấp | Thiết kế tập type không mơ hồ, bỏ method dư |
| `@RabbitHandler(isDefault=true)` chạy thường xuyên | Message không được chuyển thành DTO cụ thể | Điều tra converter thay vì dùng fallback để che lỗi |
| Lỗi parse JSON | Body sai cú pháp, content type/charset khác hợp đồng | Chặn poison message; phân loại lỗi vĩnh viễn |
| Lỗi trusted packages | Header type trỏ đến class/package không được phép | Kiểm tra nguồn gửi, mapping và policy tin cậy |
| Fallback ném exception rồi message requeue liên tục | Error handler/requeue mặc định chưa phù hợp | Thiết kế retry giới hạn và DLX/DLQ |
| Routing key đúng nhưng handler không chạy | Routing chỉ đưa message tới queue; conversion/dispatch hỏng | Kiểm tra container logs và queue unacked/DLQ |

### Tại sao không nên thêm @RabbitHandler(Object) tùy tiện?

Một method thường (không `isDefault=true`) nhận `Object` có thể match rất rộng vì phần lớn payload Java đều gán được cho `Object`. Kết hợp nó với nhiều handler cụ thể dễ tạo lựa chọn khó hiểu. Khi cần fallback, hãy **đánh dấu `isDefault = true`** để truyền đạt rõ ý định và kiểm thử với payload unknown.

### Khi không có default handler

Nếu converted payload không khớp handler nào, framework có thể báo lỗi chọn method trước khi vào business handler. Exception được xử lý bởi listener container/error handler, không phải tự động bởi một method không mang `@RabbitHandler`. Hãy kiểm tra log đầy đủ của listener endpoint và không đoán rằng message đã đến DLQ.

### Khi lỗi xảy ra trước dispatch

Nếu JSON body sai cú pháp hoặc bị chặn vì type header không hợp lệ, **conversion có thể thất bại trước khi Spring chọn bất kỳ `@RabbitHandler` nào**. Default handler cũng không thể “bắt” mọi conversion exception. Những lỗi này phải được xử lý qua container error handling, retry/reject/DLX hoặc công cụ quản trị lỗi đã thiết kế.

## 11. Ack, retry, dead-letter và tính đúng một lần

Đổi `@RabbitListener` từ method-level sang class-level **không** tự thay đổi semantics ack. Container vẫn quyết định nhận delivery, điều phối method, gửi acknowledgement và xử lý exception theo cấu hình.

~~~mermaid
flowchart TD
    Q["RabbitMQ queue<br/>delivery"] --> C["MessageConverter"]
    C -->|"Conversion lỗi"| X["Listener error handling"]
    C -->|"Conversion thành Java object"| D{"Handler selection"}
    D -->|"Chọn duy nhất"| H["@RabbitHandler được gọi"]
    D -->|"Không khớp / mơ hồ"| X
    H -->|"Business xử lý thành công"| ACK["Ack theo container ack mode"]
    H -->|"Business ném exception"| X
    X --> POLICY["Retry/requeue/reject/DLX<br/>theo cấu hình"]
~~~

| Chủ đề | Ý nghĩa khi dùng @RabbitHandler |
|---|---|
| `AcknowledgeMode.AUTO` | Container thường ack sau khi listener xử lý thành công; có xử lý lỗi nếu thất bại |
| `AcknowledgeMode.MANUAL` | Ứng dụng chịu trách nhiệm ack/nack trên channel của delivery |
| Retry | Có thể retry ở listener/container hoặc dùng topology retry riêng |
| Dead-letter | Message chỉ được đưa tới DLX khi broker nhận các điều kiện dead-letter phù hợp, với topology đã khai báo |
| Idempotency | Mỗi logical event nên có ID ổn định; consumer có thể nhận lại sau disconnect |
| Publisher confirms | Xác nhận broker xử lý publish, không xác nhận handler nào chạy hay nghiệp vụ thành công |

Nếu một handler cập nhật database rồi exception trước khi ack, message có thể được redeliver. Nếu business method được gọi hai lần, `@RabbitHandler` không giúp chống trùng. Cần lưu/deduplicate `eventId` trong phạm vi dữ liệu nghiệp vụ thích hợp, và hiểu transaction boundary giữa database với RabbitMQ.

**Không giả định “một queue + nhiều handler” là một transaction cho tất cả loại event.** Mỗi delivery được tiêu thụ và xác nhận theo cơ chế bình thường; các handler là nhánh xử lý cho từng message.

## 12. Dùng @RabbitHandler với nhiều queue hay nhiều service?

Một class-level listener có thể chỉ định nhiều queue, ví dụ:

~~~java
@RabbitListener(queues = { "orders.events.q", "orders.audit.q" })
public class SharedHandlers {
    @RabbitHandler
    public void onCreated(OrderCreated event) { /* ... */ }

    @RabbitHandler
    public void onCancelled(OrderCancelled event) { /* ... */ }
}
~~~

Spring vẫn chọn handler theo **payload type**. Tên queue nào vừa giao message **không** tự chọn method. Dù cấu hình được, việc nghe nhiều queue có thể làm trách nhiệm nghiệp vụ/khả năng quan sát khó rõ ràng. Chỉ gom khi chúng có **hợp đồng message và chính sách xử lý tương thích**.

Nếu hai service cùng lắng nghe một **queue cố định**, RabbitMQ phân phối message cho các consumer cạnh tranh — mỗi message thường được giao cho một consumer, không phải phát cho cả hai service. Nếu cả audit và fulfillment cần một bản riêng, nên có hai queue với binding thích hợp tới exchange; mỗi service có listener riêng.

### Một class hay nhiều class?

Ưu tiên class-level listener có nhiều handler khi:

- Các event thuộc **cùng một nhóm nghiệp vụ** và dùng chung chính sách consumer.
- JSON converter xác định được **kiểu DTO cụ thể** trước dispatch.
- Các method tương đối độc lập, ít xảy ra mơ hồ khi mở rộng type hierarchy.

Ưu tiên các method-level listeners hoặc class riêng khi:

- Cần **concurrency, prefetch, retry, DLQ hoặc quyền truy cập khác nhau** cho từng loại sự kiện.
- Các event có **schema và ownership khác nhau** giữa các đội.
- Producer không cung cấp type metadata, trong khi routing key mới là khóa phân loại ổn định.
- Cần nhận **raw AMQP Message** hoặc tự đọc headers/body trước khi giải mã.

Không vì giảm số class Java mà gom tất cả sự kiện của hệ thống vào một multi-method endpoint.

## 13. Quan sát và kiểm thử handler được chọn

Để kiểm chứng, cần xác định **message nào đến queue**, **được converter tạo thành class gì**, rồi **method nào được gọi**.

### 13.1. Chuẩn bị integration test

1. Sử dụng broker RabbitMQ test riêng và topology ở mục 5, không dùng queue chung với production.
2. Xác nhận queue `orders.events.q` nhận hai routing keys `order.created` và `order.cancelled`.
3. Producer và listener dùng JSON converter thích hợp; kiểm tra message có type headers/alias tương ứng.
4. Tạm dừng các consumer khác để tránh một message bị instance khác lấy trước trong lúc kiểm thử.
5. Trong hai handler, ghi `eventId` vào một test collector/thread-safe queue hoặc đếm latch; tránh assert chỉ dựa trên `System.out`.

### 13.2. Ma trận phép thử

| Kịch bản | Input/metadata | Handler mong đợi | Điều cần quan sát |
|---|---|---|---|
| A | `OrderCreated` được JSON-convert và có type metadata đúng | `onCreated` | DTO và `eventId` đúng |
| B | `OrderCancelled` được JSON-convert | `onCancelled` | Có đúng một handler được gọi |
| C | JSON hợp lệ nhưng không có type header, converter trả `Map` | Default handler, nếu có | Không tự vào `onCreated` |
| D | Type header không nhận diện được | Có thể lỗi conversion hoặc fallback tùy cấu hình | Error handler/DLQ thực tế |
| E | Hai handlers có type chồng lấp | Phải phát hiện sự mơ hồ | Không “đoán” method theo thứ tự source |
| F | JSON bị cắt hoặc sai cú pháp | Conversion lỗi trước handler | Không có business method được gọi |
| G | Handler ném exception | Listener xử lý theo ack/retry policy | Redelivery/requeue/DLX và số lần xử lý |
| H | Hai routing keys cùng tạo **một Java type** | Không có phân luồng method theo key | Cần đổi DTO, queue hoặc dispatch strategy |

### 13.3. Test một nhánh bằng RabbitTemplate

Ví dụ trong một Spring Boot integration test có `RabbitTemplate` và đúng topology:

~~~java
import java.math.BigDecimal;

rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        new OrderCreated(
                "evt-test-1", "O-TEST-1", new BigDecimal("12.50"), 1)
);
~~~

Sau publish, chờ bất đồng bộ bằng latch hoặc cơ chế await phù hợp (không kiểm tra ngay lập tức rồi kết luận fail). Assert `onCreated` nhận `evt-test-1` và `onCancelled` không nhận sự kiện đó. Sau đó publish `OrderCancelled` và đảo assertions.

Nếu muốn kiểm thử không có type metadata, tạo một AMQP `Message` chứa JSON UTF-8 cùng `contentType = application/json`, nhưng không có `__TypeId__`, rồi publish bằng `RabbitTemplate.send(...)`. Test xem default handler hay error handler chạy theo converter thực tế; không giả định JSON field name tự chọn DTO.

### 13.4. Đo kết quả, không chỉ đếm log

Những trường nên log (không lộ dữ liệu nhạy cảm):

- `eventId`, `eventType`/schema version được thỏa thuận.
- Handler đã được gọi (`onCreated`, `onCancelled`, fallback).
- Converted payload class name chỉ trong môi trường kiểm tra có kiểm soát.
- Routing key nhận được, vhost/queue và message headers cần thiết.
- Thời gian xử lý, exception category, retries, DLQ count, unacked count.

Publisher confirm `ack=true` không chứng minh `@RabbitHandler` đã xử lý. Phải xem metric của consumer, tác động nghiệp vụ hoặc điểm xác nhận xử lý hợp lệ.

## 14. Các lỗi thiết kế thường gặp

### Lỗi 1 — Chọn method theo routing key

~~~java
// Không hợp lệ về ý nghĩa dispatch: cả hai nhận cùng một kiểu.
@RabbitHandler public void created(OrderEvent event) { }
@RabbitHandler public void cancelled(OrderEvent event) { }
~~~

**Sửa:** tạo hai payload types riêng, dùng một handler tự phân loại bằng `eventType`, hoặc tách queue/listener theo routing key.

### Lỗi 2 — Không cấu hình JSON converter

Producer gửi object JSON nhưng consumer dùng converter trả `byte[]`. Handler DTO không match.

**Sửa:** xác nhận `RabbitTemplate` và listener container dùng `Jackson2JsonMessageConverter` với Jackson 2/Spring AMQP 3.x hoặc `JacksonJsonMessageConverter` với Jackson 3/Spring AMQP 4.x tương ứng.

### Lỗi 3 — Tưởng method parameter có thể giúp infer kiểu trước dispatch

Class-level listener có hai handlers, producer gửi JSON không type metadata. Converter tạo `Map` và không handler DTO nào được chọn.

**Sửa:** cung cấp type ID/alias mapper, custom conversion hoặc thay bằng method-level listener trong topology cho phép.

### Lỗi 4 — Bắt mọi sự kiện bằng Object rồi bỏ qua

Default handler `Object` chỉ log “unknown” rồi return, khiến container có thể ack và **bỏ message nghiệp vụ mới** mà chưa có handler.

**Sửa:** xem unknown event là quyết định chính sách: quarantine, reject/DLQ, alert hoặc bỏ qua có chủ đích và quan sát được.

### Lỗi 5 — Mở trustedPackages quá rộng

Message header có thể chứa Java class name do bên gửi chỉ định. Chấp nhận mọi package không cần thiết làm mở rộng rủi ro deserialization.

**Sửa:** giới hạn mapping/nguồn tin cậy và sử dụng logical event IDs, không mặc định tin metadata bên ngoài.

### Lỗi 6 — Nghĩ handler nào cũng có consumer riêng

Một queue với ba `@RabbitHandler` không tự tạo ba subscriptions tới broker.

**Sửa:** xem class-level listener là **một endpoint**; nếu cần khác biệt concurrency/retry, tách endpoints hoặc cấu hình container theo trách nhiệm.

## 15. Bài tập tự kiểm tra

### Bài 1 — @RabbitHandler chọn dựa trên gì?

Một message có routing key `order.cancelled` nhưng converter tạo ra object `OrderCreated`. Handler nào có khả năng chạy?

**Gợi ý:** handler nhận `OrderCreated`, vì method selection dựa trên Java payload type sau conversion, không dựa trên routing key. Nếu đây là bất thường, kiểm tra type header và validation của ứng dụng.

### Bài 2 — Vì sao Map không match DTO?

JSON body có `orderId` và `schemaVersion`, nhưng `onCreated(OrderCreated)` không chạy; fallback nhận `LinkedHashMap`.

**Gợi ý:** class-level listener không thể infer target DTO từ một method duy nhất trước khi chọn handler. Hãy cung cấp type metadata/mapping hoặc thay đổi thiết kế converter.

### Bài 3 — Một default hay nhiều default?

Có thể khai báo `@RabbitHandler(isDefault=true)` cho cả `Object` và `String` không?

**Đáp án:** không; chỉ tối đa một default method. Nếu muốn xử lý String đặc biệt, tạo `@RabbitHandler(String)` thông thường và để default xử lý các trường hợp còn lại.

### Bài 4 — Hai method cùng kiểu

Hai handlers đều nhận `OrderEvent` nhưng method names khác nhau. Có được phân phối ngẫu nhiên hoặc theo thứ tự khai báo?

**Đáp án:** không được dựa vào hai giả định đó. Tập handler không xác định được một method duy nhất; cần tách kiểu hoặc tự phân loại trong một handler.

### Bài 5 — Producer không phải Spring

Producer Go gửi JSON với `contentType=application/json`, không gửi `__TypeId__`. Consumer có hai DTO handlers. Đề xuất hai thiết kế giúp message được xử lý đúng.

**Gợi ý:** dùng logical type ID trong header và class mapper; hoặc một envelope DTO để listener tự dispatch bằng `eventType`; hoặc tách queue và method-level listeners theo routing.

### Bài 6 — Handler lỗi có tự vào DLQ?

`onCancelled` ném exception vì database timeout. Message có chắc vào DLQ ngay không?

**Đáp án:** không. Phụ thuộc ack mode, error handler, requeue policy, retry interceptor và DLX/binding thực tế. Với lỗi tạm thời cần retry có giới hạn và idempotency.

### Bài 7 — Class-level hay method-level?

Bạn có 3 nghiệp vụ khác nhau: thanh toán (cần hạn chế concurrency), gửi email (retry dài) và audit (cho phép bỏ qua). Có nên gom cùng class-level listener một queue?

**Gợi ý:** không nên chỉ vì code ngắn. Chúng cần chính sách tiêu thụ/ack/retry/concurrency khác nhau; cân nhắc tách queue và listener endpoints.

### Bài 8 — Viết test handler selection

Với hai DTO `OrderCreated` và `OrderCancelled`, thiết kế test bảo đảm mỗi input chỉ gọi đúng một handler và unknown JSON không bị mất âm thầm.

**Gợi ý:** dùng RabbitMQ test, latch/collector thread-safe, publish hai types có ID riêng; kiểm tra type headers và method được gọi. Gửi message không type metadata để xác nhận default/error handler đúng hợp đồng, và kiểm tra DLQ nếu cấu hình.

## 16. Checklist khi dùng @RabbitHandler

- [ ] `@RabbitListener` đặt **trên class** và các method xử lý có `@RabbitHandler` phù hợp.
- [ ] Mỗi method có một tham số payload xác định được, không chồng lấp kiểu gây ambiguity.
- [ ] Không dùng method name, routing key hoặc thứ tự khai báo để suy ra handler được chọn.
- [ ] Phân biệt **routing của RabbitMQ** (exchange/binding/queue) với **dispatch trong Spring** (converted payload type).
- [ ] Cấu hình đúng Spring AMQP JSON converter cho cả publisher và listener container.
- [ ] Nếu dùng JSON multi-method listener, xác định rõ type metadata/class mapper/alias hoặc chiến lược custom converter.
- [ ] Không dựa vào type inference của một method khi `@RabbitListener` ở cấp class.
- [ ] Nếu có fallback, chỉ khai báo một `@RabbitHandler(isDefault = true)` và xác định rõ chính sách unknown events.
- [ ] Không cố biến default handler thành nơi bắt mọi lỗi **trước conversion**.
- [ ] Giới hạn trusted packages/class mapping, kiểm tra schema version và nguồn producer.
- [ ] Đặt ack/retry/error handler/DLX cho lỗi conversion, unknown type và business exception một cách chủ đích.
- [ ] Dùng event ID ổn định và consumer idempotent để tránh xử lý trùng khi redelivery.
- [ ] Test cả trường hợp match, no match, ambiguous, malformed JSON, sai type headers và rolling schema changes.
- [ ] Đọc Reference/Javadoc theo phiên bản Spring AMQP thật của dự án thay vì copy class/behavior của nhánh mới hơn.

## 17. Tài liệu tham khảo chính thức

- [Spring AMQP — Multi-method Listeners](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/method-selection.html): `@RabbitListener` ở cấp class, nhiều `@RabbitHandler`, method selection và default handler.
- [Spring AMQP — Message Conversion for Annotated Methods](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): thứ tự chuyển đổi message và phân phối theo payload đã convert.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): JSON type mapping, Jackson và thông tin inferred type.
- [Spring AMQP 3.2 — Message Converters](https://docs.spring.io/spring-amqp/reference/3.2/amqp/message-converters.html): quy tắc của nhánh Jackson 2/Spring AMQP 3.x.
- [Spring AMQP — @RabbitHandler Javadoc](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/annotation/RabbitHandler.html): `isDefault`, điều kiện khớp tham số payload và phiên bản giới thiệu.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): khai báo endpoint và topology bằng annotations.

**Ghi nhớ:** `@RabbitHandler` không định tuyến bằng routing key hay header; nó chọn **một method phù hợp duy nhất với Java payload sau message conversion** trong class có `@RabbitListener`. Để hoạt động đúng với nhiều loại JSON, hãy thiết kế DTO riêng, converter/type mapping đáng tin cậy và fallback có chính sách xử lý lỗi rõ ràng. Khi đã hiểu ranh giới giữa routing, conversion, handler selection và acknowledgement, bạn sẽ xây consumer Spring AMQP dễ mở rộng và kiểm chứng hơn.
