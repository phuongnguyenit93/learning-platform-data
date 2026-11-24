# Chọn binder khi gửi StreamBridge đến destination động

`StreamBridge` cho phép ứng dụng gửi message từ REST controller, scheduler hoặc một nguồn sự kiện bên ngoài vào Spring Cloud Stream. Khi tên destination chỉ được biết lúc chạy, `StreamBridge` có thể tạo output binding động ở lần gửi đầu tiên. Nếu ứng dụng có nhiều binder, chẳng hạn Kafka và RabbitMQ, chỉ tên destination là chưa đủ để quyết định broker nào sẽ nhận message. Ứng dụng cần chọn binder cho lần tạo binding động đó.

API `StreamBridge` có overload nhận thêm tên binder:

~~~java
boolean send(String bindingName, String binderName, Object data);
boolean send(
        String bindingName,
        String binderName,
        Object data,
        MimeType outputContentType);
~~~

Tham số `binderName` cho `BindingService` biết binder nào sẽ tạo binding động. Tham số đầu tiên vẫn là tên output binding; khi binding chưa tồn tại, tên này được dùng làm tên destination động. Vì vậy, cần hiểu rõ binding name, destination và binder name trước khi định tuyến.

## 1. Phân biệt binding name, destination và binder name

Ba tên này có vai trò khác nhau:

| Giá trị | Ý nghĩa | Ví dụ |
|---|---|---|
| `bindingName` | Tên output binding trong Spring Cloud Stream; với binding động, nó cũng là tên destination được bind | `orders.eu` |
| `destination` | Tên tài nguyên thực trên broker, ví dụ Kafka topic hoặc RabbitMQ exchange | `orders.events.eu` |
| `binderName` | Tên binder instance mà ứng dụng chọn để tạo binding | `kafkaWest`, `rabbitOps` |

Với một binding đã khai báo tĩnh, binding name có thể khác destination. Ví dụ binding `ordersKafka` có thể gửi đến topic `orders.events` thông qua binder `kafkaWest`.

Với destination động, nếu chưa có binding mang tên đó và không có cấu hình ánh xạ riêng, `StreamBridge` dùng binding name làm destination. Ví dụ `send("orders.eu", "kafkaWest", event)` tạo output binding động có tên `orders.eu` và yêu cầu Kafka binder tạo hoặc sử dụng destination `orders.eu`.

Đừng truyền tên broker hoặc tên binder vào vị trí `bindingName`. Cũng đừng dùng tên topic làm `binderName`; hai tham số có trách nhiệm khác nhau.

## 2. Vì sao phải chọn binder rõ ràng?

Khi chỉ có một binder trên classpath, Spring Cloud Stream có thể tự chọn binder đó. Khi nhiều binder được cấu hình, ứng dụng phải xác định binder cho từng binding. Ví dụ, cùng một ứng dụng có thể nhận lệnh từ Kafka, gửi sự kiện nghiệp vụ sang Kafka và gửi bản sao audit sang RabbitMQ.

~~~text
REST / Scheduler / Service
          |
          v
      StreamBridge
          |
          +---- bindingName = orders.eu
          |     binderName  = kafkaWest
          |            |
          |            v
          |        Kafka topic
          |
          +---- bindingName = audit.events
                binderName  = rabbitOps
                       |
                       v
                 Rabbit exchange
~~~

Nếu bỏ qua `binderName`, `StreamBridge` sử dụng binder mặc định. Khi có nhiều binder mà không xác định được default binder, việc tạo binding có thể thất bại vì framework không biết nên dùng broker nào. Nếu default binder tồn tại nhưng khác broker mong muốn, message có thể đi nhầm hệ thống.

Việc chọn binder không thay thế cấu hình kết nối broker. Kafka binder vẫn cần bootstrap servers, Rabbit binder vẫn cần host/port và thông tin xác thực. `binderName` chỉ chọn binder configuration đã được khai báo trong ứng dụng.

## 3. Khai báo nhiều binder trong application.yml

Ví dụ một ứng dụng kết nối Kafka ở môi trường phía Tây và RabbitMQ dùng cho audit:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafkaWest
      binders:
        kafkaWest:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: localhost:9092
        rabbitOps:
          type: rabbit
          default-candidate: false
          environment:
            spring:
              rabbitmq:
                host: localhost
                port: 5672
                username: guest
                password: guest
      dynamic-destinations:
        - orders.eu
        - orders.us
        - audit.events
      dynamic-destination-cache-size: 64
