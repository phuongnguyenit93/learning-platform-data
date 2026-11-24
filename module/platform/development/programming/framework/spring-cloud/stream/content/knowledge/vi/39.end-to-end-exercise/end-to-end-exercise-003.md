# Hai nhóm thanh toán và thông báo nhận sự kiện độc lập

Trong một hệ thống thương mại điện tử, khi đơn hàng được tạo, nhiều bộ phận cần phản ứng với cùng một sự kiện. **Payment Service** cần xử lý thanh toán; **Notification Service** cần gửi email, SMS hoặc thông báo trong ứng dụng. Hai việc này cùng bắt đầu từ `OrderCreated`, nhưng có mục tiêu, tốc độ, lỗi và vòng đời triển khai khác nhau. Nếu một bên tạm thời không hoạt động, bên còn lại vẫn cần tiếp tục xử lý.

Bài thực hành thuộc chương **Thực hành tổng hợp** của module `SPRING_CLOUD_STREAM`. Chúng ta dùng Spring Cloud Stream với mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder cho Kafka, RabbitMQ hoặc Pulsar để xây dựng hai consumer group độc lập trên cùng một destination. Bài đi từ hợp đồng sự kiện, producer, cấu hình binding, triển khai các consumer, đến retry/DLQ, idempotency, quan sát và kiểm thử end-to-end.

## 1. Bài toán nghiệp vụ

Khi khách hàng đặt hàng thành công, Order Service phát một sự kiện:

```text
OrderCreated
    |
    +----> Payment Service
    |         - Kiểm tra yêu cầu thanh toán
    |         - Gửi lệnh authorize/charge tới payment provider
    |         - Ghi nhận kết quả thanh toán
    |
    +----> Notification Service
              - Gửi email xác nhận đã nhận đơn
              - Gửi push notification nếu khách hàng bật tính năng
              - Ghi nhận trạng thái gửi thông báo
```

Hai consumer có các yêu cầu khác nhau:

| Thuộc tính | Payment Service | Notification Service |
|---|---|---|
| Consumer group | `payment-service` | `notification-service` |
| Input destination | `orders.created` | `orders.created` |
| Công việc | Xử lý thanh toán | Gửi thông báo nhận đơn |
| Tác động ngoài broker | Payment provider, payment database | Email/SMS/push provider, notification database |
| Chính sách retry | Theo lỗi payment provider và trạng thái giao dịch | Theo lỗi nhà cung cấp thông báo |
| DLQ | DLQ riêng của thanh toán | DLQ riêng của thông báo |
| Tốc độ xử lý | Phụ thuộc payment provider và giới hạn giao dịch | Phụ thuộc email/SMS/push provider |
| Scale | Theo backlog và giới hạn payment provider | Theo backlog và giới hạn notification provider |
| Idempotency | Theo `eventId` và payment operation key | Theo `eventId` và notification delivery key |

Điều kiện quan trọng là mỗi consumer group phải nhận được **bản sao logic của cùng sự kiện**. Hai nhóm không chia nhau một nửa số message. Các instance trong cùng nhóm mới chia sẻ công việc.

## 2. Phân biệt hai nhóm độc lập với hai consumer cùng nhóm

Đây là điểm cốt lõi của bài thực hành.

```text
                    orders.created
                           |
                    Event: OrderCreated
                           |
                +----------+----------+
                |                     |
                v                     v
       group=payment-service   group=notification-service
                |                     |
          +-----+-----+         +-----+-----+
          |           |         |           |
          v           v         v           v
       Payment 1   Payment 2  Notify 1   Notify 2
```

Trong sơ đồ:

- `Payment 1` và `Payment 2` là các instance cùng thuộc `payment-service`; chúng cạnh tranh để xử lý các message của nhóm thanh toán.
- `Notify 1` và `Notify 2` là các instance cùng thuộc `notification-service`; chúng cạnh tranh để xử lý các message của nhóm thông báo.
- Cả hai nhóm đều nhận `OrderCreated`.
- Một message được xử lý trong nhóm thanh toán không làm mất bản sao mà nhóm thông báo cần nhận.

Nếu cấu hình cả hai binding cùng `group: order-processing`, các instance sẽ ở cùng một nhóm cạnh tranh. Một event có thể được giao cho Payment hoặc Notification tùy cách triển khai, thay vì cả hai cùng nhận. Đó là cấu hình sai đối với yêu cầu của bài.

## 3. Consumer group trong Spring Cloud Stream

Mỗi input binding có thể khai báo `spring.cloud.stream.bindings.<bindingName>.group`. Các consumer group cùng subscribe một destination đều nhận một bản sao dữ liệu đã publish; bên trong mỗi group, chỉ một member nhận một message cụ thể. Đây là mô hình publish-subscribe kết hợp competing consumers.

| Cấu hình | Ý nghĩa |
|---|---|
| `destination: orders.created` | Nguồn sự kiện mà binding đọc |
| `group: payment-service` | Định danh nhóm xử lý thanh toán |
| `group: notification-service` | Định danh nhóm xử lý thông báo |
| Hai group khác nhau | Mỗi nhóm có tiến độ tiêu thụ độc lập |
| Nhiều instance cùng group | Chia tải message trong cùng nhóm |
| Không khai báo group | Binder có thể tạo anonymous group; không phù hợp khi cần subscription bền vững qua vòng đời ứng dụng |

Trong production, luôn đặt group ổn định cho các consumer cần tiếp tục xử lý khi tất cả instance tạm dừng. Không dùng tên Pod, hostname hoặc UUID mới làm group mỗi lần deploy; điều đó tạo nhóm mới và có thể khiến dữ liệu được đọc lại theo offset/position ban đầu.

## 4. Hợp đồng sự kiện `OrderCreated`

Hai service cần thống nhất schema của event. Event mô tả điều đã xảy ra, không chứa lệnh nội bộ yêu cầu service khác phải chạy một hàm cụ thể.

Ví dụ JSON:

```json
{
  "eventId": "evt-20261124-000042",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T09:30:00Z",
  "orderId": "ord-100042",
  "customerId": "cus-9008",
  "currency": "VND",
  "totalAmount": 1250000,
  "paymentMethod": "CARD",
  "notificationPreference": {
    "email": true,
    "push": true
  }
}
```

Ý nghĩa trường:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh ổn định để deduplicate ở từng consumer group |
| `eventType` | Cho biết loại sự kiện |
| `schemaVersion` | Hỗ trợ tiến hóa schema |
| `occurredAt` | Thời điểm nghiệp vụ tạo sự kiện, dùng cho audit và latency |
| `orderId` | Khóa nghiệp vụ của đơn hàng |
| `customerId` | Liên kết khách hàng, cần bảo vệ dữ liệu cá nhân |
| `currency` | Đơn vị tiền tệ của số tiền |
| `totalAmount` | Tổng tiền ở đơn vị nhỏ nhất của currency theo quy ước hợp đồng |
| `paymentMethod` | Phương thức thanh toán đã chọn |
| `notificationPreference` | Tùy chọn thông báo được chụp tại thời điểm tạo đơn |

