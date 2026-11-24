# Kiểm soát đích được phép và biểu thức định tuyến từ dữ liệu bên ngoài

Trong một hệ thống hướng sự kiện, một message có thể cần được chuyển đến hàm xử lý hoặc destination khác nhau tùy loại sự kiện, tenant hay miền nghiệp vụ. Spring Cloud Stream hỗ trợ định tuyến qua mô hình hàm và các cơ chế gửi đến destination động. Tuy nhiên, dữ liệu đến từ request, file hoặc hệ thống bên ngoài phải được xem là dữ liệu chưa đáng tin cậy. Nếu dùng trực tiếp giá trị đó làm tên hàm, biểu thức SpEL hoặc tên destination, ứng dụng có thể gọi nhầm chức năng, gửi message đến tài nguyên ngoài dự kiến hoặc tạo ra quá nhiều tài nguyên trên broker.

Thiết kế định tuyến an toàn cần tách ba quyết định: **chọn hàm xử lý**, **chọn destination**, và **xác định người gửi có quyền chọn đích đó hay không**. Biểu thức định tuyến nên được cấu hình và kiểm soát bởi ứng dụng; dữ liệu bên ngoài chỉ cung cấp những thuộc tính nghiệp vụ đã được kiểm tra để chọn trong một tập lựa chọn cho phép.

Bài thuộc chương **Ghép hàm và định tuyến** của module `SPRING_CLOUD_STREAM`. Nội dung tập trung vào function routing, destination routing, allowlist, biểu thức định tuyến, kiểm tra quyền, xử lý đầu vào không hợp lệ và kiểm thử trên các binder Kafka, RabbitMQ hoặc Pulsar.

## 1. Phân biệt định tuyến hàm và định tuyến destination

Hai loại định tuyến thường được nhắc cùng nhau nhưng giải quyết hai câu hỏi khác nhau:

- **Định tuyến hàm (function routing):** chọn bean `Function` hoặc `Consumer` nào sẽ xử lý message.
- **Định tuyến destination (destination routing):** chọn topic, exchange hoặc destination nào sẽ nhận message đầu ra.

Ví dụ, một message có `eventType = OrderPlaced` có thể được đưa đến hàm `orderHandler`. Sau khi xử lý, kết quả có thể được gửi đến destination `orders.accepted`. Nếu message là `PaymentAuthorized`, ứng dụng có thể chọn `paymentHandler` và gửi kết quả đến `payments.confirmed`.

```text
Message từ nguồn bên ngoài
          |
          v
  Kiểm tra cấu trúc và quyền
          |
          v
  Chọn hàm trong allowlist
          |
          v
  Function / Consumer
          |
          v
  Chọn destination được phép
          |
          v
  Binder -> Kafka / RabbitMQ / Pulsar
```

| Quyết định | Giá trị ví dụ | Cơ chế thường dùng |
|---|---|---|
| Chọn hàm | `orderHandler` | Function routing và `spring.cloud.function.routing-expression` |
| Chọn destination | `orders.accepted` | Binding đầu ra đã cấu hình, `StreamBridge` hoặc header định tuyến output được hỗ trợ |
| Cho phép lựa chọn | `OrderPlaced` chỉ được gửi tới handler tương ứng | Allowlist, enum, map cố định và kiểm tra quyền nghiệp vụ |

Không dùng tên destination thay cho tên hàm, cũng không dùng tên hàm như một cơ chế phân quyền. Việc một hàm tồn tại trong application context không có nghĩa mọi client đều được phép yêu cầu gọi hàm đó.

## 2. Vì sao dữ liệu định tuyến từ bên ngoài cần được kiểm soát?

Giả sử một API nhận JSON:

```json
{
  "tenantId": "tenant-a",
  "eventType": "OrderPlaced",
  "target": "orders.tenant-a",
  "orderId": "ORD-42"
}
```

Các trường `tenantId`, `eventType` và `target` đều đến từ nguồn bên ngoài. Nếu ứng dụng gọi thẳng:

```java
streamBridge.send(request.target(), event);
```

thì client có thể thay `target` bằng tên destination khác. Nếu dùng trực tiếp `eventType` làm tên hàm, client có thể yêu cầu gọi một bean ngoài ý định. Nếu cho phép client gửi cả chuỗi SpEL rồi đánh giá chuỗi đó, rủi ro còn lớn hơn vì dữ liệu có thể trở thành biểu thức được thực thi.