~~~

Trong ví dụ:

- `kafkaWest` và `rabbitOps` là tên binder configuration. Đây là các tên có thể truyền vào overload `StreamBridge.send`.
- `type` chỉ loại binder được dùng để tạo cấu hình: `kafka` hoặc `rabbit`.
- `environment` chứa các thuộc tính Spring Boot dành cho binder đó.
- `default-binder` đặt Kafka làm lựa chọn mặc định khi một binding không chỉ định binder.
- `default-candidate: false` khiến `rabbitOps` chỉ được chọn khi ứng dụng tham chiếu rõ ràng.
- `dynamic-destinations` giới hạn những tên destination được phép bind động.
- `dynamic-destination-cache-size` điều chỉnh số output binding động được giữ trong cache.

Đây là cấu hình phát triển trên máy cá nhân. Production cần lấy địa chỉ, tài khoản và mật khẩu từ secret/configuration management của môi trường triển khai; không commit credential thật vào source control.

Nếu ứng dụng dùng các binder được tự động phát hiện theo tên mặc định, tên binder thường là `kafka` và `rabbit`. Nếu khai báo binder configuration riêng như `kafkaWest` hoặc `rabbitOps`, hãy dùng đúng tên cấu hình đó khi gọi `StreamBridge`.

## 4. Gửi đến destination động và chỉ định binder

Giả sử hệ thống nhận sự kiện đơn hàng từ REST API. Khu vực của đơn hàng quyết định topic đích; sự kiện audit luôn đi đến RabbitMQ:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

record OrderCreated(
        String orderId,
        String customerId,
        Region region,
        long totalMinorUnits) {}

record AuditEvent(
        String eventId,
        String action,
        String aggregateId) {}

enum Region {
    EU,
    US
}

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publishOrder(OrderCreated event) {
        String destination = switch (event.region()) {
            case EU -> "orders.eu";
            case US -> "orders.us";
        };

        return streamBridge.send(
                destination,
                "kafkaWest",
                event,
                MimeTypeUtils.APPLICATION_JSON);
    }

    boolean publishAudit(AuditEvent event) {
        return streamBridge.send(
                "audit.events",
                "rabbitOps",
                event,
                MimeTypeUtils.APPLICATION_JSON);
    }
}
~~~

Trong `publishOrder`, `orders.eu` hoặc `orders.us` là tên binding/destination động; `kafkaWest` chọn Kafka binder. Trong `publishAudit`, `audit.events` là tên destination động và `rabbitOps` chọn Rabbit binder.

Ví dụ dùng `MimeTypeUtils.APPLICATION_JSON` để yêu cầu chuyển đổi payload theo JSON. Có thể dùng overload ba tham số nếu content type mặc định của binding là phù hợp. Nếu truyền một Spring `Message`, content type trong message header cũng được tôn trọng theo cơ chế content-type negotiation.

Khi destination được tạo lần đầu, binder tương ứng sẽ thực hiện binding và provision tài nguyên broker nếu binder được cấu hình cho phép. Các lần gửi tiếp theo có thể dùng lại output binding đã cache.

## 5. Không nhận binder name tùy ý từ request bên ngoài

Không nên viết API nhận trực tiếp cả `destination` và `binderName` từ HTTP request rồi chuyển nguyên hai giá trị vào `StreamBridge`:

~~~java
// Không nên: client có thể yêu cầu bind tới tài nguyên ngoài dự kiến.
streamBridge.send(request.destination(), request.binderName(), request.payload());
~~~

Destination động có thể làm binder tạo topic hoặc exchange mới. Nếu tên đích và binder do client tự chọn, endpoint có thể vô tình trở thành đường tạo tài nguyên tùy ý, gửi dữ liệu sang broker ngoài dự kiến hoặc gây tăng số lượng binding không kiểm soát.

Thay vào đó, ánh xạ giá trị nghiệp vụ đã được xác thực sang một danh sách đích và binder cho phép:

~~~java
String destination = switch (region) {
    case EU -> "orders.eu";
    case US -> "orders.us";
};

String binderName = "kafkaWest";
streamBridge.send(destination, binderName, event);
~~~

