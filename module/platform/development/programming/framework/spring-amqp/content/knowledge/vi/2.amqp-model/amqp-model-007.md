# Consumer acknowledgement và publisher confirm là hai cơ chế độc lập

Trong mô hình AMQP của RabbitMQ, một message đi qua **hai ranh giới trách nhiệm khác nhau**: ứng dụng phát message giao message cho broker, sau đó broker giao message cho consumer. Spring AMQP hỗ trợ cả hai chiều thông qua `RabbitTemplate` và `@RabbitListener`, nhưng phản hồi ở chiều này **không thay thế** phản hồi ở chiều kia.

Ví dụ: dịch vụ đặt hàng gửi sự kiện `order.created` bằng `RabbitTemplate`. RabbitMQ có thể xác nhận đã tiếp nhận lần publish đó, trong khi dịch vụ xử lý đơn hàng vẫn chưa nhận, xử lý lỗi, hoặc chưa xác nhận message. Vì vậy, câu hỏi “broker đã nhận message chưa?” khác hoàn toàn câu hỏi “consumer đã xử lý xong message chưa?”.

## 1. Phân biệt phạm vi xác nhận

| Khía cạnh | Publisher confirm | Consumer acknowledgement |
|---|---|---|
| Ai phát tín hiệu? | RabbitMQ gửi phản hồi về **publisher** | Consumer gửi phản hồi về **RabbitMQ** |
| Đang xác nhận điều gì? | Trạng thái RabbitMQ xử lý một lần **publish** | Trạng thái consumer xử lý một lần **delivery** |
| Chiều tín hiệu | Broker → publisher | Consumer → broker |
| Phía Spring AMQP | `RabbitTemplate`, `ConfirmCallback`, `CorrelationData` | `@RabbitListener`, chế độ ACK và `Channel.basicAck/basicNack/basicReject` |
| Mã định danh gắn với phản hồi | Số thứ tự publish trên channel phát; có thể gắn `CorrelationData` ở phía ứng dụng | `deliveryTag` trên channel nhận |
| ACK thành công có nghĩa là... | Broker đã xác nhận lần publish theo cơ chế publisher confirms | Broker có thể coi delivery tương ứng đã được consumer xác nhận và loại khỏi hàng đợi |
| ACK **không** chứng minh | Có consumer đã nhận/xử lý; message chắc chắn được định tuyến đến queue | Publisher đã nhận confirm; tác vụ nghiệp vụ chắc chắn sẽ không phát sinh trùng lặp |

```mermaid
sequenceDiagram
    participant P as Publisher (RabbitTemplate)
    participant B as RabbitMQ (exchange/queue)
    participant C as Consumer (@RabbitListener)
    P->>B: basic.publish(exchange, routingKey, message)
    par Phản hồi về phía publisher
        B-->>P: publisher confirm (basic.ack / basic.nack)
    and Phản hồi về phía consumer
        B->>C: basic.deliver(message, deliveryTag)
        C-->>B: consumer basic.ack / basic.nack / basic.reject
    end
    Note over P,C: Hai phản hồi thuộc hai channel/vòng đời riêng; thứ tự thực tế có thể khác nhau.
```

Chú ý: giao thức AMQP 0-9-1 sử dụng tên lệnh `basic.ack` ở cả hai hướng. **Trùng tên lệnh không có nghĩa là chung ý nghĩa.** `deliveryTag` của consumer không được dùng để đối chiếu với số thứ tự publish của publisher; cả hai chỉ có ý nghĩa trong channel tương ứng.

## 2. Consumer acknowledgement: broker cần biết delivery đã được xử lý ra sao

Khi manual acknowledgement được bật, broker đưa message vào trạng thái **unacked** sau khi giao cho consumer. Ứng dụng quyết định thời điểm phản hồi:

- `channel.basicAck(deliveryTag, false)`: xác nhận delivery đã xử lý; RabbitMQ giải phóng delivery đó khỏi trạng thái unacked.
- `channel.basicNack(deliveryTag, false, true)`: thông báo không xử lý thành công và yêu cầu **requeue**. Message có thể được giao lại, kể cả cho một consumer khác.
- `channel.basicNack(deliveryTag, false, false)` hoặc `channel.basicReject(deliveryTag, false)`: từ chối và **không requeue**; message đi tới dead-letter exchange nếu queue có cấu hình dead-letter phù hợp, nếu không thì bị loại bỏ.

Với `basicAck`/`basicNack`, tham số `multiple=false` giới hạn thao tác vào **một delivery tag**. Khi `multiple=true`, broker có thể áp dụng ACK/NACK cho nhiều delivery chưa xác nhận trên cùng channel đến tag đó; dùng tùy tiện dễ xác nhận nhầm những message chưa xử lý xong.

Nếu channel/connection của consumer đóng khi còn delivery chưa được xác nhận, RabbitMQ có thể đưa các message unacked trở lại hàng đợi để giao lại. Điều này giúp tránh mất việc khi consumer chết, nhưng cũng tạo khả năng **xử lý lặp**: nghiệp vụ đã ghi dữ liệu thành công, rồi tiến trình chết trước khi gửi `basicAck`.

### Chế độ ACK trong Spring AMQP

Ba chế độ listener thường gặp:

| Chế độ | Cách hoạt động |
|---|---|
| `AcknowledgeMode.AUTO` | **Listener container** tự ACK khi xử lý thành công; tự áp dụng luồng từ chối/xử lý lỗi khi listener ném exception. |
| `AcknowledgeMode.MANUAL` | Ứng dụng phải chủ động gửi ACK/NACK/REJECT, thường sử dụng `com.rabbitmq.client.Channel`. |
| `AcknowledgeMode.NONE` | Dùng chế độ không đợi consumer acknowledgement ở phía broker (`autoAck`); broker không chờ callback xử lý nghiệp vụ. |

Tên `AUTO` của **Spring listener container** dễ gây nhầm lẫn: đây là *container tự xác nhận sau khi listener xử lý*, khác với chế độ RabbitMQ `autoAck=true` (Spring `NONE`). Trong bài này dùng `MANUAL` để nhìn rõ điểm quyết định ACK.

Quy tắc thiết kế là **chỉ ACK sau khi phần việc nghiệp vụ cần bảo vệ đã hoàn tất**. Nếu có giao dịch cơ sở dữ liệu, hãy để giao dịch commit thành công trước khi ACK; không ACK ngay khi vừa nhận message. Với lỗi tạm thời, cần chính sách retry có giới hạn hoặc trì hoãn thích hợp thay vì `requeue=true` vô hạn tạo vòng lặp tiêu tốn CPU. Với lỗi dữ liệu vĩnh viễn, thường từ chối không requeue và chuyển DLQ để kiểm tra.

## 3. Publisher confirm: broker phản hồi về lần publish

Publisher confirm được bật trên **channel phát message**. Sau khi publisher gửi `basic.publish`, RabbitMQ phản hồi bất đồng bộ bằng ACK hoặc NACK gắn với lần publish đó. Trong Spring AMQP, `publisher-confirm-type: correlated` cho phép theo dõi kết quả qua `RabbitTemplate.ConfirmCallback` và liên kết nó với `CorrelationData`.

Các kết quả cần diễn giải đúng:

| Kết quả ở publisher | Cách hiểu và xử lý |
|---|---|
| `ack=true` | Broker xác nhận lần publish. Điều này **không chứng minh consumer đã xử lý** và tự nó không bảo đảm message đã vào một queue có consumer. |
| `ack=false` (`nack`) | Broker báo không thể xác nhận lần publish; ghi nhận nguyên nhân, đánh giá retry theo chính sách. |
| Không thấy confirm trước hạn chờ, mất kết nối | **Trạng thái chưa biết**: không kết luận broker chắc chắn chưa nhận. Nếu phát lại, phải chấp nhận khả năng message trùng. |

