# Tách domain event khỏi persistence entity

Trong một ứng dụng Spring Kafka, dữ liệu được gửi lên Kafka thường được tiêu thụ bởi service khác, lưu trữ trong thời gian dài hoặc replay sau nhiều tháng. Vì vậy, cấu trúc message cần ổn định theo hợp đồng tích hợp. Persistence entity lại được thiết kế để phục vụ cách ứng dụng lưu và truy vấn dữ liệu ở thời điểm hiện tại. Hai mô hình này có mục đích, vòng đời và tốc độ thay đổi khác nhau.

Nếu serialize trực tiếp JPA entity để gửi Kafka, thay đổi trong database mapping có thể vô tình thay đổi payload công khai. Quan hệ lazy, proxy Hibernate, vòng tham chiếu hai chiều, trường nội bộ, dữ liệu nhạy cảm và các annotation persistence cũng có thể lọt vào quá trình serialization. Consumer khi đó bị phụ thuộc vào cấu trúc database và class Java của producer.

Cách thiết kế an toàn là giữ persistence entity ở ranh giới lưu trữ, biểu diễn sự kiện bằng một object độc lập, rồi ánh xạ dữ liệu cần công bố sang integration event contract. Event mô tả một sự thật nghiệp vụ đã xảy ra, có schema và semantics rõ ràng, không mang theo object graph do ORM quản lý.

Bài học tập trung vào cách tách persistence entity, domain event và integration event; cách ánh xạ dữ liệu; cách serialize bằng Spring Kafka; cách tiến hóa schema mà không làm hỏng consumer cũ; và cách publish đáng tin cậy bằng transactional outbox.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao không nên gửi JPA entity trực tiếp lên Kafka.
- Phân biệt domain entity, persistence entity, domain event và integration event.
- Thiết kế event contract độc lập với cấu trúc database.
- Chọn dữ liệu cần đưa vào event và loại bỏ trường nội bộ hoặc nhạy cảm.
- Viết mapper từ persistence model sang event DTO.
- Xử lý lazy relationship khi tạo event.
- Cấu hình JSON serializer/deserializer và type headers trong Spring Kafka.
- Chọn chiến lược schema evolution tương thích với consumer đang triển khai.
- Phân biệt event snapshot với event chỉ mang reference.
- Dùng transactional outbox để phối hợp database commit và publish Kafka.
- Kiểm thử mapper, serialization, compatibility và duplicate delivery.
- Lập kế hoạch chuyển đổi từ việc publish entity sang event contract ổn định.

## 1. Persistence entity và event giải quyết hai bài toán khác nhau

Persistence entity mô tả trạng thái mà ứng dụng lưu trong database. Nó thường chứa khóa chính, quan hệ, cột audit, optimistic locking version, trạng thái nội bộ và annotation của JPA.

Event mô tả một sự kiện có ý nghĩa đối với nghiệp vụ hoặc hệ thống khác. Ví dụ OrderCreated diễn tả việc một đơn hàng đã được tạo. Consumer cần biết đơn hàng nào được tạo, thời điểm nào, các dữ liệu cần thiết cho nghiệp vụ của nó và cách nhận diện event. Consumer không cần biết bảng orders có cột nào, entity có quan hệ JPA ra sao hoặc Hibernate đang dùng proxy nào.

| Tiêu chí | Persistence entity | Event contract |
|---|---|---|
| Mục đích | Lưu và truy vấn trạng thái | Công bố một sự thật hoặc thay đổi nghiệp vụ |
| Vòng đời | Theo transaction và persistence context | Có thể được lưu, replay và đọc lâu dài |
| Cấu trúc | Phụ thuộc schema database và ORM | Phụ thuộc hợp đồng producer-consumer |
| Quan hệ | Có thể chứa object graph và lazy proxy | Nên chứa giá trị hoặc snapshot có chủ đích |
| Thay đổi | Có thể thay đổi cùng migration database | Cần quản lý compatibility với consumer |
| Annotation | @Entity, @Id, @ManyToOne, @Version | Không cần annotation JPA |
| Dữ liệu | Có thể có trường nội bộ | Chỉ chứa dữ liệu được phép công bố |

Ví dụ entity:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    @Column(name = "internal_risk_score")
    private Integer internalRiskScore;

    @Version
    private long version;

    @Column(name = "created_by")
    private String createdBy;

    // getters, setters and persistence behavior
}
~~~

Nếu gửi nguyên OrderEntity, payload có thể chứa hoặc bị ảnh hưởng bởi customer, lines, internalRiskScore, version và các thuộc tính khác. Một lần đổi quan hệ JPA hoặc thêm trường database có thể làm payload thay đổi mà không có quyết định versioning event nào.

Event nên là một kiểu dữ liệu riêng, chỉ chứa thông tin cần công bố:

~~~java
public record OrderCreatedV1(
        UUID eventId,
        UUID orderId,
        String orderNumber,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt,
        String correlationId,
        List<OrderLineCreatedV1> items
) {
    public OrderCreatedV1 {
        items = List.copyOf(items);
    }
}

public record OrderLineCreatedV1(
        String sku,
        String productName,
        int quantity,
        long unitPriceMinor
) {}
~~~

Event không chứa CustomerEntity, OrderLineEntity, Hibernate proxy hay JPA annotation. Danh sách items được sao chép để event có cấu trúc bất biến sau khi tạo.

## 2. Phân biệt domain entity, persistence entity và domain event

