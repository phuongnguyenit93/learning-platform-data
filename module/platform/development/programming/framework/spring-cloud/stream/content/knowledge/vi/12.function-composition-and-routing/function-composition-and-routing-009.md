# Kiểm tra tương thích kiểu và header khi ghép hàm

Spring Cloud Function cho phép kết hợp nhiều bean Supplier, Function và Consumer thành một pipeline xử lý. Spring Cloud Stream có thể bind pipeline đó với broker như Kafka, RabbitMQ hoặc Pulsar như thể đó là một hàm duy nhất. Để pipeline hoạt động đúng, đầu ra của mỗi bước phải phù hợp với đầu vào của bước kế tiếp; khi message mang metadata, các header cần được giữ hoặc biến đổi theo một quy tắc rõ ràng.

Hai nhóm lỗi thường gặp khi ghép hàm là lỗi hợp đồng kiểu và lỗi metadata. Hợp đồng kiểu sai có thể khiến framework không chuyển đổi được payload hoặc khiến hàm nhận một kiểu khác với dự kiến. Header bị mất có thể làm mất correlation ID, event ID, tenant context hoặc thông tin phục vụ tracing. Ngược lại, sao chép mọi header một cách máy móc có thể đưa metadata nội bộ hoặc header không còn phù hợp sang bước tiếp theo.

Bài học trình bày cách thiết kế chữ ký hàm, hiểu cơ chế chuyển đổi dữ liệu, kiểm soát header trong từng bước, cấu hình composition và kiểm thử toàn pipeline. Các ví dụ dùng Java, Spring Cloud Function và Spring Cloud Stream; chi tiết converter và một số thuộc tính có thể thay đổi theo phiên bản thư viện.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích composition và quy ước ghép các hàm theo thứ tự.
- Kiểm tra kiểu đầu ra của hàm trước có tương thích với kiểu đầu vào của hàm sau hay không.
- Phân biệt chuyển đổi kiểu bằng MessageConverter và ConversionService.
- Hiểu vai trò của contentType khi chuyển payload giữa các kiểu.
- Phân biệt payload với header trong Spring Message.
- Chủ động giữ, thay đổi hoặc loại bỏ header khi ghép hàm.
- Dùng copy-input-headers và các cơ chế enrichment đúng trường hợp.
- Kiểm thử payload, content type, header và định tuyến trước khi kết nối broker thật.

## 1. Ghép hàm trong Spring Cloud Function

Spring Cloud Function xây dựng trên ba interface hàm của Java:

| Interface | Hợp đồng | Vai trò |
|---|---|---|
| Supplier<T> | Không nhận đầu vào, tạo T | Nguồn dữ liệu |
| Function<T, R> | Nhận T, trả về R | Biến đổi dữ liệu |
| Consumer<T> | Nhận T, không trả kết quả | Tiêu thụ dữ liệu |

Một hàm có thể được khai báo thành bean Spring:

~~~java
@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, ValidatedOrder> validateOrder() {
        return order -> {
            if (order.total() <= 0) {
                throw new IllegalArgumentException("Order total must be positive");
            }
            return new ValidatedOrder(
                    order.orderId(), order.customerId(), order.total());
        };
    }

    @Bean
    Function<ValidatedOrder, OrderAccepted> acceptOrder() {
        return order -> new OrderAccepted(
                order.orderId(), order.customerId(), "ACCEPTED");
    }
}

record OrderCreated(String orderId, String customerId, long total) {}

record ValidatedOrder(String orderId, String customerId, long total) {}

record OrderAccepted(String orderId, String customerId, String status) {}
~~~

Hai hàm có thể được ghép theo thứ tự validateOrder rồi acceptOrder. Đầu ra của hàm đầu tiên là ValidatedOrder, đúng với kiểu đầu vào của hàm thứ hai.

Spring Cloud Function hỗ trợ khai báo composition bằng dấu gạch đứng hoặc dấu phẩy trong spring.cloud.function.definition:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder|acceptOrder
~~~

Biểu thức trên mô tả một pipeline: message đi vào validateOrder, kết quả được chuyển sang acceptOrder, sau đó kết quả cuối cùng đi ra output binding nếu pipeline được Spring Cloud Stream bind. Dấu phẩy cũng có thể dùng làm dấu phân cách composition; dấu gạch đứng thường dễ đọc hơn khi mô tả chuỗi bước.

