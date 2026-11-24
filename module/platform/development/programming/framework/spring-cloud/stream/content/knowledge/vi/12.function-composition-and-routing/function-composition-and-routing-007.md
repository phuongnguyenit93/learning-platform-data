# Định tuyến đầu ra bằng StreamBridge và destination động

## Mục tiêu

Trong ứng dụng xử lý sự kiện, một service có thể cần phát các loại message đến những destination khác nhau. Ví dụ, sự kiện đơn hàng ở từng khu vực được gửi đến topic tương ứng; thông báo kiểm toán được gửi đến một destination riêng; hoặc một adapter gửi sự kiện đến một trong các hệ thống tích hợp đã được cấu hình.

Spring Cloud Stream cung cấp `StreamBridge` để gửi message từ code imperative đến output binding. Khi biết trước topology, ứng dụng có thể khai báo các output binding tĩnh. Khi tập đích cần linh hoạt, StreamBridge có thể tạo binding động khi gửi lần đầu đến một destination chưa được bind.

Bài học này giải thích cách chọn đích đầu ra, phân biệt destination với binding name và các khóa định tuyến bên trong broker, kiểm soát destination động, cấu hình binder và kiểm thử luồng gửi.

Sau bài học, bạn có thể:

- Gửi message đến output binding tĩnh bằng `StreamBridge.send`.
- Tạo output binding động khi gửi lần đầu đến destination được cho phép.
- Định tuyến theo loại sự kiện hoặc ngữ cảnh đã xác thực bằng bảng ánh xạ rõ ràng.
- Phân biệt destination với Kafka key/partition và RabbitMQ routing key.
- Quản lý allowlist, provisioning và binder cho các đích đầu ra.
- Xử lý kết quả gửi và kiểm thử định tuyến với Test Binder cùng broker đích.

## 1. StreamBridge và định tuyến đầu ra

`StreamBridge` là API imperative của Spring Cloud Stream. Nó cho phép gửi một đối tượng hoặc Spring `Message` đến output binding từ service, controller, scheduler hay outbox relay mà không cần khai báo một `Supplier` hoặc `Function` chỉ để phát message.

Ví dụ publisher:

```java
@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
```

Chuỗi `orders-out-0` là tên binding mà StreamBridge dùng để tìm output channel. Binding đó được cấu hình với một destination cụ thể, chẳng hạn topic Kafka hoặc destination do Rabbit/Pulsar binder quản lý.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Binding name | Tên output binding trong ứng dụng Spring Cloud Stream | `orders-out-0` |
| Destination | Đích logic trên broker mà binding gửi tới | `orders.created` |
| Binder | Adapter kết nối binding với broker | Kafka, RabbitMQ hoặc Pulsar binder |
| Partition/key/routing key | Cách broker phân vùng hoặc định tuyến bên trong destination | Kafka partition key, Rabbit routing key, Pulsar message key |

Định tuyến đầu ra có thể diễn ra ở hai cấp:

1. **Chọn destination:** quyết định message sẽ đến topic, queue/exchange hoặc topic Pulsar nào.
2. **Định tuyến bên trong destination:** chọn partition, key hoặc queue đích theo cơ chế của broker.

Hai cấp này giải quyết các vấn đề khác nhau. Chọn partition không tự chuyển message sang topic khác; thay routing key không đồng nghĩa đổi output binding.

## 2. Dùng output binding tĩnh khi topology đã biết

Nếu ứng dụng chỉ gửi đến một tập destination ổn định, hãy khai báo output binding trong cấu hình. Có thể tạo binding ngay khi khởi động bằng `spring.cloud.stream.output-bindings`:

```yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0;audit-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
        audit-out-0:
          destination: audit.events
          content-type: application/json
```

Publisher gửi đến đúng binding name:

```java
@Service
public class EventPublisher {

    private final StreamBridge streamBridge;

    public EventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publishOrder(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }

    public boolean publishAudit(AuditEvent event) {
        return streamBridge.send("audit-out-0", event);
    }
}
```

Trong ví dụ, code chọn một trong hai binding đã được khai báo. Tên binding có thể khác tên destination; cấu hình làm nhiệm vụ ánh xạ chúng.

