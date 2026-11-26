# JSON converter theo phiên bản: Jackson2JsonMessageConverter hoặc JacksonJsonMessageConverter

Khi tích hợp RabbitMQ bằng Spring AMQP, gọi `RabbitTemplate.convertAndSend(...)` với một object Java không có nghĩa là object đó tự động trở thành JSON. Tương tự, `@RabbitListener` nhận một DTO chỉ hoạt động đúng khi tầng chuyển đổi message biết cách biến các byte từ RabbitMQ thành kiểu Java tương ứng. Càng dễ nhầm hơn khi các tài liệu Spring AMQP ở những phiên bản khác nhau sử dụng hai tên lớp gần giống nhau: **`Jackson2JsonMessageConverter`** và **`JacksonJsonMessageConverter`**.

Bài này thuộc chương **Chuyển đổi dữ liệu** của module **SPRING_AMQP**. Nội dung giúp bạn lựa chọn JSON converter theo phiên bản thực sự của Spring AMQP, cấu hình nhất quán cho `RabbitTemplate` và `@RabbitListener`, hiểu body/properties/headers, xử lý tương thích producer–consumer, và kiểm tra các lỗi chuyển đổi trước khi áp dụng retry, acknowledgement hoặc dead-letter trong hệ thống xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định phiên bản `spring-amqp`, `spring-rabbit` và Jackson thực sự có trong ứng dụng.
2. Chọn **`Jackson2JsonMessageConverter`** cho nhánh dùng Jackson 2, hoặc **`JacksonJsonMessageConverter`** cho nhánh hỗ trợ Jackson 3.
3. Phân biệt chuyển đổi trên `RabbitTemplate`, trên listener container và ở bước chuyển tham số method của `@RabbitListener`.
4. Giải thích vai trò của JSON body, `contentType`, `contentEncoding` và các header nhận diện kiểu như `__TypeId__`.
5. Viết ví dụ producer–consumer có DTO, xử lý khi thiếu hoặc không khớp metadata, và bảo đảm producer/consumer khác ngôn ngữ vẫn đọc được payload.
6. Xây kế hoạch nâng cấp converter, kiểm tra lỗi deserialization và xử lý message lỗi mà không vô tình tạo vòng retry vô hạn.

## 2. MessageConverter nằm ở đâu trong đường đi của message?

RabbitMQ truyền **message body dưới dạng byte[]**. Exchange định tuyến theo routing key/binding/headers; broker thông thường không cần biết các byte trong body là JSON hay một Java object.

~~~mermaid
flowchart LR
    O["OrderCreated<br/>Java object"] --> CT["RabbitTemplate.convertAndSend<br/>JSON MessageConverter"]
    CT --> MSG["AMQP Message<br/>body: UTF-8 JSON bytes<br/>properties: contentType<br/>headers: type metadata nếu có"]
    MSG --> EX["RabbitMQ<br/>exchange → queue"]
    EX --> CL["Listener container<br/>JSON MessageConverter"]
    CL --> DTO["OrderCreated<br/>Java DTO"]
    DTO --> H["@RabbitListener<br/>nghiệp vụ"]
~~~

Tại producer, `convertAndSend(exchange, routingKey, object)` hỏi `MessageConverter` cách tạo `org.springframework.amqp.core.Message` từ object. Tại consumer, listener container dùng converter đã cấu hình để đọc message; tầng gọi phương thức có thể chuyển kiểu thêm một lần trước khi gọi `@RabbitListener`.

| Thành phần | Trách nhiệm chính | Không tự làm |
|---|---|---|
| `RabbitTemplate.send(..., Message)` | Gửi message đã có body và properties | Không tự JSON-serialize body |
| `RabbitTemplate.convertAndSend(..., Object)` | Gọi converter để tạo `Message` rồi publish | Không mặc nhiên dùng JSON nếu chưa cấu hình |
| AMQP `MessageConverter` | Ánh xạ object ↔ body bytes và một phần metadata | Không tự tạo queue/binding |
| `@RabbitListener` | Nhận message đã được listener container xử lý và gọi method | Không bảo đảm object hợp lệ chỉ vì broker đã route đúng |
| RabbitMQ broker | Định tuyến, giữ và giao các message | Không diễn giải Java DTO theo mặc định |

**Đừng nhầm:** `org.springframework.amqp.support.converter.MessageConverter` là API của **Spring AMQP**; `org.springframework.messaging.converter.MessageConverter` là API khác dùng trong bước xử lý Spring Messaging. Còn `MappingJackson2HttpMessageConverter` dành cho HTTP MVC, không phải converter để cấu hình trực tiếp cho `RabbitTemplate`.

## 3. Bảng quyết định theo phiên bản

| Phiên bản Spring AMQP | JSON converter phù hợp | Jackson tương ứng | Cần lưu ý |
|---|---|---|---|
| **Nhánh 3.x**, gồm 3.1/3.2 | `Jackson2JsonMessageConverter` | Jackson **2.x**, namespace `com.fasterxml.jackson...` | Tên lớp mang số **2**; đừng thay bằng `JacksonJsonMessageConverter` từ ví dụ của bản mới |
| **Từ nhánh 4.0**, khi dùng Jackson 3 | `JacksonJsonMessageConverter` | Jackson **3.x**, namespace `tools.jackson...` | Lớp mới xuất hiện từ Spring AMQP 4.0; dùng cấu hình đúng nhánh |
| **Spring AMQP 4.0 có code Jackson 2 cũ** | `Jackson2JsonMessageConverter` còn được đánh dấu **deprecated for removal** trong API 4.0 | Jackson 2 | Cần lập kế hoạch chuyển đổi; deprecation chưa có nghĩa là phương thức đã bị xóa ngay |
| **Bản sau 4.0** | Kiểm tra Javadoc của **chính bản resolved** | Theo BOM/dependency tree | Không giả định lớp Jackson 2 còn tồn tại ở tất cả các bản tương lai |

