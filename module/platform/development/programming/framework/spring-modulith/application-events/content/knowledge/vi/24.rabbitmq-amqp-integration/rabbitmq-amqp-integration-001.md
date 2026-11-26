# Event và AMQP

Spring Modulith giúp các module trong cùng ứng dụng trao đổi sự kiện qua application events. Khi một sự kiện cần được chuyển tới một tiến trình hoặc hệ thống khác, message broker tạo ra ranh giới giao tiếp mới. AMQP và RabbitMQ cung cấp mô hình exchange, queue, binding và routing key để định tuyến message tới các consumer phù hợp.

Tích hợp broker cần giữ rõ hai hợp đồng: event nội bộ phản ánh điều đã xảy ra trong miền nghiệp vụ; integration message là dữ liệu được công bố cho hệ thống bên ngoài. Adapter chuyển đổi giữa hai hợp đồng này, chọn exchange và routing key, định dạng payload, đồng thời xử lý xác nhận gửi, retry và lỗi. Nếu event phải được giao đáng tin cậy cùng transaction nghiệp vụ, cần dùng outbox hoặc cơ chế externalization bền vững tương thích với phiên bản Spring Modulith đang triển khai.

Bài này giới thiệu mô hình AMQP, cách thiết kế event contract, cấu hình topology RabbitMQ bằng Spring AMQP, xây dựng publisher và listener, kết hợp với ranh giới module, và vận hành luồng message có thể phục hồi.

## 1. AMQP trong kiến trúc event-driven

AMQP là giao thức messaging. RabbitMQ thường được sử dụng với AMQP 0-9-1 và cung cấp các thành phần chính:

- **Producer** tạo và publish message.
- **Exchange** nhận message từ producer và quyết định định tuyến.
- **Binding** liên kết exchange với queue cùng quy tắc routing.
- **Queue** lưu message chờ consumer nhận.
- **Consumer** nhận và xử lý message.
- **Acknowledgement** xác nhận message đã được xử lý theo semantics của broker.

Producer thường gửi message tới exchange, không gửi trực tiếp tới queue. Exchange sử dụng loại exchange, routing key và/hoặc header để chọn queue đích. Một message có thể được route tới một queue, nhiều queue hoặc không queue nào, tùy topology.

~~~mermaid
flowchart LR
    P[Producer / Spring Modulith adapter] -->|publish message| E[Exchange]
    E -->|binding + routing rule| Q1[Queue A]
    E -->|binding + routing rule| Q2[Queue B]
    Q1 --> C1[Consumer A]
    Q2 --> C2[Consumer B]
~~~

Điều này tách producer khỏi danh sách consumer cụ thể. Producer biết hợp đồng message và exchange/routing convention; topology quyết định queue nào nhận message. Khi thêm consumer mới, có thể thêm queue và binding mà không cần thay đổi producer nếu event contract và routing convention đã ổn định.

## 2. Phân biệt application event và integration message

Trong Spring Modulith, application event là cơ chế giao tiếp giữa các module trong cùng ứng dụng. Event thường mô tả một sự kiện nghiệp vụ đã xảy ra, chẳng hạn OrderPlaced hoặc PaymentCaptured. Event Publication Registry có thể theo dõi publication tới từng listener nội bộ và hỗ trợ phục hồi publication chưa hoàn tất.

Integration message là hợp đồng được công bố qua ranh giới tiến trình. Nó cần ổn định, có version và chỉ chứa dữ liệu mà consumer bên ngoài được phép sử dụng. Không nên gửi trực tiếp entity JPA hoặc class nội bộ có cấu trúc thay đổi theo implementation.

Ví dụ:

~~~java
public record OrderPlaced(
        UUID orderId,
        Instant occurredAt
) {}

public record OrderPlacedIntegrationV1(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        UUID correlationId
) {}
~~~

OrderPlaced có thể là event nội bộ dùng trong module hoặc giữa các module. OrderPlacedIntegrationV1 là hợp đồng bên ngoài có event ID, correlation ID và schema version được xác định rõ.

