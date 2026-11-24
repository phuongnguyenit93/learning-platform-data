# Tạo sẵn output binding và tạo binding khi gửi lần đầu

## Mục tiêu

Spring Cloud Stream thường kết nối function với broker thông qua các binding được suy ra từ chữ ký `Supplier`, `Function` hoặc `Consumer`. Trong một số trường hợp, ứng dụng cần phát message từ một thành phần imperative như service, controller, scheduler hoặc outbox relay. `StreamBridge` cung cấp cách gửi message đến output binding mà không cần biến thành phần đó thành một function bean.

Với `StreamBridge`, output binding có thể được **tạo sẵn khi ứng dụng khởi động** hoặc được **tạo động khi lần gửi đầu tiên xảy ra**. Hai cách đều hữu ích nhưng khác nhau về thời điểm khởi tạo, khả năng cấu hình, kiểm soát destination và cách xử lý lỗi.

Sau bài học, bạn có thể:

- Phân biệt tên binding với tên destination.
- Dùng `spring.cloud.stream.output-bindings` để tạo output binding trước khi gửi.
- Gửi đến binding đã tạo sẵn bằng `StreamBridge.send`.
- Tạo binding động khi gửi lần đầu đến một tên chưa được bind.
- Giới hạn destination động và cấu hình binder/content type phù hợp.
- Chọn cách tạo binding dựa trên topology và yêu cầu vận hành.
- Kiểm thử việc tạo binding, gửi message và provisioning với binder đích.

## 1. StreamBridge dùng để làm gì?

`StreamBridge` là API imperative để gửi dữ liệu vào một output binding của Spring Cloud Stream. Nó hữu ích khi nơi phát message không phải là một function output, chẳng hạn:

- REST controller nhận yêu cầu và phát sự kiện.
- Application service phát thông báo sau khi hoàn thành một thao tác.
- Scheduler tạo message định kỳ.
- Outbox relay đọc sự kiện đã lưu trong database rồi gửi ra broker.
- Một adapter cần chọn output binding dựa trên loại sự kiện hoặc destination đã được cho phép.

Ví dụ một service gửi thông báo:

```java
@Service
public class NotificationPublisher {

    private final StreamBridge streamBridge;

    public NotificationPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderNotification notification) {
        return streamBridge.send("notifications-out-0", notification);
    }
}
```

Tên truyền vào `send` là **binding name** mà StreamBridge sử dụng để tìm hoặc tạo output binding. Binding name được ánh xạ đến **destination** mà binder sẽ gửi message tới.

Hai khái niệm này có thể giống nhau, nhưng không bắt buộc phải giống:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Binding name | Tên định danh output binding trong cấu hình Spring Cloud Stream và khi gọi StreamBridge | `notifications-out-0` |
| Destination | Đích ở broker mà binding kết nối tới | Kafka topic `notifications`, Rabbit exchange/queue theo cấu hình, hoặc Pulsar topic |
| Binder | Thành phần kết nối binding với broker cụ thể | Kafka binder, Rabbit binder, Pulsar binder |

Trong ví dụ trên, `notifications-out-0` là tên binding; destination thực tế sẽ được cấu hình. Không mặc định rằng đổi tên binding đồng nghĩa đổi tên topic hoặc queue.

## 2. Tạo sẵn output binding khi ứng dụng khởi động

Khi biết trước những output binding mà ứng dụng cần dùng, có thể khai báo chúng trong `spring.cloud.stream.output-bindings`. Spring Cloud Stream tạo các output binding đó trong quá trình khởi động.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0;audit-events-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          content-type: application/json
        audit-events-out-0:
          destination: app.audit-events
          content-type: application/json
```

Danh sách `output-bindings` dùng dấu chấm phẩy để phân tách tên binding. Mỗi binding có thể có cấu hình riêng dưới `spring.cloud.stream.bindings.<bindingName>`, chẳng hạn destination, content type, binder và producer properties.

Sau khi binding được tạo, code gửi message bằng đúng tên binding:

```java
@Service
public class EventPublisher {

    private final StreamBridge streamBridge;

    public EventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publishNotification(Notification event) {
        return streamBridge.send("notifications-out-0", event);
    }