**Cơ sở xác minh:** tài liệu Spring AMQP 3.2 mô tả `Jackson2JsonMessageConverter` dùng Jackson 2; tài liệu Spring AMQP 4.0 giới thiệu `JacksonJsonMessageConverter` cho Jackson 3. Trong API 4.0, các lớp nền `AbstractJackson2MessageConverter`, `Jackson2JsonMessageConverter` và nhóm `Jackson2JavaTypeMapper` bị đánh dấu **deprecated for removal** để chuyển sang nhóm Jackson 3. Nhãn này là chỉ báo phải migrate; phiên bản loại bỏ cụ thể cần xem release notes/Javadoc của bản đích.

Không chọn converter chỉ dựa trên **major version của Spring Boot** hay vì bạn nhìn thấy artifact `jackson-databind` trên classpath. Với dự án đang chạy, cần xác định **resolved Spring AMQP version**, bộ Jackson được sử dụng và cấu hình dependency management thực tế.

### Quy trình tự kiểm tra dependency

Với Gradle:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-rabbit --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-amqp --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency jackson-databind --configuration compileClasspath
~~~

Với Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Thêm đường dẫn module vào task nếu dự án có nhiều module. Trên macOS/Linux dùng `./gradlew`; trên Windows dùng `.\gradlew.bat` hoặc `mvnw.cmd`. Nhìn vào phiên bản **selected/resolved** và lý do chọn trong dependency graph, thay vì chỉ đọc phiên bản khai báo ở một file build.

Trong IDE, mở class `Jackson2JsonMessageConverter` hoặc `JacksonJsonMessageConverter`: nếu class không có trong jar thực tế, import sẽ không biên dịch. Không giải quyết lỗi bằng cách thêm một Spring AMQP artifact version khác BOM một cách tùy tiện; trước hết hãy xác định nhánh Spring Boot/Spring Framework tương thích.

## 4. Nhánh Spring AMQP 3.x: cấu hình Jackson2JsonMessageConverter

Ví dụ dưới đây áp dụng cho **ứng dụng Spring AMQP 3.x**, dùng Jackson 2 và `spring-boot-starter-amqp`. Không kết hợp đoạn cấu hình này với cấu hình Jackson 3 ở mục 5 trong cùng một ứng dụng.

~~~java
package com.example.orders.config;

import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AmqpJsonConfiguration {

    @Bean
    MessageConverter amqpJsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Ở đây `MessageConverter` được import từ **`org.springframework.amqp.support.converter`**. `Jackson2JsonMessageConverter` tự quản lý mapper mặc định của nó. Nếu cần Java Time Module, quy tắc đặt tên trường hoặc chính sách deserialization khác mặc định, hãy cấu hình ObjectMapper Jackson 2 tương ứng và truyền vào converter; đừng mặc định bean ObjectMapper dùng cho HTTP đã tự được converter này sử dụng.

Ví dụ minh họa kiểu mapper Jackson 2 nếu cần điều chỉnh:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

ObjectMapper jackson2Mapper = JsonMapper.builder()
        .findAndAddModules()
        .build();

Jackson2JsonMessageConverter converter =
        new Jackson2JsonMessageConverter(jackson2Mapper);
~~~

Đây là snippet minh họa cách khởi tạo, không phải bean thứ hai để copy nguyên vào cấu hình trước. `findAndAddModules()` chỉ tìm những Jackson modules đã có trên classpath; không biến mọi kiểu Java bất kỳ thành hợp đồng wire hợp lệ. Các module ngày/giờ và cách serialize `BigDecimal` cần được kiểm tra với DTO thực tế.

Nếu bạn thấy `Jackson2JsonMessageConverter` bị IDE đánh dấu deprecated khi đã nâng lên Spring AMQP 4.0, đó là dấu hiệu cần đọc migration guide sang Jackson 3 ở mục kế tiếp; đừng xóa converter cũ rồi giữ nguyên import ObjectMapper Jackson 2 cho class mới.

## 5. Nhánh Spring AMQP 4.x: cấu hình JacksonJsonMessageConverter

Với **Spring AMQP 4.0 trở lên có hỗ trợ Jackson 3**, class được giới thiệu là **`JacksonJsonMessageConverter`** trong cùng package Spring AMQP:

~~~java
package com.example.orders.config;

import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AmqpJsonConfiguration {

    @Bean
    MessageConverter amqpJsonMessageConverter() {
        return new JacksonJsonMessageConverter();
    }
}
~~~

**Khác biệt thực chất** nằm ở thư viện Jackson:

| Thành phần | Jackson 2 | Jackson 3 |
|---|---|---|
| AMQP converter | `Jackson2JsonMessageConverter` | `JacksonJsonMessageConverter` |
| Mapper truyền vào converter | `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.ObjectMapper` hoặc mapper tương ứng |
| Lớp nền của converter | `AbstractJackson2MessageConverter` | `AbstractJacksonMessageConverter` |
| Mapper type metadata cụ thể | Nhóm `DefaultJackson2JavaTypeMapper` | Nhóm `DefaultJacksonJavaTypeMapper` |
| Khả năng copy nguyên cấu hình của nhánh kia | Không | Không |

`JacksonJsonMessageConverter` có thể dùng mapper Jackson 3 tùy biến nếu cần, nhưng hãy đọc **constructor/Javadoc của phiên bản chính xác** để sử dụng đúng kiểu `ObjectMapper` và API Jackson 3. ObjectMapper `com.fasterxml.jackson.databind.ObjectMapper` của Jackson 2 không thể được truyền vào API nhận `tools.jackson.databind.ObjectMapper` chỉ bằng cách đổi tên converter.

Ví dụ, đừng làm:

~~~java
// SAI nếu converter đòi Jackson 3 ObjectMapper:
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;

ObjectMapper jackson2Mapper = new ObjectMapper();
// new JacksonJsonMessageConverter(jackson2Mapper); // Sai kiểu mapper.
~~~

Đây là ví dụ **lỗi có chủ đích**, không dùng làm code chạy. Nếu ứng dụng phải chạy song song Jackson 2 và Jackson 3 trong giai đoạn nâng cấp, hãy cấu hình rõ bản mapper cho từng API, kiểm tra dependency tree và tránh phụ thuộc vào tên class đơn thuần.

## 6. Chọn converter nhất quán cho RabbitTemplate và @RabbitListener

Trong ứng dụng Spring Boot dùng auto-configuration phù hợp, khai báo một bean Spring AMQP `MessageConverter` là cách phổ biến để `AmqpTemplate` được auto-configure sử dụng converter đó. Đối với listener, cần kiểm tra `RabbitListenerContainerFactory` được cấu hình với cùng converter hoặc converter tương thích. Không mặc định rằng một bean được tự tạo bằng tay sẽ nhận mọi cấu hình của Boot.

### 6.1. DTO minh họa

Sử dụng `record` nếu dự án chạy Java hỗ trợ cú pháp này:

~~~java
package com.example.orders.message;

import java.math.BigDecimal;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total,
        int schemaVersion) {
}
~~~

