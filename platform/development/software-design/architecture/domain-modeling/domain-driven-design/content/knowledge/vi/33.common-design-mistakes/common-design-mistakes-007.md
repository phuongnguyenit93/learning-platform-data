# Để JPA, JSON hoặc framework quyết định toàn bộ mô hình

Domain-Driven Design (DDD) đặt mô hình miền ở trung tâm của thiết kế phần mềm. Mô hình cần diễn đạt những khái niệm, quy tắc và quyết định mà tổ chức thực sự quan tâm. JPA, JSON, ORM, web framework và message broker là những công nghệ giúp lưu trữ hoặc trao đổi thông tin. Chúng có thể ảnh hưởng đến cách triển khai, nhưng không nên tự quyết định một Order là gì, khi nào một Invoice được đóng, hay aggregate nào chịu trách nhiệm bảo vệ một invariant.

Một lỗi thiết kế phổ biến là để cấu trúc mà framework yêu cầu trở thành cấu trúc của domain model. Entity được tạo chủ yếu để ORM có thể hydrate; quan hệ hai chiều được thêm chỉ để tiện truy vấn; mọi field đều public để JSON serializer đọc; enum và trạng thái bị đặt theo tên cột; aggregate boundary bị quyết định bởi cách join bảng. Dần dần, mô hình nghiệp vụ trở thành một tập object phục vụ persistence hoặc serialization. Quy tắc bị đẩy ra service, controller và listener, khiến cùng một khái niệm có nhiều cách xử lý.

Bài học này giải thích cách nhận biết sự chi phối đó, phân biệt domain model với persistence model và API/message contract, tổ chức mapping giữa các mô hình, đồng thời dùng JPA và framework một cách thực dụng. Mục tiêu không phải cấm annotation hay buộc mọi dự án phải có nhiều lớp chuyển đổi. Mục tiêu là giữ quyền quyết định ngữ nghĩa nghiệp vụ ở đúng nơi, đồng thời kiểm soát chi phí kỹ thuật.

Sau bài học, người học có thể:

- phân biệt domain model, persistence model và transport/API model;
- nhận diện dấu hiệu framework đang quyết định aggregate, identity, lifecycle hoặc invariant;
- hiểu vì sao JPA entity và JSON DTO có các yêu cầu khác với domain object;
- lựa chọn giữa domain model độc lập, persistence-aware model và mô hình lai;
- thiết kế mapping không làm sai semantics của Entity, Value Object và Aggregate;
- xử lý lazy loading, bidirectional association, equals/hashCode và serialization;
- bảo vệ domain invariant bằng hành vi công khai thay vì setter do framework hoặc client gọi;
- kiểm thử mapping và adapter mà không để test framework thay thế test nghiệp vụ;
- chọn mức tách lớp phù hợp với độ phức tạp và chi phí bảo trì.

## 1. Ba mô hình phục vụ ba mục đích khác nhau

Một hệ thống DDD thường có ít nhất ba góc nhìn về cùng một thông tin.

**Domain model** diễn đạt ngôn ngữ, hành vi và quy tắc nghiệp vụ. Nó trả lời: đối tượng có ý nghĩa gì, ai được phép thay đổi nó, điều kiện nào phải luôn đúng và sự kiện nào xảy ra khi hành vi thành công?

**Persistence model** diễn đạt cách dữ liệu được lưu và truy xuất. Nó trả lời: bảng nào lưu dữ liệu, khóa và index ra sao, quan hệ được ánh xạ thế nào, transaction và concurrency được bảo vệ bằng cơ chế nào?

**Transport/API model** diễn đạt hợp đồng trao đổi qua HTTP, JSON, message hoặc file. Nó trả lời: consumer được gửi và nhận field nào, schema version nào, dữ liệu nào được công khai và cách tương thích khi hợp đồng thay đổi?

~~~mermaid
flowchart LR
    Client[Client / Consumer] --> API[API DTO / Message Contract]
    API --> App[Application Service]
    App --> Domain[Domain Model]
    Domain --> App
    App --> Persistence[Persistence Model / Repository Adapter]
    Persistence --> DB[(Database)]
~~~

Ba mô hình có thể chia sẻ một số kiểu dữ liệu đơn giản, nhưng không có nghĩa chúng phải có cùng cấu trúc.

Ví dụ một đơn hàng:

| Góc nhìn | Có thể biểu diễn |
|---|---|
| Domain model | Order, OrderLine, Money, OrderStatus, place(), cancel(), changeDeliveryAddress() |
| Persistence model | order_row, order_line_row, foreign key, version, indexes, audit columns |
| API model | CreateOrderRequest, OrderResponse, OrderLineResponse, error response |
| Integration contract | OrderPlaced event với event ID, order ID, snapshot và schema version |

Một API có thể cho phép client gửi productId và quantity. Domain model có thể cần ProductReference và Quantity. Persistence model có thể lưu product_id, quantity_value và unit_code. Những khác biệt đó là bình thường nếu mapping giữ đúng ý nghĩa.

### Câu hỏi kiểm tra

Khi một field xuất hiện trong cả ba mô hình, hãy hỏi:

- Nó có cùng semantics không?
- Nó có cùng lifecycle không?
- Ai có quyền tạo hoặc thay đổi nó?
- Có cần giữ nguyên tên và kiểu để tương thích không?
- Có phải chỉ là cách biểu diễn của cùng một khái niệm?

Nếu câu trả lời khác nhau, việc dùng chung một class có thể tạo coupling không cần thiết.

## 2. Vì sao framework dễ chi phối mô hình?

Framework cung cấp những quy ước tiện lợi. JPA muốn entity có identifier, cách tạo instance và mapping annotation. JSON serializer muốn biết field hoặc accessor nào được đưa vào payload. Web framework thường gắn request binding với object có thể deserialize. ORM có thể khuyến khích quan hệ hai chiều để điều hướng object graph.