Không phát số thẻ đầy đủ, CVV, token thanh toán hoặc thông tin xác thực của khách hàng trong event. Payment Service nên lấy credential thanh toán từ vault/provider token được lưu an toàn. Notification Service chỉ sử dụng địa chỉ liên hệ đã được xác thực và chính sách đồng ý phù hợp.

## 5. Tạo kiểu dữ liệu Java dùng chung

Trong ví dụ học tập, hai consumer có thể dùng cùng một record:

```java
import java.time.Instant;

public record OrderCreated(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String orderId,
        String customerId,
        String currency,
        long totalAmount,
        String paymentMethod,
        NotificationPreference notificationPreference) {
}

public record NotificationPreference(
        boolean email,
        boolean push) {
}
```

Trong một hệ thống nhiều service, không nhất thiết đóng gói class Java của Order Service vào JAR dùng chung cho mọi consumer. Hợp đồng có thể được quản lý bằng JSON Schema, Avro hoặc Protobuf và mỗi service tạo model tương ứng. Điều quan trọng là schema tương thích và quy tắc thay đổi field được công bố rõ.

## 6. Producer phát một sự kiện vào destination chung

Order Service phát `OrderCreated` một lần. Spring Cloud Stream `StreamBridge` phù hợp với trường hợp publisher được kích hoạt bởi request hoặc giao dịch nghiệp vụ:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send(
                "orders-out-0",
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", event.eventId())
                        .build());
    }
}
```

Khai báo output binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
```

Producer không cần gửi riêng một bản tới `payment-service` và một bản tới `notification-service`. Broker cùng binder fan-out theo hai consumer group. Điều này tránh việc producer tự quản lý hai đường gửi và phải giải quyết trường hợp gửi thành công cho payment nhưng thất bại với notification.

`StreamBridge.send()` trả về kết quả gửi qua binding/channel; không được diễn giải boolean thành bằng chứng payment đã xử lý, email đã gửi hoặc mọi consumer đã nhận. Để không mất event khi Order Service ghi database rồi process dừng trước khi publish, nên xem xét Transactional Outbox ở phần sau.

## 7. Hai Consumer function trong Spring Cloud Stream

Ta khai báo hai bean độc lập, mỗi bean có một input binding:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderEventConsumers {

    @Bean
    Consumer<OrderCreated> processPayment(PaymentService paymentService) {
        return event -> paymentService.processOrderCreated(event);
    }

    @Bean
    Consumer<OrderCreated> sendNotification(
            NotificationService notificationService) {
        return event -> notificationService.sendOrderReceived(event);
    }
}
```

`PaymentService` và `NotificationService` là service nghiệp vụ do ứng dụng triển khai. Trong ví dụ, mỗi consumer trả về sau khi thao tác bắt buộc đã được hoàn thành hoặc lưu trạng thái xử lý bền vững. Nếu xử lý thất bại, exception cần được truyền ra ngoài theo chính sách error handling đã chọn để binder có thể retry hoặc đưa message vào DLQ.

Chọn cả hai function trong ứng dụng:

```yaml
spring:
  cloud:
    function:
      definition: processPayment;sendNotification
```

Dấu `;` liệt kê hai function độc lập. Không dùng composition `processPayment|sendNotification` trong bài toán này. Composition sẽ đưa output của function trước làm input cho function sau, nghĩa là notification phụ thuộc vào kết quả của payment và không còn là hai consumer độc lập cùng nhận `OrderCreated`.

## 8. Cấu hình hai input binding với hai group riêng

Đây là phần cấu hình quan trọng nhất:

```yaml
spring:
  cloud:
    function:
      definition: processPayment;sendNotification
    stream:
      bindings:
        processPayment-in-0:
          destination: orders.created
          group: payment-service
          content-type: application/json
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
            backOffMaxInterval: 10000

        sendNotification-in-0:
          destination: orders.created
          group: notification-service
          content-type: application/json
          consumer:
            maxAttempts: 5
            backOffInitialInterval: 2000
            backOffMultiplier: 2.0
            backOffMaxInterval: 30000
```

Hai binding có cùng `destination` nhưng `group` khác nhau. Đây là cấu hình fan-out qua consumer groups. Hai retry policy cũng được khai báo riêng: lỗi thanh toán và lỗi thông báo không nhất thiết có cùng thời gian phục hồi.

| Binding | Function | Destination | Group |
|---|---|---|---|
| `processPayment-in-0` | `processPayment` | `orders.created` | `payment-service` |
| `sendNotification-in-0` | `sendNotification` | `orders.created` | `notification-service` |

Nếu muốn triển khai thành hai ứng dụng riêng, mỗi ứng dụng chỉ khai báo function và binding của nó, nhưng giữ nguyên destination/group tương ứng. Không cần khai báo function của service kia trong ứng dụng hiện tại.

## 9. Một ứng dụng hay hai ứng dụng triển khai riêng?

Có thể khai báo hai consumer trong cùng một Spring Boot application để minh họa mô hình. Khi triển khai production, hai service thường nên có lifecycle và resource độc lập:

```text
                     orders.created
                           |
                +----------+----------+
                |                     |
                v                     v
          Payment Deployment     Notification Deployment
          group=payment-service  group=notification-service
          2..8 replicas           1..5 replicas
          payment DB/provider    notification DB/provider
```

| Tiêu chí | Cùng một application | Hai application riêng |
|---|---|---|
| Mã triển khai | Một artifact | Mỗi service có artifact riêng |
| Scale | Scale cả process chứa hai consumer | Scale từng nhóm theo backlog riêng |
| Lỗi khởi động | Một context lỗi có thể ảnh hưởng cả hai | Có thể khởi động độc lập |
| Resource | Chia sẻ CPU, heap, connection pool | Giới hạn tài nguyên riêng |
| Release | Cùng nhịp triển khai | Release độc lập |
| Security | Một identity có thể có nhiều quyền | Có thể cấp quyền tối thiểu riêng |
| Quan sát | Chung process, cần phân biệt binding | Metric/log theo service rõ ràng |

Nếu chạy cùng một JVM, consumer group vẫn độc lập ở broker, nhưng **failure domain của process không độc lập hoàn toàn**. OOM, lỗi cấu hình toàn ứng dụng hoặc shutdown có thể làm cả hai consumer dừng. Tách deployment khi payment và notification cần SLA, scale hoặc quyền truy cập khác nhau.

## 10. Kafka: hai consumer group nhận cùng topic

Với Kafka Binder, mỗi consumer group ánh xạ tới Kafka consumer group riêng. Hai group có committed offset độc lập trên cùng topic:

```text
Kafka topic: orders.created (6 partitions)
                  |
          +-------+-------+
          |               |
          v               v
  group payment-service   group notification-service
    P0..P5 assigned         P0..P5 assigned
      |       |               |       |
   Payment instances       Notification instances