Ví dụ payload logic:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O-1001",
  "total": 250000,
  "schemaVersion": 1
}
~~~

JSON trên là **hợp đồng dữ liệu**, không phải một bản dump Java object. Các bên phải thỏa thuận ý nghĩa `total` (đơn vị tiền, làm tròn), trường bắt buộc, `schemaVersion` và cách thêm trường trong tương lai.

### 6.2. Producer dùng convertAndSend

~~~java
package com.example.orders.publisher;

import com.example.orders.message.OrderCreated;
import java.math.BigDecimal;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish() {
        OrderCreated event = new OrderCreated(
                "evt-1001", "O-1001", new BigDecimal("250000"), 1);

        rabbitTemplate.convertAndSend(
                "orders.events",    // Exchange đã được khai báo.
                "order.created",    // Routing key.
                event);
    }
}
~~~

Nếu `RabbitTemplate` dùng JSON converter tương ứng, body được tạo thành JSON bytes, thường có `contentType = application/json`. Converter có thể thêm một số header hỗ trợ type mapping theo thiết lập. Lệnh `convertAndSend` không tự tạo exchange, queue hoặc binding; cần khai báo topology để message route được tới queue.

Nếu `RabbitTemplate` vẫn dùng `SimpleMessageConverter`, behavior với một POJO `Serializable` khác JSON converter. Với object không có cách chuyển đổi được converter hỗ trợ, thao tác có thể thất bại. Vì thế, phải kiểm tra bytes và metadata của **message thực tế** thay vì đoán theo tên method.

### 6.3. Listener nhận DTO

~~~java
package com.example.orders.consumer;

import com.example.orders.message.OrderCreated;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @RabbitListener(queues = "orders.created.q")
    public void onOrderCreated(OrderCreated event) {
        if (event.schemaVersion() != 1) {
            throw new IllegalArgumentException("Unsupported event schema");
        }
        // Lưu eventId trước hoặc trong giao dịch xử lý để chống trùng.
        System.out.println("Received order: " + event.orderId());
    }
}
~~~

Listener này chỉ hoạt động như mong đợi nếu container được gắn converter JSON phù hợp và queue `orders.created.q` đã được khai báo, binding được route chính xác. Một method parameter là kiểu DTO cụ thể giúp converter suy ra kiểu đích, tùy phiên bản và cách cấu hình listener.

**Lưu ý độ tin cậy:** exception khi schema không được hỗ trợ không có nghĩa broker sẽ tự động dead-letter. Việc reject/requeue/retry/DLX phụ thuộc cấu hình listener container, error handler và broker. Cần xác định chính sách cho **lỗi dữ liệu vĩnh viễn** khác với **lỗi tài nguyên tạm thời**.

## 7. Khi cần cấu hình rõ listener container factory

Nếu không sử dụng auto-configuration hoặc có nhiều listener factories, hãy gắn **đúng Spring AMQP MessageConverter** vào factory phục vụ `@RabbitListener`:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderListenerFactoryConfig {

    @Bean
    SimpleRabbitListenerContainerFactory orderListenerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter amqpJsonMessageConverter) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(amqpJsonMessageConverter);
        return factory;
    }
}
~~~

Áp dụng cho listener:

~~~java
@RabbitListener(
    queues = "orders.created.q",
    containerFactory = "orderListenerFactory")
public void handle(OrderCreated event) {
    // ...
}
~~~

Đoạn code này có thể dùng với **một trong hai** JSON converters, vì tham số có interface `MessageConverter` chung của Spring AMQP. Khi dùng Spring Boot, tự tạo factory có thể bỏ qua các tùy chỉnh Boot sẵn có về concurrency, message conversion, retry, acknowledgement, observation hoặc transaction. Trong dự án thực tế nên kiểm tra cách dùng **listener factory configurer** của đúng Spring Boot version, sau đó mới ghi đè phần cần thiết.

Với các bản Spring AMQP hỗ trợ `@RabbitListener(messageConverter = "...")`, có thể chỉ định converter theo tên bean trực tiếp ở annotation:

~~~java
@RabbitListener(
    queues = "orders.created.q",
    messageConverter = "amqpJsonMessageConverter")
public void handle(OrderCreated event) {
    // ...
}
~~~

Cách này không đồng nghĩa hai đoạn cấu hình factory và annotation phải cùng xuất hiện. Hãy chọn một chiến lược rõ ràng, kiểm tra thuộc tính `messageConverter` có tồn tại trong phiên bản Spring AMQP của bạn, và tránh cấu hình nhiều converter không có chủ đích.

