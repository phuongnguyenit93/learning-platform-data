# transform trong DSL

## 1. Mục tiêu và phạm vi

Trong chương Java DSL của module `SPRING_INTEGRATION_CORE`, `transform` biểu diễn một endpoint chuyển đổi thông điệp. Bước này giúp nối các thành phần sử dụng kiểu dữ liệu hoặc cấu trúc khác nhau: chuỗi mã sản phẩm thành mã chuẩn, JSON thành đối tượng Java, hoặc DTO đầu vào thành mô hình mà hệ thống nội bộ hiểu được.

Sau bài học, bạn có thể:

- Chọn cách khai báo transformer bằng lambda, method reference, POJO hoặc transformer có sẵn.
- Phân biệt payload được đưa vào hàm với toàn bộ `Message<?>`.
- Viết phép biến đổi có hợp đồng kiểu dữ liệu, header và kết quả rõ ràng.
- Theo dõi thông điệp qua channel, nhận diện lỗi chuyển đổi và kiểm thử cả dữ liệu lẫn metadata.

Các ví dụ lấy **Java 17 và API Spring Integration 6.2** làm mốc. Java `record` được dùng để biểu diễn dữ liệu bất biến. Bài sử dụng `IntegrationFlow.from(...)`; những đoạn có `transformWith(...)` cần Spring Integration 6.2 trở lên. Đây là mốc API để đọc ví dụ, không phải khẳng định về phiên bản mới nhất.

## 2. transform nằm ở đâu trong luồng thông điệp?

Hãy xem một yêu cầu đặt hàng:

~~~text
Message<IncomingOrder>
  payload: mã đơn, mã khách, số lượng, đơn giá
  headers: traceId, tenantId, ...
          |
          v
      ordersIn
          |
          v
   transform: IncomingOrder -> Order
          |
          v
      ordersOut
          |
          v
Message<Order>
  payload: mã đã chuẩn hóa, số lượng, tổng tiền
  headers: metadata cần được truyền tiếp
~~~

