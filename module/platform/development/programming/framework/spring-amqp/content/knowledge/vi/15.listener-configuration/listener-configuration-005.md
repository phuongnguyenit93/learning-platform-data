# @Payload, kiểm tra dữ liệu và lỗi trước khi gọi phương thức

## 1. Vấn đề: message đã đến queue nhưng listener chưa hề chạy

Trong hệ thống **Spring AMQP** dùng RabbitMQ, producer gửi lệnh qua `RabbitTemplate`; exchange và binding định tuyến lệnh vào queue; listener khai báo bằng `@RabbitListener` để nhận và xử lý. Một tình huống thường gây khó hiểu là RabbitMQ đã giao message cho consumer, nhưng dòng log đầu tiên của phương thức listener **không xuất hiện**:

~~~java
@RabbitListener(queues = "orders.commands.q")
public void handle(@Payload @Valid PlaceOrderCommand command) {
    System.out.println("DA VAO LISTENER: " + command.orderId());
    // Không chạy tới đây nếu JSON không chuyển được thành PlaceOrderCommand
    // hoặc @Payload không vượt qua bước validation đã được cấu hình.
}
~~~

Điều này có thể xảy ra khi:

1. Payload là JSON không hợp lệ, sai `contentType` hoặc không chuyển được sang DTO.
2. Payload chuyển thành DTO được, nhưng dữ liệu vi phạm ràng buộc `@NotBlank`, `@Positive`, `@Valid`...
3. Phương thức yêu cầu header bắt buộc mà message không mang header đó, hoặc không phân giải được tham số.
4. Listener adapter không chọn được method phù hợp với message.

Những lỗi này nằm ở **lớp tiếp nhận/chuyển đổi/phân giải tham số của Spring**, tức **trước khi phương thức xử lý nghiệp vụ được gọi**. Vì vậy, chỉ viết `try/catch` trong thân method là **chưa đủ**. Cần hiểu `@Payload`, quy trình conversion, Bean Validation, listener container error handler và cách RabbitMQ xử lý ACK/NACK/requeue/dead-letter.

Bài thuộc chương **Listener khai báo** này hướng dẫn thiết lập pipeline đáng tin cậy cho **Spring AMQP + RabbitMQ AMQP 0-9-1**. Trọng tâm là phân biệt:

- **Payload hợp lệ về kỹ thuật và cấu trúc** để method có thể nhận.
- **Dữ liệu hợp lệ theo ràng buộc khai báo** trước khi xử lý.
- **Nghiệp vụ thành công** sau khi method chạy.

Ba điều trên khác nhau và không được suy luận chỉ từ việc message đã vào queue.

## 2. Pipeline của một @RabbitListener

Với listener kiểu method, đường đi thường gồm hai lớp chuyển đổi: từ **AMQP Message** sang payload Java và từ **Spring Messaging Message** sang các tham số method.

~~~mermaid
flowchart TD
    P["Producer RabbitTemplate<br/>JSON body + properties"]
    Q["RabbitMQ exchange → queue"]
    C["Listener container nhận delivery"]
    M["AMQP MessageConverter<br/>byte[] → object/DTO"]
    R["HandlerMethodArgumentResolver<br/>@Payload, @Header, @Headers"]
    V{"Bean Validation<br/>@Valid / @Validated?"}
    H["Gọi method @RabbitListener"]
    DB["Xử lý nghiệp vụ / transaction"]
    ACK["Container consumer ACK"]
    E["Lỗi trước lời gọi method<br/>conversion / argument / validation"]
    EX["Lỗi trong method"]
    EH["Error handling<br/>reject/requeue/DLX theo policy"]
    P --> Q --> C --> M --> R --> V
    M -. "thất bại" .-> E
    R -. "thất bại" .-> E
    V -- "không đạt" --> E
    V -- "đạt" --> H --> DB --> ACK
    DB -. "exception" .-> EX --> EH
    E --> EH
~~~

Đây là luồng khái niệm cho `@RabbitListener` với payload được chuyển đổi trước khi invoke. Với Spring AMQP, **thứ tự áp dụng cụ thể** còn phụ thuộc converter, method signature, adapter, type metadata và cấu hình. Một số trường hợp message adapter chuyển đổi trực tiếp đến kiểu suy luận của method; những trường hợp khác có thêm chuyển đổi ở Spring Messaging layer.

| Giai đoạn | Điều gì được kiểm tra? | Lỗi có thể gặp | Method có được gọi không? |
| --- | --- | --- | --- |
| Nhận delivery | Queue, consumer, channel, giao nhận từ RabbitMQ | Mất kết nối, consumer bị cancel | Không nếu delivery chưa tới adapter. |
| AMQP message conversion | `contentType`, JSON syntax, DTO, type mapping | `MessageConversionException`, lỗi Jackson/serialization | Thường không. |
| Phân giải tham số | `@Payload`, `@Header`, kiểu method argument | Header thiếu, không chuyển được argument, handler không phù hợp | Không. |
| Bean Validation | `@Valid`/`@Validated` với validator đã đăng ký | `MethodArgumentNotValidException` hoặc wrapper tương ứng | Không. |
| Thân listener | DB, API, domain invariant, transaction, side effect | Exception nghiệp vụ, DB timeout | Có, nhưng có thể thất bại. |
| Xác nhận delivery | ACK/NACK/reject theo container và ack mode | Connection mất, ACK không tới broker | Việc xử lý xong chưa bảo đảm broker đã nhận ACK. |

**Điểm then chốt:** lỗi trước khi gọi method vẫn là **lỗi xử lý delivery**, và listener container/error handler phải quyết định xử lý message ra sao. Nó không tự biến thành publisher confirm NACK: publisher confirms thuộc giai đoạn producer gửi vào RabbitMQ.

## 3. @Payload thực hiện điều gì?

### 3.1. Đánh dấu tham số nhận nội dung message