## 8. Cơ chế hai bước chuyển đổi của @RabbitListener

Khi listener dùng annotation ở **mức method**, dữ liệu có thể đi qua hai bước:

~~~mermaid
flowchart TD
    A["AMQP Message<br/>body = bytes"] --> B["Bước 1: AMQP MessageConverter<br/>container factory"]
    B --> C["Spring Messaging payload<br/>object / String / byte[]"]
    C --> D["Bước 2: method argument conversion<br/>DefaultMessageHandlerMethodFactory"]
    D --> E["@RabbitListener(OrderCreated event)"]
~~~

**Bước 1** dùng `org.springframework.amqp.support.converter.MessageConverter` để chuyển body và type metadata thành payload của message ở phía ứng dụng. JSON converter thay thế `SimpleMessageConverter` ở bước này.

**Bước 2** chọn tham số method. Converter mặc định ở tầng này thường là `GenericMessageConverter` dùng Spring ConversionService. Đây là hai khái niệm khác nhau; lỗi “JSON bytes đã được nhận nhưng method không nhận đúng DTO” có thể do bước 1 trả về `Map`/`byte[]`, hoặc bước 2 không thể chuyển payload đó thành `OrderCreated`.

Ví dụ:

- Listener nhận `org.springframework.amqp.core.Message`: bạn đọc `getBody()` và `getMessageProperties()` trực tiếp; đừng nghĩ body đã thành DTO.
- Listener nhận `String`: nếu bạn muốn body là chuỗi JSON thô, cần hiểu converter có thể biến JSON thành object hoặc chuỗi theo nội dung/type; chữ ký `String` không tự bảo đảm bạn luôn nhận nguyên JSON text.
- Listener nhận `OrderCreated`: cần JSON converter phù hợp, schema đúng và target type xác định được.
- Listener dùng class-level `@RabbitListener` với nhiều `@RabbitHandler`: việc chọn handler dựa trên payload sau chuyển đổi, nên type metadata và class mapping đặc biệt quan trọng.

Khi debug, quan sát **kết quả chuyển đổi bước 1** và chữ ký method trước khi thêm custom `ConversionService`. Nhiều lỗi được giải quyết bằng cấu hình AMQP JSON converter đúng nhánh mà không cần can thiệp bước 2.

## 9. Message body, contentType và encoding

JSON converter xuất/đọc **bytes**, còn `MessageProperties` cho biết consumer nên diễn giải bytes như thế nào.

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| `body` | `{"orderId":"O-1001"}` mã hóa UTF-8 | Dữ liệu trao đổi |
| `contentType` | `application/json` | Gợi ý đúng loại converter/định dạng |
| `contentEncoding` | `UTF-8` nếu được đặt | Cách giải mã ký tự; cũng có thể mô tả trong charset của contentType |
| `__TypeId__` (header) | `com.example.orders.message.OrderCreated` hoặc alias | Thông tin kiểu do Spring gửi nếu được cấu hình |
| `correlationId` | `checkout-42` | Liên hệ workflow/request; không thay thế type metadata |
| `schemaVersion` | `1` trong body | Phiên bản hợp đồng JSON của ứng dụng |

**Không bắt buộc tất cả message JSON đều có `__TypeId__`.** Đây là metadata gắn với cơ chế mapper của Spring. Một producer Node.js, Go hoặc Python thường chỉ gửi JSON body cùng contentType; bên Java phải xác định kiểu đích qua chữ ký listener, class mapper hoặc hợp đồng tương ứng.

### 9.1. Gửi JSON thủ công bằng send(...)

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;

String json = """
        {"eventId":"evt-1001","orderId":"O-1001",
         "total":250000,"schemaVersion":1}
        """;

MessageProperties properties = new MessageProperties();
properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
properties.setContentEncoding(StandardCharsets.UTF_8.name());

Message message = new Message(
        json.getBytes(StandardCharsets.UTF_8), properties);

rabbitTemplate.send("orders.events", "order.created", message);
~~~

`RabbitTemplate.send(..., Message)` **không gọi converter để JSON-serialize một POJO**; body ở ví dụ đã là UTF-8 JSON bytes. Nếu producer tự tạo body, chính producer phải bảo đảm `contentType`, charset và schema tương thích consumer.

### 9.2. Nếu contentType không phải JSON?

JSON converter thường kiểm tra `contentType` trước khi giải mã. Với contentType không được hỗ trợ, một số phiên bản trả lại raw `byte[]` và ghi cảnh báo; với JSON sai cú pháp hoặc kiểu DTO không phù hợp, converter có thể ném exception. Đừng kết luận mọi sai contentType sẽ phát ra cùng lỗi hoặc luôn vào DLQ.

Một số phiên bản Spring AMQP có cơ chế **giả định application/json** nếu thiếu contentType hoặc contentType mặc định là `application/octet-stream`; tùy lựa chọn `assumeSupportedContentType`. Chính vì có default theo version, hợp đồng liên service tốt nên **đặt contentType tường minh** khi gửi JSON, và kiểm tra hành vi với bản đang dùng.

### 9.3. Charset và ký tự tiếng Việt

JSON wire nên thống nhất UTF-8. Khi encoder/decoder khác charset, các trường như `customerName = "Nguyễn An"` có thể hỏng ký tự dù JSON có vẻ vẫn đúng cấu trúc. Các converter có thể đọc `contentEncoding`, charset tham số trong `contentType`, hoặc default charset theo thứ tự được tài liệu từng bản quy định.

Hãy test ký tự có dấu, emoji, ký tự thoát và chuỗi dài trên đường **producer → RabbitMQ → consumer**, thay vì chỉ dùng tên ASCII.