Các quy ước này hữu ích, nhưng chúng được thiết kế để giải quyết vấn đề kỹ thuật tổng quát. Chúng không biết chính sách của Order Context hay ý nghĩa của một Payment đã capture.

Khi nhóm bắt đầu bằng câu hỏi “JPA cần class này như thế nào?” thay vì “nghiệp vụ cần đối tượng này bảo vệ điều gì?”, thiết kế dễ bị đảo chiều:

~~~text
Framework requirement
        |
        v
Class structure
        |
        v
Business rules scattered around
~~~

Một cách tiếp cận phù hợp với DDD là:

~~~text
Business language and rules
        |
        v
Domain model and boundaries
        |
        v
Ports and adapters
        |
        v
JPA / JSON / framework integration
~~~

Điều này không có nghĩa domain model phải hoàn toàn không biết bất kỳ chi tiết kỹ thuật nào. Trong nhiều ứng dụng, dùng JPA annotation trực tiếp trên domain entity là một đánh đổi hợp lý. Điểm cần giữ là framework không được thay thế quyết định về ngữ nghĩa, invariant và ownership.

## 3. Dấu hiệu mô hình bị JPA hoặc JSON dẫn dắt

Không phải cứ có annotation là sai. Cần nhìn vào hậu quả đối với mô hình.

| Dấu hiệu | Vì sao đáng xem xét | Hướng kiểm tra |
|---|---|---|
| Mọi entity đều có setter public | Bất kỳ caller nào cũng có thể bỏ qua business rule | Thay bằng hành vi có tên nghiệp vụ |
| Constructor rỗng public và object luôn ở trạng thái dở dang | Framework convenience có thể lan vào domain API | Giới hạn constructor phục vụ persistence |
| Aggregate chứa quan hệ hai chiều khắp nơi | Object graph phản ánh join hơn là consistency boundary | Xác định aggregate root và ownership |
| Collection được sửa trực tiếp từ ngoài | Bỏ qua invariant của root | Cung cấp add/remove operation có kiểm tra |
| Domain object có annotation JSON và trả thẳng ra API | Serialization làm lộ cấu trúc nội bộ | Dùng response DTO ở ranh giới |
| Enum được đặt theo legacy column hoặc JSON field | Storage/contract naming chi phối ubiquitous language | Mapping tên riêng tại adapter |
| Lazy loading xảy ra trong serializer | API vô tình kích hoạt truy vấn và N+1 | Tạo projection/DTO trong transaction phù hợp |
| Entity phụ thuộc HttpServletRequest hoặc framework context | Domain bị gắn với transport | Truyền dữ liệu cần thiết qua application layer |
| Quy tắc nằm trong lifecycle callback | Behavior khó thấy và khó gọi tường minh | Đưa quy tắc nghiệp vụ vào domain operation |
| Aggregate boundary bằng đúng ranh giới bảng | Cấu trúc lưu trữ quyết định consistency | Xác định invariant trước, rồi thiết kế mapping |

Một annotation đơn lẻ không phải bằng chứng của thiết kế xấu. Vấn đề xuất hiện khi yêu cầu kỹ thuật khiến domain phải chấp nhận trạng thái không hợp lệ, public mutation, quan hệ không có ý nghĩa hoặc contract ngoài bị ràng buộc vào cấu trúc nội bộ.

## 4. JPA entity không tự động là Domain Entity

Trong JPA, entity là một đối tượng có identity được persistence provider quản lý. Trong DDD, Entity là một khái niệm miền có identity và lifecycle nghiệp vụ. Hai khái niệm thường trùng nhau trong một số hệ thống, nhưng không đồng nhất theo định nghĩa.

Một JPA entity có thể chỉ là representation của một row. Ví dụ, một dòng dữ liệu phục vụ báo cáo có ID kỹ thuật nhưng không có hành vi hoặc lifecycle nghiệp vụ riêng. Ngược lại, một domain entity có thể được lưu bằng nhiều bảng hoặc được dựng từ nhiều nguồn dữ liệu.

### So sánh trách nhiệm

| JPA Entity | Domain Entity |
|---|---|
| Phục vụ persistence context và mapping | Biểu diễn identity và hành vi nghiệp vụ |
| Có thể cần constructor/accessor theo provider | Chỉ mở API cần cho model |
| Quan hệ phản ánh cách lưu hoặc điều hướng | Quan hệ phản ánh ngữ nghĩa và ownership |
| Lifecycle liên quan persist/merge/remove | Lifecycle liên quan tạo, kích hoạt, hoàn tất, hủy |
| Có thể có field kỹ thuật như version | Có thể có business state và invariant |
| Không nhất thiết chứa rule | Nên bảo vệ quy tắc thuộc entity/aggregate |

Nếu một class vừa là domain entity vừa là JPA entity, nó đang gánh hai vai trò. Cách này có thể hợp lý, nhưng cần chủ động chấp nhận giới hạn và bảo đảm API domain không bị framework chi phối.

### Đừng nhầm table row với Aggregate

Một bảng có thể chứa nhiều aggregate hoặc một aggregate có thể được lưu qua nhiều bảng. Aggregate boundary được quyết định bởi invariant và consistency requirement, không phải số lượng bảng.

Ví dụ Order có thể được lưu trong bảng orders và order_lines, nhưng điều đó không tự chứng minh mọi thông tin liên quan đến thanh toán, vận chuyển và tồn kho phải nằm trong cùng aggregate. Payment và Inventory thường có lifecycle và owner riêng.

## 5. Anemic Domain Model do setter và ORM convenience

Một mô hình anemic thường có object chỉ chứa dữ liệu, còn mọi hành vi được đặt trong service bên ngoài:

~~~java
public class OrderEntity {
    private OrderStatus status;
    private BigDecimal total;

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Sau đó service điều khiển field:

~~~java
public void cancel(OrderEntity order) {
    if (order.getStatus() == OrderStatus.SHIPPED) {
        throw new OrderCannotBeCancelled();
    }
    order.setStatus(OrderStatus.CANCELLED);
}
~~~

Một vấn đề là bất kỳ caller nào có reference tới object cũng có thể gọi setStatus(CANCELLED), kể cả khi Order đã shipped. Quy tắc chỉ được bảo vệ nếu mọi caller nhớ gọi đúng service.

Một domain model giàu hành vi có thể biểu diễn:

~~~java
public final class Order {
    private OrderStatus status;

    public void cancel(CancellationReason reason) {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderCannotBeCancelled();
        }
        if (status == OrderStatus.CANCELLED) {
            throw new OrderAlreadyCancelled();
        }

        status = OrderStatus.CANCELLED;
        recordEvent(new OrderCancelled(id, reason));
    }
}
~~~

Đây là ví dụ rút gọn; constructor, event collection và các trạng thái khác được lược bỏ. Điểm quan trọng là chuyển trạng thái đi qua operation có ngữ nghĩa, nơi invariant được kiểm tra.

JPA có thể cần cơ chế hydrate object. Điều đó không buộc ứng dụng phải mở mọi setter cho tất cả caller. Có thể dùng field access, constructor phù hợp, package visibility hoặc persistence adapter để giới hạn mutation theo khả năng của ngôn ngữ và provider.

## 6. Setter không phải lúc nào cũng sai, nhưng setter nghiệp vụ thường che giấu quyết định

Một setter như setDescription có thể phù hợp với một metadata không có quy tắc phức tạp. Nhưng các setter sau thường là dấu hiệu cần xem lại:

- setStatus(CANCELLED)
- setPaid(true)
- setAvailableQuantity(...)
- setCreditLimit(...)
- setApprovedBy(...)
- setClosedAt(...)

Tên setter chỉ nói rằng field bị thay đổi. Nó không diễn đạt điều kiện, lý do hoặc sự kiện nghiệp vụ.

Thay bằng các operation:

- cancel(reason)
- capture(paymentReference)
- reserve(quantity)
- approve(by, decision)
- close(at, actor)
- changeCreditLimit(newLimit, approval)

Operation có thể nhận các dữ kiện đã được xác thực và bảo vệ invariant. Nếu thay đổi cần policy hoặc dữ liệu từ bên ngoài, application service lấy chúng trước rồi gọi domain operation.

## 7. JSON DTO không phải Domain Model

JSON là một format trao đổi. API request/response có các yêu cầu riêng:

- tương thích với client cũ;
- tên field ổn định;
- validation cú pháp;
- nullable hoặc optional field;
- versioning;
- che giấu dữ liệu nội bộ;
- định dạng ngày giờ và tiền;
- xử lý lỗi theo HTTP contract.

Domain model có thể cần tên và cấu trúc khác để phản ánh ngôn ngữ nghiệp vụ. Trả thẳng domain entity thành JSON tạo coupling: đổi internal field có thể vô tình đổi API; serializer có thể gọi getter gây lazy loading; client có thể gửi field mà nó không được phép thay đổi.

### Ví dụ request và domain object

API request:

~~~java
public record CreateOrderRequest(
        String customerId,
        List<CreateOrderLineRequest> lines,
        String deliveryAddressId
) {
}
~~~

Application service chuyển request thành hành vi miền:

~~~java
public OrderId handle(CreateOrderRequest request) {
    CustomerId customerId = CustomerId.from(request.customerId());

    List<OrderLineRequest> lines = request.lines().stream()
            .map(line -> new OrderLineRequest(
                    ProductId.from(line.productId()),
                    Quantity.of(line.quantity())
            ))
            .toList();

    Order order = orderFactory.create(
            customerId,
            lines,
            AddressId.from(request.deliveryAddressId())
    );

    orderRepository.save(order);
    return order.id();
}
~~~

Ở đây API nhận string và number vì đó là kiểu JSON thuận tiện. Domain sử dụng CustomerId, ProductId và Quantity để thể hiện ngữ nghĩa. Request không được phép gửi status = PAID hoặc total = 0 để ép trạng thái; hệ thống tự tính và điều khiển lifecycle.

### Response DTO cũng cần được thiết kế riêng

~~~java
public record OrderResponse(
        String orderId,
        String status,
        BigDecimal totalAmount,
        String currency,
        List<OrderLineResponse> lines
) {
}
~~~

Mapper chuyển domain object sang response. Có thể thêm label, links, pagination hoặc field chỉ phục vụ UI mà không làm domain model thay đổi.

### Đừng bind JSON trực tiếp vào Aggregate

Nếu serializer có thể tạo Order từ JSON bằng cách điền field, client có thể gửi các thuộc tính không được phép thay đổi. Điều này làm yếu boundary của aggregate và tạo mass assignment vulnerability về mặt thiết kế.

Hãy dùng request DTO có tập field cho phép rõ ràng, rồi application service gọi factory hoặc domain operation. Các field như status, approvedAt, capturedAmount hoặc internalVersion nên do server quản lý trừ khi use case cụ thể cho phép thay đổi.

## 8. Persistence Model và mapping boundary

Có ba lựa chọn phổ biến.

### Lựa chọn A: Domain model độc lập, persistence model riêng

Domain model không mang annotation JPA. Repository adapter chuyển đổi giữa domain object và persistence record.

~~~text
Application Service
       |
       v
OrderRepository (port)
       |
       v
JpaOrderRepository (adapter)
       |
       +--> OrderRow / OrderLineRow
       |
       v
Database
~~~

Ưu điểm:

- Domain không phụ thuộc JPA.
- Persistence schema có thể thay đổi độc lập.
- Quan hệ và fetch strategy không rò vào domain.
- Dễ kiểm thử domain mà không cần ORM.