Composition khai báo không đồng nghĩa với việc tạo thêm một broker hoặc topic cho mỗi hàm. Spring Cloud Stream xem composition là một đơn vị xử lý và tạo binding cho đầu vào/đầu ra của hàm tổng hợp. Nếu cần binding có tên dễ đọc, có thể dùng cơ chế alias binding của Spring Cloud Stream theo phiên bản đang sử dụng.

### 1.1. Các kiểu ghép hợp lệ

Với các hàm imperative, có thể hình dung hợp đồng ghép như sau:

| Thành phần trước | Thành phần sau | Kết quả composition |
|---|---|---|
| Supplier<T> | Function<T, R> | Supplier<R> |
| Supplier<T> | Consumer<T> | Runnable |
| Function<T, R> | Function<R, V> | Function<T, V> |
| Function<T, R> | Consumer<R> | Consumer<T> |

Consumer không tạo ra giá trị trả về, vì vậy không thể ghép nó làm bước trước cho một Function hoặc Supplier đang cần một giá trị đầu vào. Ví dụ Consumer<T> rồi Function<T, R> không có đầu ra để truyền tiếp. Tương tự, Consumer rồi Supplier không phải một composition có hợp đồng dữ liệu phù hợp.

### 1.2. Composition khác với gọi hàm lồng nhau

Bạn có thể gọi trực tiếp hàm này trong hàm kia bằng Java, nhưng declarative composition giúp tách các bước thành bean độc lập. Mỗi bước có thể được kiểm thử riêng, tái sử dụng trong pipeline khác và cấu hình theo function definition.

Ví dụ, validateOrder chỉ thực hiện kiểm tra nghiệp vụ; enrichOrder bổ sung dữ liệu; publishEvent tạo sự kiện đầu ra. Mỗi hàm có một trách nhiệm và hợp đồng kiểu rõ ràng. Khi ghép, cần xác nhận kiểu dữ liệu mà mỗi bước nhận và trả về.

## 2. Hợp đồng kiểu giữa hai hàm

### 2.1. Quy tắc cơ bản

Với hai hàm:

~~~java
Function<A, B> first;
Function<B, C> second;
~~~

Hợp đồng trực tiếp là kiểu đầu ra B của first phù hợp với kiểu đầu vào B của second. Pipeline sau khi ghép có dạng Function<A, C>.

Nếu kiểu đầu ra và đầu vào không tương thích, Java không thể ghép trực tiếp bằng Function.andThen. Spring Cloud Function có cơ chế chuyển đổi dữ liệu khi chạy, nhưng việc chuyển đổi chỉ thành công nếu có đủ thông tin kiểu và một converter phù hợp. Không nên dựa vào khả năng chuyển đổi ngầm để che giấu một hợp đồng dữ liệu được thiết kế sai.

Ví dụ phù hợp:

~~~java
@Bean
Function<OrderCreated, ValidatedOrder> validateOrder() {
    return order -> new ValidatedOrder(
            order.orderId(), order.customerId(), order.total());
}

@Bean
Function<ValidatedOrder, OrderSummary> summarizeOrder() {
    return order -> new OrderSummary(
            order.orderId(), order.customerId(), "VALID");
}

record OrderSummary(String orderId, String customerId, String result) {}
~~~

Hàm summarizeOrder nhận đúng kiểu mà validateOrder tạo ra. Đây là cách ghép dễ hiểu, dễ kiểm thử và ít phụ thuộc vào chuyển đổi tự động.

### 2.2. Bảng kiểm tra tương thích

| Đầu ra của bước trước | Đầu vào của bước sau | Đánh giá |
|---|---|---|
| Cùng kiểu DTO | Cùng kiểu DTO | Phù hợp trực tiếp |
| Kiểu con hoặc kiểu triển khai | Kiểu cha/interface mà nó thực thi | Có thể phù hợp theo quan hệ kiểu Java |
| String JSON | DTO | Cần converter và content type phù hợp |
| byte[] | DTO | Cần converter biết cách giải mã định dạng payload |
| DTO A | DTO B không có quan hệ hoặc converter | Không tương thích nếu không có chuyển đổi được hỗ trợ |
| Message<A> | Message<B> | Cần xử lý payload và header theo hợp đồng Message |
| Message<A> | B | Framework có thể trích payload và chuyển đổi theo chữ ký hàm; phải kiểm thử header và converter |