## 10. Type inference, __TypeId__ và an toàn deserialization

Spring AMQP có cơ chế type mapping để chuyển JSON thành class Java. Converter có thể lưu class name hoặc logical type ID trong header `__TypeId__`; các header liên quan cũng có thể thể hiện key/value types với collection/map.

### 10.1. Khi listener suy ra type từ method

Với một method `@RabbitListener` có **một payload parameter kiểu cụ thể**, Spring AMQP có thể suy ra kiểu đích `OrderCreated` và ưu tiên nó hơn type header từ producer. Đó là lý do hai service có thể dùng DTO khác package mà vẫn đọc cùng JSON body nếu schema tương thích.

Tuy nhiên, điều kiện infer type có giới hạn, đặc biệt với:

- Tham số là interface hoặc abstract class.
- Collection/generic type phức tạp không đủ thông tin runtime.
- Class-level `@RabbitListener` với nhiều `@RabbitHandler`.
- Các listener nhận payload qua conversion tùy biến.

Khi inferred type không đủ, converter có thể dựa vào type headers, default type hoặc `ClassMapper`/`JavaTypeMapper` được cấu hình. Đừng thiết kế liên service chỉ dựa vào Java fully-qualified class name của producer, vì class name và package giữa hai ứng dụng có thể khác nhau.

### 10.2. Dùng logical type alias thay vì tên class Java

Một hướng thiết kế là dùng alias ổn định như `order-created.v1` rồi ánh xạ đến DTO trong mỗi service. Spring AMQP có cơ chế `DefaultClassMapper` và id–class mapping; ví dụ mô tả ý tưởng:

~~~text
Producer A:
  body: {"eventId":"evt-1001","orderId":"O-1001",...}
  __TypeId__: "order-created.v1"

Consumer B:
  "order-created.v1" -> com.billing.contract.OrderCreatedEvent
~~~

Mỗi bên cần dùng **mapper phù hợp nhánh Jackson** và đồng ý quy ước alias. Nếu không muốn trao đổi các header kiểu riêng của Spring, có thể dùng một trường `eventType` hoặc schema version trong body/header ứng dụng và cấu hình listener đích tường minh. Cách nào cũng cần hợp đồng rõ ràng cho trường thiếu, trường mới và schema không tương thích.

### 10.3. Không tin header kiểu từ nguồn không tin cậy

Một producer có thể gửi header `__TypeId__` tùy ý. Nếu converter tự tải class và deserialize không có giới hạn phù hợp, ứng dụng có nguy cơ xử lý kiểu không mong muốn. Spring AMQP có các cơ chế như `trustedPackages` để giới hạn package được phép dùng khi ánh xạ type headers.

- Khai báo danh sách package đáng tin cậy **hẹp**, phù hợp DTO của ứng dụng.
- Tránh cấu hình `*` để tin tưởng tất cả package trong môi trường nhận message không đáng tin cậy.
- Không xem một message header là bằng chứng xác thực danh tính producer; quyền kết nối/vhost và bảo mật message phải được xử lý riêng.
- Khi listener có **inferred concrete type**, ưu tiên dùng kiểu đã biết từ code thay vì tin một tên class Java do bên gửi tự chỉ định, nếu hợp đồng cho phép.
- Mặc định của `trustedPackages` và constructor có thể khác nhau theo bản/đường cấu hình; kiểm tra Javadoc và cấu hình thực tế trước khi tuyên bố converter đang được bảo vệ thế nào.

## 11. Chuyển từ Jackson 2 sang Jackson 3

Việc đổi converter là **một phần** của migration; không chỉ sửa đúng một tên import.

| Hạng mục | Trước khi migrate | Việc cần làm | Bằng chứng hoàn tất |
|---|---|---|---|
| BOM/dependencies | Spring AMQP và Jackson 2 đang chạy | Chọn nhánh AMQP/Boot hỗ trợ Jackson 3; đọc release notes | Dependency tree nhất quán |
| Converter | `Jackson2JsonMessageConverter` | Chuyển sang `JacksonJsonMessageConverter` | Code biên dịch với class mới |
| ObjectMapper | `com.fasterxml.jackson...` | Dùng mapper/module Jackson 3 tương ứng | Mapper deserialize đúng DTO |
| Class/type mapping | `DefaultJackson2JavaTypeMapper` | Dùng API Jackson 3 tương đương khi cần | Header alias và class mapping chạy đúng |
| JSON schema | Body JSON hiện có | So sánh serialized bytes, tên trường, số/ngày/giờ | Producer cũ và mới tương thích |
| Converter wiring | Template + listener container | Xác nhận cả hai dùng converter dự kiến | Integration test gửi/nhận POJO |
| Retry/DLQ | Message lỗi deserialization | Kiểm tra error handler/requeue/reject | Bad payload không gây vòng lặp vô hạn |
| Observability | Log/metric trước nâng cấp | Đo conversion errors, latency, DLQ | Có số liệu so sánh trước/sau |

### 11.1. Những thay đổi thường gây lỗi

**Sai namespace của mapper:** Spring AMQP 4 dùng converter Jackson 3 nhưng code lại truyền `com.fasterxml.jackson.databind.ObjectMapper`. Đây là lỗi kiểu Java lúc compile.

**Thiếu module cho kiểu dữ liệu đặc biệt:** Jackson mapper mới không được cấu hình tương đương với mapper trước, khiến `Instant`, `LocalDateTime`, enum hoặc custom serializer thay đổi. Cần chuẩn hóa cách encode trên wire và kiểm thử dữ liệu thực.

**Type headers mang Java class name cũ:** Producer mới dùng class/package khác, consumer cũ không nhận ra tên type. Hãy kiểm tra type precedence hoặc dùng logical aliases/schema version.