```

Khi publish một record vào partition P2:

- Group `payment-service` đọc record theo offset của group đó.
- Group `notification-service` cũng đọc record theo offset của group riêng.
- Payment có thể commit offset nhanh hơn notification; điều đó không làm notification mất record.
- Nếu payment group dừng, notification group vẫn tiếp tục xử lý.
- Khi payment group chạy lại, nó tiếp tục từ offset đã commit theo chính sách Kafka và retention.

Ví dụ cả hai group có thể có các binding Kafka consumer properties riêng:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processPayment-in-0:
            consumer:
              startOffset: earliest
              enableDlq: true
              dlqName: orders.created.payment.dlt
          sendNotification-in-0:
            consumer:
              startOffset: earliest
              enableDlq: true
              dlqName: orders.created.notification.dlt
```

Đây là **Kafka Binder extended consumer properties**, không phải property chung của mọi binder. `startOffset` chỉ có ý nghĩa khi group chưa có offset được commit; nó không tua lại một group đã có committed offset. Nếu muốn replay dữ liệu đã xử lý, phải có quy trình offset/replay riêng, không chỉ đổi `startOffset`.

Kafka topic cần đủ partition cho mức song song dự kiến của **mỗi group**. Hai group cùng đọc một topic không chia nhau số partition: mỗi group có thể được gán toàn bộ partition, nhưng các instance bên trong group chia partition đó.

## 11. RabbitMQ: một exchange, hai queue theo group

RabbitMQ Binder mặc định ánh xạ destination sang topic exchange. Với consumer group có tên, binder tạo queue riêng cho từng group và bind queue vào exchange. Tên queue mặc định thường theo dạng:

```text
<destination>.<group>

orders.created.payment-service
orders.created.notification-service
```

Một publish tới exchange `orders.created` được route tới cả hai queue. Trong mỗi queue, các instance cùng group cạnh tranh nhận message.

```text
                   exchange orders.created
                         |
                  routing key: #
                   /           \
                  /             \
                 v               v
  queue orders.created.       queue orders.created.
       payment-service            notification-service
          |                              |
      Payment 1/2                   Notification 1/2
```

**Điểm khác Kafka:** RabbitMQ exchange không lưu lại lịch sử message cho một queue được tạo sau. Nếu queue của `notification-service` chưa tồn tại khi producer publish, message cũ không tự xuất hiện trong queue sau này. Với hệ thống cần nhận mọi sự kiện kể cả khi service tạm dừng, phải bảo đảm durable queue/group đã được provision trước và có chính sách lưu trữ phù hợp.

RabbitMQ Binder có `requiredGroups` ở output binding để provision queue cho những group cần nhận message, kể cả khi consumer chưa chạy tại thời điểm gửi. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          producer:
            requiredGroups:
              - payment-service
              - notification-service
```

Đây là property cần kiểm tra với RabbitMQ Binder và topology đang dùng. Nếu hạ tầng đã quản lý queue/exchange bằng IaC, hãy xác minh tên, durability, binding và quyền thay vì để ứng dụng tự khai báo tài nguyên trùng lặp.

## 12. Pulsar: hai subscription độc lập

Trong Apache Pulsar, một topic có thể có nhiều subscription. Mỗi subscription giữ cursor/ack state riêng. Vì vậy hai consumer group của Spring Cloud Stream cần được ánh xạ tới hai subscription khác nhau:

```text
Topic: persistent://acme/orders/orders.created
                         |
              +----------+----------+
              |                     |
              v                     v
 subscription payment-service   subscription notification-service
              |                     |
        Payment consumers      Notification consumers
```

Khi một subscription acknowledge message, cursor của subscription khác không bị tự động tiến theo. Nếu payment đã xử lý event nhưng notification chưa xử lý, notification subscription vẫn giữ backlog của nó.

Trong cấu hình Spring Cloud Stream, vẫn đặt `group` khác nhau cho hai input binding như phần 8. Pulsar Binder sử dụng các thành phần Spring for Apache Pulsar để tạo consumer binding; khi vận hành, cần xác minh tên subscription thực tế, subscription type và vị trí khởi tạo bằng cấu hình binder/cluster của phiên bản đang dùng. Đừng chỉ dựa vào tên bean để suy ra subscription name.

Subscription type quyết định cách các instance trong **một subscription** chia message:

| Subscription type | Hành vi chính | Khi phù hợp |
|---|---|---|
| `Exclusive` | Một consumer active | Luồng đơn giản, không cần nhiều consumer đồng thời |
| `Failover` | Active/standby; với partitioned topic có thể phân chia ownership theo partition | Cần failover và semantics ordering theo partition |
| `Shared` | Nhiều consumer cùng nhận message, không bảo đảm thứ tự tổng thể | Throughput và xử lý độc lập |
| `Key_Shared` | Phân phối theo key, giữ cùng key trên cùng consumer theo semantics Pulsar | Muốn song song giữa key và thứ tự trong key |

Hai subscription payment/notification là hai luồng độc lập. Subscription type chỉ quyết định chia tải bên trong mỗi luồng.

## 13. So sánh fan-out trên ba binder

| Khái niệm Spring Cloud Stream | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Destination | Topic | Exchange/destination | Topic |
| Consumer group | Kafka consumer group | Queue gắn với group | Subscription của consumer binding |
| Bản sao độc lập | Mỗi group có offset riêng | Mỗi group có queue riêng | Mỗi subscription có cursor riêng |
| Instance cùng group | Chia partition | Chia queue | Chia subscription theo subscription type |
| Dữ liệu khi service tạm dừng | Topic giữ theo retention | Durable queue giữ message nếu đã provision | Durable subscription giữ backlog theo retention/policy |
| Điểm cần xác minh | Offset, partition, retention | Queue tồn tại, durable, DLX/routing | Subscription name/type, cursor, retention |

Spring Cloud Stream chuẩn hóa khái niệm `destination` và `group`, nhưng mỗi binder có mô hình broker khác nhau. Không áp dụng cấu hình `kafka.bindings.*` cho RabbitMQ/Pulsar hoặc giả định Rabbit queue được tạo sau sẽ nhận lại các message đã publish.

## 14. Điều gì xảy ra khi Payment Service dừng?

Giả sử cả hai nhóm đã hoạt động, rồi Payment Service bị mất kết nối database trong 10 phút:

```text
orders.created
       |
       +--> payment-service
       |       - Retry theo policy
       |       - Lag/backlog tăng
       |       - Notification group không bị chặn
       |
       +--> notification-service
               - Tiếp tục đọc
               - Gửi thông báo nhận đơn
               - Commit/ack độc lập