Hãy ưu tiên dùng cùng một kiểu DTO hoặc một kiểu hợp đồng chung ở ranh giới giữa các hàm. Nếu phải chuyển đổi, hãy làm rõ định dạng dữ liệu và kiểm thử bằng payload thật.

### 2.3. Tránh chữ ký raw type và Object quá rộng

Chữ ký như Function hoặc Function<Object, Object> làm mất nhiều thông tin kiểu mà FunctionCatalog có thể dùng để xác định cách chuyển đổi. Khi không thể xác định kiểu đích từ chữ ký, framework có thể cần metadata bổ sung như tham số type trong content type; cách này phải được cấu hình và giới hạn lớp được phép giải tuần tự.

Ví dụ:

~~~java
// Khuyến nghị: kiểu đầu vào và đầu ra rõ ràng
Function<OrderCreated, ValidatedOrder> validateOrder;

// Khó xác định hợp đồng hơn
Function validateOrder;
Function<Object, Object> validateAnything;
~~~

Generic type trong chữ ký hàm là một phần của hợp đồng ứng dụng. Hãy giữ kiểu DTO cụ thể, tránh raw type và tránh dùng Object chỉ để làm cho nhiều kiểu dữ liệu khác nhau cùng đi qua một pipeline.

## 3. Chuyển đổi kiểu và content type

Spring Cloud Function hỗ trợ chuyển đổi để payload phù hợp với kiểu mà hàm khai báo. Cơ chế được chọn tùy thuộc dữ liệu đầu vào:

- MessageConverter chuyển payload của Spring Message sang kiểu mà hàm yêu cầu.
- ConversionService chuyển đổi dữ liệu không được truyền dưới dạng Message.

Trong luồng messaging, dữ liệu thường đã được bao bọc trong Message. Khi đó, framework sử dụng chữ ký hàm và contentType để tìm MessageConverter thích hợp.

### 3.1. Content type là gợi ý định dạng

Giả sử hàm yêu cầu Person nhưng message đến có payload là byte[] chứa JSON. Framework cần biết payload là JSON và kiểu đích là Person. Content type application/json kết hợp với kiểu đích Person giúp chọn converter phù hợp.

Ví dụ cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: registerPerson
    stream:
      bindings:
        registerPerson-in-0:
          destination: people.registered
          content-type: application/json
        registerPerson-out-0:
          destination: people.processed
          content-type: application/json
~~~

Ví dụ hàm:

~~~java
@Bean
Function<Person, PersonRegistered> registerPerson() {
    return person -> new PersonRegistered(
            person.id(), person.name(), "REGISTERED");
}

record Person(String id, String name) {}

record PersonRegistered(String id, String name, String status) {}
~~~

Binding input khai báo JSON để framework biết cách diễn giải payload. Chữ ký Person cho biết kiểu đích. Nếu content type không có, Spring Cloud Function mặc định dùng application/json trong các trường hợp được tài liệu mô tả; tuy nhiên, nên khai báo tường minh để hợp đồng giữa producer và consumer dễ quan sát.

### 3.2. Content type không thay thế kiểu đích

Content type chỉ mô tả định dạng hoặc gợi ý cho converter. Nó không tự biến một payload bất kỳ thành một DTO. Converter vẫn phải hỗ trợ tổ hợp payload hiện tại, content type và kiểu đích.

Ví dụ:

- byte[] + application/json + Person: có thể chuyển thành Person nếu JSON hợp lệ và converter hỗ trợ.
- String + text/plain + String: có thể chuyển thành chuỗi.
- byte[] + application/octet-stream + byte[]: có thể giữ nguyên dạng byte.
- JSON sai cú pháp + application/json + Person: chuyển đổi thất bại.
- XML + application/json + Person: không tương thích nếu không có converter phù hợp.

Nếu không tìm thấy converter, framework ném lỗi chuyển đổi trước hoặc trong lúc gọi hàm. Hãy xử lý lỗi theo chính sách của ứng dụng và ghi log đủ thông tin về binding, content type và kiểu đích; tránh log payload nhạy cảm.

### 3.3. Chuyển đổi giữa các bước composition