`@Payload` thuộc Spring Messaging:

~~~java
import org.springframework.messaging.handler.annotation.Payload;

public void handle(@Payload PlaceOrderCommand command) {
    // command nhận giá trị payload sau conversion.
}
~~~

Annotation này giúp framework hiểu tham số `command` chính là **payload**, khác với metadata trong headers hoặc raw AMQP `Message`.

Đối với method listener đơn giản chỉ có một tham số không phải infrastructure parameter, Spring thường suy luận tham số đó là payload **kể cả khi không viết `@Payload`**:

~~~java
@RabbitListener(queues = "orders.commands.q")
public void handle(PlaceOrderCommand command) {
    // Có thể nhận payload theo cơ chế suy luận của @RabbitListener.
}
~~~

Việc ghi `@Payload` tường minh thường có ích khi method còn có `@Header`, `@Headers` hoặc khi muốn người đọc mã nhận ra contract của listener.

### 3.2. @Payload không tự validate dữ liệu

Các khai báo:

~~~java
public void handle(@Payload PlaceOrderCommand command) { ... }
~~~

và:

~~~java
public void handle(@Payload @Valid PlaceOrderCommand command) { ... }
~~~

**Không tương đương.** `@Payload` xác định payload cần ánh xạ vào tham số. `@Valid` yêu cầu **Bean Validation** kiểm tra các constraints trên DTO **nếu validator đã được cấu hình cho listener argument resolution**.

`@Payload` cũng không tự chuyển mọi byte array thành DTO. Cần `MessageConverter` phù hợp: ví dụ JSON converter cho JSON, không thể dựa vào `SimpleMessageConverter` mặc định để tự xử lý mọi object phức tạp.

### 3.3. required=true, required=false và giá trị null

`@Payload` có thuộc tính `required`, mặc định là `true`:

~~~java
public void handle(@Payload(required = false) PlaceOrderCommand command) {
    // Dù cho phép thiếu payload, vẫn phải xử lý command == null.
}
~~~

Đặt `required=false` **không làm JSON lỗi cú pháp trở thành JSON hợp lệ**; conversion có thể thất bại **trước khi** kiểm tra payload có bắt buộc hay không. Với lệnh nghiệp vụ như tạo đơn hàng, thường nên giữ payload bắt buộc và phản hồi lỗi rõ ràng thay vì để null lọt vào service.

### 3.4. Phân biệt @Payload, @Header và raw Message

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@RabbitListener(queues = "orders.commands.q")
public void handle(
        @Payload @Valid PlaceOrderCommand command,
        @Header(name = "x-request-id", required = false) String requestId) {
    // command: dữ liệu nghiệp vụ; requestId: application header.
}
~~~

Nếu annotation `@Header(required=true)` yêu cầu một header chưa có, việc phân giải tham số có thể thất bại trước khi method được gọi. Với raw `org.springframework.amqp.core.Message`, ứng dụng có thể đọc `getBody()` và `getMessageProperties()` thủ công nhưng sẽ phải tự chịu trách nhiệm parse/validate nếu không đi qua hệ thống payload conversion.

**Không nhầm `@Payload` với `@RequestBody`** của Spring MVC. Cả hai liên quan tới data binding nhưng dùng trong những pipeline transport khác nhau.

## 4. Các lớp kiểm tra dữ liệu: kiểm tra được gì ở đâu?

Một message JSON có thể **đúng cú pháp** nhưng vẫn sai về nghiệp vụ. Nên tách các loại kiểm tra:

| Tầng | Ví dụ lỗi | Cơ chế | Có thể phát hiện trước khi gọi method? |
| --- | --- | --- | --- |
| Transport/protocol | Message không nhận được, channel đóng | RabbitMQ/client/container | Có, trước khi có method invocation. |
| Content/serialization | JSON hỏng; field số chứa object; converter không hiểu type | `MessageConverter`, Jackson | Có. |
| Cấu trúc DTO | Thiếu trường bắt buộc, chuỗi trống, số âm | Bean Validation: `@NotNull`, `@NotBlank`, `@Positive` | Có, nếu đã bật validator. |
| Schema/contract | `schemaVersion` không hỗ trợ, loại sự kiện sai | Converter/type mapping hoặc custom validator | Có thể, tùy chỗ tích hợp. |
| Quy tắc nghiệp vụ | Đơn hàng đã thanh toán, sản phẩm hết hàng, số dư không đủ | Service/domain/DB | Thường trong method hoặc service được gọi. |
| Side effect | DB timeout, HTTP downstream lỗi | Transaction/retry policy | Chỉ xảy ra trong xử lý thực tế. |

**Phân biệt:** có thể đặt kiểm tra business invariant trong custom validator, nhưng Bean Validation thường phù hợp nhất cho **input contract** không phụ thuộc dữ liệu đang thay đổi. Các ràng buộc như “khách hàng còn đủ tín dụng ở thời điểm commit” cần transaction và domain service, không thể được đảm bảo chỉ bằng `@Valid` trước khi method gọi.

## 5. DTO có Bean Validation constraints

Ví dụ đặt lệnh tạo đơn hàng bằng Java 17 records:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;
import java.util.List;

public record OrderLine(
        @NotBlank String sku,
        @Positive int quantity
) {}

public record PlaceOrderCommand(
        @NotBlank String commandId,
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal total,
        @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency,
        @NotEmpty List<@Valid OrderLine> lines
) {}
~~~

Các constraints kiểm tra:

- `commandId` và `orderId` không được null hoặc chỉ có khoảng trắng.
- `total` bắt buộc và tối thiểu `0.01`; khác với `@Positive` nếu muốn chấp nhận giá trị nhỏ theo decimal.
- `currency` là chuỗi ba chữ cái viết hoa (đây mới là kiểm tra **định dạng**, chưa bảo đảm currency code có thực).
- `lines` không rỗng; annotation `@Valid` trên phần tử list yêu cầu kiểm tra từng `OrderLine`, trong đó `quantity > 0`.