Channel chuyển thông điệp tới endpoint. Transformer chịu trách nhiệm chuyển nội dung sang hợp đồng dữ liệu mà bước sau cần. Việc khai báo `IntegrationFlow` tạo cấu hình cho các thành phần Spring; phép chuyển đổi diễn ra khi thông điệp thực sự đi qua flow. [Tài liệu DSL Basics](https://docs.spring.io/spring-integration/reference/6.2/dsl/java-basics.html).

Ở mức khái niệm:

~~~text
transform:
  Message<S> -> Message<T>
~~~

Trong trường hợp chỉ làm việc với payload, phần mã ứng dụng thường có dạng:

~~~text
f: S -> T
~~~

Một lần chuyển đổi thành công thường sinh **một thông điệp kết quả**. `S` và `T` có thể là cùng một kiểu; chuẩn hóa một `String` vẫn là transformation. Nếu kết quả payload là `List<Order>` thì đó vẫn là một thông điệp chứa danh sách. Muốn phát từng phần tử thành thông điệp riêng, dùng splitter.

| Nhu cầu | Bước DSL phù hợp | Vai trò |
| --- | --- | --- |
| Chuyển DTO đối tác thành DTO nội bộ | `transform` | Đổi nội dung hoặc cấu trúc |
| Chỉ cho đơn hợp lệ đi tiếp | `filter` | Quyết định chấp nhận hay loại bỏ |
| Chọn kênh xử lý theo loại đơn | `route` | Quyết định nơi nhận |
| Gọi dịch vụ ghi đơn vào cơ sở dữ liệu | `handle` hoặc adapter phù hợp | Thực hiện thao tác dịch vụ |
| Tách một đơn thành nhiều dòng hàng | `split` | Tách thành nhiều thông điệp |
| Gom các kết quả thuộc cùng đơn | `aggregate` | Kết hợp nhiều thông điệp theo nhóm |

Bảng này áp dụng các vai trò endpoint vào bài toán đơn hàng. Có thể một phép gọi dịch vụ cũng trả về dữ liệu mới, nhưng tên bước nên thể hiện mục đích chính để flow dễ đọc. [Tổng quan các endpoint](https://docs.spring.io/spring-integration/reference/6.2/overview.html#message-endpoints).

## 3. Các cách khai báo transform

Các đoạn ở mục này là **những cách thay thế nhau** cho một bước trong flow. Không cần đăng ký tất cả chúng trên cùng channel.

### 3.1. Lambda với kiểu payload tường minh

~~~java
import java.util.Locale;
import org.springframework.integration.dsl.IntegrationFlow;

// Đặt trong phương thức cấu hình một IntegrationFlow:
return IntegrationFlow.from("codesIn")
        .transform(String.class,
                code -> code.strip().toUpperCase(Locale.ROOT))
        .channel("codesOut")
        .get();
~~~

Với payload `"  sku-01  "`, kết quả là `"SKU-01"`. Đầu vào của lambda là payload `String`, không phải `Message<String>`.

Đối số `String.class` mô tả **kiểu đầu vào của hàm**, không phải kiểu đầu ra. Khi cần, framework thử chuyển payload sang kiểu này bằng hạ tầng conversion. Việc chuyển kiểu chỉ thành công nếu có converter phù hợp; khai báo `IncomingOrder.class` không tự cung cấp quy tắc giải mã mọi chuỗi JSON.

Trong đoạn minh họa dùng tên channel, ứng dụng phải có consumer hoặc cơ chế nhận phù hợp ở `codesOut`. Ví dụ hoàn chỉnh ở mục 4 khai báo `QueueChannel` để có thể nhận kết quả trực tiếp.

### 3.2. Generic và method reference

~~~java
return IntegrationFlow.from("numericTextIn")
        .<String, Integer>transform(Integer::parseInt)
        .channel("numbersOut")
        .get();
~~~

Hai tham số kiểu `<String, Integer>` mô tả hợp đồng của `GenericTransformer<S, T>`:

- `S` là kiểu payload nguồn: `String`.
- `T` là kiểu kết quả: `Integer`.

Chúng giúp trình biên dịch kiểm tra hàm chuyển đổi. Tuy nhiên, toàn bộ chuỗi DSL không trở thành một pipeline được kiểm tra kiểu từ đầu đến cuối; thông điệp có kiểu không phù hợp vẫn có thể tới channel lúc chạy.

Bạn cũng có thể viết:

~~~java
.transform(String.class, Integer::parseInt)
~~~

Chọn dạng có `Class` khi muốn thể hiện kiểu đầu vào rõ ràng, đặc biệt tại ranh giới tiếp nhận dữ liệu. [Javadoc về expectedType](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html#transform(java.lang.Class,org.springframework.integration.core.GenericTransformer)) và [overload GenericTransformer](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/IntegrationFlowDefinition.html#transform(org.springframework.integration.core.GenericTransformer)) mô tả hai cách này.

### 3.3. Phương thức trên POJO

Khi quy tắc có nhiều bước hoặc cần tái sử dụng, đưa logic vào một lớp riêng:

~~~java
.transform(orderMapper, "normalize")
~~~

Trong đó `orderMapper` là một đối tượng được truyền vào phương thức cấu hình, và `normalize` là tên phương thức chuyển đổi. Nếu DSL đã chỉ rõ đối tượng và phương thức, phương thức POJO không cần thêm `@Transformer` để được gọi.

Một cách khác là dùng method reference:

~~~java
.transform(IncomingOrder.class, orderMapper::normalize)
~~~

Method reference cho phép trình biên dịch kiểm tra tên và chữ ký phương thức. Dạng tên phương thức thuận tiện khi cấu hình dựa trên POJO, nhưng lỗi đổi tên có thể chỉ xuất hiện lúc khởi tạo hoặc xử lý thông điệp.

Từ Spring Integration 6.2, có overload tham chiếu theo tên bean:

~~~java
.transform("orderMapper", "normalize")
~~~

Đối tượng phải tồn tại trong Spring context với tên `orderMapper`. Đừng nhầm với `.transform("orderMapper")`: overload chỉ nhận một chuỗi diễn giải chuỗi đó như biểu thức SpEL. [Javadoc các overload transform](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

### 3.4. Biểu thức SpEL

Với phép biến đổi ngắn:

~~~java
.transform("payload.strip()")
~~~

SpEL có thể truy cập payload và header:

~~~java
.transform("headers['tenantId'] + ':' + payload")
~~~

Biểu thức thứ hai giả định `tenantId` đã có trong header và payload là giá trị cần ghép. Nếu header là dữ liệu bắt buộc, hãy kiểm tra rõ khi tiếp nhận; không dùng kết quả ghép chuỗi để suy ra rằng header hợp lệ.

SpEL phù hợp với biểu thức nhỏ. Khi có nhánh xử lý, quy tắc tiền tệ hoặc nhiều trường cần ánh xạ, phương thức Java có tên rõ ràng giúp đọc và kiểm thử dễ hơn.

## 4. Ví dụ hoàn chỉnh: chuẩn hóa đơn hàng

Giả sử hệ thống đối tác gửi mã đơn và mã khách có khoảng trắng. Hệ thống nội bộ yêu cầu mã viết hoa, số lượng dương và tổng tiền được tính từ đơn giá.

Hợp đồng của ví dụ:

| Thành phần | Quy định |
| --- | --- |
| Đầu vào | `IncomingOrder` |
| Mã đơn và mã khách | Không rỗng, bỏ khoảng trắng ở hai đầu, viết hoa bằng `Locale.ROOT` |
| Số lượng | Lớn hơn 0 |
| Đơn giá | Không null, không âm |
| Đầu ra | `Order` chứa mã chuẩn hóa, số lượng và tổng tiền |
| Tổng tiền | `unitPrice × quantity`, chưa tính thuế, phí hoặc chiết khấu |
| Metadata | Giữ `traceId` và các header ứng dụng cần thiết |
| Dữ liệu không hợp lệ | Ném ngoại lệ; không tạo đơn mặc định |

Để chạy lớp bên dưới, project cần `org.springframework.integration:spring-integration-core` thuộc dòng 6.2 với các dependency Spring tương thích. Nếu dùng Spring Boot, có thể lấy dependency qua `spring-boot-starter-integration` và để dependency management của Boot quản lý phiên bản. Ví dụ dùng Spring context trực tiếp, không cần broker hay máy chủ bên ngoài.

Đặt lớp trong file `TransformDslDemo.java` của project thực hành:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class TransformDslDemo {

    public record IncomingOrder(
            String orderId,
            String customerCode,
            int quantity,
            BigDecimal unitPrice) {
    }

    public record Order(
            String orderId,
            String customerCode,
            int quantity,
            BigDecimal totalAmount) {
    }

    public static class OrderMapper {

        public Order normalize(IncomingOrder source) {
            if (source.orderId() == null || source.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            if (source.customerCode() == null
                    || source.customerCode().isBlank()) {
                throw new IllegalArgumentException(
                        "customerCode must not be blank");
            }
            if (source.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            if (source.unitPrice() == null
                    || source.unitPrice().signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be null or negative");
            }

            String orderId = source.orderId()
                    .strip()
                    .toUpperCase(Locale.ROOT);
            String customerCode = source.customerCode()
                    .strip()
                    .toUpperCase(Locale.ROOT);
            BigDecimal total = source.unitPrice()
                    .multiply(BigDecimal.valueOf(source.quantity()));

            return new Order(
                    orderId, customerCode, source.quantity(), total);
        }
    }

    @Configuration
    @EnableIntegration
    public static class Config {

        @Bean
        public DirectChannel ordersIn() {
            return new DirectChannel();
        }

        @Bean
        public QueueChannel ordersOut() {
            return new QueueChannel(10);
        }

        @Bean
        public OrderMapper orderMapper() {
            return new OrderMapper();
        }

        @Bean
        public IntegrationFlow orderFlow(
                DirectChannel ordersIn,
                QueueChannel ordersOut,
                OrderMapper orderMapper) {

            return IntegrationFlow.from(ordersIn)
                    .transform(IncomingOrder.class, orderMapper::normalize)
                    .channel(ordersOut)
                    .get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            DirectChannel input = context.getBean(
                    "ordersIn", DirectChannel.class);
            QueueChannel output = context.getBean(
                    "ordersOut", QueueChannel.class);

            var source = new IncomingOrder(
                    " od-1001 ",
                    " kh-01 ",
                    3,
                    new BigDecimal("125000"));

            Message<IncomingOrder> request = MessageBuilder
                    .withPayload(source)
                    .setHeader("traceId", "trace-1001")
                    .setHeader("tenantId", "tenant-a")
                    .build();

            if (!input.send(request)) {
                throw new IllegalStateException("Message was not accepted");
            }

            Message<?> reply = output.receive(1000);
            if (reply == null) {
                throw new IllegalStateException("No output message");
            }

            System.out.println(reply.getPayload());
            System.out.println(reply.getHeaders().get("traceId"));
        }
    }
}
~~~

Kết quả dữ liệu mong đợi, ngoài các dòng log của framework:

~~~text
Order[orderId=OD-1001, customerCode=KH-01, quantity=3, totalAmount=375000]
trace-1001
~~~

Điểm cần theo dõi:

1. `@EnableIntegration` đăng ký hạ tầng Spring Integration cho context Java thuần. [Tài liệu cấu hình hạ tầng](https://docs.spring.io/spring-integration/reference/6.2/overview.html#configuration-enable-integration).
2. `ordersIn` là `DirectChannel`. Transformer chạy trên thread đang gọi `send`.
3. `OrderMapper` chỉ nhận và trả dữ liệu miền; không biết channel hay message.
4. `.channel(ordersOut)` chỉ định nơi nhận kết quả.
5. `ordersOut` giữ thông điệp trong bộ nhớ để chương trình gọi `receive`. Việc dùng queue ở đầu ra không khiến bước transform phía trước tự chuyển sang thread khác.

`receive(1000)` có thời gian chờ tối đa 1.000 ms. Đây là thời gian đợi ở queue, không phải giới hạn thời gian chạy của mapper. Nếu mapper bị chặn, lệnh `send` trên thread hiện tại vẫn có thể bị chặn.

Queue đầu ra không cần poller khi mã ứng dụng chủ động gọi `receive`. Nếu tạo một endpoint tiếp theo có input là queue này, endpoint đó cần cấu hình polling phù hợp.

## 5. Payload, Message và header

### 5.1. Khi chỉ trả về payload

Trong flow trên, `normalize` trả `Order`. Framework xây message kết quả và sao chép header đầu vào theo cơ chế của transformer.

Cần phân biệt:

| Nhóm header | Cách hiểu trong ví dụ |
| --- | --- |
| `traceId`, `tenantId` | Metadata ứng dụng cần truyền tiếp |
| `replyChannel`, `errorChannel` | Metadata điều phối phản hồi và lỗi |
| `correlationId`, thông tin sequence | Có thể được splitter/aggregator hoặc thành phần khác sử dụng |
| `id`, `timestamp` | Metadata hệ thống của message; không dùng thay mã nghiệp vụ |

Khi tạo message mới, không giả định `id` và `timestamp` giữ nguyên. Dùng `traceId` hoặc mã đơn theo hợp đồng của ứng dụng để theo dõi nghiệp vụ qua nhiều bước.

Header `MessageHeaders` có cấu trúc chỉ đọc, nhưng đối tượng payload hoặc giá trị header vẫn có thể là đối tượng mutable. Bất biến của message không đồng nghĩa với sao chép sâu dữ liệu bên trong. Ví dụ dùng record và `BigDecimal` để giảm việc sửa dữ liệu dùng chung. [Message và MessageBuilder](https://docs.spring.io/spring-integration/reference/6.2/message.html).

### 5.2. Khi cần đọc toàn bộ Message

Giả sử phép biến đổi phải kiểm tra `tenantId` và thêm `schemaVersion`. Có thể thay bước transform trong `orderFlow` bằng:

~~~java
.transform(Message.class, message -> {
    String tenantId = message.getHeaders()
            .get("tenantId", String.class);
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("tenantId must not be blank");
    }

    Object payload = message.getPayload();
    if (!(payload instanceof IncomingOrder input)) {
        throw new IllegalArgumentException(
                "Expected IncomingOrder payload");
    }

    Order order = orderMapper.normalize(input);

    return MessageBuilder.withPayload(order)
            .copyHeaders(message.getHeaders())
            .setHeader("schemaVersion", "2")
            .build();
})
~~~

`Message.class` báo rõ rằng lambda cần nhận message thay vì chỉ nhận payload. Việc kiểm tra `instanceof` giữ hợp đồng payload dễ thấy, tránh ép kiểu thiếu kiểm soát.

Không thay thế bằng cách chỉ khai báo generic như sau:

~~~java
// Cách khai báo này không đảm bảo lambda nhận toàn bộ Message:
.<Message<?>, Order>transform(
        message -> orderMapper.normalize(
                (IncomingOrder) message.getPayload()))
~~~

Với lambda, thông tin generic không đủ để framework luôn phân biệt yêu cầu nhận message. Khi cần payload và headers cùng lúc, dùng overload có `Message.class`. [Lambdas và Message arguments](https://docs.spring.io/spring-integration/reference/6.2/dsl/java-basics.html).

### 5.3. Khi tự trả về Message

Kết quả `Message<Order>` trong ví dụ trên được dùng làm message đầu ra. Vì bạn tự xây message, hãy sao chép và sửa header có chủ đích.

Chẳng hạn:

~~~java
return MessageBuilder.withPayload(order)
        .copyHeaders(message.getHeaders())
        .setHeader("schemaVersion", "2")
        .build();
~~~

Ở đây, `schemaVersion` cũ bị ghi đè vì `setHeader` được gọi sau `copyHeaders`. Nếu đã thiết lập header mới trước, có thể dùng `copyHeadersIfAbsent` để chỉ bổ sung những header còn thiếu.

Nếu chỉ gọi `MessageBuilder.withPayload(order).build()`, message mới không chứa các header ứng dụng của message gốc. Không dựa vào việc endpoint tự bù lại chúng. Trong Spring Integration 6.2, transformer handler không sao chép lại request headers ở lớp handler. [Mã nguồn MessageTransformingHandler](https://github.com/spring-projects/spring-integration/blob/v6.2.11/spring-integration-core/src/main/java/org/springframework/integration/transformer/MessageTransformingHandler.java) và [AbstractTransformer](https://github.com/spring-projects/spring-integration/blob/v6.2.11/spring-integration-core/src/main/java/org/springframework/integration/transformer/AbstractTransformer.java).

Nếu mục tiêu chỉ là thêm hoặc loại header, các bước `enrichHeaders` và `headerFilter` thường diễn đạt ý định trực tiếp hơn một lambda tạo message mới.

## 6. Dùng transformer có sẵn

Spring Integration có factory `org.springframework.integration.dsl.Transformers` cho các phép chuyển đổi thường gặp. Có thể đặt trực tiếp đối tượng transformer trong `.transform(...)`. [Tài liệu Transformers trong DSL](https://docs.spring.io/spring-integration/reference/6.2/dsl/java-transformers.html).

| Factory | Mục đích |
| --- | --- |
| `Transformers.fromJson(IncomingOrder.class)` | Đọc JSON thành kiểu đối tượng đích |
| `Transformers.toJson()` | Chuyển đối tượng thành JSON |
| `Transformers.fromStream("UTF-8")` | Đọc payload `InputStream` thành chuỗi theo charset |

Ví dụ JSON sau dùng lại `IncomingOrder`, `Order` và `OrderMapper` ở mục 4. Để thử, thay phần thân phương thức `orderFlow` bằng đoạn dưới, thêm import `Transformers` và gửi payload JSON thay cho record:

~~~java
// import org.springframework.integration.dsl.Transformers;

return IntegrationFlow.from(ordersIn)
        .transform(Transformers.fromJson(IncomingOrder.class))
        .transform(IncomingOrder.class, orderMapper::normalize)
        .transform(Transformers.toJson())
        .channel(ordersOut)
        .get();
~~~

Chuỗi kiểu dữ liệu dự kiến:

~~~text
String JSON
    -> IncomingOrder
    -> Order
    -> String JSON
~~~

Payload đầu vào:

~~~json
{
  "orderId": " od-1001 ",
  "customerCode": " kh-01 ",
  "quantity": 3,
  "unitPrice": 125000
}
~~~

Payload đầu ra mong đợi, không phụ thuộc thứ tự thuộc tính:

~~~json
{
  "orderId": "OD-1001",
  "customerCode": "KH-01",
  "quantity": 3,
  "totalAmount": 375000
}
~~~

Với cấu hình mặc định trong dòng 6.2, ví dụ cần thư viện Jackson 2 phù hợp trên classpath, thường gồm `jackson-databind` cùng các dependency đi kèm. Các record ở ví dụ chỉ chứa chuỗi, số nguyên và `BigDecimal` nên không cần thêm module xử lý thời gian.

Ví dụ giả định bản tin đầu vào không có header thông tin kiểu Java làm thay đổi việc chọn kiểu giải mã. Khi làm việc với header kiểu do hệ thống khác gửi, cần xem cấu hình `JsonToObjectTransformer` vì các header này có thể được xét trước kiểu đích đã khai báo. [JSON Transformers](https://docs.spring.io/spring-integration/reference/6.2/transformer.html#json-transformers).

Tách ba bước giúp xác định lỗi rõ hơn: JSON sai cấu trúc thuộc bước giải mã; số lượng âm thuộc bước ánh xạ/kiểm tra; lỗi tạo JSON thuộc bước mã hóa.

Không thay bước giải mã JSON bằng `.transform(IncomingOrder.class, input -> input)` nếu chưa có converter JSON tương ứng. Đối số `Class` không thay thế một JSON transformer.

## 7. Cấu hình endpoint với transformWith

Khi chỉ cần phép biến đổi, `.transform(IncomingOrder.class, orderMapper::normalize)` đủ rõ. Khi cần thêm tên endpoint hoặc tùy chọn vòng đời, Spring Integration 6.2 cung cấp `transformWith` để gom cấu hình vào một builder.

Thay bước transform của ví dụ bằng:

~~~java
.transformWith(spec -> spec
        .ref(orderMapper)
        .method("normalize")
        .id("normalizeOrderEndpoint"))
~~~

`ref` chỉ đối tượng xử lý, `method` chỉ phương thức cần gọi, còn `id` đặt tên endpoint để hỗ trợ theo dõi và điều khiển. Phép biến đổi dữ liệu vẫn là phương thức `normalize`.

Nhiều overload `transform` cũ nhận thêm `endpointConfigurer` đã được đánh dấu deprecated từ 6.2 để chuyển sang cách cấu hình này. Vì vậy, hãy phân biệt dạng `transform` đơn giản còn dùng trong bài với overload có cấu hình endpoint của phiên bản cũ. [Javadoc TransformerEndpointSpec](https://docs.spring.io/spring-integration/docs/6.2.11/api/org/springframework/integration/dsl/TransformerEndpointSpec.html).

## 8. Kết quả đi đâu và khi nào cần gateway?

Trong ví dụ chính, `.channel(ordersOut)` chỉ định đích đến của kết quả. Producer gửi vào `ordersIn` rồi chủ động đọc `ordersOut`. Đây là lựa chọn thuận tiện cho minh họa và kiểm thử dữ liệu đầu ra.

Nếu muốn mã ứng dụng gọi một phương thức như `Order normalize(IncomingOrder input)`, có thể dùng messaging gateway:

~~~text
Mã ứng dụng
    -> gateway
    -> channel yêu cầu
    -> transform
    -> replyChannel của yêu cầu
    -> gateway trả Order
~~~

Ở flow dành cho gateway, transformer cuối có thể không khai báo output channel cố định để kết quả được gửi về `replyChannel`. Gateway thiết lập cơ chế chờ phản hồi theo cấu hình của nó.

Không dùng nguyên flow có output `ordersOut` rồi mặc định rằng gateway sẽ nhận được kết quả. Khi đích output được chỉ định, phản hồi đi tới đích đó; một queue đầu ra bất kỳ không tự chuyển thành reply của lời gọi gateway.

Tương tự, nếu không có output channel phù hợp và cũng không có địa chỉ phản hồi, việc tạo được payload mới chưa đủ để gửi thành công message kết quả. Tài liệu mô tả vai trò `replyChannel` trong [các header của Message](https://docs.spring.io/spring-integration/reference/6.2/message.html).

## 9. null và lỗi chuyển đổi

### 9.1. Transformer phải có kết quả hợp lệ

Không dùng `null` để biểu diễn “bỏ qua đơn”:

~~~java
// Sai mục đích: muốn loại thông điệp bằng cách trả null.
.transform(IncomingOrder.class, input ->
        input.quantity() > 0 ? orderMapper.normalize(input) : null)
~~~

Theo hợp đồng transformer, trả `null` là lỗi. Nếu nghiệp vụ cho phép loại dữ liệu, hãy biểu diễn quyết định bằng `filter` và thiết kế rõ hành vi đối với thông điệp bị loại. [Hợp đồng kết quả của transformer](https://docs.spring.io/spring-integration/reference/6.2/transformer.html).

Ví dụ minh họa một flow một chiều chỉ cho số lượng dương đi tiếp:

~~~java
.filter(IncomingOrder.class, input -> input.quantity() > 0)
.transform(IncomingOrder.class, orderMapper::normalize)
~~~

Bộ lọc trên chưa kiểm tra mọi điều kiện của đơn. Mapper vẫn kiểm tra mã và đơn giá. Với request/reply, nếu filter loại thông điệp mà không tạo phản hồi thay thế, bên gọi có thể chờ đến timeout; cần chọn chính sách từ chối phù hợp.

Một danh sách rỗng, chuỗi rỗng hoặc đối tượng mặc định vẫn là payload hợp lệ về mặt kỹ thuật. Chúng không đồng nghĩa với việc bỏ thông điệp. Chỉ dùng nếu đó là kết quả được hợp đồng nghiệp vụ chấp nhận.

### 9.2. Lỗi trong ví dụ đồng bộ

Trong cấu hình `DirectChannel` của mục 4:

~~~text
input.send(request)
    -> normalize(...)
    -> IllegalArgumentException
    -> ngoại lệ messaging truyền về nơi gọi send
~~~

Framework thường bọc lỗi xử lý trong ngoại lệ messaging, trong đó có `MessageTransformationException`. Khi chẩn đoán, xem nguyên nhân gốc và message thất bại thay vì chỉ đọc lớp ngoại lệ ngoài cùng.

Việc message có header `errorChannel` không khiến mọi lỗi đồng bộ tự chuyển sang kênh đó. Đối với flow trực tiếp chạy trên thread người gửi như ví dụ này, lỗi truyền về lời gọi `send`. Với poller hoặc xử lý qua executor, cơ chế công bố `ErrorMessage` phụ thuộc hạ tầng và cấu hình xử lý lỗi. Gateway cũng có cấu hình xử lý lỗi riêng. [Tài liệu Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

| Loại lỗi | Ví dụ | Hướng xử lý trong thiết kế |
| --- | --- | --- |
| Sai định dạng | JSON không đọc được | Ghi nhận lỗi đầu vào, trả hoặc định tuyến thông báo từ chối |
| Vi phạm hợp đồng | `quantity <= 0` | Từ chối rõ ràng, giữ thông tin giúp sửa dữ liệu |
| Sai kiểu payload | Đưa `String` vào bước nhận `IncomingOrder` mà không có chuyển đổi phù hợp | Sửa thứ tự endpoint hoặc hợp đồng channel |
| Thiếu đường đi kết quả | Không có output hay reply address | Sửa cấu hình flow |
| Lỗi phụ thuộc bên ngoài | Dịch vụ tra cứu hết thời gian chờ | Đặt thao tác ở bước dịch vụ thích hợp, thiết kế timeout và retry riêng |

Retry một chuỗi JSON sai hoặc số lượng âm không làm dữ liệu tự hợp lệ. Giữ transformer thuần giúp phân biệt lỗi dữ liệu với lỗi tạm thời của hệ thống phụ thuộc.

## 10. Kiểm thử payload, header và nhánh lỗi

Có hai lớp kiểm thử bổ sung cho nhau:

- Gọi trực tiếp `OrderMapper.normalize` để kiểm tra quy tắc dữ liệu.
- Gửi message qua flow thật để kiểm tra kết nối channel, chuyển đổi và truyền metadata.

Các đoạn dưới là mã kiểm thử mẫu để chạy trong project thực hành. Chúng chưa phải báo cáo rằng ví dụ đã được thực thi trong môi trường của bạn.

### 10.1. Kiểm thử mapper không cần Spring

Đặt lớp kiểm thử cùng package `example.integration`. Project cần JUnit Jupiter:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderMapperTest {

    private final TransformDslDemo.OrderMapper mapper =
            new TransformDslDemo.OrderMapper();

    @Test
    void normalizesCodesAndComputesTotal() {
        var input = new TransformDslDemo.IncomingOrder(
                " od-1001 ", " kh-01 ", 3,
                new BigDecimal("125000"));

        var result = mapper.normalize(input);

        assertEquals("OD-1001", result.orderId());
        assertEquals("KH-01", result.customerCode());
        assertEquals(3, result.quantity());
        assertEquals(0, new BigDecimal("375000")
                .compareTo(result.totalAmount()));

        // Phép ánh xạ không sửa dữ liệu đầu vào.
        assertEquals(" od-1001 ", input.orderId());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        var input = new TransformDslDemo.IncomingOrder(
                "OD-1001", "KH-01", 0,
                new BigDecimal("125000"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.normalize(input));
    }
}
~~~

`BigDecimal.compareTo` kiểm tra giá trị số mà không buộc scale giống nhau. Nếu scale là một phần hợp đồng dữ liệu, thêm assertion riêng cho scale thay vì bỏ qua yêu cầu đó.

### 10.2. Kiểm thử flow trong Spring context

Đoạn này dùng cấu hình gốc ở mục 4, chưa thay bằng biến thể JSON hoặc biến thể yêu cầu `tenantId`. Project cần thêm `spring-test` cùng dòng Spring Framework đang dùng và JUnit Jupiter, hoặc starter test tương ứng của Spring Boot:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(TransformDslDemo.Config.class)
class OrderFlowTest {

    @Autowired
    @Qualifier("ordersIn")
    private DirectChannel input;

    @Autowired
    @Qualifier("ordersOut")
    private QueueChannel output;

    @Test
    void transformsPayloadAndPreservesTraceHeader() {
        var order = new TransformDslDemo.IncomingOrder(
                " od-1001 ", " kh-01 ", 3,
                new BigDecimal("125000"));

        Message<?> request = MessageBuilder.withPayload(order)
                .setHeader("traceId", "trace-test-01")
                .setHeader("tenantId", "tenant-a")
                .build();

        assertTrue(input.send(request));

        Message<?> response = output.receive(1000);
        assertNotNull(response);

        var payload = assertInstanceOf(
                TransformDslDemo.Order.class, response.getPayload());

        assertEquals("OD-1001", payload.orderId());
        assertEquals("KH-01", payload.customerCode());
        assertEquals(0, new BigDecimal("375000")
                .compareTo(payload.totalAmount()));
        assertEquals("trace-test-01",
                response.getHeaders().get("traceId"));
        assertEquals("tenant-a",
                response.getHeaders().get("tenantId"));

        // Một message đầu vào sinh một message đầu ra trong flow này.
        assertNull(output.receive(0));
    }

    @Test
    void propagatesInvalidInputFailureWithoutProducingAnOrder() {
        var invalid = new TransformDslDemo.IncomingOrder(
                "OD-1001", "KH-01", 0,
                new BigDecimal("125000"));

        Message<?> request = MessageBuilder.withPayload(invalid).build();

        MessagingException failure = assertThrows(
                MessagingException.class, () -> input.send(request));

        assertInstanceOf(IllegalArgumentException.class, rootCause(failure));
        assertNull(output.receive(0));
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

Các test này dùng chung queue từ Spring context, nên chạy tuần tự như cấu hình mặc định của JUnit Jupiter và đọc hết kết quả của từng test. Nếu bật chạy song song, cần cô lập context hoặc channel để một test không lấy message của test khác.

Khi mở rộng, ưu tiên các kiểm tra có ý nghĩa đối với hợp đồng:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Mã chỉ chứa khoảng trắng | Bị từ chối |
| Đơn giá âm hoặc null | Không sinh `Order` |
| Số tiền có phần thập phân | Giá trị và quy tắc scale/rounding đúng yêu cầu |
| Transformer trả message mới | Header bắt buộc còn nguyên, header chủ động đổi có giá trị mới |
| Đầu vào JSON | Đúng kiểu đích; JSON lỗi được xử lý đúng |
| Payload là danh sách | Số lượng message đúng với lựa chọn transform hay split |

## 11. Giữ phép biến đổi dễ vận hành

### 11.1. Hạn chế trạng thái dùng chung

`OrderMapper` trong ví dụ là bean singleton nhưng không chứa trạng thái thay đổi theo message. Các biến như `orderId` và `total` nằm trong phương thức.

Tránh lưu đơn đang xử lý vào field như `currentOrder`. Khi nhiều producer hoặc nhiều thread gọi endpoint, trạng thái đó có thể bị ghi đè. Một `DirectChannel` chỉ giữ việc gọi đồng bộ với từng người gửi; nó không đảm bảo mọi người gửi trong ứng dụng chỉ có một thread.

### 11.2. Tạo kết quả mới thay vì sửa payload gốc

Nếu payload là `Map` hoặc POJO mutable, một consumer khác có thể đang giữ tham chiếu tới cùng đối tượng. Việc gọi setter trong transformer có thể ảnh hưởng ngoài phạm vi bước đang đọc.

Ưu tiên ánh xạ sang đối tượng kết quả mới. Khi payload có danh sách hoặc đối tượng con mutable, cần xác định rõ phần nào được sao chép; tạo record bao ngoài không tự làm mọi đối tượng con bất biến.

### 11.3. Tách thao tác I/O khỏi ánh xạ khi có thể

Tính `quantity × unitPrice` là phép chuyển dữ liệu cục bộ. Gọi HTTP để tra giá làm bước xử lý phụ thuộc độ trễ, timeout và lỗi mạng.

Nếu cần tra cứu, biểu diễn thành bước dịch vụ hoặc enrichment có tên rõ, rồi dùng transformer để tạo hợp đồng đầu ra. Cách này giúp đặt giới hạn thời gian, retry và kiểm thử đúng tại nơi có phụ thuộc.

### 11.4. Chia bước theo ranh giới dữ liệu

Flow JSON ở mục 6 có ba ranh giới dễ quan sát:

~~~text
Giải mã -> Ánh xạ/chuẩn hóa -> Mã hóa
~~~

Một lambda dài đồng thời đọc JSON, tra cứu dịch vụ, sửa header và tạo phản hồi khiến lỗi khó gắn với bước cụ thể. Có thể bắt đầu từ mapper nhỏ, tách thêm bước khi mỗi phần có hợp đồng riêng cần quan sát.

Khi ghi log, những thông tin thường hữu ích là tên bước, kiểu payload, mã đơn và `traceId`. Không cần log toàn bộ nội dung đơn để chứng minh rằng kiểu payload đã thay đổi.

## 12. Lỗi thường gặp khi dùng transform

| Biểu hiện | Nguyên nhân cần kiểm tra | Cách sửa |
| --- | --- | --- |
| `ClassCastException` khi gọi `getPayload` | Lambda tưởng nhận message nhưng thực tế nhận payload | Dùng `transform(Message.class, ...)` |
| Không chuyển được chuỗi JSON sang DTO | Chỉ khai báo kiểu đầu vào, chưa có bước giải mã | Thêm JSON transformer hoặc converter được cấu hình rõ |
| Header theo dõi biến mất | Tự tạo message mới nhưng không sao chép metadata cần thiết | Dùng `copyHeaders` hoặc xây bộ header theo hợp đồng |
| Không có kết quả sau khi trả `null` | Dùng transformer để loại thông điệp | Chuyển quyết định sang filter và xử lý nhánh bị loại |
| Kết quả đi vào queue nhưng gateway hết hạn chờ | Output cố định không đi về reply channel của gateway | Thiết kế đường phản hồi cho flow request/reply |
| Thêm queue đầu ra mà mapper vẫn chặn bên gửi | Transformer vẫn ở trước ranh giới bất đồng bộ | Xem lại vị trí channel và mô hình thực thi |
| Chạy được nhưng dữ liệu sai ở consumer khác | Transformer sửa đối tượng mutable dùng chung | Tạo payload kết quả mới và xét sao chép đối tượng con |
| Sửa tên phương thức nhưng flow lỗi lúc chạy | Gọi POJO bằng tên phương thức dạng chuỗi | Dùng method reference hoặc kiểm thử cấu hình |

## 13. Thực hành mở rộng

1. Thêm trường `currency` vào hợp đồng đầu vào và đầu ra. Quy định các giá trị chấp nhận được, chuẩn hóa bằng mapper và kiểm thử trường hợp không hợp lệ.
2. Dùng biến thể nhận `Message.class` để yêu cầu `tenantId` và thêm `schemaVersion`. Kiểm tra riêng việc giữ `traceId`, giữ `tenantId` và ghi đè phiên bản schema.
3. Thay đầu vào record bằng JSON theo mục 6. Kiểm tra cùng một quy tắc chuẩn hóa ở cả lớp mapper và lớp flow để tách lỗi dữ liệu khỏi lỗi kết nối endpoint.
4. Chuyển nhu cầu “loại đơn có số lượng bằng 0” thành filter trước transformer. Thiết kế rõ đích nhận thông điệp bị loại; nếu gọi qua gateway, bổ sung hành vi phản hồi thay vì để người gọi chờ hết thời gian.

Kết quả thực hành cần thể hiện được hợp đồng đầu vào, đầu ra, metadata cần giữ và đường đi của lỗi. Bốn yếu tố này giúp một bước `transform` nhỏ vẫn kết nối đúng với channel, gateway, router hoặc aggregator ở các phần còn lại của hệ thống.