Content-Type negotiation cũng được sử dụng trong quá trình composition. Điều này cho phép một số hàm có kiểu đầu ra và đầu vào khác nhau vẫn ghép được nếu framework có thể chuyển đổi payload giữa hai bước.

Ví dụ về tình huống cần chuyển đổi:

~~~text
Function<Person, String>  -- tạo JSON text -->
Function<Person, Greeting> -- cần Person
~~~

Trong trường hợp này, chuỗi đầu ra phải thực sự là JSON, và converter phải nhận diện được content type cũng như kiểu Person cần tạo. Nếu hàm đầu tiên trả về chuỗi văn bản tự do như "đã nhận đơn hàng", converter JSON không thể suy ra một Person hợp lệ.

Để giảm rủi ro:

1. Ưu tiên để hàm đầu ra trả DTO có kiểu cụ thể.
2. Chỉ dùng chuyển đổi qua JSON hoặc byte[] khi có lý do tích hợp rõ ràng.
3. Khai báo content type ở binding hoặc message theo định dạng thật.
4. Kiểm thử cả dữ liệu hợp lệ và dữ liệu lỗi.
5. Nếu định dạng riêng, đăng ký MessageConverter phù hợp và kiểm thử converter độc lập.

### 3.4. MessageConverter tùy chỉnh

Khi định dạng dữ liệu không được converter mặc định hỗ trợ, có thể triển khai org.springframework.messaging.converter.MessageConverter và đăng ký thành bean. Converter cần khai báo MIME type hỗ trợ và xác định kiểu Java mà nó có thể chuyển đổi.

Ví dụ khung triển khai:

~~~java
public class BinaryOrderConverter extends AbstractMessageConverter {

    public BinaryOrderConverter() {
        super(new MimeType("application", "x-order"));
    }

    @Override
    protected boolean supports(Class<?> targetClass) {
        return OrderCreated.class.equals(targetClass);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        byte[] bytes = (byte[]) message.getPayload();
        return decodeOrder(bytes);
    }

    private OrderCreated decodeOrder(byte[] bytes) {
        // Giải mã theo định dạng nhị phân đã được đặc tả.
        throw new UnsupportedOperationException("Implement binary decoder");
    }
}
~~~

Đây là khung minh họa, cần bổ sung decoder thực tế và kiểm tra kiểu payload trước khi ép kiểu. Converter tùy chỉnh được thêm vào đầu danh sách converter của Spring Cloud Function, vì vậy nó có thể được ưu tiên hơn converter mặc định. Chỉ nên hỗ trợ MIME type và kiểu đích mà converter thực sự hiểu.

Không lấy tên lớp Java từ header do nguồn không tin cậy gửi đến rồi nạp tùy ý. Nếu dùng tham số type trong MIME type để xác định lớp giải tuần tự, cần khai báo danh sách lớp được phép theo cơ chế whitelist mà phiên bản thư viện hỗ trợ.

## 4. Message gồm payload và header

Spring Message có hai phần:

- Payload là dữ liệu nghiệp vụ, ví dụ OrderCreated.
- Header là metadata mô tả message, ví dụ contentType, correlationId, eventId, timestamp hoặc thông tin tracing.

Ví dụ tạo message:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated("o-100", "c-20", 2500))
        .setHeader("eventId", "evt-100")
        .setHeader("correlationId", "corr-900")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Header không nên thay thế payload. Dữ liệu cần được lưu trữ, kiểm tra, version hóa hoặc chia sẻ như một phần của hợp đồng nghiệp vụ nên nằm trong payload. Header phù hợp với metadata phục vụ định tuyến, tracing, correlation, content negotiation và vận hành.

### 4.1. Đọc header trong hàm

Nếu hàm cần truy cập payload và header, có thể nhận Message<T>:

~~~java
@Bean
Function<Message<OrderCreated>, Message<ValidatedOrder>> validateWithMetadata() {
    return input -> {
        OrderCreated order = input.getPayload();
        ValidatedOrder validated = new ValidatedOrder(
                order.orderId(), order.customerId(), order.total());

        return MessageBuilder.withPayload(validated)
                .setHeader("eventId", input.getHeaders().get("eventId"))
                .setHeader("correlationId", input.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

Ví dụ này chủ động chọn hai header nghiệp vụ cần giữ lại. Trong mã thực tế, nên kiểm tra header có tồn tại và có kiểu dữ liệu hợp lệ trước khi dùng. Không nên giả định mọi message đều có eventId hoặc correlationId.

Nếu muốn giữ tất cả header hiện có rồi thay payload, có thể dùng MessageBuilder.fromMessage(input).setPayload(validated).build(). Cách này thuận tiện nhưng có thể mang theo cả header không cần thiết, vì vậy cần hiểu nguồn gốc và phạm vi sử dụng của từng header.

### 4.2. Header không tự động được chuyển tiếp trong mọi trường hợp

Trong tình huống thông thường, header của input Message không được tự động chuyển sang output Message. Đây là hành vi có chủ đích: output có thể đi vào một hệ thống khác với bộ header riêng.

Nếu hàm nhận Message và trả Message, framework chủ yếu giữ nguyên Message do hàm tạo ra và thực hiện chuyển đổi payload khi cần. Vì vậy, nếu muốn giữ correlationId hoặc eventId, hãy sao chép chúng một cách có chủ đích.

Ví dụ:

~~~java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        OrderAccepted accepted =
                new OrderAccepted(order.orderId(), "ACCEPTED");

        return MessageBuilder.fromMessage(input)
                .setPayload(accepted)
                .build();
    };
}
~~~

Ở đây, MessageBuilder.fromMessage sao chép header của message đầu vào. Nếu chỉ cần một vài metadata, hãy tạo message mới và chọn header cần giữ để tránh chuyển tiếp thông tin không liên quan.

## 5. Kiểm soát việc sao chép header

### 5.1. copy-input-headers

Spring Cloud Function có thuộc tính copy-input-headers để yêu cầu framework sao chép header đầu vào sang output của một hàm. Thuộc tính này được cấu hình theo tên hàm:

~~~yaml
spring:
  cloud:
    function:
      configuration:
        uppercase:
          copy-input-headers: true
~~~

Ví dụ bean chỉ làm việc với payload:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Hàm không trực tiếp nhận Message, nhưng caller vẫn có thể gửi một Message<String>. Framework trích payload để gọi hàm và có thể sao chép header đầu vào sang output khi copy-input-headers được bật.

Nên bật thuộc tính này khi hầu hết header đầu vào thực sự cần được giữ nguyên qua hàm. Nếu chỉ một số header có ý nghĩa, tạo hàm enrichment hoặc trả Message mới với danh sách header được chọn thường rõ ràng hơn.

### 5.2. Sao chép header có chọn lọc

Ví dụ:

~~~java
@Bean
Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        OrderValidated result = new OrderValidated(
                order.orderId(), order.customerId(), order.total());

        MessageBuilder<OrderValidated> builder = MessageBuilder.withPayload(result);

        Object eventId = input.getHeaders().get("eventId");
        Object correlationId = input.getHeaders().get("correlationId");

        if (eventId != null) {
            builder.setHeader("eventId", eventId);
        }
        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }

        return builder.build();
    };
}
~~~

Cách này làm rõ hợp đồng đầu ra: output chỉ chứa metadata mà bước tiếp theo cần. Các header như deliveryAttempt, broker-specific partition metadata hoặc thông tin transport có thể không còn ý nghĩa khi message đi qua một ranh giới khác.

### 5.3. Enrichment bằng một hàm riêng

Thay vì trộn logic bổ sung metadata vào hàm nghiệp vụ, có thể tạo một hàm enrichment:

~~~java
@Bean
Function<Message<?>, Message<?>> addCorrelation() {
    return message -> MessageBuilder.fromMessage(message)
            .setHeaderIfAbsent("correlationId", UUID.randomUUID().toString())
            .build();
}

@Bean
Function<Message<OrderCreated>, Message<ValidatedOrder>> validateOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        ValidatedOrder result = new ValidatedOrder(
                order.orderId(), order.customerId(), order.total());
        return MessageBuilder.fromMessage(input)
                .setPayload(result)
                .build();
    };
}
~~~

Ghép hàm:

~~~yaml
spring:
  cloud:
    function:
      definition: addCorrelation|validateOrder
~~~

Hàm addCorrelation xử lý metadata trước khi message đến logic nghiệp vụ. validateOrder tập trung vào quy tắc đơn hàng. Đây là cách tách cross-cutting concern như correlation hoặc audit metadata khỏi code nghiệp vụ.