Các thuật ngữ này có thể được tổ chức khác nhau tùy kiến trúc, nhưng cần giữ rõ trách nhiệm.

**Domain entity** là đối tượng nghiệp vụ có identity và hành vi. Nó bảo vệ invariant, ví dụ một đơn hàng không thể chuyển sang trạng thái đã thanh toán nếu chưa được xác nhận.

**Persistence entity** là biểu diễn dùng để lưu trữ bằng ORM hoặc persistence framework. Trong ứng dụng đơn giản, domain entity và persistence entity có thể dùng chung class. Trong kiến trúc tách lớp, chúng có thể là hai kiểu khác nhau.

**Domain event** là một sự thật nghiệp vụ đã xảy ra bên trong bounded context. Tên thường dùng thì quá khứ như OrderCreated, OrderConfirmed hoặc PaymentCaptured. Event nên giữ dữ liệu cần thiết để diễn tả sự kiện, không giữ tham chiếu đến object graph đang được ORM quản lý.

**Integration event** là hợp đồng được công bố cho service hoặc bounded context khác. Nó có thể được ánh xạ từ domain event và được quản lý version độc lập với model nội bộ.

Luồng có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A["Use case / Application service"] --> B["Domain model"]
    B --> C["Domain event"]
    B --> D["Persistence mapping"]
    D --> E["JPA persistence entity"]
    C --> F["Integration event mapper"]
    F --> G["Versioned event contract"]
    G --> H["Outbox / KafkaTemplate"]
    H --> I["Kafka topic"]
    I --> J["Consumer service"]
~~~

Không bắt buộc mọi ứng dụng phải có hai lớp event riêng biệt. Với hệ thống nhỏ, domain event và integration event có thể cùng một class nếu semantics và ownership được thiết kế rõ. Tuy nhiên, không nên để class persistence entity tự động trở thành event contract chỉ vì nó đã có sẵn dữ liệu.

## 3. Vì sao serialize trực tiếp JPA entity gây rủi ro?

### 3.1. Lazy loading và persistence context

JPA thường tải quan hệ theo chiến lược LAZY. Khi serializer truy cập customer hoặc lines sau khi transaction đóng, Hibernate có thể ném LazyInitializationException. Nếu transaction vẫn mở, serialization có thể kích hoạt nhiều truy vấn ngoài dự kiến.

Ví dụ:

~~~java
kafkaTemplate.send("orders", orderEntity.getId().toString(), orderEntity);
~~~

Serializer cần đọc các getter để tạo JSON. Nếu getter truy cập quan hệ lazy, quá trình serialize có thể kích hoạt SQL hoặc lỗi vì persistence context đã đóng.

### 3.2. Vòng tham chiếu hai chiều

Một entity Order có thể tham chiếu Customer, trong khi Customer lại có danh sách orders. Serializer đi theo quan hệ này có thể tạo vòng lặp đệ quy hoặc payload rất lớn.

~~~text
Order
  -> Customer
       -> Orders
            -> Customer
                 -> ...
~~~

Các annotation Jackson như JsonManagedReference, JsonBackReference hoặc JsonIgnore có thể làm JSON serialize được, nhưng chúng đang điều chỉnh cách xuất entity thay vì tạo ra một hợp đồng tích hợp ổn định.

### 3.3. Thay đổi database vô tình thay đổi message

Thêm trường internalStatus, đổi tên property, thay quan hệ hoặc thay kiểu dữ liệu có thể làm JSON thay đổi. Consumer cũ có thể không hiểu field mới, hoặc consumer mới có thể phụ thuộc vào trường nội bộ không nên công bố.

Migration database và schema evolution của event là hai quy trình khác nhau. Không nên để migration database tự quyết định thay đổi payload Kafka.

### 3.4. Lộ dữ liệu không dành cho consumer

Entity có thể chứa email, số điện thoại, địa chỉ, ghi chú nội bộ, điểm rủi ro, thông tin audit hoặc dữ liệu phục vụ vận hành. Khi serialize toàn bộ entity, các trường đó có thể được phát tán tới nhiều service và lưu lâu trong Kafka.

Event contract cần áp dụng nguyên tắc data minimization: chỉ công bố dữ liệu mà consumer được phép và thực sự cần.

### 3.5. Consumer bị phụ thuộc vào class Java của producer

Nếu serializer gửi type header chứa tên class đầy đủ, consumer có thể phải biết package và class của producer. Khi producer refactor package, consumer có thể không deserialize được dù JSON fields không đổi.

Spring Kafka hỗ trợ type headers và type mappings, nhưng type header là metadata serialization, không phải domain contract. Với hệ thống nhiều service hoặc nhiều ngôn ngữ, nên xác định kiểu payload bằng schema hoặc event type ổn định thay vì dựa vào class name nội bộ.

## 4. Thiết kế event contract độc lập

Một event contract tốt nên trả lời được:

- Sự kiện nào đã xảy ra?
- Aggregate hoặc business object nào liên quan?
- Sự kiện xảy ra khi nào?
- Consumer cần những dữ liệu nào để phản ứng?
- Event có thể được nhận diện và deduplicate bằng gì?
- Consumer biết schema hoặc event type nào đang được gửi?
- Những trường nào là bắt buộc, tùy chọn hoặc có default?

Một envelope thường có các metadata:

| Trường | Ý nghĩa |
|---|---|
| eventId | ID duy nhất của một event |
| eventType | Tên sự kiện ổn định |
| schemaVersion | Phiên bản contract |
| occurredAt | Thời điểm nghiệp vụ xảy ra |
| producer | Service phát event |
| correlationId | Liên kết với request hoặc workflow |
| aggregateId | Identity của aggregate liên quan |