**Producer và consumer deploy lệch phiên bản:** JSON body có thể vẫn tương thích dù hai bên dùng converter ở nhánh khác nhau, nhưng type headers và quy tắc deserialization có thể không. Hãy kiểm chứng các chiều *old producer → new consumer* và *new producer → old consumer* trong thời gian rolling deployment.

**POJO JSON không khớp DTO:** Khác tên field, constructor thiếu, nested generic hoặc trường số vượt kiểu dữ liệu. Compile pass không chứng minh wire compatibility.

### 11.2. Ma trận kiểm thử nâng cấp

| Producer | Consumer | Điều cần chứng minh |
|---|---|---|
| Jackson 2 | Jackson 2 | Baseline vẫn hoạt động |
| Jackson 2 | Jackson 3 | Consumer mới đọc được JSON/header từ producer cũ |
| Jackson 3 | Jackson 2 | Consumer cũ đọc được message của producer mới khi rolling deploy |
| Jackson 3 | Jackson 3 | Luồng hoàn toàn mới hoạt động |
| JSON producer không phải Java | Consumer Spring AMQP | DTO được infer từ method hoặc mapper mà không phụ thuộc tên class Java của producer |

Đừng chỉ kiểm tra `JacksonJsonMessageConverter` khởi tạo thành công. Cần kiểm tra **bytes JSON và properties thực tế**, cách Jackson xử lý null/unknown fields, encoding và semantics listener khi gặp schema không hỗ trợ.

## 12. Xử lý lỗi conversion trong hệ thống bất đồng bộ

Lỗi conversion có thể xảy ra **trước khi logic của method `@RabbitListener` chạy**. Ví dụ body là JSON hỏng cú pháp:

~~~text
{"eventId":"evt-1001","orderId":}
~~~

Hoặc body là JSON hợp lệ nhưng DTO yêu cầu `orderId` theo quy tắc validation của ứng dụng:

~~~json
{
  "eventId": "evt-1001",
  "total": 250000,
  "schemaVersion": 1
}
~~~

Trường hợp đầu có thể lỗi parser/deserialization. Trường hợp sau có thể deserialize thành object nhưng **vi phạm hợp đồng nghiệp vụ**; Jackson không tự biết mọi ràng buộc validation trừ khi có cấu hình hoặc kiểm tra tương ứng.

~~~mermaid
flowchart TD
    M["Message từ queue"] --> C{"AMQP JSON converter xử lý được?"}
    C -->|Không| ERR["Conversion error<br/>trước method listener"]
    C -->|Có| L["@RabbitListener DTO"]
    L --> V{"Schema và dữ liệu hợp lệ?"}
    V -->|Không| BAD["Business validation error"]
    V -->|Có| OK["Thực hiện nghiệp vụ"]
    ERR --> POLICY["Error handler / reject / retry / DLX<br/>theo cấu hình thực tế"]
    BAD --> POLICY
    OK --> ACK["Ack theo listener mode"]
~~~

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| JSON sai cú pháp | Thiếu dấu ngoặc, ký tự không hợp lệ | Xem như payload vĩnh viễn lỗi; không requeue vô hạn |
| Content type sai | `text/plain` hoặc bytes nhị phân gửi vào consumer JSON | Kiểm tra producer contract và converter settings |
| Type header không an toàn | Class ngoài danh sách trusted | Từ chối/điều tra producer và giới hạn type mapping |
| Kiểu DTO không phù hợp | JSON object nhưng listener nhận interface thiếu mapping | Điều chỉnh DTO/class mapping/type inference |
| Schema version không hỗ trợ | `schemaVersion=9` trong ứng dụng chỉ đọc v1 | Version routing/compatibility hoặc DLQ để phân tích |
| Lỗi tạm thời ngoài converter | Database/API không sẵn sàng sau khi deserialize | Retry/backoff có giới hạn, idempotency |

Spring AMQP có `ConditionalRejectingErrorHandler` và những cơ chế nhận diện một số lỗi conversion fatal trong các phiên bản phù hợp. Tuy nhiên kết quả cuối cùng (ack, reject, requeue hay dead-letter) phụ thuộc container, error handler, retry interceptor và cấu hình broker. Không khẳng định “mọi lỗi JSON đều tự vào DLQ”.

Nếu muốn thu hồi message lỗi:

1. Khai báo queue nguồn và DLX/DLQ/binding có thật.
2. Chọn chính sách reject/requeue cho lỗi không thể khắc phục, tách khỏi retry của lỗi tạm thời.
3. Quan sát DLQ, lưu correlation ID/message ID và thông tin lỗi an toàn.
4. Sau khi sửa schema/configuration, có quy trình reprocess message và chống xử lý trùng.

**Lưu ý:** Publisher confirms báo broker xử lý publish, còn consumer acknowledgement báo delivery đã được xử lý theo cơ chế consumer. Cả hai không tự bảo đảm **exactly-once**. Với event quan trọng, cần idempotency theo event ID và cân nhắc transactional outbox.

## 13. Thực hành kiểm chứng converter đang sử dụng

### 13.1. Kiểm tra body/properties tại producer

Có thể dùng `RabbitTemplate` với JSON converter đã cấu hình và một `MessagePostProcessor` để quan sát message **sau khi converter chạy, trước khi gửi**:

~~~java
OrderCreated event = new OrderCreated(
        "evt-1001", "O-1001", new BigDecimal("250000"), 1);

rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        event,
        message -> {
            var properties = message.getMessageProperties();
            System.out.println("contentType=" + properties.getContentType());
            System.out.println("headers=" + properties.getHeaders().keySet());
            System.out.println("bodyBytes=" + message.getBody().length);
            return message;
        });
~~~

Kết quả mong đợi: `contentType` phù hợp với JSON, `bodyBytes` có độ dài hợp lý, header type có thể xuất hiện tùy converter/mapper. Việc in **tên header** giúp tránh lộ payload có dữ liệu nhạy cảm. Trong môi trường test có thể decode bytes UTF-8 để đối chiếu JSON khi được phép.