```

Kết quả mong muốn:

1. Notification Service tiếp tục gửi thông báo nhận đơn nếu dependency của nó khỏe.
2. Payment Service không đánh dấu giao dịch thành công khi chưa có kết quả xác thực từ payment provider.
3. Message của payment group vẫn được giữ theo semantics của broker và chưa được ack/commit thành công nếu chưa xử lý an toàn.
4. Khi database/payment provider hồi phục, payment group tiếp tục xử lý backlog.
5. Không gửi lại thông báo chỉ vì payment group retry cùng `OrderCreated`.

Nếu hai consumer nằm trong cùng process, lỗi binding có thể tác động lifecycle của process. Tách deployment nếu yêu cầu vận hành đòi hỏi notification tiếp tục ngay cả khi payment application crash.

## 15. Mỗi nhóm có retry policy riêng

Payment và Notification phụ thuộc các dịch vụ ngoài khác nhau. Vì vậy số lần retry và backoff có thể khác:

| Lỗi | Payment | Notification |
|---|---|---|
| Timeout ngắn | Retry hữu hạn, kiểm tra trạng thái giao dịch trước lần thử tiếp | Retry hữu hạn với backoff |
| HTTP 429 từ provider | Tuân thủ `Retry-After`, giới hạn tốc độ | Tuân thủ quota email/SMS provider |
| Credential hết hạn | Dừng/giảm xử lý, cảnh báo cấu hình | Dừng/giảm xử lý, cảnh báo cấu hình |
| Event sai schema | DLQ và điều tra contract | DLQ riêng và điều tra contract |
| Event duplicate | Idempotency theo payment operation | Idempotency theo notification delivery |
| Lỗi vĩnh viễn | Quarantine và xử lý nghiệp vụ | Quarantine; không gửi lặp vô hạn |

Ví dụ cấu hình chung ở phần 8 đã đặt `maxAttempts` khác nhau. `maxAttempts` tính cả lần xử lý đầu tiên trong cấu hình consumer chung; retry/backoff cụ thể còn phụ thuộc binder, imperative/reactive processing và custom error handler. DLQ phải được bật/khai báo theo đúng binder.

## 16. Kafka: DLQ tách riêng theo consumer group

Hai group có thể dùng hai DLT khác nhau để đội payment và notification xử lý độc lập:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processPayment-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.payment.dlt
          sendNotification-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.notification.dlt
```

Kafka Binder cần consumer group tường minh cho DLQ. DLT cũng cần được provision đúng partition count/retention và quyền ghi. Nếu một group lỗi, record được xử lý theo DLT policy của group đó; group còn lại vẫn có offset riêng.

Không dùng chung một consumer group cho cả hai function rồi hy vọng `dlqName` sẽ tách nghiệp vụ. Tên binding và group phải được xác minh trong log/runtime config; DLT record nên giữ `eventId`, source topic, partition/offset, group và nguyên nhân lỗi để truy vết.

## 17. RabbitMQ: DLQ tách theo queue/group

Với RabbitMQ Binder, mỗi group có queue riêng nên có thể cấu hình DLQ riêng cho từng binding:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processPayment-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
          sendNotification-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

Tên queue/DLQ được binder tạo phụ thuộc destination, group và các thuộc tính naming. Xác minh queue thực tế trên broker; không đoán tên DLQ chỉ từ tên function. `requeueRejected: false` giúp tránh đưa delivery thất bại quay lại queue chính theo đường reject tương ứng, còn `autoBindDlq` khai báo DLX/DLQ khi binder được phép provision.

Nếu Payment queue lỗi liên tục, DLQ payment tăng; queue notification không bị lấy mất message bởi payment consumer. Tuy vậy, hai queue vẫn có thể cùng chịu ảnh hưởng nếu RabbitMQ cluster, vhost, disk hoặc network gặp sự cố.

## 18. Pulsar: subscription backlog và DLQ riêng

Pulsar giữ trạng thái ack theo subscription. Khi payment subscription bị lỗi, backlog của nó tăng; notification subscription vẫn có thể tiến cursor. Cần theo dõi:

- Tên topic đầy đủ, ví dụ `persistent://acme/orders/orders.created`.
- Tên subscription tương ứng với payment và notification.
- Subscription type (`Shared`, `Key_Shared`, `Failover` hoặc `Exclusive`).
- Backlog, unacknowledged messages và redelivery của từng subscription.
- Retry letter topic và dead-letter topic của từng nhóm.
- Quyền đọc topic chính và quyền publish retry/DLQ topic.

Pulsar Binder sử dụng cấu hình consumer của Spring for Apache Pulsar; cấu hình retry/DLQ cụ thể phụ thuộc phiên bản binder và API được expose. Không sao chép thuộc tính Kafka `enableDlq` hoặc Rabbit `autoBindDlq` sang Pulsar. Xác minh cấu hình consumer builder/extended binding properties của release đang chạy và test một message lỗi trong môi trường tích hợp.

## 19. Idempotency cho Payment Service

Payment là tác động có rủi ro cao: cùng một `OrderCreated` có thể được giao lại sau timeout, process crash hoặc ack/commit chưa hoàn tất. Nếu mỗi lần nhận đều gọi charge mới, khách hàng có thể bị trừ tiền nhiều lần.

Một payment operation cần khóa idempotency ổn định, ví dụ `payment:{orderId}:initial`. Quy trình minh họa:

```text
Receive OrderCreated(eventId, orderId)
          |
          v
Check processed event / payment operation
          |
    +-----+------+
    |            |
 already done   new operation
    |            |
    v            v
 return result   reserve idempotency key
                 call provider with same key
                 persist provider result
                 mark event processed
```

Ví dụ bảng dữ liệu:

```sql
CREATE TABLE payment_operation (
    order_id          VARCHAR(100) PRIMARY KEY,
    event_id          VARCHAR(100) NOT NULL,
    idempotency_key   VARCHAR(160) NOT NULL UNIQUE,
    status            VARCHAR(32) NOT NULL,
    provider_reference VARCHAR(160),
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE payment_consumed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Đây là schema minh họa; phải điều chỉnh kiểu dữ liệu, transaction và unique constraints theo database. Nếu provider hỗ trợ idempotency key, dùng cùng key khi retry một payment operation. Nếu timeout xảy ra sau khi provider đã charge nhưng trước khi response về, truy vấn trạng thái theo key/reference trước khi tạo giao dịch mới.

Không coi `eventId` của message mới sau replay là một payment operation mới nếu nó đại diện cùng một sự kiện nghiệp vụ gốc. Khi replay, giữ `originalEventId` và idempotency key ban đầu.

## 20. Idempotency cho Notification Service

Notification cũng có thể bị giao lại. Một event được gửi email hai lần sẽ làm giảm trải nghiệm và có thể gửi SMS tốn phí. Tạo delivery key theo loại thông báo và người nhận:

```text
notificationKey = eventId + channel + recipientId + templateVersion
```

Ví dụ bảng:

```sql
CREATE TABLE notification_delivery (
    notification_key VARCHAR(300) PRIMARY KEY,
    event_id          VARCHAR(100) NOT NULL,
    channel           VARCHAR(24) NOT NULL,
    recipient_id      VARCHAR(100) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    provider_reference VARCHAR(160),
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);
```

Notification Service kiểm tra delivery key trước khi gửi. Nếu đã `SENT`, lần redelivery chỉ xác nhận đã xử lý mà không gọi provider lần nữa. Nếu provider hỗ trợ idempotency, truyền cùng delivery key. Nếu provider không hỗ trợ, phải xử lý cửa sổ không chắc chắn khi request timeout nhưng nhà cung cấp có thể đã gửi thành công; trạng thái `UNKNOWN` cần reconciliation thay vì retry mù.

Payment và notification có **hai deduplication ledger khác nhau**. Việc payment đã ghi `eventId` không có nghĩa notification được phép bỏ qua event đó; mỗi group phải lưu trạng thái xử lý của chính nó.

## 21. Ack/commit sau khi tác động đã an toàn

Một consumer không nên coi message hoàn tất trước khi side effect bắt buộc được lưu bền vững. Ví dụ Payment Service:

```text
Broker delivers OrderCreated
       |
       v