Các metadata này có thể nằm trong payload, Kafka headers hoặc schema registry metadata. Hãy chọn một quy ước thống nhất và ghi rõ trong contract. Không tạo nhiều nguồn dữ liệu mâu thuẫn, ví dụ eventType trong JSON khác với header.

Ví dụ event cụ thể:

~~~java
public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        String orderNumber,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt,
        String correlationId
) {}
~~~

Tên OrderConfirmedV1 thể hiện đây là hợp đồng event version 1. Việc đặt version trong tên class chỉ là lựa chọn tổ chức code; wire contract vẫn cần eventType/schema version rõ ràng và không nên phụ thuộc tên class Java.

### Dùng tên event diễn tả sự thật đã xảy ra

Nên dùng:

- OrderCreated
- OrderConfirmed
- PaymentCaptured
- ShipmentDispatched

Tránh dùng tên chung hoặc mệnh lệnh:

- Order
- UpdateOrder
- ProcessPayment
- DoShipment

Event mô tả điều đã xảy ra. Command mô tả điều được yêu cầu thực hiện. Phân biệt hai loại message giúp consumer hiểu đúng semantics và tránh xử lý event như một yêu cầu chưa được xác nhận.

## 5. Chọn snapshot hay chỉ gửi reference

Có hai cách phổ biến để mô tả dữ liệu trong event.

**Snapshot event** mang các giá trị cần thiết tại thời điểm sự kiện xảy ra. Ví dụ OrderCreated mang orderNumber, customerId, tổng tiền, currency và các dòng hàng đã được xác nhận.

**Reference event** chỉ mang orderId hoặc aggregateId để consumer gọi API hoặc truy vấn nguồn dữ liệu khi cần thêm thông tin.

| Cách | Ưu điểm | Đánh đổi |
|---|---|---|
| Snapshot | Consumer xử lý độc lập, replay có thể tái hiện dữ liệu tại thời điểm event | Payload lớn hơn, cần quản lý dữ liệu nhạy cảm |
| Reference | Payload nhỏ, giảm trùng lặp dữ liệu | Consumer phụ thuộc API/database nguồn và có thể đọc trạng thái mới thay vì trạng thái lúc event xảy ra |

Nếu consumer cần biết giá đơn hàng tại thời điểm tạo đơn, event nên mang snapshot giá và currency. Nếu chỉ mang orderId rồi gọi API sau vài giờ, giá trị có thể đã thay đổi; consumer sẽ không tái hiện được sự kiện gốc.

Không gửi toàn bộ entity chỉ vì muốn tạo snapshot. Hãy chọn đúng các trường thuộc contract và chuyển quan hệ thành scalar values hoặc nested value object đã định nghĩa.

## 6. Mapper từ persistence entity sang event

Mapper là ranh giới chuyển đổi giữa persistence model và event contract. Nó cần rõ ràng, dễ kiểm thử và chỉ lấy dữ liệu cần thiết.

Ví dụ mapper thủ công:

~~~java
@Component
public class OrderEventMapper {

    public OrderCreatedV1 toOrderCreated(
            OrderEntity order,
            UUID eventId,
            Instant occurredAt,
            String correlationId) {

        List<OrderLineCreatedV1> items = order.getLines()
                .stream()
                .map(line -> new OrderLineCreatedV1(
                        line.getProduct().getSku(),
                        line.getProduct().getName(),
                        line.getQuantity(),
                        line.getUnitPriceMinor()
                ))
                .collect(Collectors.toList());

        return new OrderCreatedV1(
                eventId,
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getId(),
                order.getTotalAmountMinor(),
                order.getCurrency(),
                occurredAt,
                correlationId,
                items
        );
    }
}
~~~

Ví dụ trên cho thấy event chỉ nhận giá trị cần thiết. Nó không giữ tham chiếu đến order, customer hoặc product entity.

Nếu sử dụng MapStruct, mapper cũng nên nhận entity và trả về event DTO. Không để MapStruct tự động map toàn bộ quan hệ không cần thiết. Khai báo rõ các field, bỏ qua trường không thuộc contract và kiểm tra generated mapping khi schema thay đổi.

### Kiểm soát lazy relationship

Mapper trong ví dụ truy cập customer, lines và product. Hãy đảm bảo dữ liệu cần thiết đã được tải trong transaction.

Ví dụ repository dùng entity graph:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    @EntityGraph(attributePaths = {
            "customer",
            "lines",
            "lines.product"
    })
    Optional<OrderEntity> findWithEventDataById(UUID id);
}
~~~

Application service gọi mapper khi transaction và persistence context còn hoạt động:

~~~java
@Transactional(readOnly = true)
public OrderCreatedV1 buildEvent(UUID orderId) {
    OrderEntity order = orderRepository
            .findWithEventDataById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    return orderEventMapper.toOrderCreated(
            order,
            UUID.randomUUID(),
            Instant.now(),
            null
    );
}
~~~

Trong ví dụ này eventId được tạo khi xây dựng event. Với event được lưu vào outbox, eventId phải được tạo một lần và lưu cùng outbox record để lần publish lại giữ nguyên identity.

Không mở Open Session in View chỉ để serializer có thể truy cập lazy entity. Việc đó che giấu boundary persistence và có thể tạo truy vấn không kiểm soát trong lúc serialize.

## 7. Tạo event từ domain event thay vì đọc entity ở tầng Kafka