### 13.2. Kiểm tra consumer nhận DTO hay byte[]

Thử lần lượt:

1. Listener nhận `OrderCreated` và assert `orderId = O-1001`, `schemaVersion = 1`.
2. Gửi JSON hợp lệ **không có `__TypeId__`**, nhưng có `contentType=application/json`; kiểm tra suy luận kiểu từ method.
3. Gửi body không phải JSON cùng `contentType=application/json`; ghi nhận error handler và cách message được xử lý.
4. Gửi JSON UTF-8 có tên tiếng Việt; xác nhận ký tự không biến dạng.
5. Thay `schemaVersion` thành giá trị không được hỗ trợ; kiểm tra logic validation và DLQ.
6. Thử Jackson 2 producer với Jackson 3 consumer nếu đang chuẩn bị migration.

Để kiểm thử thực tế thay vì chỉ mock converter, nên chạy RabbitMQ test với queue/exchange/binding riêng và version broker tương đương môi trường đích. Các test conversion thuần có thể gọi converter trực tiếp, nhưng **routing, retry, nack và DLQ** cần integration test vì chúng là hành vi liên quan broker/container.

### 13.3. Assert round-trip converter ở mức unit

Ví dụ kiểm tra vòng chuyển đổi **trên một converter đã được cấu hình theo đúng nhánh**:

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.MessageConverter;
import static org.assertj.core.api.Assertions.assertThat;

MessageConverter converter = /* bean JSON converter của ứng dụng */;
OrderCreated original = new OrderCreated(
        "evt-1001", "O-1001", new BigDecimal("250000"), 1);

Message message = converter.toMessage(original, new MessageProperties());

assertThat(message.getMessageProperties().getContentType())
        .contains("json");

Object converted = converter.fromMessage(message);
assertThat(converted).isInstanceOf(OrderCreated.class);
~~~

Đây là đoạn **minh họa trong test**, không phải một class Java hoàn chỉnh: các biến được cấp từ test fixture; kết quả `fromMessage` phụ thuộc type header/mapper. Nếu thử với JSON đến từ non-Spring producer không có type header, hãy dùng converter cùng type inference qua `@RabbitListener` hoặc cấu hình class mapper phù hợp; không bắt buộc `fromMessage` thô tự suy ra DTO.

## 14. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Điều cần làm |
|---|---|---|
| `Cannot resolve symbol JacksonJsonMessageConverter` | Project vẫn dùng Spring AMQP 3.x | Dùng `Jackson2JsonMessageConverter` đúng bản hoặc lên kế hoạch nâng cấp |
| `Jackson2JsonMessageConverter` deprecated | Đang ở nhánh 4.0 có API Jackson 2 cũ | Đọc hướng dẫn chuyển sang Jackson 3 |
| `ObjectMapper cannot be converted...` | Trộn mapper Jackson 2 với converter Jackson 3 | Chọn đúng `tools.jackson...` hoặc `com.fasterxml...` theo converter |
| `ClassCastException` với `LinkedHashMap` | Converter không biết kiểu DTO đích | Cấu hình inferred type, class mapper, header hoặc target type rõ ràng |
| Listener nhận `byte[]` thay vì object | Converter không phải JSON, contentType không khớp hoặc wiring sai | Kiểm tra template/container factory và metadata |
| Ngày giờ bị lỗi hoặc khác format | Mapper/module/serialization config khác giữa các service | Đồng bộ hợp đồng JSON và test dữ liệu ngày/giờ |
| Consumer báo type không được trusted | Header type ngoài package tin cậy | Kiểm tra nguồn phát và cấu hình danh sách package cho phép |
| Message lỗi liên tục requeue | Retry/error handler không phân biệt payload lỗi vĩnh viễn | Giới hạn retry, reject và DLQ tùy cấu hình |
| Publish thành công nhưng listener không chạy | Exchange/binding/routing key sai hoặc queue không có consumer | Kiểm tra topology, publisher returns, logs và consumer count |
| Header `__TypeId__` mang class name khác package | Dùng Java class name làm wire contract | Ưu tiên listener inferred DTO hoặc logical aliases và schema version |

Đặc biệt, **không sửa lỗi JSON bằng cách chỉ thay retry policy**. Nếu payload vĩnh viễn không thể deserialize, retry cùng một bytes và cùng converter sẽ thất bại lặp lại; phải sửa producer contract, converter hoặc đưa message vào luồng xử lý lỗi thích hợp.

## 15. Bài tập thực hành có đáp án gợi ý

### Bài tập 1 — Chọn converter đúng nhánh

Project resolved `spring-rabbit` thuộc Spring AMQP 3.2, IDE không tìm thấy `JacksonJsonMessageConverter`. Có nên thêm Spring AMQP 4 vào từng dependency?

**Đáp án gợi ý:** không nên chỉ vì tên lớp. Với 3.2 dùng `Jackson2JsonMessageConverter` cho Jackson 2. Nếu muốn chuyển sang Jackson 3, hãy xác nhận toàn bộ Spring Boot/Spring Framework/JDK compatibility và nâng theo BOM, release notes.

### Bài tập 2 — Giải thích convertAndSend

Producer gọi `convertAndSend("orders.events", "order.created", orderEvent)` nhưng nhận một body dạng Java serialization. Lỗi ở đâu?

**Đáp án gợi ý:** kiểm tra `RabbitTemplate.getMessageConverter()` hoặc cấu hình template; `SimpleMessageConverter` không tự biến mọi POJO thành JSON. Cần JSON converter đúng nhánh và kiểm tra contentType/body thực tế.

### Bài tập 3 — Consumer không cần class name của producer