DB transaction: create/reserve payment operation
       |
       v
Call payment provider with idempotency key
       |
       v
Persist result / reconcile uncertain result
       |
       v
Handler completes -> binder acknowledges/commits per configuration
```

Trong thực tế, gọi payment provider không thể nằm trong transaction ACID của database. Có thể dùng trạng thái `PENDING`, workflow/saga và reconciliation job. Nếu process dừng sau khi provider đã charge nhưng trước khi database ghi kết quả, lần nhận lại phải tra cứu provider theo idempotency key/reference.

Notification Service cũng cần phân biệt `SENT`, `FAILED_RETRYABLE`, `FAILED_PERMANENT` và `UNKNOWN`. Không ack một event chỉ vì đã đưa nó vào executor trong memory; nếu process chết trước khi executor xử lý, công việc có thể mất.

## 22. Transactional Outbox ở Order Service

Có một cửa sổ lỗi ở producer:

```text
1. Order Service commit order vào DB.
2. Process crash trước khi publish OrderCreated.
3. Đơn hàng tồn tại nhưng hai consumer không nhận event.
```

Transactional Outbox giải quyết bằng cách ghi đơn hàng và outbox record trong cùng một transaction database:

```sql
BEGIN;

INSERT INTO orders(order_id, customer_id, status, total_amount)
VALUES ('ord-100042', 'cus-9008', 'CREATED', 1250000);

INSERT INTO outbox_event(event_id, aggregate_id, event_type, payload, status)
VALUES ('evt-20261124-000042', 'ord-100042', 'OrderCreated', :json, 'NEW');

COMMIT;
```

Một outbox publisher đọc record `NEW`, gửi tới `orders.created` bằng Spring Cloud Stream/`StreamBridge`, sau đó cập nhật trạng thái gửi. Nếu publisher crash sau khi broker nhận event nhưng trước khi đánh dấu `SENT`, nó có thể gửi lại; vì vậy hai consumer vẫn phải idempotent theo `eventId`.

Outbox giúp tránh mất event giữa database commit và publish, nhưng không biến toàn bộ luồng producer → broker → hai database → payment provider/email provider thành một distributed transaction duy nhất.

## 23. Hai nhóm độc lập không đồng nghĩa thứ tự giữa hai nhóm

Kafka có thể ghi `OrderCreated` vào một partition; cả hai group đọc cùng log nhưng tiến độ và thời điểm xử lý khác nhau. RabbitMQ có hai queue riêng; consumer queue payment có thể nhanh hơn queue notification. Pulsar có hai subscription cursor riêng.

Vì vậy không được giả định:

```text
Payment xử lý xong trước -> Notification chắc chắn xử lý sau
```

Hai handler có thể chạy song song. Nếu notification cần biết kết quả payment, hãy phát event kết quả riêng như `PaymentAuthorized` hoặc `PaymentDeclined`, rồi cho notification workflow xử lý event đó. Không dùng việc đọc chung `OrderCreated` để suy ra payment đã thành công.

Nếu business cần gửi email "đơn hàng đã thanh toán", trigger nên là `PaymentAuthorized`, không phải `OrderCreated`. Nếu chỉ gửi email "đã nhận đơn", `OrderCreated` là sự kiện phù hợp.

## 24. Ordering theo `orderId` trong từng nhóm

Hai consumer group có thể có thứ tự và tốc độ xử lý riêng. Nếu một nhóm cần giữ thứ tự cho cùng đơn hàng:

- Với Kafka, producer gán record key là `orderId`; các event cùng key vào cùng partition. Mỗi group có assignment partition riêng.
- Với RabbitMQ, dùng routing key/queue partitioning có thiết kế; nhiều consumer cùng queue có thể hoàn thành khác thứ tự nếu xử lý bất đồng bộ.
- Với Pulsar, chọn subscription type và message key phù hợp; `Key_Shared` có thể giữ phân phối theo key, cần kiểm tra batching semantics.

Trong ví dụ event `OrderCreated` có thể đặt key là `orderId`. Payment và Notification vẫn nhận bản sao độc lập vì key chỉ quyết định partition/routing trong từng destination, không gộp hai group thành một.

## 25. Schema evolution khi hai nhóm triển khai ở nhịp khác nhau

Payment và Notification có thể release vào thời điểm khác nhau. Khi Order Service thêm field, event cần giữ tương thích:

| Thay đổi | Rủi ro | Quy tắc an toàn |
|---|---|---|
| Thêm field optional | Consumer cũ không biết field | Có default/null semantics rõ |
| Đổi tên field | Consumer cũ không đọc được | Thêm field mới, duy trì field cũ trong giai đoạn chuyển đổi |
| Đổi kiểu `totalAmount` | Deserialize lỗi hoặc sai số | Version schema và migration có kiểm soát |
| Xóa field | Consumer cũ cần field bị mất | Chỉ xóa sau khi mọi consumer đã nâng cấp |
| Đổi meaning của field | Deserialize vẫn thành công nhưng nghiệp vụ sai | Dùng field/event type/version mới |

Không đưa logic riêng của payment (ví dụ provider authorization token) vào schema dùng chung cho notification. Event contract chỉ nên chứa dữ liệu cần thiết cho các subscriber và tuân thủ nguyên tắc tối thiểu hóa dữ liệu.

## 26. Retry và DLQ độc lập theo service

Mỗi consumer group có thể có retry/DLQ policy riêng:

```text
orders.created
     |
     +--> payment-service
     |       retry policy P
     |       orders.created.payment.dlt
     |
     +--> notification-service
             retry policy N
             orders.created.notification.dlt