Trong kiến trúc domain-oriented, application service có thể nhận domain event sau khi aggregate thay đổi trạng thái. Adapter tích hợp ánh xạ domain event sang integration event.

Ví dụ domain event:

~~~java
public record OrderConfirmedDomainEvent(
        UUID orderId,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt
) {}
~~~

Integration contract:

~~~java
public record OrderConfirmedV1(
        UUID eventId,
        String orderId,
        String customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt
) {}
~~~

Mapper:

~~~java
@Component
public class OrderIntegrationEventMapper {

    public OrderConfirmedV1 toIntegrationEvent(
            OrderConfirmedDomainEvent event,
            UUID eventId) {

        return new OrderConfirmedV1(
                eventId,
                event.orderId().toString(),
                event.customerId().toString(),
                event.totalAmountMinor(),
                event.currency(),
                event.occurredAt()
        );
    }
}
~~~

Domain event và integration event có thể trùng dữ liệu, nhưng không bắt buộc trùng cấu trúc hoặc tên. Domain event phản ánh ngôn ngữ nội bộ của bounded context; integration event phản ánh điều mà consumer bên ngoài được phép dựa vào.

Nếu một thay đổi domain nội bộ không ảnh hưởng hợp đồng tích hợp, mapper có thể giữ nguyên integration event. Đây là lợi ích quan trọng của ranh giới chuyển đổi.

## 8. Publish event bằng KafkaTemplate

Sau khi đã có event DTO, producer chỉ gửi contract đó. Không truyền persistence entity vào KafkaTemplate.

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedV1> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedV1> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedV1>> publish(
            OrderCreatedV1 event) {

        return kafkaTemplate.send(
                "orders.created",
                event.orderId().toString(),
                event
        );
    }
}
~~~

Key thường là aggregate ID hoặc business key ổn định để các event cùng aggregate có thể được phân phối vào cùng partition trong một topic. Không dùng eventId làm key nếu nghiệp vụ cần ordering theo orderId.

Ví dụ listener consumer nhận contract:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreatedV1 event) {
    billingService.prepareInvoice(event);
}
~~~

Consumer không cần dependency vào OrderEntity, CustomerEntity hoặc repository của producer. Nó chỉ cần hiểu event contract và dữ liệu mà contract công bố.

Ví dụ dùng CompletableFuture vì Spring Kafka 3.0 trở lên trả về CompletableFuture từ KafkaTemplate.send(). Với Spring Kafka 2.x, API trả về ListenableFuture và cách đăng ký callback cần điều chỉnh theo version đang dùng. Các ví dụ dùng Java record giả định Java 16 trở lên; dự án cũ có thể dùng immutable class với constructor và getter.

## 9. Cấu hình JSON serialization độc lập với class entity

Spring Kafka cung cấp JsonSerializer và JsonDeserializer dựa trên Jackson. Serializer chuyển object thành JSON bytes; deserializer cần biết kiểu đích hoặc dùng type metadata để xác định kiểu.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.contract.OrderCreatedV1
        spring.json.trusted.packages: com.example.contract
        spring.json.use.type.headers: false
~~~

Ví dụ này dành cho một consumer group chỉ nhận OrderCreatedV1. Nếu một topic có nhiều loại event, hãy thiết kế type mapping hoặc envelope có eventType và cấu hình resolver rõ ràng. Không tắt type headers rồi giả định một deserializer mặc định có thể tự nhận diện mọi kiểu payload.

### Type headers và class name

Spring Kafka mặc định có thể thêm type information vào Kafka headers. Header này thường chứa thông tin để xác định kiểu Java của payload. Khi producer và consumer là hai service độc lập, việc phụ thuộc vào package/class name của producer làm tăng coupling.

Có thể chọn một trong các cách:

- Dùng một target type cố định cho topic chỉ chứa một event type và bỏ qua type headers.
- Dùng type mapping với token ổn định, ánh xạ token sang class tương ứng ở từng service.
- Dùng envelope có eventType rõ ràng và resolver chỉ chấp nhận danh sách type được phép.
- Dùng schema registry với Avro, Protobuf hoặc JSON Schema khi cần quản lý schema tập trung.

Chỉ thêm package thực sự được tin cậy vào trusted packages. Không cấu hình wildcard toàn bộ package hoặc mọi package chỉ để tránh lỗi deserialization. Type metadata đến từ message cần được xem là input bên ngoài.

Tài liệu Spring Kafka mô tả các tùy chọn ADD_TYPE_INFO_HEADERS, USE_TYPE_INFO_HEADERS, VALUE_DEFAULT_TYPE, TRUSTED_PACKAGES và TYPE_MAPPINGS; hãy đối chiếu phiên bản dependency đang chạy vì API và class name serializer có thể thay đổi theo thế hệ Spring Kafka. <https://docs.spring.io/spring-kafka/reference/kafka/serdes.html>

## 10. Không chia sẻ persistence module giữa producer và consumer

Một cách làm thường thấy là tạo module chung chứa entity và cho producer/consumer cùng import. Khi entity thay đổi, cả hai service có thể phải nâng version module, dù consumer chỉ cần một phần dữ liệu.

Module contract nên chứa các kiểu event công khai và schema liên quan, không chứa JPA entity, repository hoặc persistence configuration.

Có thể tổ chức:

~~~text
order-service
  domain/
  persistence/
    OrderEntity
    OrderRepository
  integration/
    OrderEventMapper
    OrderEventPublisher