Chi phí:

- Có mapping hai chiều.
- Cần xử lý identity và version.
- Aggregate phức tạp có thể cần mapper cẩn thận.
- Có nguy cơ mapping bị thiếu hoặc không nhất quán.

### Lựa chọn B: Domain model dùng JPA trực tiếp

Một class có thể vừa là domain entity vừa là JPA entity:

~~~java
@Entity
@Table(name = "orders")
@Access(AccessType.FIELD)
public class Order {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private long version;

    protected Order() {
        // Dành cho persistence provider.
    }

    public void cancel(CancellationReason reason) {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderCannotBeCancelled();
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

Cách này giảm mapping và phù hợp với ứng dụng có domain model tương đối gần relational model. Cần chú ý:

- Annotation không được quyết định invariant.
- Field access giúp không cần public setter cho persistence.
- Constructor dành cho provider nên được giới hạn.
- Không để API serializer trả trực tiếp entity.
- Quan hệ JPA phải phù hợp với aggregate ownership.
- Các behavior vẫn cần test độc lập với database.

### Lựa chọn C: Mô hình lai

Một số kiểu domain như Money, Quantity hoặc Address có thể được map bằng embeddable/converter; aggregate root dùng JPA; API vẫn có DTO riêng. Đây là lựa chọn thực dụng khi lợi ích của việc tách hoàn toàn không bù được chi phí mapping.

Không có lựa chọn nào đúng cho mọi hệ thống. Điều cần đánh giá là mức coupling, độ phức tạp của model, tần suất schema thay đổi, yêu cầu portability và khả năng kiểm thử.

## 9. Ví dụ tách Domain Aggregate khỏi JPA Row

Giả sử Order có hành vi đặt hàng và hủy hàng. Domain model không biết bảng lưu trữ:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
    private OrderStatus status;

    private Order(OrderId id, CustomerId customerId,
                  List<OrderLine> lines, OrderStatus status) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.lines = new ArrayList<>(lines);
        this.status = Objects.requireNonNull(status);
        validate();
    }

    public static Order place(
            OrderId id,
            CustomerId customerId,
            List<OrderLine> lines
    ) {
        if (lines == null || lines.isEmpty()) {
            throw new OrderMustContainALine();
        }
        return new Order(id, customerId, lines, OrderStatus.PLACED);
    }

    public void cancel(CancellationReason reason) {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderCannotBeCancelled();
        }
        if (status == OrderStatus.CANCELLED) {
            throw new OrderAlreadyCancelled();
        }
        status = OrderStatus.CANCELLED;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderStatus status() {
        return status;
    }

    private void validate() {
        if (lines.isEmpty()) {
            throw new OrderMustContainALine();
        }
    }
}
~~~

Persistence model có thể được thiết kế theo schema:

~~~java
@Entity
@Table(name = "orders")
public class OrderRow {
    @Id
    UUID id;

    UUID customerId;

    @Enumerated(EnumType.STRING)
    OrderStatus status;

    @Version
    long version;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL,
               orphanRemoval = true)
    List<OrderLineRow> lines = new ArrayList<>();

    protected OrderRow() {
    }
}
~~~

Mapper:

~~~java
final class OrderMapper {
    Order toDomain(OrderRow row) {
        List<OrderLine> lines = row.lines.stream()
                .map(this::toDomain)
                .toList();

        return Order.reconstitute(
                new OrderId(row.id),
                new CustomerId(row.customerId),
                lines,
                row.status
        );
    }

    OrderRow toRow(Order order) {
        OrderRow row = new OrderRow();
        row.id = order.id().value();
        row.customerId = order.customerId().value();
        row.status = order.status();

        row.lines = order.lines().stream()
                .map(line -> toRow(line, row))
                .collect(Collectors.toCollection(ArrayList::new));

        return row;
    }
}
~~~

Các phương thức reconstitute và OrderLine mapper cần được thiết kế trong implementation thực tế; ví dụ chỉ tập trung vào ranh giới. Reconstitution phải kiểm tra dữ liệu lưu trữ có thể tạo ra một aggregate hợp lệ, hoặc có cơ chế xử lý dữ liệu cũ không còn thỏa invariant mới.

### Mapping không phải thao tác copy field mù quáng

Mapper cần hiểu:
- ID được chuyển sang kiểu domain nào;
- Value Object được dựng từ những cột nào;
- null trong database có ý nghĩa gì;
- trạng thái legacy được ánh xạ ra sao;
- collection có thứ tự nghiệp vụ không;
- field nào là snapshot;
- version dùng để bảo vệ concurrency;
- dữ liệu không hợp lệ được xử lý như thế nào.

Nếu mapping chỉ dùng reflection để copy mọi field cùng tên, một thay đổi schema có thể vô tình thay đổi nghĩa domain.

## 10. JPA Value Object: Embeddable và Converter

Value Object thường được lưu trong nhiều cột của một row. JPA cung cấp @Embeddable và @Embedded để map một nhóm thuộc tính.

~~~java
@Embeddable
public class MoneyEmbeddable {
    @Column(name = "amount", precision = 19, scale = 4)
    private BigDecimal amount;

    @Column(name = "currency", length = 3)
    private String currency;

    protected MoneyEmbeddable() {
    }

    public MoneyEmbeddable(BigDecimal amount, String currency) {
        this.amount = Objects.requireNonNull(amount);
        this.currency = Objects.requireNonNull(currency);
    }
}
~~~

Một domain Money có thể được map qua adapter hoặc converter. Cần phân biệt MoneyEmbeddable là persistence representation với Money là domain concept nếu chúng có lifecycle hoặc invariant khác nhau.

### AttributeConverter

Một converter có thể chuyển một Value Object thành một cột đơn:

~~~java
@Converter(autoApply = false)
public class CustomerCodeConverter
        implements AttributeConverter<CustomerCode, String> {

    @Override
    public String convertToDatabaseColumn(CustomerCode value) {
        return value == null ? null : value.value();
    }

    @Override
    public CustomerCode convertToEntityAttribute(String value) {
        return value == null ? null : CustomerCode.of(value);
    }
}
~~~

Converter phù hợp khi một kiểu có biểu diễn database đơn giản. Với Value Object gồm nhiều thuộc tính, Embeddable hoặc mapper riêng có thể rõ hơn.

### Null semantics phải được xác định

Một database column nullable có thể biểu diễn “chưa biết”, “không áp dụng”, “chưa nhập” hoặc “không có”. Không nên để null tự động lan khắp domain nếu domain cần phân biệt những trạng thái đó.

Có thể dùng Optional ở boundary hoặc Value Object/enum thể hiện trạng thái cụ thể. Không phải cứ field nullable là cần Optional trong mọi lớp; điều quan trọng là semantics được xác định.

## 11. Quan hệ JPA không quyết định Aggregate Boundary

JPA cho phép @OneToOne, @OneToMany, @ManyToOne và @ManyToMany. Những annotation này mô tả quan hệ persistence. Chúng không tự xác định aggregate.

Ví dụ, Order có thể tham chiếu Customer bằng CustomerId thay vì giữ toàn bộ Customer object. Customer có lifecycle riêng và được Customer Context sở hữu. Nếu Order cần tên hoặc địa chỉ tại thời điểm đặt, nó có thể lưu snapshot cần thiết.

Tương tự, Order có thể giữ ReservationId do Inventory cấp thay vì nhúng InventoryItem aggregate vào Order.

### Aggregate boundary xuất phát từ invariant

Hãy hỏi:

- Những thay đổi nào phải được kiểm tra nguyên tử?
- Ai bảo vệ invariant?
- Có thể chấp nhận eventual consistency không?
- Đối tượng nào có lifecycle độc lập?
- Những đối tượng nào có thể được truy cập bằng ID?
- Quy mô aggregate có làm transaction quá lớn không?

Một quan hệ database có thể tồn tại mà không cần object reference trong domain. Foreign key là ràng buộc lưu trữ; nó không bắt buộc domain phải có navigation property.

### Tránh aggregate quá lớn do tiện join

Nếu Order chứa Customer, Inventory, Payment, Shipment và toàn bộ Product Catalog dưới dạng object graph, một thao tác nhỏ có thể hydrate hàng trăm đối tượng. Quan trọng hơn, ranh giới consistency bị nhòe và các context bắt đầu chia sẻ model.

Thường nên tham chiếu aggregate khác bằng identity và trao đổi qua application service hoặc domain event.

## 12. Lazy Loading và N+1 không nên quyết định domain behavior

Lazy loading là chiến lược tải dữ liệu của ORM. Nó có thể hữu ích, nhưng khi domain method hoặc JSON serializer vô tình truy cập collection lazy, hệ thống có thể phát sinh truy vấn ngoài dự kiến.

Ví dụ:

~~~java
Order order = repository.findById(id).orElseThrow();
return order.getLines().stream()
        .map(this::toResponse)
        .toList();
~~~

Nếu getLines() kích hoạt lazy loading, mỗi order trong danh sách có thể tạo thêm query. Khi serialize nhiều order, N+1 xuất hiện.

Cách xử lý:
- chọn fetch plan phù hợp với use case;
- dùng projection/read model cho truy vấn màn hình;
- map DTO trong transaction có chủ đích;
- không để serializer tự quyết định cần tải quan hệ nào;
- tránh đổi toàn bộ quan hệ sang EAGER chỉ để sửa một endpoint.

EAGER loading cũng có thể tạo graph lớn và query không cần thiết. Fetch strategy là quyết định adapter/query, không phải lý do để làm aggregate chứa thêm khái niệm.

## 13. Bidirectional Association và vòng lặp object graph

Một quan hệ hai chiều như Order có lines và mỗi OrderLine có order reference có thể tiện cho ORM. Nhưng nó tạo nhiều vấn đề:

- phải giữ hai phía đồng bộ;
- dễ tạo vòng lặp khi serialize JSON;
- equals/hashCode có thể đi qua graph vô hạn;
- một child có thể thay đổi parent ngoài ý muốn;
- test fixture khó dựng;
- object graph có thể tải dữ liệu ngoài phạm vi use case.

Trong domain model, nếu OrderLine chỉ tồn tại trong lifecycle của Order, nó thường không cần public reference để thay đổi root. OrderRoot cung cấp operation addLine/removeLine và quản lý collection nội bộ.

Trong persistence model, quan hệ hai chiều có thể vẫn cần để map foreign key. Khi đó, helper method ở persistence adapter hoặc entity có thể đồng bộ hai phía. Đừng để yêu cầu đó lan thành API domain.

## 14. equals và hashCode với JPA Entity

JPA entity có identity theo khóa. Nhưng khóa có thể chưa được gán cho đến khi persist. Nếu equals/hashCode dựa trên mutable field hoặc generated ID chưa có, object trong HashSet có thể trở nên không tìm được sau khi ID thay đổi.

Một số nguyên tắc:

- Không dùng toàn bộ mutable fields để định danh entity.
- Không để equals/hashCode truy cập lazy association.
- Xác định rõ semantics khi ID chưa được cấp.
- Không dùng business key làm identity nếu business key có thể đổi.
- Kiểm tra proxy behavior của provider.
- Dùng Value Object cho equality theo giá trị thay vì áp quy tắc entity lên mọi class.

Trong domain model, equality của Entity thường dựa trên identity ổn định trong phạm vi model. Value Object dựa trên các giá trị cấu thành. Persistence adapter phải bảo đảm mapping không phá vỡ các semantics đó.