    public boolean publishAudit(AuditEvent event) {
        return streamBridge.send("audit-events-out-0", event);
    }
}
```

### Khi nào nên tạo sẵn?

Tạo sẵn binding phù hợp khi:

- Tập destination tương đối ổn định và biết trước khi triển khai.
- Mỗi output cần cấu hình content type, partitioning hoặc producer behavior rõ ràng.
- Cần chọn binder cụ thể trong ứng dụng có nhiều binder.
- Muốn lỗi cấu hình hoặc lỗi provisioning được phát hiện trong quá trình startup thay vì ở request đầu tiên.
- Muốn quan sát topology đầu ra ngay khi ứng dụng khởi động.

Tạo sẵn không có nghĩa broker destination chắc chắn đã tồn tại. Binder có thể tự provision destination nếu được hỗ trợ và được bật quyền tương ứng; nếu tự động tạo bị tắt, destination phải được tạo trước theo quy trình hạ tầng. Quyền tạo topic, exchange, queue hoặc Pulsar topic vẫn phụ thuộc broker và cấu hình binder.

## 3. Tạo binding động ở lần gửi đầu tiên

Nếu `StreamBridge.send` nhận một binding name chưa được khai báo hoặc chưa tồn tại, Spring Cloud Stream có thể tạo output binding động khi lần gửi đầu tiên đến tên đó được thực hiện.

Ví dụ:

```java
@Service
public class AlertPublisher {

    private final StreamBridge streamBridge;

    public AlertPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(Alert alert) {
        return streamBridge.send("inventory-alerts", alert);
    }
}
```

Nếu chưa có binding tên `inventory-alerts`, StreamBridge yêu cầu framework tạo binding đầu ra động. Trong trường hợp không có cấu hình ánh xạ riêng, tên được dùng làm destination mặc định. Binder tương ứng sẽ thực hiện kết nối và provisioning theo cấu hình, quyền hạn và khả năng của nó.

Có thể cấu hình binding động bằng tên đã biết trong cấu hình:

```yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-alerts:
          destination: inventory.alerts
          content-type: application/json
```

Sau đó code vẫn gọi:

```java
streamBridge.send("inventory-alerts", alert);
```

Ở đây, `inventory-alerts` là binding name; `inventory.alerts` là destination. Cách khai báo trước thuộc tính theo tên binding giúp định nghĩa destination và content type ngay cả khi binding chỉ được tạo khi gửi lần đầu.

### Giới hạn destination động

Có thể giới hạn các destination được phép tạo động bằng cấu hình `spring.cloud.stream.dynamic-destinations` nếu ứng dụng cần allowlist:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - inventory-alerts
        - audit-events
```

Danh sách này cần khớp với tên destination/binding động mà ứng dụng được phép sử dụng theo phiên bản Spring Cloud Stream đang chạy. Hãy xác minh hành vi allowlist của phiên bản cụ thể trong integration test. Nếu ứng dụng không có nhu cầu gửi đến tập đích thay đổi, tạo sẵn output binding thường dễ kiểm soát hơn.

Không lấy trực tiếp tên destination từ tham số HTTP hoặc dữ liệu người dùng rồi truyền vào `StreamBridge.send`. Nếu làm vậy, một request có thể khiến ứng dụng cố tạo destination ngoài dự kiến, gây rủi ro vận hành, chi phí tài nguyên hoặc truy cập chéo. Hãy ánh xạ loại sự kiện sang danh sách binding/destination đã được cho phép.

## 4. Cấu hình content type và message đầu ra

Dù binding được tạo sẵn hay tạo động, message vẫn cần được chuyển đổi sang định dạng mà consumer mong đợi. Có thể cấu hình content type ở binding:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          content-type: application/json
```

Publisher có thể gửi POJO:

```java
public record OrderNotification(
        String eventId,
        String orderId,
        String message
) {}

boolean accepted = streamBridge.send(
        "notifications-out-0",
        new OrderNotification(
                "evt-100",
                "order-42",
                "Đơn hàng đã được xác nhận"
        )
);
```

Spring Cloud Stream sử dụng content type và cơ chế conversion tương ứng để chuyển payload. Nếu gửi `Message<?>`, có thể gắn application headers bằng `MessageBuilder`:

```java
Message<OrderNotification> message = MessageBuilder
        .withPayload(notification)
        .setHeader("eventId", notification.eventId())
        .setHeader("eventType", "order.notification")
        .build();

boolean accepted = streamBridge.send("notifications-out-0", message);
```

Chỉ thêm headers ứng dụng có ý nghĩa và được consumer mong đợi. Không tự tạo metadata do broker quản lý như offset, partition đã gán hoặc delivery tag. Các chi tiết về serialization native và header mapping còn phụ thuộc binder; content type không thay thế serializer riêng của broker khi binding được cấu hình native encoding.

## 5. Chọn binder và producer properties

Trong ứng dụng có nhiều binder, output binding cần kết nối với đúng binder. Với binding tạo sẵn, có thể khai báo binder rõ ràng:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          binder: kafka
          content-type: application/json
```