order-contract
  OrderCreatedV1
  OrderConfirmedV1
  OrderLineCreatedV1

billing-service
  messaging/
    OrderCreatedListener
  application/
    BillingService
~~~

Một số hệ thống không chia sẻ Java contract module mà quản lý schema trong Schema Registry hoặc repository riêng. Consumer có thể dùng Java, Go, Python hoặc .NET mà vẫn hiểu cùng một wire contract.

Nếu dùng shared library, giữ nó nhỏ và version độc lập. Tránh đưa toàn bộ package domain/persistence của producer vào dependency của consumer.

## 11. Schema evolution là hợp đồng riêng của event

Database schema có thể thay đổi vì tối ưu truy vấn, chuẩn hóa dữ liệu hoặc thay đổi cách lưu trữ. Event schema thay đổi khi consumer cần dữ liệu mới hoặc semantics của event thay đổi.

Không phải mọi thay đổi entity đều cần thay đổi event. Ví dụ thêm cột internalRiskScore chỉ phục vụ fraud engine nội bộ không có nghĩa OrderCreated phải thêm trường này.

Ngược lại, nếu consumer cần biết deliveryMethod mới, đó là thay đổi contract và cần đánh giá compatibility.

### Các hướng compatibility phổ biến

| Chế độ | Ý nghĩa tổng quát | Khi cân nhắc |
|---|---|---|
| Backward | Schema mới đọc được dữ liệu được ghi theo schema cũ | Consumer mới cần đọc record cũ |
| Forward | Consumer/schema cũ đọc được dữ liệu được ghi theo schema mới | Producer mới triển khai trước consumer |
| Full | Cả backward và forward | Hai thế hệ producer/consumer cần cùng tương thích |
| None | Không kiểm tra compatibility | Chỉ dùng khi chấp nhận breaking change có kế hoạch |

Tên và hướng kiểm tra cụ thể phụ thuộc Schema Registry. Với topic lưu event lâu dài, cần xem cả dữ liệu lịch sử; chế độ transitive kiểm tra với nhiều version cũ hơn thay vì chỉ version liền trước.

Không thể chỉ nhìn tên BACKWARD hoặc FORWARD rồi áp dụng máy móc. Hãy kiểm tra registry đang dùng, format Avro/Protobuf/JSON Schema và cách serializer/deserializer đọc schema ID.

## 12. Quy tắc thay đổi event an toàn

Các thay đổi thường ít rủi ro hơn:

- Thêm field tùy chọn với default hợp lý.
- Thêm metadata không làm thay đổi semantics hiện có.
- Thêm giá trị mới vào một enum nếu consumer cũ có chiến lược xử lý unknown value.
- Thêm nested object tùy chọn có schema rõ ràng.
- Tăng độ chi tiết của tài liệu contract mà không thay đổi wire format.

Các thay đổi có thể phá vỡ consumer:

- Xóa field đang được consumer sử dụng.
- Đổi tên field mà không có giai đoạn chuyển tiếp.
- Đổi kiểu dữ liệu, ví dụ String sang Integer.
- Đổi đơn vị timestamp từ milliseconds sang seconds.
- Thay ý nghĩa field nhưng giữ nguyên tên.
- Đổi currency hoặc quy tắc làm tròn mà không công bố semantics.
- Thêm enum value mới khi consumer cũ không xử lý giá trị chưa biết.
- Thay event snapshot bằng reference nhưng không thông báo.

Một quy tắc quan trọng: field mới không nên trở thành bắt buộc đối với consumer cũ nếu producer có thể phát message mà consumer cũ không hiểu.

### Ví dụ thêm field tùy chọn

Version 1:

~~~json
{
  "eventId": "e-100",
  "orderId": "o-100",
  "currency": "VND",
  "totalAmountMinor": 250000
}
~~~

Version 2 thêm sourceChannel:

~~~json
{
  "eventId": "e-100",
  "orderId": "o-100",
  "currency": "VND",
  "totalAmountMinor": 250000,
  "sourceChannel": "MOBILE"
}
~~~

Nếu consumer cũ bỏ qua field lạ và contract cho phép field tùy chọn, nó có thể tiếp tục hoạt động. Consumer mới cần định nghĩa hành vi khi đọc record cũ không có sourceChannel.

Không dựa vào một serializer cụ thể để mặc định mọi consumer đều bỏ qua unknown field. Kiểm thử cấu hình Jackson, schema format và version thực tế.

## 13. Khi nào cần event version mới?

Không cần tạo version mới chỉ vì thêm một field tùy chọn tương thích. Nhưng nên tạo version hoặc event type mới khi semantics thay đổi hoặc không thể bảo đảm consumer cũ hiểu đúng.

Ví dụ:

- OrderCreatedV1 mang tổng tiền theo đơn vị minor currency.
- Một thay đổi muốn chuyển totalAmount sang decimal string với quy tắc scale khác.
- Event cũ chỉ thể hiện order đã tạo; event mới thay đổi thành order đã được thanh toán và xác nhận tồn kho.

Không nên giữ cùng eventType nhưng thay ý nghĩa. Consumer có thể deserialize thành công nhưng xử lý sai nghiệp vụ, đây là lỗi nguy hiểm hơn lỗi parse.

Các chiến lược version:

1. Thêm schema field tương thích trong cùng topic.
2. Dùng eventType/version mới trong cùng topic nếu consumer có thể dispatch theo type.
3. Dùng topic mới khi cần triển khai song song hoặc tách ownership rõ ràng.
4. Publish song song hai contract trong giai đoạn migration có kiểm soát.
5. Ngừng version cũ sau khi xác nhận không còn consumer cần nó.