JSON hợp lệ:

~~~json
{
  "commandId": "cmd-1001",
  "orderId": "ORD-1001",
  "total": 250000.00,
  "currency": "VND",
  "lines": [
    {"sku": "BOOK-001", "quantity": 2}
  ]
}
~~~

JSON **đúng cú pháp nhưng sai constraints**:

~~~json
{
  "commandId": "",
  "orderId": " ",
  "total": -100,
  "currency": "vn",
  "lines": [
    {"sku": "", "quantity": 0}
  ]
}
~~~

JSON thứ hai có thể deserialize thành `PlaceOrderCommand`, nhưng phải bị chặn ở bước validation **nếu hệ thống đã gắn validator cho listener**.

### 5.1. @NotNull khác @NotBlank, @NotEmpty

| Constraint | Áp dụng thường gặp | Điều quan trọng |
| --- | --- | --- |
| `@NotNull` | Bất kỳ reference type | Chỉ cấm null; không cấm chuỗi trống. |
| `@NotBlank` | `String` / `CharSequence` | Cấm null và chuỗi chỉ gồm whitespace. |
| `@NotEmpty` | String, collection, map, array | Cấm null/rỗng nhưng không kiểm tra ý nghĩa từng phần tử. |
| `@Positive` | Số | Bắt buộc lớn hơn 0; với số tiền có thể dùng `@DecimalMin`. |
| `@Pattern` | Chuỗi | Kiểm tra regex, không xác minh sự tồn tại của một đối tượng nghiệp vụ. |
| `@Valid` | DTO lồng nhau / container elements | Cho phép cascading validation; cần constraint trên DTO con. |

Nếu muốn kiểm tra tổng tiền bằng tổng dòng hàng, đó là **cross-field validation** hoặc domain validation; có thể dùng custom class-level constraint, nhưng vẫn cần tính lại/đối chiếu ở service nếu dữ liệu giá sản phẩm đến từ DB.

## 6. Cấu hình Spring Boot, JSON converter và validator

Ví dụ dưới đây nhắm **Spring Boot 3.x**, **Spring AMQP 3.x**, Java 17+, RabbitMQ **AMQP 0-9-1**. Trong Spring AMQP 4.x, JSON converter đã chuyển theo hướng Jackson 3; chọn API tương ứng với phiên bản dự án, không trộn package Jackson 2 và Jackson 3.

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Ba dependency phục vụ ba việc riêng:

1. `starter-amqp`: `RabbitTemplate`, `@RabbitListener`, listener container và tương tác RabbitMQ.
2. `starter-json`: hỗ trợ Jackson JSON cho body DTO; cũng có thể đã tồn tại gián tiếp qua starter khác.
3. `starter-validation`: Jakarta Validation API và provider (thông thường Hibernate Validator) để các `@NotBlank`, `@Positive`... thực sự được thực thi.

**Có annotation `@Valid` trong code nhưng không có validation provider hoặc không cấu hình validator cho listener** thì không thể mặc định kết luận payload sẽ được kiểm tra.

### 6.2. Kết nối và lựa chọn chính sách thử nghiệm

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
        default-requeue-rejected: false
~~~

Trong ví dụ học tập này, `default-requeue-rejected: false` giúp tránh vòng lặp nóng khi message bị từ chối. **Không bê nguyên cấu hình này vào production** mà chưa phân loại lỗi: nếu không có retry advice hoặc chính sách lỗi riêng, cả những exception tạm thời như DB timeout cũng có thể bị reject không requeue.

`acknowledge-mode: auto` ở đây là **Spring container AUTO**, tức container gửi consumer ACK **sau khi listener xử lý thành công**; không phải RabbitMQ `autoAck=true`. Khi lỗi xảy ra trước hoặc trong method, container sẽ quyết định reject/requeue theo error handling.