Các rủi ro chính:

- **Gửi sai luồng:** message chứa dữ liệu của tenant A nhưng được chuyển sang destination của tenant B.
- **Mở rộng quyền ngoài ý muốn:** client chọn một handler có quyền truy cập dữ liệu hoặc thao tác nhạy cảm.
- **Tạo tài nguyên tràn lan:** mỗi giá trị ngẫu nhiên tạo một topic, exchange, queue hoặc binding mới.
- **Rò rỉ dữ liệu:** message được gửi tới một destination mà người nhận không được phép xem dữ liệu.
- **Khó vận hành:** số lượng binding động, destination và metric tăng không giới hạn.
- **Rủi ro biểu thức:** biểu thức định tuyến được cung cấp từ bên ngoài có thể truy cập những thuộc tính hoặc bean ngoài phạm vi dự kiến.

Nguyên tắc thiết kế là chỉ cho dữ liệu ngoài ảnh hưởng đến một lựa chọn đã được định nghĩa trước. Ứng dụng phải tự quyết định lựa chọn nào hợp lệ và kiểm tra quyền trước khi gửi.

## 3. Định tuyến hàm bằng `RoutingFunction`

Spring Cloud Function cung cấp cơ chế routing để chọn function theo message. Trong ứng dụng Spring Cloud Stream, có thể kích hoạt router function bằng định nghĩa `functionRouter` và cấu hình biểu thức định tuyến. Biểu thức thường đọc payload hoặc message headers và trả về tên function bean đã đăng ký.

Ví dụ cấu hình chọn handler theo `eventType`:

```yaml
spring:
  cloud:
    function:
      definition: functionRouter
      routing-expression: "payload.eventType == 'OrderPlaced' ? 'orderHandler' : payload.eventType == 'PaymentAuthorized' ? 'paymentHandler' : 'unsupportedEventHandler'"
    stream:
      bindings:
        functionRouter-in-0:
          destination: integration.events
          group: event-router
          content-type: application/json
```

Biểu thức trên chỉ chọn một trong ba tên hàm được viết cố định trong cấu hình. Giá trị `eventType` là dữ liệu đầu vào; nó không được dùng làm một chuỗi biểu thức. Nhờ vậy, client không thể tự thêm cú pháp SpEL để thay đổi logic định tuyến.

Các handler cần được khai báo thành bean với chữ ký tương thích với message mà router chuyển đến:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, String tenantId) {}

record PaymentAuthorized(String paymentId, String orderId) {}

@Configuration
class EventHandlers {

    @Bean
    Consumer<OrderPlaced> orderHandler() {
        return event -> {
            // Xử lý sự kiện đơn hàng đã tạo.
        };
    }

    @Bean
    Consumer<PaymentAuthorized> paymentHandler() {
        return event -> {
            // Xử lý sự kiện thanh toán đã được xác nhận.
        };
    }

    @Bean
    Consumer<Object> unsupportedEventHandler() {
        return event -> {
            // Ghi nhận hoặc cách ly loại sự kiện không được hỗ trợ.
        };
    }
}
```

Đây là ví dụ về cấu trúc handler; khi triển khai cần xác nhận cách binder và phiên bản framework chuyển đổi payload theo kiểu đích của function được chọn. Nếu các handler có kiểu payload khác nhau, content type, schema và cơ chế conversion phải được kiểm thử cùng router. Không giả định mọi payload đều có thể deserialize thành mọi kiểu Java.

### Biểu thức định tuyến phải là cấu hình tin cậy

`spring.cloud.function.routing-expression` là biểu thức do ứng dụng cấu hình. Không nhận nguyên chuỗi biểu thức từ HTTP request, message payload hoặc một trường header bên ngoài rồi đưa chuỗi đó vào bộ đánh giá SpEL. Hãy để dữ liệu bên ngoài cung cấp giá trị như `eventType`, sau đó dùng biểu thức tĩnh để ánh xạ giá trị đó đến một function trong allowlist.

Nếu logic định tuyến phức tạp, cần kiểm tra quyền theo tenant hoặc cần tra cứu cấu hình động từ database, một router viết bằng Java thường dễ kiểm thử và kiểm soát hơn biểu thức SpEL dài.

## 4. Không dùng tên hàm tùy ý từ payload

Một cách triển khai nguy hiểm là lấy trường `handler` từ JSON và dùng nguyên giá trị đó làm tên function. Thay vào đó, ánh xạ giá trị nghiệp vụ đã được chấp nhận sang tên bean nội bộ:

```java
import java.util.Map;