Nếu mỗi tenant có broker riêng, hãy lấy binder name từ cấu hình tenant đã được quản trị và kiểm tra quyền truy cập trước khi gửi. Không tin cậy header hoặc query parameter tùy ý để quyết định broker.

## 6. Dùng dynamic-destinations để giới hạn tên đích

Thuộc tính `spring.cloud.stream.dynamic-destinations` là allowlist cho destination có thể được bind động:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.us
        - audit.events
~~~

Khi thuộc tính này được cấu hình, chỉ các destination trong danh sách mới được phép bind động. Khi không cấu hình, framework cho phép mọi destination động theo mặc định.

Allowlist này giới hạn tên destination, không chọn binder. Việc chọn binder vẫn phải thực hiện bằng tham số `binderName` của `StreamBridge.send` hoặc cấu hình binder của binding tĩnh.

Nếu ứng dụng cần tạo topic theo mã khách hàng, không nhất thiết đưa mọi mã khách hàng vào allowlist. Hãy cân nhắc dùng một số topic phân vùng ổn định như `orders.eu` và đặt `tenantId` trong key/header/payload theo hợp đồng dữ liệu. Cách này kiểm soát tốt số lượng destination và quyền provision tài nguyên.

## 7. Cache output binding động

`StreamBridge` cache các output binding động để những lần gửi sau không phải tạo lại binding. Cache có cơ chế tự loại bỏ; tài liệu hiện hành mô tả kích thước mặc định là 10 và có thể thay đổi bằng `spring.cloud.stream.dynamic-destination-cache-size`.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destination-cache-size: 128
~~~

Chọn kích thước dựa trên số destination hoạt động đồng thời, không dựa trên tổng số khách hàng hoặc tổng số topic từng tồn tại. Khi số destination vượt cache size, một binding cũ có thể bị loại bỏ và phải tạo lại khi được sử dụng lần sau; điều này có thể làm tăng độ trễ ở lần gửi tiếp theo.

Không đặt cache size cực lớn để che một mô hình destination có cardinality không giới hạn. Nếu ứng dụng tạo destination mới cho mỗi request hoặc mỗi user, hãy xem lại mô hình phân vùng dữ liệu và vòng đời tài nguyên trên broker.

## 8. Quy tắc quan trọng: một binding name không tự đổi binder

Tham số `binderName` có tác dụng khi `StreamBridge` tạo binding động. Nếu binding đã được tạo trước bởi `spring.cloud.stream.output-bindings`, hoặc tên binding đã được tạo trước với binder khác, giá trị `binderName` truyền trong lần gọi sau sẽ không thay đổi binder của binding đó.

Ví dụ:

~~~java
streamBridge.send("orders.out", "kafkaWest", event1);

// Không dùng cùng binding name với kỳ vọng chuyển binding đã tạo sang Rabbit.
streamBridge.send("orders.out", "rabbitOps", event2);
~~~

Sau lần gọi đầu tiên, `orders.out` đã được tạo bằng `kafkaWest`. Lần gọi thứ hai không phải cách chuyển binding đang tồn tại sang `rabbitOps`.

Nếu cần gửi đến hai broker bằng cùng một destination logic, tạo hai output binding tĩnh với tên khác nhau và ánh xạ cả hai đến destination tương ứng:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersKafka;ordersRabbit
      bindings:
        ordersKafka:
          destination: orders.events
          binder: kafkaWest
        ordersRabbit:
          destination: orders.events
          binder: rabbitOps
~~~

Gửi qua từng binding:

~~~java
streamBridge.send("ordersKafka", event);
streamBridge.send("ordersRabbit", event);
~~~

Ở đây mỗi binding đã có binder được cấu hình rõ ràng. Không cần truyền `binderName` khi gọi `send`; binding name sẽ tìm đến cấu hình tĩnh của nó. Hai broker có thể có cùng tên destination logic, nhưng mỗi binding được quản lý riêng.

## 9. Chọn binder tĩnh hay động?

| Nhu cầu | Cách phù hợp |
|---|---|
| Mọi message luôn đi đến một Kafka topic cố định | Output binding tĩnh với `binder: kafkaWest` |
| Destination thay đổi theo khu vực nhưng chỉ dùng Kafka | `StreamBridge.send(destination, "kafkaWest", data)` |
| Destination thay đổi và có thể gửi qua Kafka hoặc RabbitMQ | Chọn `binderName` rõ ràng cho mỗi lần tạo binding động |
| Hai broker cần nhận cùng logical destination | Hai output binding tĩnh riêng, mỗi binding chỉ định binder |
| Chỉ muốn thay default cho binding không chỉ định binder | `spring.cloud.stream.default-binder` |
| Muốn hạn chế destination động | `spring.cloud.stream.dynamic-destinations` |