Không publish hai event tương đương mà không có eventId hoặc migration plan rõ ràng. Consumer có thể xử lý cả hai và tạo side effect trùng.

## 14. Event là dữ liệu lịch sử, không phải bản sao entity hiện tại

Một event cần giữ sự thật tại thời điểm xảy ra. Nếu OrderCreated được phát lúc 10:00 và order đổi địa chỉ lúc 11:00, replay OrderCreated vẫn phải diễn tả dữ liệu đúng lúc 10:00 theo contract.

Đừng serialize lại entity hiện tại mỗi khi cần replay event cũ. Entity có thể đã thay đổi, quan hệ đã bị xóa hoặc field đã được migration.

Nếu event mang snapshot, hãy tạo payload tại thời điểm nghiệp vụ xảy ra và lưu đúng payload đó trong outbox/event store nếu cần replay.

Nếu event chỉ mang reference, hãy ghi rõ consumer đang lấy trạng thái hiện tại từ API nguồn; đó là một semantics khác với snapshot lịch sử.

Không dùng event như một cơ chế gửi toàn bộ database row. Event là hợp đồng truyền tải facts có ý nghĩa nghiệp vụ.

## 15. Transactional outbox: lưu event cùng transaction nghiệp vụ

Nếu application service cập nhật database rồi gọi KafkaTemplate trực tiếp trong cùng method @Transactional, transaction database và Kafka producer transaction thông thường không tự trở thành một transaction nguyên tử.

Có thể xảy ra:

- Database commit thành công nhưng Kafka publish thất bại: consumer không nhận event.
- Kafka publish thành công nhưng database rollback: consumer nhận event cho thay đổi chưa được commit.
- Publish thành công nhưng service chết trước khi ghi nhận trạng thái: retry có thể publish duplicate.

Transactional outbox giải quyết bằng cách ghi business state và outbox row trong cùng một database transaction. Một relay riêng đọc outbox rồi publish Kafka.

~~~mermaid
flowchart TD
    A["Application service"] --> B["DB transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox row"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox relay"]
    F --> G["KafkaTemplate"]
    G --> H["Kafka topic"]
    H --> I["Consumer"]
~~~

Ví dụ outbox entity tối giản:

~~~java
@Entity
@Table(name = "outbox_message")
public class OutboxMessage {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String aggregateId;

    @Column(nullable = false)
    private String eventType;

    @Column(nullable = false)
    private int schemaVersion;

    @Lob
    @Column(nullable = false)
    private String payload;

    @Column(nullable = false)
    private Instant createdAt;

    private Instant publishedAt;

    // status, attempts and persistence methods
}
~~~

Application service tạo event DTO, serialize thành payload và lưu outbox:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    OrderEntity order = orderFactory.create(command);
    orderRepository.save(order);

    UUID eventId = UUID.randomUUID();
    Instant occurredAt = Instant.now();

    OrderCreatedV1 event = orderEventMapper.toOrderCreated(
            order,
            eventId,
            occurredAt,
            command.correlationId()
    );

    String payload;
    try {
        payload = objectMapper.writeValueAsString(event);
    }
    catch (JsonProcessingException ex) {
        throw new EventSerializationException(ex);
    }

    outboxRepository.save(
            OutboxMessage.pending(
                    event.eventId(),
                    event.orderId().toString(),
                    "OrderCreated",
                    1,
                    payload,
                    occurredAt
            )
    );
}
~~~

OrderEntity và outbox row được commit hoặc rollback trong cùng database transaction. Kafka chưa được gọi trong transaction nghiệp vụ này.

Relay đọc các outbox row chưa publish, gửi payload đến topic tương ứng và đánh dấu published sau khi nhận xác nhận từ broker. Cần thiết kế locking/claim để nhiều relay instance không xử lý cùng row đồng thời.

### Outbox vẫn có thể publish duplicate

Nếu Kafka nhận record thành công nhưng relay chết trước khi cập nhật publishedAt, row sẽ được gửi lại khi relay chạy lại. Đây là hành vi at-least-once thường gặp của outbox.

Giữ nguyên eventId trong mọi lần publish lại và yêu cầu consumer idempotent theo eventId. Không tạo eventId mới khi relay retry cùng một outbox row.

Nếu cần thứ tự theo aggregate, relay cần giữ thứ tự publish cho cùng aggregate hoặc dùng sequence number và kiểm tra ở consumer. Nhiều relay song song có thể publish event của cùng aggregate sai thứ tự nếu không có cơ chế claim/partition phù hợp.

## 16. Vì sao @TransactionalEventListener(AFTER_COMMIT) chưa đủ cho publish quan trọng?

Có thể dùng Spring @TransactionalEventListener(phase = AFTER_COMMIT) để publish sau khi database transaction commit. Điều này tránh publish event khi transaction rollback.

Tuy nhiên, có một khoảng thời gian giữa database commit và callback gửi Kafka. Nếu process chết trong khoảng đó, event không được gửi và không có outbox row để relay khôi phục.

Vì vậy:

- Dùng AFTER_COMMIT cho side effect không quan trọng hoặc có thể tái tạo.
- Dùng transactional outbox khi việc phát event phải bền vững cùng transaction nghiệp vụ.
- Không gọi hai cơ chế là atomic database-to-Kafka transaction nếu không có cơ chế phối hợp thực sự.