Một adapter chuyển đổi từ event nội bộ sang integration message:

~~~java
@Component
class OrderEventMapper {

    OrderPlacedIntegrationV1 toIntegrationEvent(
            OrderPlaced event,
            UUID eventId,
            UUID correlationId
    ) {
        return new OrderPlacedIntegrationV1(
                eventId,
                event.orderId(),
                event.occurredAt(),
                correlationId
        );
    }
}
~~~

Trong thực tế, event nội bộ có thể đã chứa eventId và correlationId. Khi đó adapter giữ nguyên các định danh này. Không tạo event ID mới mỗi lần retry hoặc replay vì consumer cần một định danh ổn định để deduplicate.

## 3. Exchange, queue, binding và routing key

### 3.1. Các loại exchange

RabbitMQ cung cấp một số loại exchange phổ biến:

| Loại exchange | Quy tắc định tuyến | Trường hợp sử dụng |
|---|---|---|
| Direct | Routing key phải khớp chính xác với binding key | Định tuyến theo loại event hoặc đích cố định |
| Topic | Routing key được so khớp theo các segment, hỗ trợ wildcard | Định tuyến theo domain, event type hoặc vùng nghiệp vụ |
| Fanout | Broadcast tới mọi queue được bind | Phát thông báo tới nhiều consumer mà không lọc theo routing key |
| Headers | So khớp theo message headers và binding arguments | Định tuyến dựa trên metadata thay vì routing key |

Với topic exchange, routing key thường có dạng các segment phân cách bằng dấu chấm, ví dụ:

- order.placed
- order.cancelled
- payment.captured
- inventory.reserved

Wildcard * khớp đúng một segment; # khớp không hoặc nhiều segment. Binding order.* nhận order.placed và order.cancelled nhưng không nhận order.payment.failed. Binding order.# có thể nhận các routing key sâu hơn.

Hãy chọn loại exchange theo quy tắc định tuyến mà consumer cần. Không nên tạo một exchange cho từng consumer nếu các consumer chỉ cần lọc những event type khác nhau trong cùng một domain.

### 3.2. Queue và binding

Queue là nơi message chờ consumer. Queue có thể durable hoặc transient. Với message nghiệp vụ cần tồn tại qua restart, thường cần durable queue cùng message persistent và cấu hình durability phù hợp của broker.

Binding xác định cách message từ exchange đi vào queue. Một exchange có thể bind tới nhiều queue; một queue cũng có thể bind từ nhiều exchange. Khi một message khớp nhiều binding, queue nhận message theo topology và semantics của RabbitMQ.

Routing key không phải partition key của Kafka. RabbitMQ sử dụng exchange và binding để định tuyến message tới queue; việc consumer xử lý song song, thứ tự và redelivery phụ thuộc queue type, consumer concurrency, prefetch và acknowledgement.

### 3.3. Ví dụ topology cho đơn hàng

Một topic exchange có thể định tuyến event đơn hàng tới queue kho và queue thông báo:

~~~text
Exchange: business.events (topic)

Queue: inventory.order-events
Binding: order.placed

Queue: notification.order-events
Binding: order.#

Producer:
exchange = business.events
routingKey = order.placed
~~~

Khi OrderPlaced được publish, cả hai queue nhận bản sao message theo binding tương ứng. Consumer kho giữ hàng; consumer thông báo gửi xác nhận cho khách hàng. Mỗi queue có trạng thái, retry và acknowledgement riêng. Một consumer lỗi không ngăn consumer khác tiếp tục xử lý message đã nhận ở queue của nó.

## 4. Khai báo topology bằng Spring AMQP

Spring AMQP cung cấp các abstraction như Exchange, Queue, Binding, RabbitTemplate và @RabbitListener. Với Spring Boot, các bean topology có thể được khai báo trong cấu hình ứng dụng để RabbitAdmin tự động khai báo với broker khi kết nối.

Ví dụ:

~~~java
@Configuration
class OrderRabbitTopology {