Service A dùng DTO `com.checkout.events.OrderCreated`; service B dùng `com.billing.contract.OrderCreated`. Cả hai có cùng JSON schema. B có nhất thiết cần class A không?

**Đáp án gợi ý:** không. Method-level listener có một concrete DTO parameter có thể suy ra kiểu đích của B. Cần kiểm tra cấu hình type precedence/converter và schema thực tế; không đặt Java class name làm hợp đồng liên service.

### Bài tập 4 — Phân biệt hai bước conversion

AMQP converter trả về `byte[]`, trong khi method `@RabbitListener(OrderCreated event)` cần DTO. Vì sao method không tự chạy được?

**Đáp án gợi ý:** bước chuyển body bytes thành object chưa phù hợp; GenericMessageConverter ở bước tham số method không mặc nhiên parse JSON từ byte[]. Hãy cấu hình AMQP JSON converter cho listener container hoặc listener annotation đúng phiên bản.

### Bài tập 5 — Bảo mật type header

Một message từ nguồn không tin cậy có `__TypeId__` trỏ đến một class nội bộ không thuộc hợp đồng. Bạn có nên bật `trustedPackages("*")` để hết lỗi?

**Đáp án gợi ý:** không. Cần giới hạn package, xác thực nguồn, dùng DTO/type mapping được kiểm soát hoặc reject message; wildcard toàn bộ làm tăng phạm vi class có thể bị deserialize.

### Bài tập 6 — Migration Jackson 2 → Jackson 3

Hãy viết checklist test cho `OrderCreated` với `BigDecimal`, `Instant`, nội dung tiếng Việt, thiếu `schemaVersion`, và trường mới chưa biết.

**Đáp án gợi ý:** kiểm tra hai hướng producer/consumer cũ–mới, serialization bytes, charset, Jackson time module, số chính xác, unknown fields/null handling, type headers, DLQ và handling của schema version. Compile thành công chưa đủ.

### Bài tập 7 — Lỗi JSON nên retry thế nào?

Consumer nhận `{"orderId":}` và exception parser. Queue đang requeue liên tục. Hãy đề xuất phản ứng vận hành.

**Đáp án gợi ý:** coi đây là lỗi payload vĩnh viễn; xác minh message ở nguồn, cấu hình xử lý lỗi giới hạn/reject vào DLQ hoặc quarantine, thu thập metadata an toàn để điều tra và chỉ reprocess khi dữ liệu đã được sửa. Không retry vô hạn cùng payload.

## 16. Checklist áp dụng cho dự án Spring AMQP

- [ ] Xác minh `spring-amqp`, `spring-rabbit`, Jackson **resolved version**, Spring Boot BOM và JDK.
- [ ] Chọn `Jackson2JsonMessageConverter` cho nhánh Jackson 2 hoặc `JacksonJsonMessageConverter` cho nhánh Jackson 3 đúng phiên bản.
- [ ] Kiểm tra mapper Jackson namespace: `com.fasterxml.jackson...` và `tools.jackson...` không thay thế trực tiếp cho nhau.
- [ ] Gắn JSON converter vào **đúng `RabbitTemplate`** và **đúng listener container factory**/annotation.
- [ ] Xác nhận body là JSON UTF-8, `contentType` rõ ràng; theo dõi `contentEncoding` hoặc charset khi cần.
- [ ] Không mặc định mọi message JSON đều có `__TypeId__` hoặc package Java của producer giống consumer.
- [ ] Dùng DTO/schema version và hợp đồng fields rõ ràng; quản lý type aliases nếu ứng dụng dựa vào type headers.
- [ ] Giới hạn trusted packages với nguồn không tin cậy; tránh mở `*` tùy tiện.
- [ ] Test Java Time, `BigDecimal`, null, unknown fields, nested collections và ký tự tiếng Việt.
- [ ] Test producer/consumer khác phiên bản trong giai đoạn rolling deploy.
- [ ] Phân biệt lỗi converter với lỗi routing, connect, publisher confirm và consumer business logic.
- [ ] Định nghĩa rõ error handler/retry/requeue/DLX cho dữ liệu lỗi vĩnh viễn, không gây poison-message loop.
- [ ] Đọc tài liệu **theo version cụ thể**, không copy class từ nhánh mới nhất vào dự án cũ.

## 17. Nguồn tra cứu chính thức

- [Spring AMQP 3.2 — Message Converters](https://docs.spring.io/spring-amqp/reference/3.2/amqp/message-converters.html): `Jackson2JsonMessageConverter` và Jackson 2.
- [Spring AMQP 4.0 — Message Converters](https://docs.spring.io/spring-amqp/reference/4.0/amqp/message-converters.html): `JacksonJsonMessageConverter` và Jackson 3; thông tin deprecation API Jackson 2.
- [Spring AMQP — Message Conversion for Annotated Methods](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): hai bước conversion và suy luận type của `@RabbitListener`.
- [Spring AMQP — API/Javadoc](https://docs.spring.io/spring-amqp/api/): constructors, class mapper và các method có thay đổi theo version.
- [Spring Boot — AMQP Messaging](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): `RabbitTemplate`, auto-configuration và việc gắn `MessageConverter` bean.

**Ghi nhớ:** `Jackson2JsonMessageConverter` và `JacksonJsonMessageConverter` có cùng mục tiêu chuyển object ↔ JSON message, nhưng thuộc **hai thế hệ Jackson khác nhau**. Hãy kiểm tra Spring AMQP version rồi chọn class tương thích, cấu hình nhất quán cho publisher/listener, và kiểm thử body JSON cùng type metadata trên đường đi thực tế. Khi xử lý được đúng ranh giới giữa conversion, routing và acknowledgement, bạn sẽ dễ nâng cấp Spring AMQP hơn và giảm rủi ro xử lý message sai hoặc lặp vô hạn.