Không có một implementation equals/hashCode phổ quát cho mọi JPA provider và mọi chiến lược ID. Hãy chọn theo provider, lifecycle ID và cách collection được sử dụng, rồi viết test cho các trường hợp transient, managed, detached và proxy nếu có.

## 15. JPA lifecycle callback không phải nơi mặc định đặt business rule

Các callback như @PrePersist, @PreUpdate hoặc @PostLoad phục vụ lifecycle persistence. Chúng phù hợp cho metadata kỹ thuật như audit timestamp hoặc chuẩn hóa storage nếu semantics rõ.

Không nên đặt các quyết định nghiệp vụ quan trọng trong callback mà caller không nhìn thấy:

~~~java
@PreUpdate
void validateOrder() {
    if (status == OrderStatus.CANCELLED && shippedAt != null) {
        throw new IllegalStateException();
    }
}
~~~

Nếu quy tắc là “đơn đã giao không thể bị hủy”, nó nên được bảo vệ bởi Order.cancel(). Callback có thể là lớp phòng thủ persistence bổ sung, nhưng không phải nơi duy nhất chứa invariant.

Một lý do là callback có thể được kích hoạt bởi thao tác ORM, bulk update hoặc lifecycle khác với hành vi domain mà người đọc mong đợi. Business operation nên được gọi tường minh và có thể kiểm thử mà không cần persistence context.

## 16. JSON serialization và domain object

Serialization có thể vô tình:
- gọi getter có side effect hoặc lazy loading;
- làm lộ field nội bộ;
- tạo vòng lặp do quan hệ hai chiều;
- thay đổi contract khi rename property;
- serialize enum theo tên class;
- định dạng tiền và thời gian không ổn định;
- cho phép client gửi field không được phép thay đổi.

Không nên dùng domain entity làm response chỉ vì serializer có thể đọc nó. DTO cho phép kiểm soát chính xác contract.

### Không để Jackson annotation định nghĩa domain semantics

Các annotation như @JsonProperty, @JsonIgnore, @JsonFormat hoặc custom serializer có thể hữu ích trên DTO. Khi đặt chúng trực tiếp lên domain entity, class miền bị gắn với một thư viện và contract cụ thể.

Nếu domain model được dùng nội bộ trong một ứng dụng nhỏ, mức coupling đó có thể được chấp nhận. Nhưng khi API có nhiều consumer hoặc model cần tiến hóa độc lập, tách DTO thường giảm rủi ro đáng kể.

### Không serialize object graph persistence

Không nên trả trực tiếp entity có lazy collection, bidirectional relationship hoặc proxy. Tạo response DTO trong application/query layer với fetch plan rõ ràng.

~~~java
OrderResponse toResponse(OrderView view) {
    return new OrderResponse(
            view.id().value().toString(),
            view.status().name(),
            view.total().amount(),
            view.total().currency().getCurrencyCode(),
            view.lines().stream()
                    .map(this::toLineResponse)
                    .toList()
    );
}
~~~

Ví dụ dùng OrderView để thể hiện dữ liệu đã được lấy phù hợp với use case. DTO không cần mang toàn bộ aggregate.

## 17. Enum và tên field theo schema bên ngoài

Database legacy có thể lưu:
- O, P, C;
- 0, 1, 2;
- CLOSED_BY_USER;
- CANCELLED_AFTER_PAYMENT.

API có thể yêu cầu status là "cancelled". Domain language có thể dùng OrderStatus.CANCELLED và event OrderCancelled.

Không nên để giá trị storage hoặc wire format trở thành tên domain chỉ vì mapping thuận tiện.

Với JPA, @Enumerated(EnumType.STRING) thường dễ đọc hơn ORDINAL, nhưng đổi tên enum có thể ảnh hưởng dữ liệu đã lưu. Nếu cần mã storage ổn định, dùng converter hoặc mapping riêng.

~~~java
public enum OrderStatus {
    DRAFT,
    PLACED,
    CANCELLED,
    SHIPPED
}
~~~

Adapter có thể chuyển status sang mã legacy hoặc API value. Khi đổi contract, versioning và migration cần được xem xét ở boundary.

## 18. Validation của request khác với invariant của domain

Request validation kiểm tra hình dạng đầu vào:
- field bắt buộc;
- độ dài;
- format email;
- JSON type;
- số lượng phần tử;
- định dạng ID.

Domain invariant kiểm tra tính hợp lệ trong ngữ cảnh nghiệp vụ:
- Order phải có ít nhất một dòng khi được đặt;
- quantity phải phù hợp với sản phẩm;
- đơn đã dispatch không thể hủy theo luồng thông thường;
- ngày giao phải hợp lệ theo lịch;
- currency của giá phải phù hợp với order.

Ví dụ DTO có thể dùng Bean Validation:

~~~java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotEmpty List<@Valid CreateOrderLineRequest> lines
) {
}
~~~

Nhưng domain factory vẫn phải bảo vệ invariant vì object có thể được tạo từ message, batch hoặc test mà không qua HTTP validation.

Không nên coi annotation @Valid là hàng rào duy nhất bảo vệ domain. Validation ở transport và invariant ở domain có mục đích khác nhau.

## 19. Event serialization và Integration Contract

Domain Event biểu diễn fact trong một bounded context. Integration Event là hợp đồng được công bố cho context khác hoặc hệ thống ngoài. Hai loại có thể có nội dung khác nhau.

Một Domain Event có thể chứa kiểu miền, ID mạnh và dữ liệu nội bộ. Trước khi publish, adapter có thể chuyển thành integration DTO ổn định:

~~~java
public record OrderPlacedIntegrationEvent(
        String eventId,
        String orderId,
        String customerReference,
        Instant occurredAt,
        int schemaVersion
) {
}
~~~