final class HandlerRegistry {

    private static final Map<String, String> ALLOWED_HANDLERS = Map.of(
        "ORDER_PLACED", "orderHandler",
        "PAYMENT_AUTHORIZED", "paymentHandler"
    );

    String resolve(String eventType) {
        String handler = ALLOWED_HANDLERS.get(eventType);
        if (handler == null) {
            throw new IllegalArgumentException("Unsupported event type");
        }
        return handler;
    }
}
```

`eventType` là một mã nghiệp vụ, không phải tên bean tùy ý. Registry giới hạn những handler có thể được chọn. Trong ứng dụng thật, registry có thể được xây dựng từ cấu hình được quản trị và kiểm tra lúc khởi động; không cho một client chưa được xác thực tự thêm handler mới.

Nếu hệ thống cần cho phép một tenant chỉ phát một số loại sự kiện, kiểm tra quyền trước khi trả về handler:

```java
String resolveHandler(AuthenticatedTenant tenant, String eventType) {
    if (!tenant.allowedEventTypes().contains(eventType)) {
        throw new AccessDeniedException("Event type is not permitted");
    }
    return handlerRegistry.resolve(eventType);
}
```

Kiểm tra quyền phải dựa trên danh tính đã xác thực và chính sách phía server. Không tin `tenantId` trong payload là bằng chứng người gửi thuộc tenant đó.

## 5. Định tuyến destination bằng allowlist

Sau khi chọn handler, ứng dụng có thể cần gửi kết quả đến destination khác nhau. Với destination ổn định, cách rõ ràng nhất là cấu hình sẵn các output binding và chọn một binding trong code.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      output-bindings: orderOutput;paymentOutput
      bindings:
        orderOutput:
          destination: orders.accepted
          content-type: application/json
        paymentOutput:
          destination: payments.confirmed
          content-type: application/json
```

Service chọn binding đã cấu hình:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class EventPublisher {

    private static final Map<String, String> OUTPUT_BINDINGS = Map.of(
        "ORDER_ACCEPTED", "orderOutput",
        "PAYMENT_CONFIRMED", "paymentOutput"
    );

    private final StreamBridge streamBridge;

    EventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(String resultType, Object event) {
        String binding = OUTPUT_BINDINGS.get(resultType);
        if (binding == null) {
            throw new IllegalArgumentException("Unsupported result type");
        }
        if (!streamBridge.send(binding, event)) {
            throw new IllegalStateException("Output binding did not accept message");
        }
    }
}
```

Code chỉ chọn một trong các binding đã khai báo. Mỗi binding có destination và content type riêng. Cách này phù hợp với các luồng quan trọng cần provisioning, quyền và cấu hình producer rõ ràng.

## 6. Destination động nhưng vẫn giới hạn

Khi số destination được chọn ở runtime, `StreamBridge` có thể tạo output binding động. Cấu hình `spring.cloud.stream.dynamicDestinations` giới hạn danh sách destination mà cơ chế dynamic destination được phép sử dụng.

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - tenant-a.events
        - tenant-b.events
        - tenant-c.events
```

Không nên truyền tên đích do người dùng nhập trực tiếp vào `send`. Hãy ánh xạ tenant hoặc miền nghiệp vụ đã được xác thực sang destination được quản trị:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record TenantEvent(String tenantId, String eventType, String body) {}

@Service
class TenantRouter {

    private static final Map<String, String> DESTINATIONS = Map.of(
        "tenant-a", "tenant-a.events",
        "tenant-b", "tenant-b.events",
        "tenant-c", "tenant-c.events"
    );

    private final StreamBridge streamBridge;
    private final TenantAuthorization authorization;

    TenantRouter(StreamBridge streamBridge, TenantAuthorization authorization) {
        this.streamBridge = streamBridge;
        this.authorization = authorization;
    }