Không nên tạo correlation ID mới nếu message đã có một ID hợp lệ. Nếu có yêu cầu chuẩn hóa ID, cần xác định rõ quy tắc giữ nguyên, thay thế và ghi log để có thể truy vết xuyên suốt pipeline.

## 6. Header và định tuyến

Header có thể mang thông tin để quyết định hàm nào cần xử lý message. Spring Cloud Function cung cấp RoutingFunction, được đăng ký trong FunctionCatalog với tên functionRouter.

Có thể khai báo hàm định tuyến dựa trên header hoặc routing expression. Ví dụ, message có eventType OrderCreated được chuyển tới handleOrder; các message còn lại được đưa tới ignoreEvent:

~~~java
@Bean
Function<Message<OrderCreated>, OrderAccepted> handleOrder() {
    return message -> new OrderAccepted(
            message.getPayload().orderId(), "ACCEPTED");
}

@Bean
Consumer<Message<?>> ignoreEvent() {
    return message -> log.info(
            "Ignoring unsupported event type: {}",
            message.getHeaders().get("eventType"));
}
~~~

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: functionRouter
      routing-expression: "headers.eventType == 'OrderCreated' ? 'handleOrder' : 'ignoreEvent'"
~~~

Biểu thức là SpEL; nó được đánh giá trên input argument. Khi input là Message, expression có thể truy cập payload và headers. Cần bảo đảm tên hàm đích tồn tại trong FunctionCatalog và có chữ ký phù hợp với kiểu message được định tuyến.

### 6.1. Định tuyến theo từng message và reactive stream

Với hàm imperative, một message là đơn vị công việc nên routing instruction có thể được truyền trong header của message. Có thể dùng spring.cloud.function.definition hoặc spring.cloud.function.routing-expression trong header.

Với hàm reactive nhận Publisher/Flux, đơn vị công việc là toàn bộ stream. Function được gọi để nhận Publisher, sau đó Reactor xử lý các phần tử bên trong. Vì vậy, không thể dựa vào header của từng phần tử để chọn lại function cho mỗi message theo cùng cách imperative. Routing instruction cho reactive function cần được cung cấp qua application properties và áp dụng cho cả stream.

### 6.2. Thứ tự ưu tiên routing instruction

Khi có nhiều nguồn chỉ định route, Spring Cloud Function áp dụng thứ tự ưu tiên được tài liệu mô tả:

1. MessageRoutingCallback đối với hàm imperative.
2. Message header nếu không có MessageRoutingCallback.
3. Application properties.

Nếu route không tồn tại trong FunctionCatalog, framework có thể ném exception. Hãy kiểm tra tên route trong test và có chính sách rõ ràng cho message không định tuyến được.

### 6.3. Kiểm soát dữ liệu header dùng để định tuyến

Không cho nguồn không tin cậy tùy ý quyết định tên bean hoặc function definition. Chỉ cho phép các route trong danh sách định trước, xác thực eventType và bảo vệ những endpoint có thể thay đổi cấu hình ứng dụng. Với routing expression, giới hạn quyền gửi header và không xem header là một vùng cấu hình đáng tin cậy.

## 7. Header ở ranh giới Kafka, RabbitMQ và Pulsar

Spring Message header là mô hình metadata ở tầng ứng dụng. Mỗi broker có quy tắc riêng để lưu hoặc vận chuyển metadata:

| Broker | Ví dụ metadata thường gặp | Điểm cần kiểm tra |
|---|---|---|
| Kafka | Record key, timestamp, partition, record headers | Kiểu byte của header, key và partitioning |
| RabbitMQ | Routing key, exchange, delivery tag, properties | Header AMQP, kiểu dữ liệu và mapping của binder |
| Pulsar | Message key, properties, event time, sequence | Mapping properties và metadata subscription |

Binder ánh xạ một phần metadata giữa broker và Spring Message. Không nên giả định mọi header của Spring được lưu giống nhau trên cả ba broker. Một số header phục vụ nội bộ framework có thể bị loại bỏ hoặc chuyển thành metadata khác.

Nếu cần giữ correlation ID xuyên qua nhiều dịch vụ, hãy định nghĩa tên header ở cấp ứng dụng và kiểm thử mapping trên binder được triển khai. Nếu cần giữ event ID lâu dài, cân nhắc đưa nó vào payload hoặc một trường metadata được chuẩn hóa rõ ràng.