    @Bean
    TopicExchange businessEventsExchange() {
        return new TopicExchange(
                "business.events",
                true,
                false
        );
    }

    @Bean
    Queue inventoryOrderEventsQueue() {
        return QueueBuilder
                .durable("inventory.order-events")
                .build();
    }

    @Bean
    Queue notificationOrderEventsQueue() {
        return QueueBuilder
                .durable("notification.order-events")
                .build();
    }

    @Bean
    Binding inventoryOrderBinding(
            Queue inventoryOrderEventsQueue,
            TopicExchange businessEventsExchange
    ) {
        return BindingBuilder
                .bind(inventoryOrderEventsQueue)
                .to(businessEventsExchange)
                .with("order.placed");
    }

    @Bean
    Binding notificationOrderBinding(
            Queue notificationOrderEventsQueue,
            TopicExchange businessEventsExchange
    ) {
        return BindingBuilder
                .bind(notificationOrderEventsQueue)
                .to(businessEventsExchange)
                .with("order.#");
    }
}
~~~

Ví dụ minh họa hai queue cùng một exchange. Trong ứng dụng thực tế, nên đặt tên bean rõ ràng và tách topology theo bounded context hoặc adapter để tránh phụ thuộc vào tên bean chung như queue/exchange khi có nhiều module.

Topology cần được quản lý nhất quán giữa các môi trường. Nếu queue đã tồn tại với tham số khác, broker có thể từ chối khai báo lại. Các thay đổi như queue type, durability hoặc argument cần migration có kế hoạch; không tùy tiện xóa queue production để ứng dụng khai báo lại.

## 5. Định dạng message và event contract

Message cần có payload và metadata đủ để consumer hiểu, xác thực và truy vết.

Các trường hữu ích:

| Trường | Mục đích |
|---|---|
| eventId | Định danh ổn định để deduplicate |
| eventType | Loại event, ví dụ OrderPlaced |
| schemaVersion | Phiên bản cấu trúc payload |
| occurredAt | Thời điểm sự kiện xảy ra |
| aggregateId | Định danh đối tượng nghiệp vụ |
| correlationId | Liên kết các bước của một luồng |
| causationId | Event/command dẫn tới event hiện tại |
| tenantId | Phân vùng nghiệp vụ nếu hệ thống multi-tenant |

Có thể đặt metadata trong payload envelope hoặc AMQP message headers. Chọn một quy ước nhất quán và ghi rõ trường nào là bắt buộc. Không để consumer phải đoán event type từ tên queue hoặc cấu trúc JSON.

Ví dụ payload JSON:

~~~json
{
  "eventId": "6f0f0d90-93b5-4a61-a6d8-2d8b9fcd1b8d",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T10:00:00Z",
  "aggregateId": "8c1f7b1b-5b70-4f6a-a5d4-6fca2f5c8d77",
  "correlationId": "a8c7b9d0-9a8e-4a17-bc11-9a7a4b2d6e31",
  "payload": {
    "orderId": "8c1f7b1b-5b70-4f6a-a5d4-6fca2f5c8d77"
  }
}
~~~

Không đưa thông tin bí mật, token, dữ liệu cá nhân không cần thiết hoặc toàn bộ aggregate vào message. Consumer cần đủ dữ liệu để thực hiện hợp đồng; các dữ liệu khác có thể được truy vấn qua API có kiểm soát nếu kiến trúc cho phép.

### 5.1. JSON message converter

Spring AMQP có thể dùng message converter để chuyển object Java sang JSON và ngược lại. Ví dụ cấu hình Jackson converter:

~~~java
@Configuration
class RabbitMessageConfiguration {

    @Bean
    MessageConverter rabbitMessageConverter(
            ObjectMapper objectMapper
    ) {
        return new Jackson2JsonMessageConverter(objectMapper);
    }
}
~~~

Producer và consumer cần thống nhất content type, type metadata và cách ánh xạ class. Trong môi trường nhiều service, tránh yêu cầu consumer phải deserialize một class Java nằm trong package của producer. Dùng DTO/contract độc lập và cấu hình type mapping hoặc converter theo schema đã công bố.