### 6.3. Khai báo Jackson JSON converter

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderJsonConfiguration {

    @Bean
    Jackson2JsonMessageConverter jackson2JsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Với Spring Boot 3.x, bean converter có thể được auto-configure vào `RabbitTemplate` và listener container factory do Boot quản lý. Nếu ứng dụng có custom `RabbitTemplate` hoặc custom container factory, phải **kiểm tra và thiết lập message converter cho những bean đó**; nếu không producer có thể gửi JSON nhưng listener đang dùng converter khác.

Trong Spring AMQP 4.x, dùng converter tương ứng:

~~~java
// Spring AMQP 4.x: ý tưởng tương đương, dùng Jackson 3.
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;

@Bean
JacksonJsonMessageConverter jsonMessageConverter() {
    return new JacksonJsonMessageConverter();
}
~~~

Đoạn này là **lựa chọn thay thế theo phiên bản**, không đặt cạnh bean Jackson 2 cùng lúc trong một cấu hình thật.

### 6.4. Bật Bean Validation cho argument của @RabbitListener

Một cách tường minh là cung cấp `DefaultMessageHandlerMethodFactory` với `Validator` cho `RabbitListenerEndpointRegistrar`:

~~~java
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.annotation.RabbitListenerConfigurer;
import org.springframework.amqp.rabbit.config.RabbitListenerEndpointRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@Configuration
@EnableRabbit
public class RabbitMethodValidationConfiguration
        implements RabbitListenerConfigurer {

    private final Validator validator;

    public RabbitMethodValidationConfiguration(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureRabbitListeners(
            RabbitListenerEndpointRegistrar registrar) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();
        factory.setValidator(validator);
        factory.afterPropertiesSet();
        registrar.setMessageHandlerMethodFactory(factory);
    }
}
~~~

Với `spring-boot-starter-validation`, Spring Boot 3.x thông thường cung cấp `Validator` đủ để inject. Nếu môi trường không có bean validator, có thể khai báo `LocalValidatorFactoryBean` theo hướng dẫn Spring Validation. Cơ chế cấu hình thay thế qua registrar/handler method factory có thể thay đổi theo phiên bản, nhưng nguyên tắc vẫn là **gắn validation provider vào argument resolution của listener**, không chỉ dán `@Valid` lên DTO.

**Phân biệt hai mảnh cấu hình**:

- `Jackson2JsonMessageConverter` giúp **chuyển bytes thành DTO**.
- `DefaultMessageHandlerMethodFactory#setValidator(...)` giúp **kiểm tra DTO trước khi gọi listener method**.

Hai cơ chế không thay thế nhau. Với DTO đã deserialize thành công nhưng vi phạm `@NotBlank`, lỗi kỳ vọng là lỗi validation, không phải lỗi JSON syntax.

## 7. Khai báo topology và một listener được validate

### 7.1. Exchange, queue, binding và DLQ

Khai báo một queue xử lý lệnh và một dead-letter queue để quan sát message bị reject:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderListenerTopology {
    public static final String EXCHANGE = "orders.commands";
    public static final String ROUTING_KEY = "orders.place";
    public static final String QUEUE = "orders.commands.q";
    public static final String DLX = "orders.dlx";
    public static final String DLQ = "orders.invalid.q";

    @Bean
    DirectExchange ordersCommandsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    DirectExchange ordersDlx() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersCommandsQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("orders.invalid")
                .build();
    }

    @Bean
    Queue ordersInvalidQueue() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersCommandsBinding(
            Queue ordersCommandsQueue, DirectExchange ordersCommandsExchange) {
        return BindingBuilder.bind(ordersCommandsQueue)
                .to(ordersCommandsExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    Binding ordersInvalidBinding(
            Queue ordersInvalidQueue, DirectExchange ordersDlx) {
        return BindingBuilder.bind(ordersInvalidQueue)
                .to(ordersDlx)
                .with("orders.invalid");
    }
}
~~~

Trong môi trường học tập, `RabbitAdmin` có thể khai báo các bean topology khi kết nối RabbitMQ. RabbitMQ sẽ dead-letter message bị reject không requeue **nếu queue có DLX được khai báo đúng**. Nếu DLX hoặc binding DLQ sai, message có thể không đến nơi điều tra như mong đợi.

**Lưu ý vận hành:** RabbitMQ khuyến nghị cân nhắc khai báo DLX bằng **policy** thay vì hardcode `x-dead-letter-exchange` trong queue arguments khi cần thay đổi cấu hình production linh hoạt. Ví dụ trên ưu tiên tự chứa để thực hành.

### 7.2. Listener được bảo vệ bằng @Payload @Valid

~~~java
import jakarta.validation.Valid;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class PlaceOrderListener {

    private final OrderApplicationService orderService;

    public PlaceOrderListener(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(queues = OrderListenerTopology.QUEUE)
    public void handle(@Payload @Valid PlaceOrderCommand command) {
        // Chỉ tới đây nếu bước conversion và configured validation thành công.
        orderService.placeOrder(command);
    }
}
~~~

`OrderApplicationService` là service nghiệp vụ của ứng dụng: thực hiện idempotency theo `commandId`, kiểm tra dữ liệu trong DB, ghi đơn hàng và commit transaction. Ví dụ không triển khai toàn bộ service vì chủ đề là **tiền xử lý trước khi listener method được gọi**.

Ở cấu hình như mục 6:

1. JSON hợp lệ, DTO đạt constraints → gọi `handle(...)` rồi xử lý nghiệp vụ.
2. JSON sai cú pháp/không thể deserialize → lỗi converter **trước** `handle(...)`.
3. JSON parse thành DTO nhưng `orderId=""` hoặc `quantity=0` → lỗi Bean Validation **trước** `handle(...)`.
4. JSON đúng và Bean Validation đạt nhưng DB báo đơn hàng đã tồn tại → lỗi **trong service**; phải xử lý idempotency hoặc phân loại exception riêng.

### 7.3. Producer minh họa

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class PlaceOrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public PlaceOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendValidCommand() {
        PlaceOrderCommand command = new PlaceOrderCommand(
                "cmd-1001",
                "ORD-1001",
                new BigDecimal("250000.00"),
                "VND",
                List.of(new OrderLine("BOOK-001", 2))
        );
        rabbitTemplate.convertAndSend(
                OrderListenerTopology.EXCHANGE,
                OrderListenerTopology.ROUTING_KEY,
                command,
                message -> {
                    message.getMessageProperties().setMessageId(command.commandId());
                    return message;
                }
        );
    }
}
~~~

JSON converter được cấu hình trên `RabbitTemplate` sẽ serialize command sang JSON. Nếu chỉ gửi String bằng converter mặc định và lại muốn nhận DTO thì cần kiểm tra `contentType`, encoding và converter thực tế, không chỉ tên queue.

## 8. Lỗi xảy ra trước method: try/catch ở đâu?

### 8.1. Vì sao try/catch bên trong handle không đủ?

Đoạn sau **chỉ bắt được exception xảy ra sau khi method bắt đầu**:

~~~java
@RabbitListener(queues = "orders.commands.q")
public void handle(@Payload @Valid PlaceOrderCommand command) {
    try {
        processOrder(command);
    } catch (Exception exception) {
        // Không bắt được lỗi JSON converter hoặc @Valid xảy ra trước invocation.
        throw exception;
    }
}
~~~

Khi converter không tạo được `PlaceOrderCommand`, hoặc validator từ chối payload, Spring chưa thể gọi `handle(...)`. Vì vậy exception không chạy qua khối `try/catch` trên.

Lỗi có thể được bọc dưới `ListenerExecutionFailedException` hoặc được nhận diện từ nguyên nhân sâu hơn như `MessageConversionException`, `MethodArgumentNotValidException`, `MessageHandlingException`. Tên lớp chính xác và wrapper có thể khác tùy giai đoạn và phiên bản Spring AMQP; khi điều tra phải đọc **root cause**, không chỉ tên exception ngoài cùng.

### 8.2. Container ErrorHandler

Listener container có cơ chế `ErrorHandler` để xử lý exception từ việc tiếp nhận và gọi listener. Trong cấu hình phổ biến của Spring AMQP, `ConditionalRejectingErrorHandler` phân biệt một số **fatal exception** (ví dụ conversion/argument errors) và có thể chuyển chúng thành `AmqpRejectAndDontRequeueException`, khiến message bị reject không requeue.

Đây là lý do một message JSON sai có thể đi thẳng tới DLQ, trong khi exception từ database theo cấu hình khác có thể được requeue hoặc retry. **Không nên giả định mọi lỗi tự động có cùng chính sách**; hãy kiểm tra error handler thực tế, ack mode, `defaultRequeueRejected`, retry advice và DLX.

| Trường hợp | Thường thuộc tầng | Hướng xử lý khuyến nghị |
| --- | --- | --- |
| JSON sai cú pháp | Converter | Reject không requeue; ghi nhận root cause; dead-letter nếu có DLX. |
| Không chuyển được JSON sang kiểu DTO | Converter/type mapping | Kiểm tra schema/converter, có thể reject/DLQ; tránh retry nóng nếu lỗi vĩnh viễn. |
| DTO vi phạm `@Valid` | Argument validation | Reject/DLQ hoặc lưu lỗi contract theo chính sách; không xử lý nghiệp vụ. |
| Thiếu `@Header(required=true)` | Argument resolution | Sửa producer contract, reject/DLQ nếu message không thể tự hồi phục. |
| DB timeout/network phụ thuộc lỗi | Method/service | Retry hữu hạn, backoff; sau giới hạn có thể DLQ. |
| Lỗi vi phạm quy tắc nghiệp vụ không thể hồi phục | Method/service | Không requeue vô hạn; phân loại business failure và xử lý riêng. |

### 8.3. RabbitListenerErrorHandler khác container ErrorHandler

Spring AMQP cho phép khai báo `@RabbitListener(errorHandler = "...")` để dùng `RabbitListenerErrorHandler` ở tầng adapter khi xử lý một lời gọi listener có lỗi. Đây có thể là điểm tập trung logging/handling cho những lỗi đủ điều kiện đến adapter.

Tuy nhiên **không nên chỉ dựa vào RabbitListenerErrorHandler để bắt mọi lỗi sớm**. Một lỗi conversion có thể xảy ra trước khi adapter tạo được Spring Messaging message hoặc trước khi chọn method; khi ấy listener-specific error handler **có thể không được gọi**. Muốn kiểm soát nhất quán cả các lỗi trước invocation, cần quan sát và cấu hình **container-level error handling**.

Một hệ thống có thể có cả hai loại handler:

- **Adapter/listener-specific:** xử lý logic bổ sung khi invocation đạt đến tầng đó.
- **Listener container:** quyết định xử lý delivery khi exception thoát ra, bao gồm reject/requeue, DLX và logging.

**Không nuốt lỗi rồi trả thành công** trừ khi thật sự muốn consumer ACK message đó. Nếu error handler che exception và trả về giá trị thành công khi nghiệp vụ chưa hoàn tất, container có thể coi delivery đã xử lý thành công tùy mode.

## 9. ACK, reject, requeue và DLQ khi validation lỗi

### 9.1. Ba chế độ acknowledgment cần phân biệt

| Spring container ack mode | Cách hoạt động | Rủi ro khi validation lỗi |
| --- | --- | --- |
| `AUTO` | Container gửi ACK sau khi method thành công, quyết định reject/requeue khi exception. | Cần error handler/ retry/DLX để tránh vòng lặp hoặc mất dấu lỗi. |
| `MANUAL` | Ứng dụng/handler chịu trách nhiệm ACK/NACK theo thiết kế. | Nếu lỗi xảy ra **trước khi method chạy**, method không có cơ hội gọi `basicAck`; phải có chiến lược error handling phù hợp. |
| `NONE` | Broker delivery với auto-ack; broker không đợi ACK thủ công cho các delivery đó. | Message có thể đã được coi là xử lý xong từ góc nhìn broker **trước khi validation**; không phù hợp nếu cần kiểm soát thất bại. |

`AcknowledgeMode.AUTO` của Spring **không phải** AMQP `autoAck=true`. Trong `AUTO`, listener hoàn thành thì container ACK; lỗi sẽ được container phân loại và phản hồi theo cấu hình.

### 9.2. Dead-letter xảy ra khi nào?

Message bị reject **không requeue** có thể được RabbitMQ đưa tới dead-letter exchange nếu queue được cấu hình DLX hợp lệ:

~~~mermaid
flowchart LR
    I["orders.commands.q"]
    CV["Converter + @Valid"]
    OK["handle() + business commit + ACK"]
    FAIL["Exception trước method"]
    DLX["orders.dlx"]
    DLQ["orders.invalid.q"]
    I --> CV
    CV -- "hợp lệ" --> OK
    CV -- "conversion/validation fail" --> FAIL
    FAIL -- "reject(requeue=false)" --> DLX --> DLQ
~~~

**Có DLX không đồng nghĩa mọi exception đều được dead-letter.** Khi error handler quyết định `requeue=true`, message có thể quay lại queue nguồn. Khi message đã được ACK trước, hoặc chưa từng vào queue, DLX không thể tự khắc phục. Nếu DLX/binding sai, message có thể không vào DLQ như kỳ vọng.

### 9.3. Tại sao retry không giới hạn là nguy hiểm?

Một payload `{"quantity": 0}` vi phạm `@Positive` sẽ vẫn sai sau lần nhận thứ 10.000 nếu producer không sửa dữ liệu. Requeue ngay liên tục làm tiêu hao CPU, network, log và có thể ảnh hưởng message hợp lệ.

Nên:

1. Phân loại **lỗi vĩnh viễn** (converter/contract/validation) và **lỗi tạm thời** (database/network).
2. Lỗi vĩnh viễn: reject không requeue, đẩy tới DLQ/quarantine với dấu vết đầy đủ.
3. Lỗi tạm thời: retry hữu hạn với backoff; sau giới hạn đưa tới DLQ hoặc trạng thái cần điều tra.
4. Dùng event/command ID ổn định để consumer chống trùng khi có redelivery.
5. Quan sát lượng message ready/unacknowledged, redelivery và DLQ, thay vì chỉ đếm exception phía ứng dụng.

## 10. Validation groups và custom validation

### 10.1. @Valid với nhóm mặc định

`@Valid` áp dụng Bean Validation theo nhóm mặc định nếu không có cơ chế group khác. Với payload tạo đơn hàng:

~~~java
@RabbitListener(queues = OrderListenerTopology.QUEUE)
public void handle(@Payload @Valid PlaceOrderCommand command) {
    // Với default group, kiểm tra constraints như @NotBlank, @Positive...
}
~~~

Nếu cần các quy tắc khác nhau cho lệnh tạo/sửa, có thể khai báo validation groups và dùng `@Validated(...)` khi Spring Messaging argument resolver/validator đã được cấu hình tương thích. Ví dụ khái niệm:

~~~java
public interface CreateGroup {}
public interface UpdateGroup {}

// Trên tham số listener:
// void handle(@Payload @Validated(CreateGroup.class) CreateCommand command)
~~~

Không nên lạm dụng một DTO duy nhất với hàng chục groups. Một command type rõ ràng cho mỗi loại nghiệp vụ (ví dụ `PlaceOrderCommand`, `CancelOrderCommand`) thường đơn giản hơn và giảm rủi ro producer thay schema làm ảnh hưởng consumer.

### 10.2. Custom class-level constraint

Nếu một ràng buộc phụ thuộc nhiều field của DTO, ví dụ tổng tiền phải bằng tổng giá trị các dòng *đã được producer đính kèm*, có thể viết custom Bean Validation constraint ở cấp class. Nhưng đừng xem validation ấy là thay thế domain transaction; giá bán và khuyến mãi có thể đã thay đổi trong database khi message được tiêu thụ.

**Nguyên tắc thiết kế:** trước method nên kiểm tra **cấu trúc, tính đầy đủ, định dạng và những ràng buộc không cần đọc DB**. Trong method/service nên kiểm tra **business invariants tại thời điểm commit**, quyền xử lý nghiệp vụ, idempotency và các phụ thuộc ngoài.

## 11. Kiểm chứng bằng ba loại message

Để thấy rõ **method chưa chạy**, hãy thử trên RabbitMQ cục bộ và một listener có log tại đầu method. Không dùng queue production để cố ý gửi dữ liệu sai.

### 11.1. Trường hợp A: JSON hợp lệ và DTO đạt validation

Producer gọi `PlaceOrderPublisher.sendValidCommand()` ở mục 7. Listener phải:

- Được gọi với `PlaceOrderCommand` hợp lệ.
- In/ghi log bắt đầu method nếu bạn thêm log.
- Ghi nghiệp vụ thành công, sau đó container gửi ACK.

Nếu vẫn có exception ở service, đó là **lỗi trong method** chứ không phải Bean Validation.

### 11.2. Trường hợp B: JSON đúng cú pháp nhưng vi phạm constraints

Gửi một DTO với `orderId=" "`, `currency="vn"`, `quantity=0` bằng JSON converter:

~~~java
PlaceOrderCommand invalid = new PlaceOrderCommand(
        "cmd-invalid-001",
        " ",
        new java.math.BigDecimal("-100"),
        "vn",
        java.util.List.of(new OrderLine("", 0))
);

rabbitTemplate.convertAndSend(
        OrderListenerTopology.EXCHANGE,
        OrderListenerTopology.ROUTING_KEY,
        invalid
);
~~~

Đây là đoạn minh họa trong method đã có bean `RabbitTemplate rabbitTemplate`. Khi listener validation được gắn đúng, DTO tạo được nhưng vi phạm constraints; **thân method không chạy**. Với cấu hình ví dụ `default-requeue-rejected=false` và DLX hợp lệ, message có thể được dead-letter vào `orders.invalid.q`.

Nếu listener vẫn chạy dù DTO sai, cần kiểm tra có thực sự bật `Validator` ở `RabbitListenerEndpointRegistrar` hay không, và các annotation `@Valid`, `@NotBlank`, `@Positive` có được đặt trên đúng kiểu/tham số.

### 11.3. Trường hợp C: JSON không chuyển đổi được

Để thử lỗi cú pháp JSON, gửi raw `Message` có `contentType=application/json` nhưng body sai:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;

MessageProperties properties = new MessageProperties();
properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
properties.setMessageId("cmd-broken-json-001");

Message broken = new Message(
        "{not-valid-json".getBytes(StandardCharsets.UTF_8),
        properties
);

rabbitTemplate.send(
        OrderListenerTopology.EXCHANGE,
        OrderListenerTopology.ROUTING_KEY,
        broken
);
~~~

Ở đây không dùng `convertAndSend` vì producer cần cố ý gửi **body JSON sai**. Đoạn code đặt trong method có bean `RabbitTemplate rabbitTemplate`. Listener converter không thể parse body; lỗi diễn ra **trước khi Bean Validation được chạy** và trước khi listener method bắt đầu.

### 11.4. So sánh kết quả

| Thử nghiệm | JSON parse | Bean Validation | Gọi `handle(...)`? | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| A: DTO hợp lệ | Đạt | Đạt | **Có** | Service chạy; ACK sau xử lý thành công. |
| B: DTO vi phạm constraints | Đạt | Không đạt | **Không** | Lỗi validation; reject/requeue/DLQ theo policy. |
| C: JSON hỏng | Không đạt | Chưa chạy | **Không** | Lỗi converter; reject/requeue/DLQ theo policy. |
| D: DTO hợp lệ nhưng DB timeout | Đạt | Đạt | **Có** | Exception nghiệp vụ/tạm thời; retry theo policy. |

Tuy cùng có thể đi tới DLQ, B và C có **root cause khác nhau**. Tách đúng nguyên nhân giúp sửa lỗi ở producer schema, converter hay quy tắc dữ liệu, thay vì tăng retry vô ích.

## 12. Quan sát và phân loại lỗi

Những trường hữu ích trong log/metrics:

| Trường | Mục đích |
| --- | --- |
| `messageId` hoặc `commandId` | Xác định cùng logical command qua retry và redelivery. |
| `correlationId` | Ghép message với workflow/request gốc. |
| `appId` và `type` | Biết producer nào và contract message nào đang gửi dữ liệu. |
| Exchange, routing key, queue, vhost | Kiểm tra đường định tuyến trước khi listener nhận. |
| `contentType` và type headers | Chẩn đoán converter, JSON và inferred target type. |
| Exception **root cause** | Phân biệt conversion, validation, missing header và business error. |
| `redelivered`, `x-death` khi có | Quan sát history giao lại/dead-letter theo broker và topology. |
| Delivery ACK/reject/requeue | Biết message đã được xử lý thế nào ở broker. |
| DLQ depth / oldest message age | Phát hiện contract sai kéo dài hoặc poison messages. |

### 12.1. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Biện pháp |
| --- | --- | --- |
| `@Valid` có nhưng listener vẫn nhận `orderId=""` | Validation provider/handler method factory chưa được cấu hình hoặc annotation đặt sai vị trí. | Kiểm tra starter validation, registrar, DTO constraints, đơn vị test invalid payload. |
| Raw `byte[]` hoặc `LinkedHashMap` tới listener | Converter không phù hợp hoặc type mapping thiếu. | Dùng JSON converter, inferred type rõ ràng, schema/headers đúng. |
| `MessageConversionException` trước log đầu method | JSON syntax/contentType/schema hoặc trusted type headers lỗi. | Đọc root cause; sửa publisher/contract, dead-letter nếu lỗi vĩnh viễn. |
| `MethodArgumentNotValidException` | DTO parse được nhưng không đạt Bean Validation. | Sửa dữ liệu hoặc contract; reject/DLQ theo chính sách. |
| Thiếu `@Header` bắt buộc | Producer không cung cấp application header. | Chỉnh producer, cho optional nếu nghiệp vụ cho phép. |
| Message bị requeue liên tục dù JSON không đổi | Error handler/policy cho requeue lỗi vĩnh viễn. | Chặn retry nóng, phân loại fatal, dùng DLX/quarantine. |
| DLQ trống dù listener liên tục báo lỗi | Không có DLX, binding sai, message đang requeue hoặc đã ACK. | Kiểm tra queue arguments/policy, ack mode và message state. |
| Consumer method chạy nhiều lần cùng command | Redelivery sau mất ACK hoặc producer retry. | Dùng idempotency theo `commandId` với transaction DB. |

### 12.2. Metrics nên tách theo giai đoạn

- `listener_conversion_failures_total`: message không chuyển thành DTO.
- `listener_validation_failures_total`: DTO tạo được nhưng không đạt constraints.
- `listener_business_failures_total`: method chạy nhưng service thất bại.
- `listener_success_total` và processing latency: thành công thực tế sau các kiểm tra đầu vào.
- `queue_ready`, `queue_unacknowledged`, `dlq_depth`: trạng thái broker.

Các tên trên là **đề xuất metric ứng dụng**, không phải tên built-in bắt buộc của RabbitMQ. Dùng cùng message ID/correlation ID trong log để theo dõi một delivery, nhưng **không ghi toàn bộ payload chứa thông tin nhạy cảm** vào error logs.

## 13. Ảnh hưởng của validation tới giao dịch, retry và idempotency

### 13.1. Validate trước method không đồng nghĩa message được xử lý đúng một lần

Giả sử command hợp lệ, listener gọi DB thành công, nhưng mất connection trước khi consumer ACK tới RabbitMQ. Broker có thể giao lại message. `@Valid` vẫn đạt trong lần sau, và service có nguy cơ tạo đơn hàng lần hai nếu thiếu idempotency.

Giải pháp:

1. Producer gắn **commandId/eventId ổn định**, giữ ID khi retry cùng logical command.
2. Consumer kiểm tra `processed_commands(commandId)` trong database.
3. Ghi dấu đã xử lý **trong cùng transaction** với thay đổi nghiệp vụ khi khả thi.
4. Chỉ xác nhận delivery sau khi transaction thành công.
5. Phân biệt retry ở consumer với retry publish của producer; cả hai đều có thể tạo delivery trùng.

Không nên dùng `deliveryTag` làm ID nghiệp vụ: delivery tag thuộc một channel và một lần giao, không ổn định qua redelivery.

### 13.2. @Valid không phải bước bảo mật hoàn chỉnh

Payload đến từ queue vẫn là dữ liệu đầu vào từ một hệ thống khác. Bên cạnh constraints:

- **Giới hạn trusted packages/type mapping** của JSON converter; không tùy tiện deserialize class name do header ngoài cung cấp.
- **Phân quyền broker và vhost**, bảo vệ credentials/TLS; `appId` trong message không phải chứng thực producer.
- **Ràng buộc kích thước payload**, giới hạn nested data và số lượng list elements để tránh tiêu tốn bộ nhớ/CPU.
- **Xác minh domain authorization** và dữ liệu tham chiếu ở service trong transaction, không tin mọi ID nhận từ message.
- **Versioning contract** để producer mới không làm consumer cũ lỗi chuyển đổi hàng loạt.

### 13.3. Khi nào cần custom error policy?

Một hệ thống thực tế có thể áp dụng:

- **Permanent input errors:** conversion/validation/type mismatch → reject không requeue, DLQ và alert producer.
- **Transient processing errors:** DB timeout, downstream outage → retry hữu hạn với backoff, sau đó DLQ.
- **Duplicate command đã xử lý:** consumer idempotent xác định đã hoàn tất → ACK, không lặp side effect.
- **Unknown business outcome:** chẳng hạn DB commit có thể thành công nhưng kết nối mất → đối soát bằng command ID trước khi thử lại.

Không nên cấu hình “mọi exception đều requeue” hoặc “mọi exception đều dead-letter” nếu nhu cầu nghiệp vụ khác nhau. Error classification là một phần của thiết kế xử lý bất đồng bộ đáng tin cậy.

## 14. Checklist triển khai

Trước khi cho listener nhận lưu lượng production, kiểm tra:

| Kiểm tra | Vì sao quan trọng? |
| --- | --- |
| Producer và consumer thống nhất JSON schema, encoding, `contentType` | Tránh converter failure trước method. |
| `@Payload`/method signature diễn đạt đúng kiểu DTO | Argument resolver có thông tin kiểu mục tiêu rõ ràng. |
| DTO có constraints thích hợp, kể cả DTO lồng nhau | Loại input sai cấu trúc trước xử lý nghiệp vụ. |
| Validation provider và validator được nối vào method factory | `@Valid` thật sự được chạy. |
| Đã test JSON invalid và DTO violation riêng | Xác nhận phân loại conversion vs validation. |
| Error handler có chính sách cho fatal vs transient | Tránh requeue vô hạn hoặc làm mất message cần retry. |
| Queue có DLX/DLQ hợp lệ và đã kiểm chứng | Có nơi giữ message bị reject để phân tích. |
| Ack mode phù hợp, đã test mất connection/ACK | Hành vi delivery rõ ràng khi xử lý thất bại. |
| Consumer idempotent theo event/command ID | Tránh side effect lặp khi redelivery. |
| Có log/metrics và alert cho các lỗi trước invocation | Không bỏ sót message chỉ vì method không in log. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@Payload` có tự đảm bảo `orderId` không rỗng không?

**Trả lời:** Không. `@Payload` chỉ đánh dấu tham số payload; để kiểm tra nội dung, cần constraints và `@Valid`/validator được cấu hình cho listener.

**Câu 2.** JSON sai cú pháp và DTO vi phạm `@NotBlank` có cùng giai đoạn lỗi không?

**Trả lời:** Không. JSON sai cú pháp thất bại khi conversion; DTO vi phạm constraints là lỗi Bean Validation sau khi đã parse được.

**Câu 3.** Vì sao `try/catch` ở đầu `handle(...)` không bắt được mọi lỗi converter?

**Trả lời:** Vì converter và argument resolution chạy **trước khi method được invoke**; khi chúng lỗi, method không được gọi.

**Câu 4.** `@RabbitListener(errorHandler="...")` có bảo đảm bắt mọi JSON conversion failure không?

**Trả lời:** Không. Một số lỗi có thể xảy ra trước tầng listener adapter phù hợp; container error handler cần được cấu hình và quan sát.

**Câu 5.** Với Spring `acknowledge-mode=AUTO`, consumer đã ACK trước khi method chạy chưa?

**Trả lời:** Không. Container AUTO xác nhận sau xử lý thành công; khác AMQP auto-ack của `NONE`.

**Câu 6.** Nếu JSON sai schema vĩnh viễn, tăng requeue từ 3 lên vô hạn có giúp sửa message không?

**Trả lời:** Không. Cần reject/dead-letter/quarantine, sửa producer hoặc triển khai consumer tương thích contract; retry nóng chỉ lặp lại cùng lỗi.

**Câu 7.** Khi DTO đạt `@Valid`, có thể bỏ kiểm tra DB và idempotency không?

**Trả lời:** Không. `@Valid` kiểm tra input constraints, không bảo đảm dữ liệu DB hiện tại, transaction, authorization hoặc side effect chỉ diễn ra một lần.

**Câu 8.** Muốn kiểm tra một trường header bắt buộc trước khi method chạy, dùng gì?

**Trả lời:** Khai báo `@Header` với `required=true` theo Spring Messaging. Nếu header thiếu, argument resolution có thể thất bại trước invocation; cần xử lý theo chính sách lỗi.

## 16. Tài liệu tham khảo

- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener`, `@Payload`, tham số method và listener adapter.
- [Spring AMQP — Annotation-driven Conversion](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): converter, inferred argument type và cấu trúc message method.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `ConditionalRejectingErrorHandler`, lỗi fatal, reject/requeue.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): JSON serialization/deserialization, converter type mapping.
- [Spring Framework — @Payload](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): `required` và ngữ nghĩa của payload parameter.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Bean Validation, `@Valid`, `Validator` và constraints.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): xác nhận phía consumer và publisher là hai cơ chế riêng.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): xử lý message bị reject không requeue và điều kiện định tuyến tới DLQ.

**Ghi nhớ:** `@Payload` giúp ánh xạ message body vào tham số listener; `@Valid`/`@Validated` cùng validator đã cấu hình giúp kiểm tra DTO **trước khi gọi method**. Khi JSON conversion, phân giải tham số hoặc validation thất bại, `@RabbitListener` có thể **chưa được invoke**, nên `try/catch` bên trong method không đủ. Hãy kết hợp **message converter đúng, Bean Validation, container error handling, chính sách ACK/reject/requeue, DLX/DLQ, retry có backoff, transaction và idempotency** để các thông điệp bất đồng bộ được xử lý an toàn và có thể quan sát.