Outbox tăng thêm bảng, relay và cleanup, nhưng tạo được nguồn dữ liệu bền vững để retry publish sau restart.

## 17. Quản lý tiền tệ, thời gian và kiểu dữ liệu trong contract

Một event contract cần định nghĩa semantics, không chỉ định nghĩa kiểu Java.

### Tiền tệ

Không dùng double hoặc float cho tiền. Hai lựa chọn thường gặp:

- Số nguyên theo minor unit, ví dụ 1250 VND minor units hoặc 1099 cents tùy currency.
- Decimal string có quy tắc scale và rounding được ghi rõ.

Nếu dùng totalAmountMinor, contract phải quy định cách xác định exponent của currency. Không giả định mọi currency có hai chữ số thập phân.

### Thời gian

Dùng timestamp có timezone/offset rõ ràng, thường là Instant UTC hoặc ISO-8601. Ghi rõ occurredAt là thời điểm nghiệp vụ xảy ra, không phải thời điểm Kafka nhận record.

Nếu cần thời điểm publish, dùng publishedAt riêng. Không đổi đơn vị milliseconds/seconds giữa các version mà không thay đổi contract.

### Enum và giá trị chưa biết

Consumer cũ có thể nhận enum value mới. Hãy định nghĩa hành vi unknown value: bỏ qua, ghi nhận, chuyển quarantine hoặc dùng UNKNOWN nếu schema và nghiệp vụ cho phép.

### Null và field vắng mặt

Null, field không tồn tại và giá trị mặc định có thể mang semantics khác nhau. Contract cần nói rõ field nào bắt buộc, nullable, optional và default. Không dựa vào cách Jackson serialize null để ngầm định nghĩa hợp đồng.

## 18. Bảo vệ dữ liệu và giới hạn thông tin event

Event có thể được lưu trong Kafka lâu hơn bản ghi database và được nhiều service đọc. Hãy coi payload là dữ liệu được phát tán qua một ranh giới hệ thống.

Trước khi thêm field, xác định:

- Consumer nào cần field này?
- Có dữ liệu cá nhân hoặc dữ liệu nhạy cảm không?
- Có thể gửi identifier thay vì giá trị nhạy cảm không?
- Retention và quyền truy cập topic có phù hợp không?
- Có cần mã hóa hoặc masking không?
- Field có thể bị ghi vào log, tracing hoặc dead-letter topic không?

Không đưa password, access token, secret, thông tin thanh toán đầy đủ hoặc trường nội bộ vào event. Kafka ACL kiểm soát ai được đọc topic; nó không thay thế việc tối thiểu hóa dữ liệu trong payload.

Nếu event cần mang dữ liệu cá nhân, cần xác định mục đích, quyền truy cập, retention và quy trình xử lý yêu cầu xóa theo chính sách dữ liệu của hệ thống.

## 19. Kiểm thử ranh giới persistence và event contract

Không chỉ kiểm tra mapper trả về object khác entity. Cần kiểm tra contract độc lập với database schema và serialization thực tế.

Các lớp kiểm thử:

### Mapper unit test

- Tạo entity có customer, lines và product.
- Xác nhận mapper chỉ lấy field được công bố.
- Xác nhận không có internalRiskScore, JPA version hoặc audit user trong event.
- Xác nhận null/optional relationship có hành vi rõ.
- Xác nhận snapshot đúng tại thời điểm event được tạo.

### Serialization contract test

- Serialize event thành JSON.
- So sánh tên field, kiểu dữ liệu và định dạng timestamp.
- Deserialize payload bằng target type mà consumer dùng.
- Xác nhận không cần class name của producer trong type header nếu contract không phụ thuộc nó.
- Xác nhận unknown field và field thiếu được xử lý theo quy tắc đã định.

### Compatibility test

- Consumer mới đọc payload version cũ.
- Consumer cũ đọc payload version mới nếu compatibility policy yêu cầu.
- Enum value mới được xử lý đúng.
- Thay đổi field không làm đổi semantics hiện tại.
- Schema Registry từ chối thay đổi breaking khi policy được bật.

### Outbox integration test

- Database rollback thì không có business row và outbox row.
- Database commit thì cả hai row cùng tồn tại.
- Kafka publish thành công rồi relay chết trước khi đánh dấu published: event có thể được gửi lại nhưng eventId không đổi.
- Nhiều relay instance không làm mất row.
- Consumer nhận duplicate chỉ tạo side effect một lần.
- Thứ tự event của cùng aggregate được giữ theo yêu cầu.

Dùng Testcontainers cho database và Kafka khi cần xác nhận hành vi tích hợp thực tế. Dùng fixture JSON cố định để kiểm tra wire contract; tránh chỉ serialize rồi deserialize cùng một class vì producer và consumer có thể cùng mắc một lỗi mà test vẫn pass.

## 20. Chuyển đổi từ publish entity sang publish event DTO

Nếu hệ thống đang gửi JPA entity trực tiếp, hãy chuyển đổi theo từng bước có kiểm soát:

1. Liệt kê topic, producer và consumer đang đọc payload entity.
2. Ghi lại các field consumer thực sự sử dụng, bao gồm field đọc từ nested relationship.
3. Định nghĩa event contract mới theo nhu cầu tích hợp, không sao chép toàn bộ entity.
4. Tạo mapper và unit test cho các field công khai.
5. Chọn cách version: thêm field tương thích, type mới hoặc topic mới.
6. Cấu hình serializer/deserializer và type mapping cho contract.
7. Triển khai consumer có thể đọc contract mới trước khi producer chuyển hẳn.
8. Publish thử hoặc dual-publish trong giai đoạn chuyển tiếp nếu cần, với event identity và deduplication rõ ràng.
9. Theo dõi consumer lag, deserialization error, schema error và business processing result.
10. Ngừng payload entity cũ sau khi xác nhận không còn consumer phụ thuộc.
11. Xóa dependency persistence khỏi shared contract module nếu có.
12. Lưu fixture payload cũ để kiểm thử replay và migration.