Tên class, package Java và cấu trúc entity nội bộ không nên trở thành hợp đồng bắt buộc của hệ thống bên ngoài. Khi đổi schema, thêm version và chiến lược tương thích ngược; không âm thầm đổi kiểu hoặc ý nghĩa trường đang được consumer sử dụng.

## 6. Publish message bằng RabbitTemplate

RabbitTemplate là abstraction phổ biến để gửi message tới exchange và routing key.

~~~java
@Component
@RequiredArgsConstructor
class RabbitOrderEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    public void publish(OrderPlacedIntegrationV1 event) {
        rabbitTemplate.convertAndSend(
                "business.events",
                "order.placed",
                event,
                message -> {
                    MessageProperties properties =
                            message.getMessageProperties();

                    properties.setMessageId(
                            event.eventId().toString()
                    );
                    properties.setContentType(
                            MessageProperties.CONTENT_TYPE_JSON
                    );
                    properties.setHeader("schemaVersion", 1);
                    properties.setHeader(
                            "correlationId",
                            event.correlationId().toString()
                    );

                    return message;
                }
        );
    }
}
~~~

Message ID và correlation header giúp quan sát và deduplicate. Nếu đã đặt metadata trong envelope, có thể lặp lại một số trường trong AMQP headers để phục vụ routing, tracing hoặc broker tooling; cần giữ chúng đồng bộ.

Gọi convertAndSend không tự chứng minh broker đã lưu message. Với luồng quan trọng, cần cấu hình publisher confirms và xử lý kết quả confirm. Nếu bật mandatory publish và publisher returns, ứng dụng cũng có thể phát hiện message không được route tới queue nào. Confirm ACK và returned message là hai tín hiệu cần được xem cùng nhau: broker có thể xác nhận publish nhưng message không được định tuyến như mong muốn.

## 7. Nhận message bằng @RabbitListener

Consumer có thể dùng @RabbitListener để đăng ký phương thức nhận message từ queue:

~~~java
@Component
@RequiredArgsConstructor
class InventoryOrderEventsListener {

    private final InventoryApplicationService inventory;