    public void publish(
            AuthenticatedTenant caller,
            String requestedTenant,
            TenantEvent event) {

        authorization.requireCanPublishTo(caller, requestedTenant);

        String destination = DESTINATIONS.get(requestedTenant);
        if (destination == null) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        if (!streamBridge.send(destination, event)) {
            throw new IllegalStateException("Could not send tenant event");
        }
    }
}
```

`AuthenticatedTenant` và `TenantAuthorization` đại diện cho thành phần xác thực/ủy quyền của ứng dụng. Ví dụ cho thấy thứ tự cần giữ: xác thực người gọi, kiểm tra quyền với tenant đích, ánh xạ sang tên destination nội bộ, rồi mới gửi. `dynamic-destinations` là lớp giới hạn cấu hình bổ sung; nó không thay thế authorization nghiệp vụ.

Nếu destination có thể liệt kê trước, hãy ưu tiên output binding có sẵn. Dynamic destination phù hợp khi số đích thực sự thay đổi trong runtime nhưng vẫn có thể giới hạn bằng chính sách và quy trình provisioning.

## 7. Định tuyến output bằng message header

Một function có thể trả về `Message<?>` với metadata chỉ định destination đầu ra. Spring Cloud Stream hỗ trợ header định tuyến output `spring.cloud.stream.sendto.destination` trong các luồng function phù hợp. Header này cho phép chọn đích khi xử lý message, nhưng giá trị của nó vẫn phải được kiểm soát như mọi destination động khác.

Ví dụ function chọn một destination trong tập cho phép:

```java
import java.util.Map;
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

record IncomingEvent(String eventType, String tenantId, String body) {}

@Component
class EventDestinationRouter
        implements Function<Message<IncomingEvent>, Message<IncomingEvent>> {

    private static final Map<String, String> ALLOWED = Map.of(
        "ORDER_PLACED", "orders.events",
        "PAYMENT_AUTHORIZED", "payments.events"
    );

    @Override
    public Message<IncomingEvent> apply(Message<IncomingEvent> message) {
        String eventType = message.getPayload().eventType();
        String destination = ALLOWED.get(eventType);

        if (destination == null) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        return MessageBuilder.fromMessage(message)
            .setHeader("spring.cloud.stream.sendto.destination", destination)
            .build();
    }
}
```

Header định tuyến được tạo bởi code tin cậy sau khi tra cứu allowlist. Không sao chép trực tiếp một header cùng tên từ message bên ngoài, vì người gửi có thể tự đặt giá trị destination. Hãy loại bỏ hoặc ghi đè header định tuyến đến từ nguồn không đáng tin cậy trước khi function tạo header nội bộ.

Cấu hình binding đầu vào và giới hạn các output destination có thể dùng:

```yaml
spring:
  cloud:
    function:
      definition: eventDestinationRouter
    stream:
      dynamic-destinations:
        - orders.events
        - payments.events
      bindings:
        eventDestinationRouter-in-0:
          destination: integration.events
          group: destination-router
          content-type: application/json
```

Header định tuyến output và dynamic destination vẫn phụ thuộc khả năng của phiên bản Spring Cloud Stream, binder và cấu hình binding. Hãy kiểm thử với binder thực tế, nhất là khi dùng nhiều binder hoặc destination có yêu cầu partition/routing key riêng.

## 8. Biểu thức SpEL: đọc dữ liệu, không thực thi dữ liệu

Biểu thức định tuyến có thể đọc các trường của payload hoặc headers để đưa ra quyết định. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: functionRouter
      routing-expression: "payload.eventType == 'OrderPlaced' ? 'orderHandler' : 'unsupportedEventHandler'"
```

Biểu thức là cấu hình tĩnh. Message chỉ cung cấp giá trị `eventType`. Khi message mang `OrderPlaced`, router chọn `orderHandler`; các giá trị khác đi đến handler mặc định. Đây là cách dùng dữ liệu ngoài để chọn một nhánh đã được lập trình.

Không cấu hình theo kiểu:

```yaml
# Không làm theo cách này: biểu thức được đưa vào từ nguồn không tin cậy.
spring:
  cloud:
    function:
      routing-expression: "#{${request.expression}}"
```

Không nhận expression từ request, header hoặc payload để đánh giá động. SpEL là ngôn ngữ biểu thức có khả năng truy cập thuộc tính và đối tượng theo context; đưa nội dung do client điều khiển vào bộ đánh giá có thể tạo đường thực thi ngoài dự kiến.