Việc phương thức `rabbitTemplate.convertAndSend(...)` trả về bình thường chỉ cho biết lời gọi gửi đã hoàn thành ở phía ứng dụng tại thời điểm đó; **không đồng nghĩa đã có publisher confirm**. Confirm được xử lý qua callback hoặc future tương ứng, và cần theo dõi cả trường hợp quá hạn chờ.

### Confirm ACK vẫn có thể đi kèm message không có queue nhận

Một lần publish vào **exchange tồn tại** nhưng `routingKey` không khớp binding có thể được broker **confirm ACK**, dù message không được định tuyến tới queue nào. Khi bật cờ `mandatory` và publisher returns, RabbitMQ trả lại message không định tuyến được bằng `basic.return`; trong Spring AMQP, xử lý qua `ReturnsCallback`.

- **Confirm callback** trả lời: broker đã phản hồi thế nào với lần publish?
- **Returns callback** trả lời: message có bị broker **trả lại vì không định tuyến được** hay không?
- **Consumer ACK** trả lời: consumer đã xác nhận một delivery cụ thể chưa?

Ba tín hiệu trên không thể thay thế nhau. Trường hợp `return` cộng với `confirm ACK` là **hợp lệ**, không mâu thuẫn: broker xử lý thành công lần publish nhưng không tìm được queue phù hợp. Nếu không bật `mandatory`/returns, message không định tuyến được có thể bị loại bỏ mà publisher vẫn nhận confirm ACK.

Publisher confirm cũng cần được đặt trong thiết kế độ bền phù hợp: dùng queue/exchange durable khi cần, message persistent khi phù hợp, hiểu chính sách lưu trữ/replication của loại queue, và kiểm tra lỗi định tuyến. Không suy ra bảo đảm “xử lý đúng một lần” chỉ từ confirm.

## 4. Ví dụ với Spring Boot và Spring AMQP

Giả sử RabbitMQ có exchange `orders.events`, queue `orders.created.q` và binding với routing key `order.created`. Các tên này là ví dụ; exchange, queue và binding phải được khai báo trước hoặc được ứng dụng khai báo bằng `Declarables`/`RabbitAdmin`.

### 4.1. Bật confirm, return và manual acknowledgement

```yaml
# application.yml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: manual
```

`publisher-confirm-type` và `publisher-returns` là cấu hình cho **publisher**, còn `listener.simple.acknowledge-mode` điều khiển **consumer listener container** (với container kiểu `simple`). Chúng tác động lên hai hướng độc lập.

### 4.2. Phía publisher: gắn mã tương quan và xử lý phản hồi

```java
@Configuration
class PublisherConfig {
    private static final Logger log = LoggerFactory.getLogger(PublisherConfig.class);

    @Bean
    RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMandatory(true);

        template.setConfirmCallback((correlation, ack, reason) -> {
            String eventId = correlation == null ? "unknown" : correlation.getId();
            if (ack) {
                log.info("Broker confirmed publish, eventId={}", eventId);
            } else {
                log.error("Broker NACK, eventId={}, reason={}", eventId, reason);
            }
            // Ứng dụng thực: cập nhật trạng thái gửi một cách bền vững.
        });

        template.setReturnsCallback(returned -> {
            log.error("Unroutable: exchange={}, key={}, reason={}",
                returned.getExchange(),
                returned.getRoutingKey(),
                returned.getReplyText());
            // Ứng dụng thực: ghi nhận sự kiện chưa được định tuyến.
        });
        return template;
    }
}

@Component
class OrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    void publishOrderCreated(String eventId, String jsonPayload) {
        CorrelationData correlation = new CorrelationData(eventId);
        rabbitTemplate.convertAndSend(
            "orders.events", "order.created", jsonPayload, correlation);
        // Đến đây chưa thể khẳng định đã có confirm ACK.
    }
}
```