Không nên serialize trực tiếp aggregate hoặc domain event object nếu nó làm lộ cấu trúc nội bộ và khiến consumer phụ thuộc vào package/class của producer.

Integration contract cần:
- schema version;
- event ID;
- thời điểm có ý nghĩa;
- correlation/causation ID khi cần;
- semantics rõ của field;
- chính sách compatibility;
- quy tắc xử lý duplicate và ordering.

Message schema là boundary. Thay đổi field hoặc semantics phải được đánh giá theo consumer, không chỉ theo việc code producer compile được.

## 20. Mapping và kiểm thử

Khi tách mô hình, mapping là một phần quan trọng của adapter. Cần kiểm thử nó như một hợp đồng.

### Domain unit test

Kiểm tra:
- factory tạo object hợp lệ;
- operation bảo vệ invariant;
- trạng thái chuyển đúng;
- event được tạo khi hành vi thành công;
- hành vi bị từ chối không làm thay đổi object.

Không cần JPA hoặc JSON framework trong domain unit test.

### Mapper test

Kiểm tra:
- domain object chuyển sang persistence model giữ đủ giá trị;
- persistence row được reconstitute thành domain object đúng;
- Money, Quantity, ID và enum không mất semantics;
- null/legacy values được xử lý theo quy tắc;
- collection order được giữ nếu có ý nghĩa.

~~~java
@Test
void mapsMoneyWithoutLosingCurrency() {
    Money domain = Money.of("125.50", Currency.getInstance("VND"));

    MoneyEmbeddable row = mapper.toRow(domain);
    Money restored = mapper.toDomain(row);

    assertThat(restored).isEqualTo(domain);
}
~~~

### Adapter integration test

Chạy với database phù hợp để xác minh:
- mapping thực tế của JPA;
- cascade/orphan removal;
- optimistic locking;
- unique constraints;
- transaction rollback;
- lazy/eager behavior cần thiết;
- converter và schema.

### API contract test

Xác minh:
- JSON field và format ổn định;
- không lộ field nội bộ;
- request không thể mass-assign trạng thái;
- error response đúng contract;
- schema version tương thích.

Một fake mapper test không chứng minh database mapping thật đúng. Một controller test không chứng minh aggregate bảo vệ invariant. Mỗi test cần đặt đúng tầng.

## 21. Tiến hóa schema mà không ép domain đổi theo

Database schema thay đổi vì hiệu năng, migration, legacy compatibility hoặc chuẩn hóa dữ liệu. Những thay đổi đó không nhất thiết là thay đổi domain.

Ví dụ, một cột full_name được tách thành given_name và family_name. Nếu domain concept vẫn là CustomerName, persistence mapper có thể dựng Value Object từ hai cột. Nếu domain có thêm preferred name, schema có thể lưu thêm cột mà API hoặc domain chỉ sử dụng khi cần.

Ngược lại, một thay đổi nghiệp vụ như cho phép nhiều địa chỉ giao hàng có hiệu lực theo thời gian có thể yêu cầu domain model thay đổi, dù database có thể lưu bằng một bảng mới hoặc JSON column.

Phân biệt:
- schema change;
- API contract change;
- domain rule change;
- data migration;
- mapping change.

Chúng có thể xảy ra cùng lúc nhưng không đồng nghĩa. Ghi nhận tác động ở từng boundary giúp tránh để schema dictate model.

## 22. Khi nào có thể dùng chung một class?

Không phải lúc nào cũng cần ba class khác nhau cho một khái niệm. Có thể dùng chung nếu:
- semantics thực sự giống nhau;
- lifecycle giống nhau;
- API không làm lộ dữ liệu nội bộ;
- persistence requirement không ép public mutation;
- mapping không phức tạp;
- các thay đổi ở một boundary ít có khả năng phá boundary khác;
- nhóm chấp nhận coupling và có test phù hợp.

Ví dụ một Value Object nhỏ như CurrencyCode hoặc CountryCode có thể dùng chung giữa domain và persistence nếu invariant, representation và dependency ổn định. Một class cấu hình bất biến cũng có thể vừa được deserialize vừa được dùng trong application nếu contract rõ.

Nên tách khi:
- API cần field khác hoặc versioning độc lập;
- persistence cần field kỹ thuật;
- domain có invariant/lifecycle khác;
- nhiều consumer phụ thuộc contract;
- ORM buộc public setters hoặc object graph không phù hợp;
- dữ liệu cần che giấu hoặc biến đổi;
- một thay đổi storage có thể làm đổi domain semantics ngoài ý muốn.

Quyết định nên dựa trên coupling và chi phí thực tế, không theo luật “luôn tách” hoặc “luôn dùng chung”.

## 23. Lựa chọn chiến lược theo mức độ phức tạp

| Tình huống | Cách tiếp cận có thể phù hợp |
|---|---|
| CRUD đơn giản, ít rule, một ứng dụng nhỏ | Một model persistence-aware có thể đủ |
| Domain có invariant và lifecycle đáng kể | Domain model có hành vi; adapter persistence riêng hoặc mapping có kiểm soát |
| Nhiều API consumer và schema version | DTO/contract riêng |
| Nhiều bounded context | Model riêng theo context, integration contract rõ |
| Legacy database phức tạp | Persistence model riêng và Anti-Corruption Layer |
| Hiệu năng đọc phức tạp | Read model/projection riêng, không làm aggregate phình ra |
| Hệ thống event-driven | Domain event và integration event tách theo semantics |
| ORM mapping đơn giản, model gần relational | Có thể dùng JPA trực tiếp nhưng giữ behavior và boundary |

Một hệ thống có thể chọn cách khác nhau ở từng module. Không cần áp một kiến trúc đồng nhất nếu mức độ phức tạp khác nhau.

## 24. Quy trình thiết kế để framework phục vụ mô hình