Tên `kafka` phải tương ứng với binder đã được đăng ký trong ứng dụng. Nếu không khai báo binder cho binding, framework sử dụng binder mặc định hoặc lựa chọn phù hợp theo cấu hình nhiều binder.

Producer properties chung và thuộc tính riêng của binder nên được đặt theo đúng namespace. Ví dụ, thuộc tính Kafka producer không nên đặt vào cấu hình chung rồi mong RabbitMQ hoặc Pulsar áp dụng cùng ý nghĩa. Khi dùng binding động, nếu cần cấu hình riêng về binder, partition, native encoding hoặc producer properties, hãy khai báo các thuộc tính theo binding name trước khi gửi lần đầu và xác minh chúng thực sự được áp dụng.

Với một tập output đã biết, tạo sẵn binding giúp cấu hình và rà soát binder rõ ràng hơn. Dynamic binding phù hợp khi tập đích thực sự cần linh hoạt, nhưng không nên dùng nó để né việc thiết kế topology hoặc quản lý cấu hình producer.

## 6. So sánh hai cách tạo binding

| Tiêu chí | Tạo sẵn bằng `output-bindings` | Tạo động ở lần gửi đầu |
|---|---|---|
| Thời điểm tạo | Khi ứng dụng khởi động | Khi StreamBridge lần đầu gửi đến binding chưa tồn tại |
| Danh sách binding | Biết trước và khai báo trong cấu hình | Có thể thay đổi theo nhu cầu runtime trong phạm vi được phép |
| Cấu hình | Dễ khai báo đầy đủ trước startup | Nên khai báo thuộc tính theo tên binding nếu cần tùy chỉnh |
| Phát hiện lỗi | Nhiều lỗi kết nối/provisioning có thể lộ ra khi startup | Lỗi có thể xuất hiện ở request hoặc tác vụ gửi đầu tiên |
| Topology | Ổn định, dễ quan sát | Linh hoạt nhưng cần quản lý danh sách đích |
| Use case | Notification, audit, domain events có destination cố định | Destination động đã được kiểm soát, ví dụ nhóm đích theo cấu hình runtime |
| Rủi ro chính | Startup phụ thuộc vào việc tạo/kết nối các output đã khai báo | Tạo đích ngoài ý muốn, cấu hình thiếu và độ trễ ở lần gửi đầu |

### Chọn theo tình huống

- Nếu ứng dụng luôn phát đến `app.notifications` và `app.audit-events`, hãy tạo sẵn hai output binding.
- Nếu một adapter cần gửi đến một trong vài destination được chọn từ cấu hình runtime, có thể dùng dynamic binding với allowlist.
- Nếu mỗi tenant có một topic riêng, cân nhắc kỹ số lượng destination và vòng đời provisioning. Thông thường, partition key hoặc tenant ID trong payload/header có thể đáp ứng yêu cầu phân vùng mà không cần tạo vô hạn topic.
- Nếu cần binder-specific producer configuration hoặc một topology quan trọng với SLA, ưu tiên khai báo binding và cấu hình rõ ràng.

## 7. Xử lý kết quả gửi và lỗi provisioning

`StreamBridge.send` trả về boolean cho biết việc gửi qua output binding/channel đã được chấp nhận theo cơ chế gửi của framework. Giá trị `true` **không chứng minh** broker đã lưu message bền vững, consumer đã nhận hoặc nghiệp vụ phía consumer đã hoàn tất.

Publisher cần xử lý cả trường hợp trả về `false` và exception do lỗi tạo binding, chuyển đổi payload hoặc gửi. Không nên bỏ qua kết quả:

```java
public void publish(OrderNotification event) {
    boolean accepted = streamBridge.send("notifications-out-0", event);

    if (!accepted) {
        throw new IllegalStateException(
                "Spring Cloud Stream did not accept the notification"
        );
    }
}
```

Nếu đây là message phát sinh từ một transaction nghiệp vụ, không nên chỉ gửi qua StreamBridge rồi giả định database và broker đã commit nguyên tử. Có thể dùng transactional outbox: ghi trạng thái nghiệp vụ và bản ghi outbox trong cùng transaction database, sau đó relay gửi message. Relay cần lưu trạng thái gửi và chịu được việc gửi lại; consumer nên idempotent theo event ID.

Các lỗi cần quan sát:

- Binding name không đúng hoặc không được cấu hình như dự kiến.
- Binder không có trong classpath hoặc không thể được lựa chọn.
- Broker không sẵn sàng hoặc credentials không có quyền publish/provision.
- Destination chưa tồn tại trong khi auto-provisioning bị tắt.
- Payload không thể chuyển đổi hoặc serializer không tương thích.
- Dynamic destination bị từ chối bởi allowlist.
- Producer/binder từ chối gửi hoặc xảy ra lỗi bất đồng bộ sau khi lời gọi send đã trả về.

Log nên có event ID, binding name và loại lỗi. Tránh log toàn bộ payload hoặc headers nếu có dữ liệu nhạy cảm. Theo dõi lỗi publish và tình trạng outbox để phát hiện message bị kẹt.

## 8. Kiểm thử output binding tạo sẵn

Kiểm thử binding tạo sẵn cần xác minh binding được khởi tạo và StreamBridge gửi message đến đúng output. Với Spring Cloud Stream Test Binder, có thể kiểm tra ở mức framework mà không cần broker thật.

Ví dụ cấu hình test:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          content-type: application/json
```

Test nên xác minh:

1. Application context khởi động với output binding đã khai báo.
2. Gọi publisher dùng đúng binding name.
3. Message xuất hiện ở destination/binding đích trong Test Binder.
4. Payload được chuyển đổi đúng và custom headers cần thiết có mặt.
5. Binding dùng đúng binder khi ứng dụng có nhiều binder.

Test Binder xác minh hành vi framework, không chứng minh broker thật đã provision topic hoặc exchange. Với Kafka, RabbitMQ hoặc Pulsar, cần integration test khi muốn xác nhận quyền publish, provisioning, native serialization và broker-specific producer behavior.

## 9. Kiểm thử binding động

Với binding động, cần xác minh hành vi tạo binding ở lần gửi đầu và chính sách destination:

- Gửi lần đầu đến tên chưa được bind và xác minh framework tạo output binding.
- Gửi lần tiếp theo đến cùng tên và xác minh binding được sử dụng lại theo vòng đời framework.
- Nếu có allowlist, kiểm tra destination hợp lệ được chấp nhận và destination ngoài danh sách bị từ chối.
- Kiểm tra content type, destination mapping, binder và producer properties đã khai báo theo tên binding.
- Kiểm tra lỗi khi broker không cho phép provision hoặc publish.
- Kiểm tra hệ thống không tạo destination tùy ý từ input không đáng tin cậy.

Ví dụ test logic publisher có thể dùng Test Binder hoặc mock ở mức đơn vị để xác minh tên binding được chọn. Nhưng hành vi provisioning động phải được kiểm tra bằng application context và binder thực tế; mock `StreamBridge.send` không chứng minh framework đã tạo binding.

## 10. Quy trình lựa chọn và triển khai

Khi cần gửi message từ code imperative:

1. Liệt kê các destination ứng dụng cần gửi đến.
2. Nếu tập đích ổn định, khai báo tên trong `spring.cloud.stream.output-bindings`.
3. Nếu cần binding động, xác định quy tắc ánh xạ tên, allowlist và giới hạn số lượng đích.
4. Phân biệt binding name với destination; khai báo `bindings.<bindingName>.destination` khi hai tên khác nhau.
5. Khai báo content type, binder và producer properties trước khi gửi lần đầu nếu cần hành vi cụ thể.
6. Gửi bằng `StreamBridge.send(bindingName, data)` và kiểm tra kết quả.
7. Thiết kế retry, outbox và idempotency theo yêu cầu giao nhận.
8. Kiểm thử với Test Binder, sau đó kiểm tra provisioning và publish trên broker đích.

Ghi rõ binding name và destination trong tài liệu vận hành. Khi đổi destination hoặc binder, cập nhật cấu hình và test để tránh một thay đổi hạ tầng làm gửi nhầm message.

## Kết luận

`spring.cloud.stream.output-bindings` cho phép tạo output binding ngay khi ứng dụng khởi động, phù hợp với topology ổn định và cần cấu hình tường minh. Nếu `StreamBridge.send` được gọi với tên chưa có binding, Spring Cloud Stream có thể tạo binding động ở lần gửi đầu, phù hợp với tập đích linh hoạt đã được kiểm soát.

Trong cả hai cách, hãy phân biệt binding name với destination, cấu hình content type và binder đúng phạm vi, giới hạn destination động và xử lý kết quả gửi có chủ đích. Giá trị `true` từ `send` không phải xác nhận consumer đã xử lý. Khi cần độ tin cậy giữa database và broker, hãy kết hợp outbox, retry và idempotent consumer.