Các đoạn Java trên tập trung vào API; cần imports tương ứng của Spring AMQP, Spring Framework và SLF4J. `eventId` nên có tính duy nhất và được lưu cùng trạng thái phát sự kiện để đối soát sau khi ứng dụng khởi động lại. Callback chỉ ghi log là ví dụ quan sát, **chưa phải** một cơ chế retry/đối soát bền vững. Một `RabbitTemplate` thường chỉ có một `ConfirmCallback` và một `ReturnsCallback`; nếu nhiều thành phần cùng muốn theo dõi, hãy tập trung đăng ký callback ở một nơi.

### 4.3. Phía consumer: hoàn tất nghiệp vụ trước khi ACK

```java
@Component
class OrderConsumer {
    private final OrderProcessingService orderService;

    OrderConsumer(OrderProcessingService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(queues = "orders.created.q", ackMode = "MANUAL")
    public void consume(Message message, Channel channel) throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();
        String payload = new String(message.getBody(), StandardCharsets.UTF_8);

        try {
            // Service thực hiện xử lý idempotent và commit DB trước khi trả về.
            orderService.processIdempotently(payload);
        } catch (NonRetryableOrderException e) {
            channel.basicReject(tag, false);   // Không requeue; DLX nếu có.
            return;
        } catch (Exception e) {
            channel.basicNack(tag, false, true); // Ví dụ lỗi tạm thời.
            return;
        }

        channel.basicAck(tag, false);            // ACK sau khi xử lý thành công.
    }
}
```

`OrderProcessingService` và `NonRetryableOrderException` là các kiểu nghiệp vụ cần hiện thực trong ứng dụng. Một cách triển khai thực tế cho `processIdempotently` là chạy trong transaction cơ sở dữ liệu, lưu `eventId` với ràng buộc `UNIQUE`, kiểm tra sự kiện đã áp dụng chưa và chỉ cập nhật nghiệp vụ khi chưa có. Phần transaction nên được hoàn tất khi phương thức service trả về, **trước** lệnh `basicAck` trong listener.

Nếu gọi `basicAck` thất bại do kết nối đứt sau khi DB đã commit, broker vẫn có thể giao lại message. Đó là lý do kiểm tra `eventId` không thể bỏ qua. Ngược lại, nếu ACK trước rồi xử lý DB thất bại, broker có thể đã loại delivery khỏi queue và công việc bị bỏ dở.

Đoạn `basicNack(..., true)` chỉ minh họa nhánh requeue. Khi vận hành, cần giới hạn số lần thử, phân loại lỗi, cân nhắc TTL + DLX hoặc cơ chế retry của Spring AMQP để tránh giao lại tức thì mãi mãi. `basicReject(..., false)` chỉ đến DLQ nếu topology có cấu hình dead-letter phù hợp.

## 5. Xâu chuỗi trạng thái: một ACK không kéo theo ACK kia

| Tình huống | Publisher thấy gì? | Broker/consumer có thể xảy ra điều gì? | Hệ quả |
|---|---|---|---|
| Broker nhận và định tuyến thành công; consumer hoàn tất | Confirm ACK | Consumer ACK sau khi xử lý | Đường đi thành công, nhưng vẫn cần idempotency cho lần giao lại có thể có. |
| Broker nhận message; consumer xử lý lỗi | Confirm ACK | Consumer NACK/requeue hoặc reject/DLX | Confirm của publisher **không đổi** theo lỗi xử lý của consumer. |
| Broker nhận message; consumer chết khi đang xử lý | Confirm ACK | Message đang unacked có thể được giao lại khi channel đóng | Consumer mới có thể gặp message mà consumer cũ đã xử lý dở hoặc đã commit DB. |
| Routing key sai, không có queue nhận | Có thể vẫn confirm ACK | Message bị return khi bật `mandatory`; không có consumer ACK | Cần theo dõi **returns** và binding, không chỉ confirm. |
| Publisher mất kết nối trước khi thấy confirm | NACK hoặc timeout/không rõ kết quả | Broker có thể đã nhận message trước khi kết nối đứt | Retry có thể tạo bản sao; dùng event ID và đối soát. |