Có thể khai báo binding mà không cần đưa vào danh sách `output-bindings` nếu binding được tạo theo cách khác trong ứng dụng. `output-bindings` hữu ích khi muốn chủ động tạo output binding ngay trong quá trình startup và phát hiện sớm một số lỗi cấu hình/kết nối.

**Nên chọn binding tĩnh khi:**

- Các destination được biết trước khi triển khai.
- Mỗi đích cần cấu hình riêng về content type, binder, partitioning hoặc producer properties.
- Muốn topology dễ kiểm kê, giám sát và cấp quyền.
- Muốn lỗi provisioning hoặc kết nối xuất hiện trong startup thay vì request đầu tiên.

Tạo binding trong startup không đảm bảo broker đã có sẵn topic, queue, exchange hoặc Pulsar topic. Việc tạo tài nguyên phụ thuộc khả năng auto-provisioning, quyền của tài khoản và cấu hình binder. Nếu auto-provisioning không được bật, hạ tầng cần tạo destination theo quy trình triển khai.

## 3. Tạo binding động ở lần gửi đầu tiên

Khi gọi `StreamBridge.send` với tên chưa có output binding, Spring Cloud Stream có thể tạo binding động cho tên đó ở lần gửi đầu. Nếu không có cấu hình ánh xạ riêng, tên được truyền vào được dùng làm destination mặc định.

Ví dụ:

```java
@Service
public class RegionalEventPublisher {

    private final StreamBridge streamBridge;

    public RegionalEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String destination, OrderCreated event) {
        return streamBridge.send(destination, event);
    }
}
```

Nếu lần đầu gọi:

```java
streamBridge.send("orders.eu", event);
```

và chưa có binding tên `orders.eu`, framework có thể tạo output binding động hướng đến destination `orders.eu`. Các lần gửi tiếp theo dùng binding đã được tạo theo cơ chế quản lý binding của framework.

Có thể giới hạn tập destination động:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.apac
        - orders.us
```

Khi bật allowlist, chỉ những destination được liệt kê mới được phép tạo binding động theo chính sách của framework. Hãy xác minh chính xác cách kiểm tra allowlist và tên được so khớp với phiên bản Spring Cloud Stream đang dùng.

Destination động hữu ích khi tập đích thực sự được chọn lúc chạy, nhưng vẫn phải nằm trong phạm vi đã dự kiến. Không lấy chuỗi destination trực tiếp từ HTTP request, message bên ngoài hoặc dữ liệu người dùng rồi chuyển thẳng vào `StreamBridge.send`. Điều đó có thể khiến ứng dụng cố tạo topic/queue ngoài dự kiến hoặc gửi dữ liệu sang nơi không được phép.

## 4. Định tuyến theo loại sự kiện bằng bảng ánh xạ

Một cách triển khai an toàn là ánh xạ giá trị nghiệp vụ đã được xác thực sang một tập destination cố định. Không để dữ liệu đầu vào tùy ý quyết định tên broker destination.

Ví dụ:

```java
public enum Region {
    EU,
    APAC,
    US
}
```

Publisher sử dụng bảng ánh xạ:

```java
@Service
public class RegionalOrderPublisher {

    private static final Map<Region, String> DESTINATIONS = Map.of(
            Region.EU, "orders.eu",
            Region.APAC, "orders.apac",
            Region.US, "orders.us"
    );

    private final StreamBridge streamBridge;

    public RegionalOrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(Region region, OrderCreated event) {
        String destination = DESTINATIONS.get(region);
        if (destination == null) {
            throw new IllegalArgumentException("Unsupported region");
        }

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId())
                .setHeader("eventType", "order.created")
                .build();

        return streamBridge.send(destination, message);
    }
}
```

Các destination trong bảng ánh xạ cũng phải nằm trong allowlist:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.apac
        - orders.us
```

Giá trị `region` cần được xác thực theo chính sách ứng dụng trước khi gọi publisher. Nếu region xuất phát từ tenant hoặc thông tin người dùng, hãy xác thực quyền truy cập tenant đó. Không dùng một header do producer bên ngoài tùy ý gửi làm bằng chứng phân quyền.