Không dùng header broker-specific làm hợp đồng nghiệp vụ dùng chung trừ khi chấp nhận sự phụ thuộc đó và đã có kiểm thử tương ứng.

## 8. Kiểm thử tương thích kiểu và header

Kiểm thử cần xác minh ba việc: hàm nhận đúng kiểu, payload đầu ra đúng nội dung và metadata được giữ hoặc loại bỏ theo hợp đồng.

### 8.1. Unit test từng hàm

Các hàm độc lập có thể được kiểm thử trực tiếp:

~~~java
class OrderFunctionTest {

    private final Function<OrderCreated, ValidatedOrder> validate =
            order -> new ValidatedOrder(
                    order.orderId(), order.customerId(), order.total());

    @Test
    void createsValidatedOrder() {
        ValidatedOrder result = validate.apply(
                new OrderCreated("o-1", "c-1", 1200));

        assertThat(result.orderId()).isEqualTo("o-1");
        assertThat(result.total()).isEqualTo(1200);
    }
}
~~~

Unit test nên bao gồm dữ liệu hợp lệ, dữ liệu biên, kiểu null nếu hợp đồng cho phép và exception nghiệp vụ.

### 8.2. Kiểm thử header bằng Message

~~~java
@Test
void preservesSelectedHeaders() {
    Message<OrderCreated> input = MessageBuilder
            .withPayload(new OrderCreated("o-1", "c-1", 1200))
            .setHeader("eventId", "evt-1")
            .setHeader("correlationId", "corr-1")
            .setHeader("internalDebug", "remove-me")
            .build();

    Message<OrderValidated> output = validateOrder().apply(input);

    assertThat(output.getHeaders().get("eventId")).isEqualTo("evt-1");
    assertThat(output.getHeaders().get("correlationId")).isEqualTo("corr-1");
    assertThat(output.getHeaders()).doesNotContainKey("internalDebug");
}
~~~

Test này chứng minh output giữ đúng hai header đã chọn và không phát tán header nội bộ. Hàm validateOrder trong test cần là factory hoặc bean trả về Function tương ứng.

### 8.3. Kiểm thử composition qua FunctionCatalog

FunctionCatalog cung cấp wrapper đã được instrument để hỗ trợ các tính năng như composition và chuyển đổi kiểu. Khi kiểm thử composition, hãy lấy hàm tổng hợp từ catalog thay vì chỉ gọi trực tiếp bean gốc:

~~~java
Function<OrderCreated, OrderAccepted> pipeline =
        functionCatalog.lookup("validateOrder|acceptOrder");

OrderAccepted result = pipeline.apply(
        new OrderCreated("o-1", "c-1", 1200));

assertThat(result.status()).isEqualTo("ACCEPTED");
~~~

Kiểu generic trả về trong ví dụ minh họa hợp đồng mong muốn; tùy API và phiên bản, lookup có thể trả wrapper hoặc kiểu hàm tổng quát và cần ép kiểu phù hợp trong test.

### 8.4. Kiểm thử MessageConverter

Hãy kiểm tra trường hợp message chứa JSON bytes và content type application/json được chuyển thành DTO:

~~~java
Message<byte[]> input = MessageBuilder
        .withPayload("""
                {"id":"p-1","name":"Lan"}
                """.getBytes(StandardCharsets.UTF_8))
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Sau đó gọi hàm có kiểu đầu vào Person qua FunctionCatalog và xác minh kết quả. Bổ sung test cho JSON sai cú pháp, content type không đúng và DTO thiếu trường bắt buộc. Nếu dùng converter tùy chỉnh, test trực tiếp converter trước khi kiểm thử toàn pipeline.

### 8.5. Integration test với test binder và broker thật

Test binder giúp xác minh binding, payload và header ở mức Spring Cloud Stream trong bộ nhớ. Nó không thay thế integration test cho mapping metadata riêng của Kafka, RabbitMQ hoặc Pulsar.

Với luồng quan trọng, kiểm thử:

- Header được nhận và chuyển đổi thế nào ở input binding.
- Header nào được giữ ở output binding.
- Content type và payload sau serialize/deserialize.
- Partition key hoặc routing key có đúng với dữ liệu.
- Message không hợp lệ bị xử lý theo chính sách lỗi.
- Correlation ID có thể được truy vết xuyên qua producer và consumer.

## 9. Quy trình thiết kế một pipeline an toàn về kiểu và header

Khi tạo pipeline mới, hãy đi theo trình tự:

1. Viết chữ ký Supplier, Function hoặc Consumer cho từng bước.
2. Ghi lại kiểu đầu vào và đầu ra của mỗi hàm.
3. Kiểm tra đầu ra bước trước có tương thích với đầu vào bước sau.
4. Ưu tiên DTO có kiểu cụ thể; chỉ dùng converter khi có lý do rõ ràng.
5. Xác định content type của payload ở mỗi ranh giới messaging.
6. Liệt kê header nào cần đọc, thêm, giữ, thay hoặc loại bỏ.
7. Chọn cách xử lý header: Message API, copy-input-headers hoặc enrichment function.
8. Kiểm tra tên function trong FunctionCatalog và function definition.
9. Nếu có routing, xác thực route và chỉ cho phép function đích đã định trước.
10. Kiểm thử payload, conversion, header, composition và binder trước khi triển khai.

## 10. Những lỗi thường gặp

1. **Ghép hai hàm có kiểu không khớp**: đầu ra của bước trước không thể dùng làm đầu vào của bước sau. Hãy điều chỉnh DTO hoặc đăng ký converter có chủ đích.
2. **Dùng raw Function hoặc Object quá rộng**: framework khó suy ra kiểu đích và hợp đồng không còn rõ. Hãy khai báo generic cụ thể.
3. **Cho rằng content type tự xác định kiểu Java**: content type chỉ hỗ trợ lựa chọn converter; kiểu đích vẫn đến từ chữ ký hàm hoặc metadata được phép. Hãy kiểm tra cả hai.
4. **Trả String nhưng nghĩ đó luôn là JSON**: chuỗi văn bản tự do không thể được giải mã thành DTO chỉ vì cấu hình application/json. Hãy bảo đảm payload đúng định dạng.
5. **Mặc định header input luôn được chuyển tiếp**: header thường không được propagate sang output. Hãy sao chép có chọn lọc hoặc cấu hình copy-input-headers.
6. **Sao chép toàn bộ header mà không kiểm tra**: metadata transport, header nội bộ hoặc thông tin nhạy cảm có thể lọt sang bước khác. Hãy xác định danh sách header cần giữ.
7. **Ghi dữ liệu nghiệp vụ vào header**: header có thể bị giới hạn kích thước hoặc ánh xạ khác nhau giữa broker. Hãy giữ dữ liệu nghiệp vụ trong payload.
8. **Định tuyến theo header không được xác thực**: message có thể chọn một hàm ngoài dự kiến. Hãy dùng allowlist và kiểm soát nguồn gửi.
9. **Dùng header để route từng phần tử trong reactive stream**: reactive function được gọi theo đơn vị stream, không theo từng Message. Hãy cấu hình route cho cả stream hoặc chuyển sang xử lý imperative phù hợp.
10. **Chỉ unit test từng hàm mà không test composition**: thứ tự, converter và header mapping có thể sai ở cấp pipeline. Hãy kiểm thử hàm tổng hợp qua FunctionCatalog.
11. **Chỉ test bằng test binder**: binder thật có thể ánh xạ header khác nhau. Hãy bổ sung integration test cho broker đang triển khai.

## Kết luận

Ghép hàm đáng tin cậy bắt đầu từ hợp đồng kiểu rõ ràng: đầu ra của bước trước phải phù hợp với đầu vào của bước sau. Spring Cloud Function hỗ trợ chuyển đổi thông qua MessageConverter hoặc ConversionService khi có đủ thông tin kiểu và định dạng; contentType là một phần của quyết định chuyển đổi chứ không thay thế kiểu đích.

Message chứa payload và header, nhưng header đầu vào không mặc nhiên được chuyển tiếp sang output. Hãy chủ động sao chép header cần thiết, dùng copy-input-headers khi muốn giữ header theo cấu hình, hoặc tách enrichment thành một hàm riêng. Với định tuyến, chỉ cho phép route hợp lệ và kiểm thử cả trường hợp không tìm thấy hàm đích.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