Nếu quy tắc thay đổi thường xuyên, lưu một bảng cấu hình có schema rõ ràng như `eventType -> handlerCode` hoặc `tenantId -> destinationCode`. Xác thực và kiểm tra bảng cấu hình trước khi áp dụng. Không lưu chuỗi SpEL tùy ý do người dùng quản lý trừ khi có một hệ thống quản trị biểu thức được thiết kế, sandbox và kiểm toán riêng.

## 9. Kiểm soát message headers đến từ bên ngoài

Headers là một phần của message và có thể được producer bên ngoài cung cấp. Một số header có ý nghĩa điều khiển, chẳng hạn function definition, routing expression, content type hoặc target destination. Nếu ứng dụng tin tưởng các header này mà không xác minh nguồn gốc, người gửi có thể tác động đến cách xử lý message.

Khi nhận message từ nguồn không đáng tin cậy:

1. Xác định rõ header nào được phép đi qua ranh giới hệ thống.
2. Loại bỏ hoặc ghi đè header điều khiển nội bộ trước khi đưa message vào router.
3. Chỉ tạo header định tuyến sau khi xác thực payload và quyền người gửi.
4. Dùng danh sách tên header được phép và quy tắc chuyển tiếp rõ ràng.
5. Không dùng header làm bằng chứng xác thực hoặc ủy quyền.

Ví dụ lọc message trước khi xử lý:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<IncomingEvent> sanitized = MessageBuilder
    .withPayload(original.getPayload())
    .setHeader("correlationId", trustedCorrelationId)
    .setHeader("eventType", validatedEventType)
    .build();