Có thể định tuyến theo event type tương tự:

```java
String destination = switch (event.type()) {
    case ORDER_CREATED -> "orders.created";
    case ORDER_CANCELLED -> "orders.cancelled";
    case ORDER_REFUNDED -> "orders.refunded";
};
streamBridge.send(destination, event);
```

Trong code production, nên dùng enum hoặc kiểu sealed rõ ràng và có nhánh xử lý giá trị không hỗ trợ. Bảng ánh xạ giúp reviewer thấy toàn bộ đích có thể được chọn và hỗ trợ kiểm thử từng nhánh.

## 5. Cấu hình riêng cho destination động

Nếu destination động cần content type hoặc thuộc tính binding riêng, có thể khai báo cấu hình theo tên binding trước khi lần gửi đầu tiên xảy ra:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.apac
      bindings:
        orders.eu:
          destination: company.orders.eu
          content-type: application/json
        orders.apac:
          destination: company.orders.apac
          content-type: application/json
```

Code gọi `send` bằng binding name tương ứng:

```java
streamBridge.send("orders.eu", event);
streamBridge.send("orders.apac", event);
```

Ở đây `orders.eu` và `orders.apac` là tên binding được gọi từ code; destination vật lý/logical trên broker được cấu hình riêng. Việc khai báo thuộc tính trước giúp framework tạo binding động với cấu hình mong muốn khi cần.

Nếu ứng dụng có nhiều binder, hãy đặc biệt cẩn thận. Một dynamic binding cần được gắn với binder phù hợp theo cơ chế cấu hình của phiên bản framework; không giả định tên destination tự chọn đúng binder. Với những đích cần binder khác nhau hoặc producer properties đặc biệt, output binding tĩnh được cấu hình tường minh thường dễ kiểm soát hơn. Không để logic nghiệp vụ quyết định binder bằng cách kiểm tra tên broker.

## 6. Destination khác với partition key và routing key

Một lỗi thiết kế phổ biến là dùng một cơ chế định tuyến bên trong broker để giải quyết nhu cầu chọn destination.

### Kafka

Kafka lưu record trong topic và partition. Output binding xác định topic; key của record có thể được dùng để chọn partition. Các record cùng key thường được phân vào cùng partition theo partitioner đang cấu hình, hỗ trợ thứ tự theo key trong partition đó.

Ví dụ:

- Destination/topic: `orders.created`.
- Record key: `order-42`.
- Partition: do partitioner xác định từ key và topology topic.

Thay key không có nghĩa gửi sang topic khác. Nếu cần tách dữ liệu sang topic `orders.eu` và `orders.apac`, hãy chọn binding/destination tương ứng trước; sau đó mới dùng key để quyết định phân vùng trong topic đó.

### RabbitMQ

RabbitMQ publish message đến exchange với routing key. Exchange và binding rules quyết định queue nào nhận message. Routing key không phải tên output binding và cũng không nhất thiết là tên queue. Nếu cần chọn exchange/destination khác, cần chọn output binding hoặc cấu hình binder phù hợp. Nếu chỉ cần chọn queue qua topic/direct exchange, routing key và topology exchange đảm nhiệm phần định tuyến bên trong broker.

### Pulsar

Pulsar destination xác định topic. Message key có thể hỗ trợ phân vùng hoặc xử lý theo key tùy schema và subscription. Key không thay thế việc chọn topic. Hãy phân biệt topic được chọn bởi binding với key được gửi cùng message.

| Broker | Chọn destination | Định tuyến bên trong destination |
|---|---|---|
| Kafka | Output binding → topic | Record key/partitioner → partition |
| RabbitMQ | Output binding và exchange được cấu hình | Routing key + exchange bindings → queue |
| Pulsar | Output binding → topic | Message key và cơ chế partitioning |

## 7. Content type, headers và serialization

Dù gửi đến binding tĩnh hay động, payload vẫn cần có định dạng phù hợp với consumer. Có thể khai báo `content-type` theo binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders.eu:
          destination: company.orders.eu
          content-type: application/json
```