```

Một payment event lỗi không nên làm Notification Service phải retry cùng message nếu notification đã xử lý thành công. Ngược lại, email provider lỗi không nên khiến Payment Service gọi lại payment provider.

| Consumer | Retry phù hợp | DLQ dùng cho |
|---|---|---|
| Payment | Timeout tạm thời, provider 429/503, lỗi DB tạm thời | Event sai schema, trạng thái không thể xử lý, vượt retry limit |
| Notification | Timeout email/SMS/push, provider throttling | Địa chỉ không hợp lệ, template/schema lỗi, vượt retry limit |

Không retry lỗi vĩnh viễn với backoff vô hạn. Dùng bounded retry, exponential backoff, jitter và parking lot/triage. Khi replay, giữ `originalEventId` để không tạo payment hoặc notification duplicate.

## 27. Kafka: retry/DLT per binding

Ví dụ Kafka Binder cho hai consumer group:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processPayment-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.payment.dlt
          sendNotification-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.notification.dlt
```

Đây là extended property của Kafka Binder. Cả hai input binding cần group tường minh. DLT phải có partition và quyền ghi phù hợp; với partitioned topic, xác minh partition routing của DLT. Nếu app có custom error handler, cần kiểm tra handler đó có thay thế binder DLQ path hay không.

Khi payment DLT tăng, chỉ payment workflow cần điều tra/replay. Notification group đã commit offset riêng và không tự động phát lại chỉ vì payment DLT có message.

## 28. RabbitMQ: queue và DLQ per group

Ví dụ RabbitMQ Binder:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processPayment-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
          sendNotification-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
```

Với group có tên, RabbitMQ Binder provision queue riêng cho từng group và bind vào destination exchange. DLQ naming/routing phụ thuộc cấu hình binder. Xác minh queue/exchange thực tế trong đúng vhost, nhất là khi dùng prefix, partitioning hoặc queue được provision bởi IaC.

Nếu một queue dùng Single Active Consumer, scale thêm instance không tạo thêm active consumer cho queue đó. Điều này ảnh hưởng throughput của riêng group tương ứng, không làm mất queue của group kia.

## 29. Pulsar: subscription type và cursor độc lập

Pulsar giữ cursor cho từng subscription. Hai subscription cùng topic có thể có backlog khác nhau và xử lý với tốc độ khác nhau. Hãy theo dõi stats theo từng subscription, không chỉ tổng topic.

Nếu chọn `Shared`, nhiều consumer trong một subscription chia message, nhưng không có bảo đảm thứ tự tổng thể. Nếu cần thứ tự theo key, cân nhắc `Key_Shared` và cấu hình producer key/batching phù hợp. `Failover` phù hợp mô hình active/standby hoặc partitioned failover; `Exclusive` chỉ có một consumer.

Retry letter topic và dead letter policy phải cấu hình theo Pulsar client/binder release thực tế. Tách tên retry/DLQ cho payment và notification để hai workflow không dùng chung retry state. Xác minh ACL cho subscription và producer ghi retry/DLQ topic.

## 30. Scale độc lập theo backlog

Hai nhóm có thể cần số replica khác nhau. Ví dụ:

| Chỉ số | Payment | Notification |
|---|---:|---:|
| Backlog hiện tại | 18.000 | 2.000 |
| Throughput mỗi Pod (benchmark) | 120 event/s | 500 event/s |
| Replica mong muốn | 4 | 2 |
| Max replica | 8 | 5 |
| Bottleneck chính | Payment provider quota | Email/SMS provider quota |

Không dùng cùng một autoscaler/metric để scale cả hai Deployment. Với Kafka, mỗi group có lag riêng; KEDA Kafka scaler cần trỏ đúng `consumerGroup` và topic. Với RabbitMQ, scaler phải đo đúng queue group. Với Pulsar, scaler phải đo đúng subscription. Nếu payment backlog tăng, notification Deployment không cần scale chỉ vì cùng destination.

Đặt max replica theo năng lực downstream. Tăng payment consumer quá nhanh có thể vượt giới hạn provider và tạo nhiều lỗi 429; tăng notification quá nhanh có thể vượt email quota hoặc gây rate limit.

## 31. Security và quyền truy cập tối thiểu

Hai service không nhất thiết cần cùng quyền broker hoặc cùng credential ngoài:

| Thành phần | Quyền cần thiết |
|---|---|
| Order Service producer | Produce vào `orders.created` |
| Payment Service consumer | Consume từ destination/group payment; publish payment result nếu có |
| Notification Service consumer | Consume từ destination/group notification |
| Payment DLQ worker | Read payment DLT và replay theo quy trình được phép |
| Notification DLQ worker | Read notification DLT và replay theo quy trình được phép |

Không cấp Notification Service quyền đọc payment database hoặc payment provider secret nếu không cần. Không cấp Payment Service quyền truy cập token email/SMS. Với Kafka, cấu hình ACL theo topic/group; với RabbitMQ, giới hạn vhost/exchange/queue; với Pulsar, giới hạn tenant/namespace/topic và role. Credential scaler/monitoring cũng nên tách khỏi runtime consumer.

## 32. Quan sát trạng thái từng nhóm

Metric cần gắn nhãn `service`, `binding`, `destination`, `group` và `outcome` ở mức cardinality hợp lý:

| Metric | Payment | Notification |
|---|---|---|
| Consumer lag/backlog | Theo `payment-service` | Theo `notification-service` |
| Processing rate | Payment operation/s | Notification delivery/s |
| Processing latency | p50/p95/p99 authorize | p50/p95/p99 delivery |
| Retry count | Payment retry | Notification retry |
| DLQ count | Payment DLT | Notification DLT |
| Duplicate skipped | Payment idempotency | Notification idempotency |
| Error rate | Provider/DB/business | Email/SMS/push/template |
| Oldest event age | Tuổi event chưa xử lý | Tuổi event chưa xử lý |

Một dashboard tổng destination không đủ: payment có thể lag 20 phút trong khi notification lag bằng 0. Cảnh báo theo từng group để đội đúng service phản ứng.

## 33. Kiểm thử unit cho từng consumer

Unit test nên xác minh logic nghiệp vụ và idempotency riêng:

```java
@Test
void paymentConsumerUsesOrderIdempotency() {
    OrderCreated event = sampleOrderCreated();

    paymentService.processOrderCreated(event);

    verify(paymentGateway).authorize(
            eq(event.orderId()),
            eq("payment:" + event.orderId() + ":initial"));
}