```

Ví dụ tạo message mới chỉ giữ những metadata đã được ứng dụng kiểm tra. Trong code thực tế, cần giữ thêm các header vận chuyển cần thiết theo binder và tracing instrumentation, đồng thời loại bỏ các header điều khiển mà nguồn ngoài không được phép đặt.

## 10. Xử lý loại sự kiện hoặc đích không được hỗ trợ

Một router cần quy định rõ hành vi khi dữ liệu không khớp allowlist. Không nên âm thầm gửi đến destination mặc định không rõ ý nghĩa hoặc bỏ message mà không có dấu vết.

Các lựa chọn phổ biến:

| Tình huống | Hướng xử lý |
|---|---|
| `eventType` không được hỗ trợ | Từ chối, ghi nhận lý do và chuyển vào luồng cách ly nếu cần điều tra |
| Tenant không tồn tại | Trả lỗi nghiệp vụ hoặc cách ly message theo chính sách |
| Người gửi không có quyền | Từ chối trước khi gửi; ghi audit an toàn |
| Destination không nằm trong allowlist | Không tạo binding; ghi metric và xử lý lỗi rõ ràng |
| Schema không tương thích | Chuyển sang error handling/DLQ phù hợp, không đoán loại hàm |
| Broker không khả dụng | Áp dụng retry producer/outbox phù hợp; không đổi destination để né lỗi |

Destination cách ly hoặc quarantine cũng cần được cấu hình và bảo vệ. Không gửi dữ liệu nhạy cảm đến một queue debug có quyền truy cập rộng. Khi replay message đã cách ly, giữ event ID và metadata nguồn để có thể đối soát.

## 11. Kiểm tra quyền ở nhiều tầng

Một allowlist tên destination không tự bảo đảm người gửi được phép gửi dữ liệu đến destination đó. Cần tách ít nhất ba lớp:

- **Xác thực:** xác định người gửi hoặc dịch vụ gửi là ai.
- **Ủy quyền nghiệp vụ:** xác định danh tính đó được phát loại sự kiện nào, cho tenant nào hoặc cho miền dữ liệu nào.
- **Quyền broker:** tài khoản ứng dụng được phép publish đến topic, exchange hoặc namespace nào.

Ví dụ tenant A chỉ được phát sự kiện của tenant A. Dù `tenant-b.events` nằm trong allowlist toàn ứng dụng, tenant A vẫn phải bị từ chối khi yêu cầu gửi sang đó. Ngược lại, code nghiệp vụ cho phép tenant A cũng không thể publish nếu tài khoản binder không có quyền ghi destination tương ứng.

Không cấp tài khoản broker với quyền quản trị toàn cụm cho một router chỉ vì nó cần gửi đến vài destination. Dùng quyền tối thiểu theo topic, exchange, namespace hoặc tenant khi broker hỗ trợ. Nếu ứng dụng dùng một credential chung, cần giới hạn chặt hơn ở tầng ứng dụng và giám sát mọi lần định tuyến.

## 12. Khác biệt giữa Kafka, RabbitMQ và Pulsar

Spring Cloud Stream cung cấp abstraction chung, nhưng destination và cơ chế định tuyến vật lý khác nhau:

| Broker | Destination đầu ra | Các điểm cần kiểm soát |
|---|---|---|
| Kafka | Topic và partition | Topic được phép, quyền produce, key/partitioner, số partition và retention |
| RabbitMQ | Exchange, routing key và queue binding | Exchange được phép, routing key, queue binding, quyền publish và xử lý message không được định tuyến |
| Pulsar | Topic và namespace | Namespace/topic được phép, quyền produce, partitioned topic và key ordering |

Với Kafka, gửi đến một topic không tự chọn partition theo tenant nếu producer không đặt key hoặc partition phù hợp. Với RabbitMQ, exchange có thể định tuyến message đến nhiều queue dựa trên routing key; chọn exchange không đồng nghĩa chỉ có một queue nhận. Với Pulsar, topic và subscription là hai khái niệm khác nhau; producer chọn topic, còn subscription quyết định cách consumer nhận message.

Khi dùng dynamic destination, phải xác nhận binder có thể resolve đúng broker và destination. Trong ứng dụng đa binder, cấu hình binder mặc định hoặc chỉ định binder cho binding cần rõ ràng. Không để dữ liệu bên ngoài quyết định tên binder, địa chỉ broker hoặc credential.

## 13. Tránh định tuyến gây mất thứ tự hoặc sai hợp đồng

Định tuyến theo tenant hoặc event type có thể chia message thành nhiều destination. Điều này ảnh hưởng thứ tự và cách consumer xử lý:

- Nếu các sự kiện của cùng một đơn hàng cần đúng thứ tự, phải giữ cùng key/partition hoặc cùng luồng xử lý theo khả năng broker.
- Nếu các event type có schema khác nhau, destination nên có hợp đồng rõ hoặc message phải có discriminator và schema version.
- Nếu một event được phát sang nhiều destination, xác định rõ fan-out là chủ đích và xử lý trường hợp chỉ một nhánh gửi thành công.
- Nếu routing rule thay đổi, cần tính đến message đang nằm trong broker theo quy tắc cũ và message mới theo quy tắc mới.

Không nên thay destination chỉ vì consumer đang lỗi hoặc chậm. Điều đó có thể tạo hai luồng trạng thái khác nhau và làm mất khả năng đối soát. Lỗi consumer nên được xử lý bằng retry, DLQ và quan sát tại luồng tương ứng.

## 14. Kiểm thử biểu thức và allowlist

Kiểm thử router cần xác minh cả trường hợp hợp lệ và trường hợp bị từ chối:

| Kịch bản | Đầu vào | Kết quả cần xác minh |
|---|---|---|
| Event type hợp lệ | `OrderPlaced` | Chọn đúng `orderHandler` |
| Event type hợp lệ khác | `PaymentAuthorized` | Chọn đúng `paymentHandler` |
| Event type lạ | `UnknownEvent` | Đi vào handler cách ly hoặc bị từ chối theo chính sách |
| Tenant được phép | Tenant A gửi destination A | Message được gửi đến destination A |
| Tenant vượt quyền | Tenant A yêu cầu destination B | Bị từ chối trước khi gọi `StreamBridge.send` |
| Destination ngoài allowlist | `admin.commands` | Không tạo binding hoặc publish đến đích đó |
| Header điều khiển giả mạo | Message tự đặt header target/function | Header bị loại bỏ hoặc ghi đè bằng giá trị tin cậy |
| Expression injection | Payload chứa chuỗi có cú pháp SpEL | Chuỗi chỉ được xem là dữ liệu và không được đánh giá |
| Broker lỗi | Destination hợp lệ nhưng broker từ chối publish | Lỗi được quan sát và xử lý theo chính sách gửi |
| Nhiều tenant đồng thời | Các message từ nhiều tenant | Không rò dữ liệu hoặc dùng nhầm destination giữa các tenant |

Unit test nên kiểm tra hàm ánh xạ `eventType -> handler` và `tenant -> destination` độc lập. Integration test cần xác nhận function router, message conversion, header mapping và binder hoạt động đúng. Test binder hữu ích để kiểm tra luồng Spring, nhưng không thay thế kiểm thử quyền broker, routing exchange RabbitMQ, partition Kafka hoặc namespace Pulsar trên môi trường tương thích.

## 15. Quan sát định tuyến trong production

Router cần có log và metric để trả lời:

- Message được phân loại theo event type nào?
- Handler nào được chọn và theo rule version nào?
- Destination đã được chọn sau khi kiểm tra allowlist là gì?
- Có bao nhiêu lần định tuyến bị từ chối vì tenant, event type hoặc destination không hợp lệ?
- Có bao nhiêu lần gửi thất bại theo binder và destination?
- Có destination nào tăng số lượng binding hoặc backlog bất thường không?

Ghi log `eventId`, `correlationId`, event type đã chuẩn hóa, rule version và destination đã được phép. Không ghi token, credential hoặc toàn bộ payload nhạy cảm. Metric label cần có cardinality giới hạn; tránh dùng tenant ID tùy ý, UUID hoặc tên destination do client tự nhập làm label.

Khi cập nhật allowlist hoặc routing rule, nên version hóa cấu hình và lưu audit ai thay đổi, thay đổi khi nào, vì sao. Điều này giúp giải thích vì sao cùng một event type có thể được định tuyến khác nhau giữa hai thời điểm.

## 16. Quy trình triển khai an toàn

Khi thiết kế routing từ dữ liệu bên ngoài, thực hiện theo trình tự:

1. Xác định rõ đang chọn function, destination hay cả hai.
2. Định nghĩa event type và các trường định tuyến trong schema; không dùng chuỗi biểu thức làm dữ liệu nghiệp vụ.
3. Xác thực người gửi và kiểm tra quyền tenant/miền dữ liệu.
4. Chuẩn hóa dữ liệu đầu vào, từ chối giá trị thiếu hoặc không hợp lệ.
5. Ánh xạ event type sang function trong allowlist bằng biểu thức tĩnh hoặc router Java.
6. Ánh xạ tenant hoặc kết quả xử lý sang binding/destination được phép.
7. Nếu dùng dynamic destination, giới hạn bằng `dynamicDestinations` và provisioning có kiểm soát.
8. Loại bỏ hoặc ghi đè các header điều khiển đến từ nguồn không tin cậy.
9. Kiểm tra quyền publish ở broker theo nguyên tắc tối thiểu.
10. Kiểm thử trường hợp hợp lệ, vượt quyền, expression injection, broker lỗi và nhiều tenant đồng thời.
11. Theo dõi rule version, số binding động, lỗi định tuyến và backlog.
12. Thay đổi routing rule theo quy trình có kiểm soát và có khả năng rollback.

## 17. Tự kiểm tra

- [ ] Phân biệt được function routing và destination routing.
- [ ] Giải thích được vai trò của `functionRouter` và `spring.cloud.function.routing-expression`.
- [ ] Biết vì sao biểu thức định tuyến phải là cấu hình tin cậy, không lấy nguyên từ payload bên ngoài.
- [ ] Ánh xạ event type sang function trong allowlist.
- [ ] Ánh xạ tenant hoặc miền nghiệp vụ sang destination được phép.
- [ ] Biết dùng output binding có sẵn khi destination ổn định và dynamic destination khi thật sự cần.
- [ ] Hiểu `dynamicDestinations` chỉ giới hạn đích động, không thay thế authorization.
- [ ] Nhận diện và xử lý header điều khiển bị giả mạo.
- [ ] Kiểm tra quyền broker, thứ tự message và schema khi định tuyến.
- [ ] Thiết kế kiểm thử cho event type lạ, tenant vượt quyền và destination không hợp lệ.

## Kết luận

Định tuyến an toàn cần phân biệt việc chọn hàm xử lý với việc chọn destination đầu ra. Spring Cloud Function có thể dùng `functionRouter` và biểu thức `spring.cloud.function.routing-expression` để chọn function; Spring Cloud Stream có thể gửi đến binding có sẵn hoặc destination động. Dữ liệu bên ngoài chỉ nên cung cấp mã nghiệp vụ đã được xác thực để chọn trong allowlist do ứng dụng quản lý. Không đánh giá biểu thức do client gửi, không tin header điều khiển chưa được kiểm tra và không dùng tên destination như cơ chế phân quyền. Kết hợp allowlist, authorization, quyền broker tối thiểu, kiểm thử và quan sát giúp luồng định tuyến có thể mở rộng mà vẫn kiểm soát được.