Không có một lệnh ACK “end-to-end” nối publisher confirm với consumer acknowledgement. Chúng thuộc **hai channel khác nhau, hai thông điệp phản hồi khác nhau và hai thời điểm trách nhiệm khác nhau**. Ngay cả khi cùng nhận `ack=true` ở cả hai phía, việc ghi DB ở producer, đưa message qua broker và cập nhật DB ở consumer không tự trở thành một giao dịch phân tán duy nhất.

## 6. Thiết kế đáng tin cậy từ hai cơ chế độc lập

1. **Theo dõi publish riêng:** gắn `eventId`/`CorrelationData`, xử lý confirm ACK/NACK, timeout và `ReturnsCallback`; không coi việc `convertAndSend` trả về là đã xác nhận.
2. **Theo dõi delivery riêng:** ở consumer, ACK sau khi nghiệp vụ commit; phân biệt lỗi tạm thời và vĩnh viễn để chọn retry/requeue/DLX.
3. **Chấp nhận khả năng trùng:** cùng một sự kiện có thể được gửi lại hoặc giao lại; thiết kế consumer idempotent bằng `eventId`, ràng buộc dữ liệu và transaction.
4. **Kiểm tra topology:** exchange, routing key, binding, queue, chính sách durable/persistent và DLX phải phù hợp với yêu cầu mất dữ liệu/khôi phục.
5. **Tách rủi ro dữ liệu của publisher:** nếu phát message phải đi cùng cập nhật cơ sở dữ liệu, cân nhắc **transactional outbox** để không có khoảng hở giữa commit DB và gửi message; worker outbox vẫn cần confirm, returns và xử lý gửi lại.
6. **Quan sát các mốc độc lập:** số message chờ xác nhận publish, số return/unroutable, queue ready/unacked, tốc độ ACK/NACK, redelivery, retry và DLQ. Chỉ số unacked tăng kéo dài có thể liên quan consumer xử lý chậm, thiếu ACK hoặc prefetch cao.

## 7. Bài thực hành kiểm chứng

Với topology `orders.events` → (`order.created`) → `orders.created.q`, thực hiện lần lượt:

1. **Luồng bình thường:** publish một `eventId`, quan sát `ConfirmCallback(ack=true)`, consumer xử lý rồi gửi `basicAck`; đối chiếu log hai đầu.
2. **Sai routing key:** publish bằng `order.unknown` trong khi không có binding tương ứng; quan sát `ReturnsCallback` nếu bật `mandatory`, đồng thời confirm vẫn có thể ACK. Kiểm tra không có consumer nhận.
3. **Lỗi xử lý:** tạo lỗi tạm thời trong consumer; quan sát NACK và redelivery. Xác minh publisher confirm trước đó không thay đổi. Dừng thử nghiệm sớm để tránh requeue liên tục.
4. **Lỗi sau commit:** mô phỏng tiến trình consumer ngắt sau khi đã ghi DB nhưng trước khi ACK; khi message được giao lại, kiểm tra `eventId` ngăn xử lý nghiệp vụ trùng.
5. **Mất confirm:** tạo sự cố kết nối ở publisher quanh lúc gửi; ghi nhận kết quả chưa chắc chắn và thử lại theo cùng `eventId`. Kiểm tra cơ chế idempotency trước khi coi retry là an toàn.

**Tự kiểm tra:** Nếu log ghi `publisher confirm: ACK`, có thể kết luận đơn hàng đã được xử lý thành công không? **Không.** Chỉ biết broker đã xác nhận lần publish; cần quan sát consumer/tiến trình nghiệp vụ riêng. Nếu consumer đã ACK, có thể kết luận lần publish tương ứng vừa nhận confirm không? **Cũng không.** Consumer ACK thuộc delivery trên channel nhận, hoàn toàn tách biệt với publisher confirm.