@Test
void notificationConsumerUsesDeliveryKey() {
    OrderCreated event = sampleOrderCreated();

    notificationService.sendOrderReceived(event);

    verify(notificationGateway).send(
            eq(event.customerId()),
            eq("order-received"),
            contains(event.eventId()));
}
```

Đây là ví dụ định hướng; method signature và mock setup phải khớp với interface thực tế của ứng dụng. Unit test không chứng minh broker fan-out hoặc offset/subscription độc lập.

## 34. Test Binder: kiểm tra wiring và payload

Spring Cloud Stream Test Binder giúp gửi message vào input destination và kiểm tra output trong test context. Nó hữu ích để kiểm tra function được bind và payload/header được chuyển đổi, nhưng không mô phỏng đầy đủ broker consumer group.

Các kiểm tra phù hợp:

- `processPayment-in-0` nhận `OrderCreated` với content type đúng.
- `sendNotification-in-0` nhận cùng schema.
- Consumer gọi đúng service nghiệp vụ.
- Function phát event kết quả (nếu có) đúng destination.
- Exception được quan sát theo cấu hình test.

Không dùng Test Binder làm bằng chứng duy nhất rằng Kafka có hai group offset, RabbitMQ có hai durable queues hoặc Pulsar có hai subscription độc lập. Cần integration test với broker thực hoặc Testcontainers.

## 35. Integration test: chứng minh cả hai group đều nhận một event

Kịch bản tối thiểu với broker thật:

1. Khởi động Kafka/RabbitMQ/Pulsar test broker.
2. Khởi động Payment consumer với group `payment-service`.
3. Khởi động Notification consumer với group `notification-service`.
4. Publish đúng một `OrderCreated` có `eventId` duy nhất.
5. Chờ payment audit ghi nhận `eventId`.
6. Chờ notification audit ghi nhận cùng `eventId`.
7. Xác minh mỗi group có đúng một xử lý thành công.

Kết quả mong đợi:

```text
Published eventId: evt-test-001

Payment audit:
  evt-test-001 -> PROCESSED

Notification audit:
  evt-test-001 -> SENT