Khi bắt đầu một capability mới hoặc tái cấu trúc một phần hệ thống, hãy đi theo trình tự:

1. **Làm rõ ngôn ngữ nghiệp vụ:** thuật ngữ, actor, quyết định và lifecycle.
2. **Xác định invariant:** điều gì phải luôn đúng và ai bảo vệ?
3. **Xác định aggregate boundary:** thao tác nào cần consistency cùng nhau?
4. **Thiết kế domain API:** factory, operation và event theo ngôn ngữ miền.
5. **Xác định use case:** application service cần port nào?
6. **Thiết kế persistence mapping:** bảng, key, version, fetch plan và transaction.
7. **Thiết kế transport contract:** request, response và integration event.
8. **Viết test theo boundary:** domain, use case, mapper, adapter và API.
9. **Đánh giá coupling:** thay schema hoặc serializer có buộc đổi domain không?
10. **Đo hiệu năng và điều chỉnh adapter:** fetch strategy, projection và index.
11. **Ghi lại trade-off:** lý do chọn model chung hoặc model tách riêng.
12. **Review khi contract thay đổi:** xác định consumer và dữ liệu lịch sử bị ảnh hưởng.

Trình tự này không bắt buộc mọi nhóm phải thiết kế domain hoàn chỉnh trước khi xem database. Khám phá có thể lặp lại. Nhưng các quyết định kỹ thuật nên được đánh giá dựa trên model và use case, thay vì vô tình trở thành nguồn định nghĩa nghiệp vụ.

## 25. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Để JPA entity chính là domain model mà không cân nhắc | Persistence lifecycle và public API có thể làm yếu invariant | Đánh giá coupling, giới hạn mutation và tách adapter khi cần |
| Trả domain entity trực tiếp thành JSON | API bị gắn với cấu trúc nội bộ, lazy loading và vòng lặp | Dùng request/response DTO |
| Bind request trực tiếp vào aggregate | Client có thể thay đổi field không được phép | Map command/request sang domain operation |
| Aggregate boundary theo bảng | Consistency boundary không phản ánh nghiệp vụ | Bắt đầu từ invariant và ownership |
| Dùng quan hệ hai chiều ở mọi nơi | Object graph lớn, cascade và serialization phức tạp | Chỉ giữ quan hệ cần cho semantics |
| Đặt business rule trong JPA callback | Hành vi ẩn và phụ thuộc lifecycle persistence | Đặt rule trong entity/aggregate operation |
| Dùng setter public để ORM tiện | Caller bỏ qua business transition | Field access hoặc adapter/reconstitution có kiểm soát |
| Dùng EAGER để tránh lỗi lazy | Query dư thừa và graph lớn | Fetch plan theo use case |
| Dùng ORDINAL cho enum | Thứ tự enum thay đổi làm sai dữ liệu | STRING hoặc converter mã ổn định |
| equals/hashCode theo mutable field | Collection hỏng khi state đổi | Dùng identity ổn định và test lifecycle |
| Mapping copy field mù quáng | Mất semantics, null và legacy rule | Mapper có chủ đích, test round-trip |
| Dùng domain event làm integration schema trực tiếp | Consumer phụ thuộc class nội bộ | Chuyển qua integration DTO versioned |
| Cho Bean Validation bảo vệ mọi invariant | Message/batch có thể bỏ qua validation HTTP | Bảo vệ invariant trong domain |
| Tách quá nhiều lớp không có lợi ích | Mapping boilerplate và chi phí bảo trì | Chọn mức tách theo coupling và complexity |

## 26. Checklist rà soát

- [ ] Domain model có ngôn ngữ, hành vi và invariant rõ ràng.
- [ ] Persistence model được xem là representation lưu trữ, không phải định nghĩa domain.
- [ ] API/message DTO có contract và versioning phù hợp.
- [ ] JPA annotation không quyết định aggregate boundary hoặc business lifecycle.
- [ ] Public API không mở setter cho trạng thái quan trọng mà bỏ qua rule.
- [ ] Constructor/reconstitution dành cho persistence được giới hạn hợp lý.
- [ ] Aggregate root kiểm soát thay đổi collection và child entity.
- [ ] Quan hệ JPA phản ánh nhu cầu mapping, không tự động thành domain association.
- [ ] Lazy loading và N+1 được kiểm soát ở query/adapter layer.
- [ ] JSON serializer không duyệt trực tiếp object graph persistence.
- [ ] Request DTO chỉ nhận field mà use case cho phép.
- [ ] Domain invariant vẫn được bảo vệ khi input đến từ message, batch hoặc test.
- [ ] Money, Quantity, ID và enum được map không mất semantics.
- [ ] equals/hashCode được xem xét với generated ID và ORM proxy.
- [ ] JPA lifecycle callback không phải nơi duy nhất chứa business rule.
- [ ] Domain Event và Integration Event được phân biệt.
- [ ] Mapper, JPA adapter và API contract có test phù hợp.
- [ ] Quyết định dùng model chung hay tách model có lý do rõ ràng.
- [ ] Schema change không tự động bị coi là domain change.
- [ ] Trade-off và coupling được review khi framework hoặc contract thay đổi.

## Kết luận

JPA, JSON và framework là công cụ triển khai, mỗi công cụ có mô hình và ràng buộc riêng. Domain model cần phản ánh ngôn ngữ, hành vi và invariant của nghiệp vụ; persistence model cần phục vụ lưu trữ; transport model cần bảo vệ hợp đồng với consumer. Chúng có thể dùng chung một số kiểu khi semantics thực sự trùng nhau, nhưng không nên bị ép giống nhau chỉ để giảm mapping. Khi aggregate boundary xuất phát từ invariant, domain operation bảo vệ lifecycle, adapter kiểm soát mapping và DTO bảo vệ contract, framework có thể thay đổi mà không buộc mô hình nghiệp vụ thay đổi theo.