Gửi POJO:

```java
boolean accepted = streamBridge.send("orders.eu", event);
```

Hoặc gửi Spring Message với application headers:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", correlationId)
        .build();

boolean accepted = streamBridge.send("orders.eu", message);
```

Headers như `eventId` và `correlationId` là metadata do ứng dụng định nghĩa. Không tự tạo metadata do broker quản lý như Kafka offset, Rabbit delivery tag hoặc Pulsar message ID. Việc truyền custom headers và chuyển đổi payload phụ thuộc binder, content type và cấu hình native encoding/decoding. Producer và consumer phải thống nhất schema và wire format.

## 8. Kết quả send, lỗi và bảo đảm giao nhận

`StreamBridge.send` trả về boolean cho biết message được chấp nhận qua output binding/channel theo cơ chế của framework. Giá trị `true` không chứng minh rằng consumer đã nhận, xử lý hay commit nghiệp vụ. Nó cũng không thay thế acknowledgment của broker hoặc transaction xuyên database và broker.

Publisher nên kiểm tra kết quả và xử lý exception:

```java
public void publish(OrderCreated event) {
    boolean accepted = streamBridge.send("orders.eu", event);

    if (!accepted) {
        throw new IllegalStateException(
                "Output binding did not accept the event"
        );
    }
}
```

Trong production, cần quan sát cả lỗi xảy ra khi tạo binding, provisioning destination, serialize payload hoặc gửi đến broker. Một số lỗi có thể xuất hiện dưới dạng exception đồng bộ; lỗi gửi bất đồng bộ có thể được báo qua cơ chế callback/error của binder. Hãy kiểm tra tài liệu và hành vi của binder đang dùng.

Nếu sự kiện phát sinh cùng một thay đổi database, gửi trực tiếp từ transaction service có thể tạo khoảng trống: database commit nhưng message không được gửi, hoặc message được gửi trong khi database rollback. Có thể dùng transactional outbox:

1. Ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database.
2. Relay đọc các bản ghi chưa gửi và chọn output binding theo bảng ánh xạ đã kiểm soát.
3. Relay gửi message qua StreamBridge.
4. Khi trạng thái gửi được xác nhận theo chính sách của relay, đánh dấu bản ghi outbox đã gửi.
5. Nếu relay dừng sau khi gửi nhưng trước khi đánh dấu, message có thể được gửi lại; consumer cần idempotent theo event ID.

Đừng đánh dấu outbox hoàn tất chỉ vì một lần gọi send trả về true nếu yêu cầu độ bền cần xác nhận broker cụ thể. Thiết kế trạng thái relay dựa trên semantics xác nhận của binder và chấp nhận khả năng gửi lặp.

## 9. Provisioning và quyền truy cập destination

Binding động không đồng nghĩa broker tự động tạo mọi tài nguyên. Kết quả phụ thuộc binder và cấu hình hạ tầng:

- Kafka có thể yêu cầu topic được tạo trước hoặc cho phép auto topic creation theo broker policy.
- RabbitMQ có thể cần exchange, queue và bindings được provision bởi binder hoặc hạ tầng.
- Pulsar có thể yêu cầu topic/namespace được tạo trước hoặc dùng chính sách auto creation của cluster.

Tài khoản ứng dụng cần quyền publish đến destination được phép. Quyền tạo topic, exchange hoặc queue nên được cấp riêng theo nguyên tắc least privilege. Nếu ứng dụng không cần tạo tài nguyên runtime, hãy tắt hoặc hạn chế provisioning động và quản lý topology bằng IaC/quy trình triển khai.

Đối với destination động, cần có chính sách về:

- Danh sách destination được phép.
- Quyền publish theo binder và namespace.
- Quy tắc đặt tên và giới hạn cardinality.
- Cách xử lý destination không tồn tại.
- Theo dõi số binding/destination được tạo và lỗi provisioning.
- Vòng đời destination khi một tenant hoặc tích hợp bị ngừng hoạt động.

Không tạo một topic cho từng request hoặc từng user nếu partitioning, key hoặc tenant metadata đã đáp ứng yêu cầu. Quá nhiều destination có thể làm tăng tải metadata, chi phí quản trị và độ phức tạp vận hành.

## 10. Kiểm thử định tuyến đầu ra

Nên kiểm thử cả quyết định chọn đích và hành vi của binding.

### Unit test cho bảng ánh xạ

Kiểm tra mỗi loại sự kiện hoặc region được ánh xạ đến đúng binding name. Kiểm tra giá trị không hỗ trợ bị từ chối và không thể tạo destination tùy ý.

Có thể mock StreamBridge để xác minh publisher gọi đúng tên binding với payload dự kiến. Test này xác minh logic lựa chọn, nhưng không chứng minh binding đã được tạo hay broker nhận được message.

### Test Binder

Dùng Spring Cloud Stream Test Binder để kiểm tra:

- Binding tĩnh được khởi tạo theo cấu hình.
- StreamBridge gửi message đến output channel mong đợi.
- Dynamic binding được tạo khi gửi lần đầu đến destination hợp lệ.
- Allowlist từ chối destination không được phép theo cấu hình.
- Payload và application headers được chuyển đổi như dự kiến.

Test Binder kiểm tra framework ở mức test, không mô phỏng đầy đủ provisioning, quyền hoặc metadata native của từng broker.

### Broker integration test

Dùng Kafka, RabbitMQ hoặc Pulsar chạy trong môi trường test để xác minh:

- Destination/topic/exchange/queue thực tế đúng.
- Binder được chọn đúng.
- Broker account có quyền publish và provisioning cần thiết.
- Kafka key/partition, Rabbit routing key/queue hoặc Pulsar key/partition hoạt động đúng.
- Consumer nhận được payload và headers theo contract.
- Lỗi broker hoặc destination không tồn tại được quan sát và xử lý đúng.

Với hệ thống dùng nhiều binder, cần test từng loại binder có trong production. Không suy ra hành vi của RabbitMQ hoặc Pulsar chỉ từ một test chạy với Kafka.

## 11. Quy trình triển khai

Khi thiết kế định tuyến đầu ra bằng StreamBridge, thực hiện theo trình tự:

1. Xác định các loại sự kiện và destination mà ứng dụng cần gửi.
2. Nếu tập đích ổn định, khai báo output binding tĩnh và ánh xạ binding name sang destination.
3. Nếu cần dynamic binding, định nghĩa allowlist và quy tắc đặt tên; không nhận tên destination tùy ý từ bên ngoài.
4. Viết bảng ánh xạ từ event type/region đã xác thực sang binding name.
5. Cấu hình content type, binder và producer properties cho từng đích.
6. Phân biệt chọn destination với key, partition hoặc routing key bên trong broker.
7. Kiểm tra kết quả send, exception, provisioning và quyền publish.
8. Nếu cần phối hợp với database, dùng outbox và idempotent consumer.
9. Viết unit test, Test Binder test và broker integration test cho từng nhánh định tuyến.

Ghi lại danh sách binding name, destination, binder, owner và quyền truy cập trong tài liệu vận hành. Khi thêm destination mới, cập nhật allowlist, cấu hình broker và contract test trước khi triển khai code gửi đến đích đó.

## Kết luận

`StreamBridge` cho phép gửi message từ code imperative đến output binding. Binding tĩnh phù hợp với topology đã biết và cần cấu hình rõ ràng; dynamic binding cho phép tạo output binding khi gửi lần đầu đến destination được kiểm soát. Bảng ánh xạ từ loại sự kiện hoặc ngữ cảnh đã xác thực giúp ứng dụng định tuyến mà không phụ thuộc dữ liệu destination tùy ý.

Hãy phân biệt destination với Kafka partition key, RabbitMQ routing key và Pulsar message key. Kiểm soát allowlist, provisioning, binder và quyền publish; kiểm tra kết quả gửi và kiểm thử trên broker đích. Giá trị `true` từ StreamBridge không phải xác nhận consumer đã xử lý message, vì vậy luồng nghiệp vụ cần độ tin cậy vẫn phải có retry, outbox và idempotency phù hợp.