Nếu tập destination đã biết trước và cần cấu hình producer riêng cho từng đích, output binding tĩnh thường dễ vận hành hơn. Dynamic binding hữu ích khi destination thực sự chỉ được quyết định lúc chạy và có thể quản lý bằng allowlist, cache, quyền provision và monitoring.

## 10. Cấu hình binder riêng cho nhiều broker cùng loại

Một ứng dụng có thể kết nối hai Kafka cluster hoặc hai RabbitMQ broker. Khi đó `type` giống nhau nhưng binder configuration name khác nhau:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafkaPrimary:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: kafka-primary.internal:9092
        kafkaArchive:
          type: kafka
          default-candidate: false
          environment:
            spring:
              kafka:
                bootstrap-servers: kafka-archive.internal:9092
~~~

Có thể chọn từng cấu hình:

~~~java
streamBridge.send("orders.live", "kafkaPrimary", event);
streamBridge.send("orders.archive", "kafkaArchive", event);
~~~

`kafkaPrimary` và `kafkaArchive` là hai binder name, dù cả hai có `type: kafka`. Khi cần chọn một broker cụ thể, không truyền chung giá trị `kafka` nếu ứng dụng đã khai báo nhiều binder configuration cùng loại và yêu cầu định tuyến đến một instance cụ thể.

Khi cấu hình binder tường minh, hãy khai báo đầy đủ mọi binder được ứng dụng sử dụng. Việc bật cấu hình binder riêng có thể làm quy trình phát hiện binder mặc định không còn được áp dụng như trước. `default-candidate: false` hữu ích khi một binder chỉ được chọn qua tên tường minh và không nên tham gia việc chọn default.

## 11. Binder name và binder type

`type` trong cấu hình binder cho biết loại integration, ví dụ `kafka` hoặc `rabbit`. Tên khóa dưới `spring.cloud.stream.binders` là tên cấu hình binder mà ứng dụng tham chiếu, ví dụ `kafkaPrimary`, `rabbitOps`.

API hiện hành dùng tên tham số `binderName`. Một số tài liệu phiên bản cũ dùng tên `binderType`; hãy đối chiếu API `StreamOperations`/`StreamBridge` thuộc phiên bản Spring Cloud Stream được Spring Cloud BOM của ứng dụng quản lý. Ý nghĩa cần giữ đúng là chọn định danh binder được cấu hình, không phải chọn loại dữ liệu hay tên destination.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbitOps:
          type: rabbit
~~~

Trong trường hợp này, khi muốn chọn cấu hình trên, truyền `rabbitOps` vào tham số binder name. Nếu chỉ có binder Rabbit tự động phát hiện và không khai báo cấu hình riêng, tên binder thường là `rabbit`.

## 12. Chọn default binder không thay thế lựa chọn theo destination

`spring.cloud.stream.default-binder` xác định binder mặc định cho các binding chưa chỉ định binder. Đây là lựa chọn dự phòng chung của ứng dụng, không phải quy tắc định tuyến theo tên destination.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafkaWest
~~~

Nếu gọi:

~~~java
streamBridge.send("orders.eu", event);
~~~

và `orders.eu` là binding động chưa được tạo, framework dùng default binder. Nếu muốn gửi đến RabbitMQ trong một ứng dụng có Kafka làm default, hãy chỉ định:

~~~java
streamBridge.send("audit.events", "rabbitOps", event);
~~~

Không nên dựa vào thứ tự dependency hoặc thứ tự binder trên classpath để chọn broker. Khi có nhiều binder, lựa chọn cần được thể hiện trong cấu hình hoặc trong tham số của lệnh gửi.

## 13. Nội dung message và content type

`StreamBridge.send` nhận `Object`, vì vậy có thể gửi POJO hoặc Spring `Message`. Framework áp dụng quy trình chuyển đổi output, content type và partitioning tương tự output của function/supplier.

Gửi POJO với content type rõ ràng:

~~~java
streamBridge.send(
        "orders.eu",
        "kafkaWest",
        event,
        MimeTypeUtils.APPLICATION_JSON);
~~~

Hoặc tạo message với header:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("event-source", "order-api")
        .setHeader("schema-version", "1")
        .setHeader("contentType", MimeTypeUtils.APPLICATION_JSON)
        .build();

streamBridge.send("orders.eu", "kafkaWest", message);
~~~

Nếu truyền `Message`, content type trong header được dùng cho quá trình chuyển đổi theo cơ chế của Spring Cloud Stream. Cần bảo đảm serializer/deserializer phía consumer tương thích với định dạng đã gửi. Việc chọn binder không tự đồng bộ schema giữa Kafka và RabbitMQ; mỗi broker/binding vẫn cần hợp đồng message rõ ràng.

## 14. Kết quả trả về của send

Các overload `send` trả về boolean. Giá trị `true` cho biết message đã được gửi qua output channel; `false` cho biết channel không nhận message. Một lỗi cấu hình binder, lỗi provision hoặc lỗi chuyển đổi có thể được ném thành exception.

Ví dụ xử lý kết quả:

~~~java
boolean accepted = streamBridge.send(
        "orders.eu",
        "kafkaWest",
        event,
        MimeTypeUtils.APPLICATION_JSON);

if (!accepted) {
    throw new IllegalStateException("Output channel rejected the event");
}
~~~

Mặc định, `StreamBridge` sử dụng thread gửi và thao tác send là blocking. Nếu bật async bằng `streamBridge.setAsync(true)`, việc gửi được thực hiện bất đồng bộ. Khi đó không được xem boolean trả về như xác nhận cuối cùng rằng broker đã lưu message; cần theo dõi lỗi gửi bất đồng bộ theo cơ chế của binder và cấu hình quan sát phù hợp.

Nếu nghiệp vụ yêu cầu xác nhận bền vững, cần xác định semantics acknowledgement của binder và broker đang dùng. Chọn đúng binder chỉ xác định nơi gửi; nó không tự tạo bảo đảm exactly-once hoặc durability cho message.

## 15. Provisioning và quyền trên broker

Khi tạo destination động, binder có thể cần quyền tạo topic, exchange hoặc tài nguyên liên quan. Hành vi provision phụ thuộc binder và cấu hình broker:

- Kafka binder có thể provision topic nếu tài khoản có quyền và auto-create được cho phép.
- Rabbit binder có thể khai báo exchange/queue/binding theo cấu hình producer và binder.
- Tên destination phải tuân thủ quy ước của hệ thống và chính sách broker.
- Môi trường production có thể yêu cầu tạo sẵn tài nguyên bằng quy trình hạ tầng thay vì cho ứng dụng tự provision.

Nếu ứng dụng không có quyền tạo tài nguyên, binding động có thể thất bại ngay cả khi `binderName` đúng. Phân biệt lỗi chọn binder với lỗi kết nối, xác thực, authorization hoặc provisioning.

## 16. Giám sát và giới hạn số destination

Khi dùng destination động trên nhiều binder, theo dõi tối thiểu:

- Số lần gửi theo binder và destination.
- Số binding động đang được cache và số lần cache eviction.
- Tỷ lệ send trả về `false`.
- Exception khi tạo binding hoặc provision tài nguyên.
- Độ trễ gửi và lỗi kết nối từng broker.
- Số destination mới phát sinh trong một khoảng thời gian.

Không đưa payload nhạy cảm hoặc credential vào log. Log nên có event ID, binding name, binder name, destination đã được phép và kết quả gửi.

Đặt giới hạn cho số destination được phép và quyền tạo tài nguyên trên broker. Nếu một tenant bị lỗi cấu hình khiến mỗi request tạo một destination mới, allowlist, cache và quota giúp giới hạn tác động.

## 17. Kiểm thử chọn binder

Kiểm thử nên xác nhận cả binder được chọn và tài nguyên nhận message:

1. Cấu hình hai binder, gửi một destination động với `kafkaWest`, xác nhận record xuất hiện trong Kafka.
2. Gửi một destination khác với `rabbitOps`, xác nhận message xuất hiện trên RabbitMQ.
3. Gửi destination không nằm trong `dynamic-destinations`, xác nhận binding không được tạo.
4. Gửi cùng binding name với binder khác sau khi binding đầu tiên đã được tạo; xác nhận ứng dụng không dựa vào lời gọi đó để chuyển binder.
5. Khởi động với output binding tĩnh và binder property; xác nhận binder tĩnh được ưu tiên theo cấu hình.
6. Kiểm tra `default-binder` khi gọi overload không truyền binder name.
7. Kiểm tra payload JSON, content type và header ở phía consumer.
8. Mô phỏng lỗi xác thực/provision trên một broker; xác nhận log và metric chỉ ra đúng binder.
9. Kiểm tra cache eviction khi số destination vượt cache size.

Có thể dùng `StreamOperations` trong unit test thay vì phụ thuộc trực tiếp vào lớp `StreamBridge`, vì `StreamBridge` triển khai contract này. Integration test vẫn cần binder thật hoặc môi trường broker tương đương để xác nhận routing và provisioning.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Message luôn đi đến Kafka dù muốn RabbitMQ | Gọi overload hai tham số hoặc dùng default binder | Dùng `send(bindingName, binderName, data)` |
| Không tìm thấy binder | Truyền sai binder configuration name | Dùng đúng tên khóa trong `spring.cloud.stream.binders` |
| Gọi lần hai vẫn dùng binder cũ | Binding name đã được tạo trước bằng binder khác | Dùng binding name riêng hoặc khai báo hai output binding tĩnh |
| `binderName` không có tác dụng | Binding đã được pre-create bằng `output-bindings` hoặc cấu hình tĩnh | Chỉ dùng tham số này cho binding động chưa được tạo |
| Binding động bị từ chối | Destination không nằm trong allowlist | Bổ sung destination được phê duyệt hoặc sửa mapping |
| Tạo quá nhiều binding | Destination được sinh từ giá trị không giới hạn | Giới hạn destination và điều chỉnh mô hình partitioning |
| Binding không tạo được | Broker không cho phép provision hoặc credential thiếu quyền | Kiểm tra quyền và tạo sẵn tài nguyên theo chính sách |
| Không có default binder | Có nhiều binder nhưng không đặt default hoặc không truyền binder name | Đặt `default-binder` hoặc chỉ định binder rõ ràng |
| Consumer không giải mã được | Content type/schema không khớp | Đồng bộ serializer, converter và schema |

## 19. Checklist trước khi phát hành

- Xác định destination là binding tĩnh hay dynamic destination.
- Phân biệt `bindingName`, `destination`, `binderName` trong từng lệnh gửi.
- Khai báo đủ binder configuration và kết nối broker riêng.
- Dùng tên binder configuration chính xác trong `StreamBridge.send`.
- Đặt `default-binder` nếu ứng dụng cần lựa chọn mặc định.
- Dùng `dynamic-destinations` để giới hạn destination có thể bind động.
- Không cho client truyền tùy ý destination hoặc binder name.
- Không dùng lại binding name với kỳ vọng chuyển sang binder khác sau khi binding đã tạo.
- Dùng output binding tĩnh riêng nếu cần cùng logical destination trên nhiều broker.
- Chọn cache size theo số destination hoạt động đồng thời.
- Kiểm tra content type, serializer và schema ở phía consumer.
- Kiểm tra quyền provision tài nguyên trên từng broker.
- Theo dõi send result, lỗi binder, cache eviction và số destination.
- Kiểm thử routing với từng binder trên môi trường tích hợp.

Khi gửi đến destination động trong ứng dụng có nhiều binder, hãy chọn binder ngay tại thời điểm tạo binding bằng overload `StreamBridge.send(bindingName, binderName, data)`. Tên binder phải khớp với cấu hình binder trong ứng dụng; tên destination vẫn được truyền riêng qua binding name. Binding tĩnh cần chỉ định binder trong cấu hình, còn binding động cần truyền binder name khi tạo lần đầu. Kết hợp lựa chọn rõ ràng với allowlist, cache có giới hạn, quyền provision và kiểm thử trên từng broker để tránh gửi nhầm hệ thống hoặc tạo destination ngoài kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0 — Producing and Consuming Messages: StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream 5.0 — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream 5.0 — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [StreamBridge API — Spring Cloud Stream 5.0.2](https://javadoc.io/static/org.springframework.cloud/spring-cloud-stream/5.0.2/spring.cloud.stream/org/springframework/cloud/stream/function/StreamBridge.html)