```

Không chỉ kiểm tra hai method đã được gọi trong cùng JVM; phải xác minh broker routing/subscription thực tế để phát hiện cấu hình vô tình dùng chung group.

## 36. Integration test: nhiều instance trong cùng group

Chạy hai Payment instances cùng `payment-service` và hai Notification instances cùng `notification-service`. Publish một tập event có ID khác nhau.

Điều cần xác minh:

- Payment instances chia công việc; một event không bị xử lý đồng thời bởi cả hai instance trong cùng group theo mô hình broker bình thường.
- Notification instances cũng chia công việc độc lập.
- Mỗi event vẫn được xử lý một lần logic ở **mỗi group**.
- Mỗi event có thể được xử lý bởi một Payment instance và một Notification instance.
- Khi tăng instance, không đổi group name.

Nếu dùng Kafka, số consumer có partition bị giới hạn bởi partition count trong mỗi group. Nếu dùng RabbitMQ, queue của mỗi group có nhiều consumer cạnh tranh. Nếu dùng Pulsar, subscription type quyết định chia tải trong subscription.

## 37. Integration test: dừng một nhóm

Kịch bản quan trọng để chứng minh tính độc lập:

1. Khởi động cả hai service.
2. Dừng toàn bộ Payment instances (giữ group/queue/subscription bền vững).
3. Publish 10 `OrderCreated` events.
4. Xác minh Notification Service xử lý đủ 10 event.
5. Xác minh payment backlog/lag tăng hoặc message được giữ theo broker policy.
6. Khởi động lại Payment Service.
7. Xác minh Payment Service xử lý các event đang chờ theo offset/cursor/queue.
8. Xác minh Notification không gửi lại 10 thông báo chỉ vì Payment khởi động lại.

Với RabbitMQ, queue của payment phải tồn tại/durable trong thời gian consumer dừng; dùng provisioning/`requiredGroups` phù hợp nếu producer vẫn phát event. Với Kafka/Pulsar, xác minh retention và subscription/offset policy đủ dài cho thời gian gián đoạn.

## 38. Integration test: lỗi và DLQ độc lập

Tạo lỗi chỉ trong Payment Service, ví dụ payment provider test trả 503. Xác minh:

- Payment group retry theo chính sách của nó.
- Notification group vẫn xử lý thành công.
- Sau khi hết retry, payment event đi vào payment DLT/queue theo cấu hình.
- Notification không có bản ghi lỗi chỉ vì payment thất bại.
- Khi replay payment event sau khi provider phục hồi, idempotency không tạo giao dịch trùng.

Lặp lại với lỗi chỉ trong Notification Service (ví dụ email provider trả 429). Payment vẫn phải giữ trạng thái thanh toán chính xác; notification retry/DLQ độc lập.

## 39. Integration test: duplicate delivery và crash window

Broker thường cung cấp at-least-once trong nhiều cấu hình. Kiểm thử các cửa sổ:

| Điểm crash | Rủi ro | Kết quả cần có |
|---|---|---|
| Trước khi DB ghi | Message được giao lại | Xử lý bình thường khi nhận lại |
| Sau DB commit, trước ack/offset commit | Message được giao lại | Idempotency bỏ qua side effect trùng |
| Sau provider thành công, trước khi ghi trạng thái | Không chắc provider đã thực hiện | Tra cứu bằng idempotency key/reference |
| Sau publish event kết quả, trước khi đánh dấu outbox sent | Event kết quả có thể publish lại | Consumer downstream deduplicate |
| Sau email provider thành công, trước khi ghi `SENT` | Có thể gửi email lần nữa | Provider idempotency hoặc trạng thái `UNKNOWN` + reconciliation |

Không tuyên bố exactly-once cho toàn bộ luồng chỉ vì Kafka transaction hoặc một binder có cấu hình exactly-once. Database và payment/email provider bên ngoài cần cơ chế idempotency/reconciliation riêng.

## 40. Theo dõi lag/backlog độc lập

Ví dụ dashboard trong một thời điểm:

| Metric | `payment-service` | `notification-service` |
|---|---:|---:|
| Backlog | 12.500 | 120 |
| Processing rate | 150 event/s | 450 event/s |
| Error rate | 8% | 0,2% |
| Retry rate | 7% | 0,1% |
| Oldest event age | 95 giây | 2 giây |
| Replica hiện tại | 4 | 2 |

Từ số liệu này, chỉ Payment Service cần điều tra sâu. Tăng Notification replicas không giải quyết payment backlog. Trước khi tăng payment replicas, phải kiểm tra payment provider quota, database capacity, partition assignment và tỉ lệ lỗi.

Với Kafka, đọc lag theo từng consumer group. Với RabbitMQ, đọc depth của queue tương ứng từng group và phân biệt ready/unacknowledged. Với Pulsar, đọc backlog theo từng subscription. Không gộp các metric này thành một chỉ số chung mà bỏ mất danh tính nhóm.

## 41. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ Payment hoặc Notification nhận event | Hai binding cùng group hoặc destination cấu hình sai | Kiểm tra `group` riêng và binding name |
| Một event chỉ đến một service | Dùng competing consumers trong cùng group | Tạo group/subscription/queue riêng cho từng service |
| Notification không nhận event khi đang dừng | Rabbit queue chưa được provision/durable hoặc retention không đủ | Tạo queue trước, kiểm tra `requiredGroups`/durability |
| Service khởi động lại đọc lại nhiều event | Group name đổi hoặc offset/subscription reset | Giữ group ổn định, kiểm tra initial offset/cursor |
| Payment bị charge hai lần | Thiếu idempotency key/reconciliation | Dùng operation key ổn định và unique constraint |
| Email gửi hai lần | Redelivery sau provider success nhưng trước khi ghi trạng thái | Delivery ledger, provider idempotency hoặc reconciliation |
| Payment backlog tăng nhưng notification bình thường | Payment dependency chậm hoặc retry lỗi | Điều tra riêng payment provider/DB và group lag |
| Cả hai cùng dừng | Cùng process hoặc broker/cluster chung gặp sự cố | Tách deployment nếu cần failure isolation; kiểm tra broker |
| RabbitMQ tạo anonymous queue mới mỗi lần | Không đặt group | Dùng group bền vững và kiểm tra queue provisioning |
| Kafka consumer dư nhưng không xử lý | Consumer/concurrency vượt partition count | Tăng partition có kế hoạch hoặc giảm concurrency |
| Pulsar hai service đọc cùng subscription | Subscription name/group bị cấu hình trùng | Dùng hai subscription độc lập |
| DLQ của payment nhận cả lỗi notification | Hai binding dùng chung DLQ hoặc sai tên binding | Cấu hình DLQ riêng theo input binding |

## 42. Bài thực hành tổng hợp theo từng bước

Thực hiện trong môi trường phát triển hoặc staging:

**Bước 1 — Chuẩn bị destination và event contract.** Chọn `orders.created`, định nghĩa `OrderCreated`, tạo `eventId` ổn định và thống nhất `schemaVersion`.

**Bước 2 — Tạo producer.** Order Service gửi một event qua output binding `orders-out-0`. Nếu cần bảo đảm không mất event giữa DB commit và publish, triển khai outbox.

**Bước 3 — Tạo Payment consumer.** Khai báo `Consumer<OrderCreated>` tên `processPayment`, group `payment-service`, idempotency key và retry/DLQ riêng.

**Bước 4 — Tạo Notification consumer.** Khai báo `Consumer<OrderCreated>` tên `sendNotification`, group `notification-service`, delivery key và retry/DLQ riêng.

**Bước 5 — Cấu hình hai function độc lập.** Đặt `spring.cloud.function.definition=processPayment;sendNotification`, hai binding cùng destination nhưng group khác nhau.

**Bước 6 — Kiểm thử fan-out.** Publish một event và xác minh cả hai service đều ghi nhận cùng `eventId`.

**Bước 7 — Kiểm thử scale.** Chạy nhiều instance trong mỗi group, xác minh chia tải trong nhóm và không mất bản sao giữa nhóm.

**Bước 8 — Kiểm thử lỗi độc lập.** Tắt payment provider hoặc giả lập 503; notification vẫn gửi. Sau đó giả lập email provider 429; payment vẫn xử lý.

**Bước 9 — Kiểm thử dừng/khởi động.** Dừng một service, tiếp tục publish event, rồi khởi động lại và xác minh backlog được xử lý theo broker policy.

**Bước 10 — Kiểm thử duplicate/replay.** Gửi lại cùng `eventId`; mỗi group phải tránh side effect trùng theo ledger riêng.

## 43. Tiêu chí nghiệm thu

Bài thực hành được xem là đạt khi chứng minh được:

- Một `OrderCreated` được publish một lần tới destination chung.
- `payment-service` và `notification-service` có group riêng, nhận cùng event độc lập.
- Nhiều instance cùng group chia tải, không biến thành nhiều subscription độc lập ngoài ý muốn.
- Dừng một service không làm group còn lại ngừng xử lý trong điều kiện broker vẫn khỏe.
- Retry và DLQ được cấu hình/quan sát độc lập theo binding.
- Payment và notification đều có idempotency riêng.
- Restart/rebalance/redelivery không tạo payment hoặc notification trùng.
- Dashboard hiển thị lag/backlog, error, retry và DLQ theo từng group.
- Schema và quyền truy cập chỉ cung cấp dữ liệu cần thiết cho mỗi service.
- Có integration test broker thật chứng minh fan-out, pause/resume và failure isolation.

## 44. Câu hỏi tự kiểm tra

1. Vì sao hai binding cùng destination nhưng khác `group` đều nhận một bản sao event?
2. Nếu hai consumer có cùng group, message được phân phối thế nào?
3. Tại sao không nên dùng group name chứa Pod ID hoặc UUID mới mỗi lần deploy?
4. Kafka offset của `payment-service` có làm tiến offset của `notification-service` không?
5. RabbitMQ cần queue riêng cho từng group như thế nào và tại sao queue phải tồn tại trước khi publish nếu muốn giữ message?
6. Pulsar subscription cursor độc lập có ý nghĩa gì khi một service dừng?
7. Vì sao `processPayment;sendNotification` khác `processPayment|sendNotification`?
8. Nếu payment provider đã charge nhưng consumer crash trước khi ack, cơ chế nào ngăn charge lần hai?
9. Nếu email đã gửi nhưng database chưa ghi `SENT`, Notification Service nên xử lý trạng thái không chắc chắn thế nào?
10. Vì sao payment và notification cần DLQ riêng?
11. Làm sao chứng minh Notification Service vẫn nhận event khi Payment Service dừng?
12. Vì sao Test Binder không đủ để chứng minh hai Kafka consumer group hoặc hai RabbitMQ queue được tạo đúng?

## Kết luận

Để Payment Service và Notification Service nhận cùng một `OrderCreated` một cách độc lập, hãy publish một event tới destination chung và khai báo **hai input binding có hai consumer group khác nhau**. Các instance trong mỗi group chia sẻ công việc; hai group có tiến độ, retry, DLQ và khả năng scale riêng. Kafka thực hiện điều này bằng consumer group/offset riêng, RabbitMQ bằng queue riêng bind vào exchange, còn Pulsar bằng subscription/cursor riêng. Mỗi service cần idempotency cho side effect của mình, xử lý at-least-once, theo dõi backlog riêng và có integration test chứng minh fan-out cũng như khả năng một nhóm tiếp tục hoạt động khi nhóm kia gặp sự cố.

## Tài liệu tham khảo

- Spring Cloud Stream — Consumer Groups: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html
- Spring Cloud Stream — Functional Binding Names: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html
- Spring Cloud Stream — Binding Properties: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html
- Spring Cloud Stream — Producing and Consuming Messages / StreamBridge: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html
- Spring Cloud Stream — Kafka Binder Reference: https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html
- Spring Cloud Stream — RabbitMQ Binder Reference: https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Spring Cloud Stream — Test Binder: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html
- Apache Kafka — Consumer Groups and Documentation: https://kafka.apache.org/documentation/
- RabbitMQ — Exchanges and Queues: https://www.rabbitmq.com/docs/exchanges
- RabbitMQ — Consumers: https://www.rabbitmq.com/docs/consumers
- Apache Pulsar — Messaging and Subscriptions: https://pulsar.apache.org/docs/4.0.x/concepts-messaging/