    @RabbitListener(queues = "inventory.order-events")
    public void on(OrderPlacedIntegrationV1 event) {
        inventory.reserveFor(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

Container listener quản lý việc nhận message và acknowledgement theo cấu hình. Với chế độ AUTO thường dùng trong Spring AMQP, container ack khi listener kết thúc bình thường; exception được xử lý theo error handler và retry/requeue policy. Cần hiểu rõ cấu hình thực tế, không mặc định rằng mọi exception đều đưa message vào dead-letter queue.

Nghiệp vụ consumer nên nằm trong service có transaction và idempotency:

~~~java
@Service
@RequiredArgsConstructor
class InventoryApplicationService {

    private final ProcessedEventRepository processedEvents;
    private final InventoryRepository inventory;

    @Transactional
    public void reserveFor(UUID orderId, UUID eventId) {
        boolean firstDelivery = processedEvents.tryRegister(
                "inventory",
                eventId
        );

        if (!firstDelivery) {
            return;
        }

        inventory.reserveFor(orderId);
    }
}
~~~

Thao tác đăng ký event ID cần dựa trên unique constraint và cùng transaction với cập nhật tồn kho. Nếu listener bị gọi lại sau khi DB đã commit nhưng broker chưa nhận ack, lần giao lại sẽ được deduplicate.

## 8. Kết hợp event nội bộ Spring Modulith với RabbitMQ

### 8.1. Giữ ranh giới module

Module nghiệp vụ không nên phụ thuộc trực tiếp vào RabbitTemplate hoặc tên queue của RabbitMQ. Module công bố application event; adapter ở lớp tích hợp chuyển event thành message bên ngoài.

~~~mermaid
flowchart LR
    A[Order module] --> B[OrderPlaced application event]
    B --> C[Internal module listeners]
    B --> D[Integration adapter]
    D --> E[AMQP message]
    E --> F[RabbitMQ exchange]
    F --> G[Consumer queues]
~~~

Cách tổ chức này giữ module nghiệp vụ tập trung vào domain event và cho phép thay broker mà không phải thay đổi logic nghiệp vụ. Adapter chịu trách nhiệm mapping event, routing key, headers, serialization và xử lý lỗi vận chuyển.

### 8.2. Gửi trực tiếp sau commit và giới hạn của nó

Có thể dùng @ApplicationModuleListener để gọi adapter sau khi transaction nghiệp vụ commit. Tuy nhiên, việc listener được gọi sau commit không tự tạo atomic commit giữa database và RabbitMQ. Nếu ứng dụng dừng sau DB commit nhưng trước khi publish, message có thể không được gửi. Nếu RabbitTemplate trả về trước khi publisher confirm hoàn tất, listener có thể được xem là hoàn tất trước khi broker xác nhận.

Với thông báo best-effort, có thể chấp nhận giới hạn này và bổ sung metric/alert. Với integration event bắt buộc không được mất, hãy dùng transactional outbox hoặc cơ chế externalization có persistence/retry được hỗ trợ bởi phiên bản Spring Modulith đang dùng.

### 8.3. Ghi outbox cùng transaction nghiệp vụ

Trong transactional outbox, service ghi dữ liệu aggregate và outbox record trong cùng transaction. Outbox record lưu payload, exchange và routing key cần gửi.

~~~java
@Transactional
public UUID place(PlaceOrderCommand command) {
    Order order = orders.place(command);

    OrderPlacedIntegrationV1 event =
            new OrderPlacedIntegrationV1(
                    UUID.randomUUID(),
                    order.getId(),
                    clock.instant(),
                    command.correlationId()
            );

    ordersRepository.save(order);

    outbox.append(
            event.eventId(),
            "business.events",
            "order.placed",
            event
    );

    events.publishEvent(
            new OrderPlaced(order.getId(), event.occurredAt())
    );

    return order.getId();
}
~~~

Outbox repository phải dùng cùng database transaction manager với dữ liệu nghiệp vụ. Khi transaction rollback, cả aggregate và outbox record rollback. Khi commit, relay có thể gửi record ngay cả khi tiến trình dừng sau đó.

Relay claim record trong transaction ngắn, gửi RabbitMQ ngoài transaction, chờ publisher confirm và kiểm tra returned message nếu mandatory routing được bật. Chỉ sau confirm thành công và không có lỗi routing, relay mới đánh dấu record SENT. Nếu kết quả không rõ hoặc relay dừng trước khi cập nhật SENT, record có thể được gửi lại; consumer phải idempotent.

Spring Modulith có cơ chế theo dõi publication nội bộ qua Event Publication Registry. Một số phiên bản và cấu hình cung cấp khả năng externalize event thông qua module tích hợp tương ứng. Khi chọn cơ chế externalization có sẵn, cần xác minh artifact, API, persistence và semantics confirm của đúng phiên bản; không giả định rằng listener completion đồng nghĩa broker đã xử lý message.

## 9. Reliability: durability, confirms và acknowledgements

Độ tin cậy của RabbitMQ phụ thuộc nhiều lớp:

- Exchange và queue topology được khai báo đúng.
- Queue có durability phù hợp.
- Message được publish với delivery mode persistent khi cần.
- Broker được cấu hình replication phù hợp, ví dụ quorum queue cho yêu cầu HA.
- Producer sử dụng publisher confirms và phát hiện unroutable message.
- Consumer acknowledgement sau khi xử lý thành công.
- Consumer có idempotency để chịu được redelivery.

Durable queue không tự làm message persistent. Persistent message cũng không thay thế publisher confirms. Publisher confirm không chứng minh consumer đã xử lý. Consumer ack không bảo đảm side effect bên ngoài transaction database đã hoàn tất.

Với message quan trọng, hãy đánh giá các thuộc tính trên cùng nhau. Mức durability thực tế phụ thuộc loại queue, số replica, tình trạng quorum và cấu hình broker; không thể suy ra chỉ từ một flag durable.

## 10. Retry, dead-letter và poison message

Lỗi consumer thường được chia thành hai nhóm:

- Lỗi tạm thời: database timeout, dịch vụ phụ thuộc tạm dừng, giới hạn tốc độ. Có thể retry với backoff.
- Lỗi vĩnh viễn: payload không hợp lệ, schema không hỗ trợ, dữ liệu không thỏa hợp đồng. Nên quarantine hoặc dead-letter để điều tra.

RabbitMQ hỗ trợ dead-letter exchange (DLX) để định tuyến message bị reject, hết TTL hoặc vượt một số điều kiện queue sang nơi xử lý khác. Có thể khai báo DLX bằng queue arguments hoặc policy ở broker. Policy thường thuận tiện hơn cho vận hành vì có thể thay đổi mà không cần sửa code khai báo queue.

Một luồng retry có kiểm soát:

1. Listener thất bại và container áp dụng retry policy.
2. Retry có backoff và giới hạn số lần.
3. Nếu vẫn thất bại, message được dead-letter hoặc chuyển sang quarantine.
4. Operator xem event ID, lỗi cuối và schema version.
5. Sau khi sửa nguyên nhân, replay message theo phạm vi được duyệt.

Tránh requeue tức thì vô hạn. Message lỗi có thể quay lại liên tục, chiếm worker và gây ảnh hưởng tới message tốt. Dead-letter queue cần được giám sát như một phần của luồng nghiệp vụ.

## 11. Thứ tự và concurrency ở RabbitMQ

RabbitMQ không có partition theo cách Kafka dùng. Một queue có thể có nhiều consumer; khi prefetch lớn hơn một hoặc có xử lý bất đồng bộ, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự nhận.

Nếu cần tuần tự theo aggregate, có thể:

- Dùng queue riêng cho luồng cần thứ tự và một consumer xử lý tuần tự.
- Dùng routing key và exchange để chia queue theo nhóm nghiệp vụ, nếu số nhóm được quản lý rõ.
- Dùng aggregate version/sequence ở consumer để phát hiện event cũ hoặc event bị thiếu.
- Giới hạn prefetch và concurrency phù hợp với yêu cầu ordering.
- Dùng một cơ chế serialization theo aggregate ở application layer.

Không dùng một queue duy nhất với concurrency cao rồi giả định mọi event của cùng aggregate sẽ hoàn tất theo thứ tự. Cần kiểm tra cả thứ tự giao, redelivery, consumer concurrency và transaction commit.

## 12. Quan sát và vận hành

Các metric hữu ích:

**Producer và relay**
- Số message publish, publisher confirm ACK/NACK và timeout.
- Số message returned do không route được.
- Tuổi outbox record PENDING lâu nhất.
- Số lần retry và số record SENT/FAILED.

**RabbitMQ**
- Queue depth, publish/ack rate và unacked message.
- Consumer count, consumer capacity và channel errors.
- Redelivery rate, dead-letter rate và queue availability.
- Memory/disk alarm, connection và channel churn.

**Consumer**
- Số event nhận, xử lý thành công, deduplicate và lỗi.
- Thời gian xử lý theo event type.
- Số message đang in-flight và số lần redelivery.
- Số event bị quarantine theo schema hoặc lỗi nghiệp vụ.

Log nên có eventId, aggregateId, eventType, schemaVersion, exchange, routingKey, queue, correlationId và consumer name. Không ghi payload nhạy cảm. Dùng correlation ID để nối log từ module nguồn, relay, broker adapter và consumer.

Đặt cảnh báo theo tuổi message lâu nhất, queue depth tăng liên tục, confirm NACK/timeout, tỷ lệ redelivery và DLQ growth. Một queue có ít message nhưng message cũ không được xử lý có thể báo hiệu lỗi nghiêm trọng hơn một queue lớn đang giảm đều.

## 13. Kiểm thử tích hợp AMQP

Unit test có thể kiểm tra mapper, routing key và logic tạo envelope. Integration test với RabbitMQ cần xác minh topology, converter, routing và acknowledgement.

| Kịch bản | Điều cần xác minh |
|---|---|
| Publish event hợp lệ | Message tới đúng queue theo binding |
| Routing key không khớp | Message được trả về hoặc xử lý theo chính sách unroutable |
| Consumer xử lý thành công | Listener kết thúc và message được ack theo cấu hình |
| Consumer ném exception | Retry/requeue/DLX diễn ra theo policy |
| Message không deserialize được | Được quarantine hoặc dead-letter, không retry vô hạn |
| Producer timeout sau khi broker nhận | Retry không tạo side effect trùng |
| Relay dừng sau confirm, trước mark SENT | Message có thể gửi lại và consumer deduplicate |
| Queue/binding thay đổi | Topology được khai báo/migrate đúng |
| Consumer restart | Message chưa ack được redeliver |
| Event schema version cũ | Consumer hỗ trợ hoặc từ chối có kiểm soát |
| Hai consumer cùng queue | Concurrency và ordering phù hợp yêu cầu |

Test cần xác minh failure window thực tế. Chỉ mock RabbitTemplate và kiểm tra convertAndSend được gọi chưa chứng minh broker đã nhận, route đúng hoặc consumer đã ack.

## 14. Lỗi thiết kế thường gặp

**Module nghiệp vụ phụ thuộc RabbitTemplate.** Logic domain bị gắn với broker và topology. Dùng application event và adapter ở ranh giới tích hợp.

**Gửi entity trực tiếp làm payload.** Consumer bị phụ thuộc cấu trúc persistence nội bộ. Dùng integration DTO có schema version.

**Dùng routing key như partition key.** RabbitMQ định tuyến qua exchange/binding; ordering phụ thuộc queue và consumer. Xác định đúng semantics của broker.

**Coi convertAndSend là publish thành công.** Cần publisher confirm và xử lý returned message khi routing bắt buộc.

**Coi publisher confirm là consumer ack.** Confirm chỉ xác nhận broker xử lý publish theo semantics của nó. Consumer cần acknowledgement riêng.

**Gửi trực tiếp sau commit cho event bắt buộc không mất.** Có thể mất event ở khoảng trống sau commit. Dùng outbox hoặc externalization bền vững.

**Ack trước khi commit side effect.** Message có thể bị loại khỏi queue dù database rollback. Commit nghiệp vụ trước khi ack.

**Retry vô hạn không backoff.** Poison message có thể làm nghẽn queue. Dùng retry có giới hạn và DLX.

**Không idempotent consumer.** Redelivery là hành vi bình thường. Deduplicate theo event ID trong cùng transaction với side effect.

## 15. Quy trình thiết kế một AMQP adapter

Khi tích hợp một module Spring Modulith với RabbitMQ, hãy thực hiện theo trình tự:

1. Xác định event nghiệp vụ và integration contract độc lập.
2. Xác định consumer, exchange, queue và binding cần thiết.
3. Chọn exchange type và routing convention theo nhu cầu định tuyến.
4. Khai báo durable topology và message converter phù hợp.
5. Viết adapter publish, thêm event ID, schema version và correlation metadata.
6. Cấu hình publisher confirms, mandatory returns và xử lý lỗi gửi.
7. Viết listener với transaction và idempotency rõ ràng.
8. Chọn retry, dead-letter và quy trình replay.
9. Nếu event bắt buộc không được mất, ghi outbox cùng transaction và chỉ mark SENT sau confirm.
10. Kiểm thử routing, ack, redelivery, duplicate và restart với RabbitMQ.

Spring Modulith quản lý ranh giới module và publication nội bộ; Spring AMQP cung cấp abstraction để giao tiếp với RabbitMQ. Adapter kết nối hai lớp bằng integration contract rõ ràng. Khi topology, publisher confirm, consumer acknowledgement, outbox và idempotency được thiết kế cùng nhau, event có thể đi qua ranh giới tiến trình với khả năng phục hồi và quan sát phù hợp với yêu cầu nghiệp vụ.