Không thay payload tại một topic mà không kiểm kê consumer. Một consumer cũ có thể vẫn đang chạy trong một deployment chậm cập nhật hoặc một job replay ít được sử dụng.

Nếu dual-publish, tránh phát hai event cùng semantics mà consumer không biết chúng là hai bản của cùng một fact. Dùng eventId ổn định, phân biệt topic/version và có kế hoạch dừng rõ ràng.

## 21. Các lỗi thiết kế thường gặp

**Serialize trực tiếp JPA entity.** Payload phụ thuộc ORM, lazy loading và database mapping. Tạo event DTO riêng.

**Dùng entity làm shared contract.** Consumer bị phụ thuộc vào persistence module của producer. Tạo contract module độc lập hoặc quản lý schema riêng.

**Map toàn bộ object graph.** Payload có thể rất lớn, vòng tham chiếu và lộ dữ liệu. Chọn field cần công bố và chuyển quan hệ thành ID/value snapshot.

**Map entity sau khi transaction đã đóng.** Lazy relationship có thể gây LazyInitializationException. Fetch dữ liệu cần thiết và map trong transaction hoặc dùng projection.

**Thêm field database rồi vô tình thêm field event.** Contract thay đổi mà không có compatibility review. Mapper phải ánh xạ tường minh.

**Dùng type header chứa class name làm hợp đồng.** Consumer phụ thuộc package producer. Dùng eventType/schema ổn định hoặc type mapping.

**Tắt type header nhưng không cấu hình target type.** Consumer không biết deserialize payload thành class nào. Cấu hình default type hoặc resolver rõ ràng.

**Tin cậy mọi package khi deserialize.** Message có thể điều khiển class resolution không mong muốn. Chỉ khai báo package/type được phép.

**Đổi semantics mà không đổi version.** Consumer deserialize thành công nhưng hiểu sai event. Tạo event type/version mới khi ý nghĩa thay đổi.

**Gửi reference nhưng mong consumer có snapshot lịch sử.** API nguồn trả trạng thái hiện tại, không phải trạng thái lúc event xảy ra. Chọn snapshot nếu cần replay chính xác.

**Publish Kafka trực tiếp trong database transaction và nghĩ là atomic.** Database và Kafka có thể commit độc lập. Dùng outbox hoặc cơ chế phối hợp phù hợp.

**Tạo eventId mới mỗi lần relay retry.** Consumer không deduplicate được cùng một fact. Lưu eventId trong outbox và giữ nguyên khi publish lại.

**Chỉ test round-trip cùng class.** Test không phát hiện contract coupling. Dùng fixture JSON và compatibility test giữa các version.

## 22. Checklist tách event khỏi persistence entity

- [ ] Persistence entity chỉ phục vụ lưu trữ và truy vấn.
- [ ] Event contract không có JPA annotation hoặc ORM proxy.
- [ ] Domain event và integration event có ownership rõ ràng.
- [ ] Event name mô tả fact đã xảy ra.
- [ ] Có eventId ổn định và aggregateId/business key phù hợp.
- [ ] Có occurredAt và semantics thời gian rõ ràng.
- [ ] Chỉ công bố field consumer thực sự cần.
- [ ] Không phát tán internal field, secret hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Quan hệ entity được chuyển thành ID hoặc snapshot value object.
- [ ] Mapper được kiểm thử độc lập.
- [ ] Lazy relationship được tải có chủ đích trước khi map.
- [ ] JSON serializer/deserializer có target type hoặc type mapping rõ.
- [ ] Không phụ thuộc class name/package của producer như wire contract.
- [ ] Trusted packages được giới hạn.
- [ ] Schema evolution có compatibility policy.
- [ ] Thay đổi semantics tạo event type/version mới.
- [ ] Snapshot/reference được chọn theo yêu cầu replay và tính nhất quán.
- [ ] Database và Kafka publish có cơ chế reliability phù hợp.
- [ ] Outbox giữ nguyên eventId qua retry.
- [ ] Consumer idempotent theo eventId.
- [ ] Có mapper, serialization, compatibility và outbox integration tests.
- [ ] Có kế hoạch migration nếu topic hiện đang mang entity payload.

## Kết luận

Persistence entity mô tả dữ liệu được lưu và quan hệ ORM; domain event diễn tả sự thật nghiệp vụ; integration event là hợp đồng công bố cho service khác. Không serialize trực tiếp entity lên Kafka vì điều đó kéo schema database, lazy relationship, proxy, trường nội bộ và class Java của producer vào payload công khai. Hãy tạo event DTO độc lập, ánh xạ tường minh, chọn snapshot hoặc reference theo semantics, quản lý type/schema version và kiểm thử compatibility. Khi event phải được phát cùng thay đổi database, transactional outbox giúp lưu business state và event intent trong cùng transaction; relay có thể publish lại nên eventId ổn định và consumer idempotent vẫn rất cần thiết.

## Tài liệu tham khảo

- [Spring Kafka – Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Apache Kafka – Design and Implementation](https://kafka.apache.org/documentation/#design)

