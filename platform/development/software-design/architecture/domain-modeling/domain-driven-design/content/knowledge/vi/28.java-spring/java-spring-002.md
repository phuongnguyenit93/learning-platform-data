# Định danh có kiểu riêng để tránh nhầm lẫn giữa các aggregate

Trong DDD, mỗi Aggregate có một định danh để phân biệt nó với các Aggregate khác. Trong Java, nếu mọi định danh đều được biểu diễn bằng cùng một kiểu như UUID, Long hoặc String, compiler không thể phát hiện khi lập trình viên truyền nhầm ID của Aggregate này sang thao tác dành cho Aggregate khác.

Ví dụ, Order và Customer đều có ID kiểu UUID. Một phương thức tìm Order nhưng nhận UUID vẫn có thể bị gọi với customerId. Giá trị có thể hợp lệ về cú pháp, nhưng sai về ngữ nghĩa. Lỗi thường chỉ xuất hiện khi chạy chương trình hoặc khi dữ liệu bị truy cập nhầm.

**Strongly Typed ID** (định danh có kiểu riêng) giải quyết vấn đề bằng cách tạo một kiểu Java cho từng loại định danh: OrderId, CustomerId, PaymentId. Dù bên trong chúng đều chứa UUID, compiler xem chúng là những kiểu khác nhau. Nhờ đó, một phương thức nhận OrderId không thể nhận CustomerId một cách vô tình.

Trong Java và Spring, cách làm này có thể được áp dụng xuyên suốt Domain Model, Application Service, Repository, Controller và Persistence Adapter. API hoặc database vẫn có thể trao đổi/lưu giá trị UUID thông thường; lớp chuyển đổi ở ranh giới sẽ tạo lại kiểu định danh tương ứng.

## 1. Vấn đề khi dùng cùng một kiểu cho mọi ID

Giả sử hệ thống bán hàng có ba Aggregate:

- Order: đơn hàng.
- Customer: khách hàng.
- Payment: khoản thanh toán.

Mỗi Aggregate có một ID UUID. Cách triển khai ban đầu có thể như sau:

~~~java
public class OrderService {
    public Order getOrder(UUID id) {
        // load order
        return null;
    }

    public void assignCustomer(UUID orderId, UUID customerId) {
        // assign customer to order
    }
}
~~~

Đoạn gọi dưới đây vẫn biên dịch:

~~~java
UUID orderId = UUID.randomUUID();
UUID customerId = UUID.randomUUID();
OrderService service = new OrderService();
service.getOrder(customerId);
service.assignCustomer(customerId, orderId);
~~~

Compiler chỉ biết cả hai tham số đều là UUID. Nó không biết UUID đầu tiên đại diện cho Order hay Customer. Việc đổi thứ tự hai tham số cũng không bị phát hiện.

Lỗi tương tự xuất hiện khi repository nhận ID chung:

~~~java
public interface OrderRepository {
    Optional<Order> findById(UUID id);
}

public interface CustomerRepository {
    Optional<Customer> findById(UUID id);
}
~~~

Chữ ký phương thức không thể hiện đầy đủ ngữ nghĩa. Tên biến giúp người đọc hiểu phần nào, nhưng tên biến không tạo ra bảo vệ ở compile time.

### 1.1. Lỗi nhầm ID thường khó phát hiện

Nhầm ID có thể dẫn đến:

- Truy vấn nhầm Aggregate và nhận kết quả không tồn tại.
- Gắn một Order vào sai Customer.
- Cập nhật hoặc hủy nhầm Payment.
- Ghi một tham chiếu sai nhưng vẫn vượt qua kiểm tra kiểu dữ liệu.
- Truyền nhầm ID giữa các Bounded Context khi nhiều hệ thống cùng dùng UUID.

Nếu UUID không tồn tại trong bảng đích, lỗi có thể chỉ là 404 hoặc dữ liệu không tìm thấy. Nguy hiểm hơn, nếu tình cờ có cùng UUID trong bảng khác, hệ thống có thể thao tác nhầm một đối tượng hợp lệ.

## 2. Strongly Typed ID là gì?

Strongly Typed ID là một kiểu riêng biểu diễn một loại định danh cụ thể. Giá trị bên trong có thể là UUID, Long, String hoặc một kiểu khác, nhưng kiểu bên ngoài thể hiện ý nghĩa miền.

~~~java
public record OrderId(UUID value) {}

public record CustomerId(UUID value) {}

public record PaymentId(UUID value) {}
~~~

Ba kiểu này đều chứa UUID nhưng không thể thay thế cho nhau:

~~~java
public Order findOrder(OrderId id) {
    // ...
    return null;
}

OrderId orderId = new OrderId(UUID.randomUUID());
CustomerId customerId = new CustomerId(UUID.randomUUID());

findOrder(orderId);     // Hợp lệ
findOrder(customerId);  // Lỗi biên dịch
~~~

Compiler phát hiện sai loại định danh trước khi chương trình chạy. Đây là lợi ích chính của kiểu riêng.

### 2.1. Kiểu riêng làm rõ ngôn ngữ miền

So sánh hai chữ ký:

~~~java
void refund(UUID id);

void refund(PaymentId paymentId);
~~~

Chữ ký thứ hai cho biết chính xác hành động nhận định danh nào. Điều này đặc biệt hữu ích khi một use case có nhiều tham số cùng biểu diễn UUID:

~~~java
void transfer(
        AccountId sourceAccountId,
        AccountId destinationAccountId,
        TransferId transferId
);
~~~

Tên kiểu làm rõ vai trò của từng giá trị và giảm phụ thuộc vào thứ tự tham số hoặc tên biến.

### 2.2. Khác biệt giữa Strongly Typed ID và Value Object

Strongly Typed ID thường được cài đặt bằng Value Object trong Java, nhưng cần phân biệt ý nghĩa:

- ID trả lời câu hỏi: đây là Aggregate hoặc Entity nào?
- Value Object khác biểu diễn một giá trị có ý nghĩa miền, chẳng hạn Money, Quantity, EmailAddress hoặc CreditLimit.

ID có equality dựa trên giá trị định danh trong cùng loại ID. Hai OrderId có cùng UUID là bằng nhau; một OrderId và CustomerId có cùng UUID vẫn là hai kiểu khác nhau và không bằng nhau.

~~~java
OrderId orderA = new OrderId(UUID.fromString(
        "00000000-0000-0000-0000-000000000001"
));
OrderId orderB = new OrderId(UUID.fromString(
        "00000000-0000-0000-0000-000000000001"
));
CustomerId customer = new CustomerId(orderA.value());

orderA.equals(orderB); // true
orderA.equals(customer); // false
~~~

Với Java record, equals() và hashCode() được sinh dựa trên kiểu record và các component. Điều này phù hợp với định danh có một giá trị duy nhất.

## 3. Tạo ID type an toàn trong Java

Một kiểu ID cần bảo vệ các đặc tính cơ bản:

- Giá trị bên trong không null.
- Có cách tạo ID mới nếu hệ thống tự sinh ID.
- Có cách parse từ biểu diễn bên ngoài.
- Có thể lấy giá trị nguyên thủy khi cần mapping.
- Equality dựa trên loại ID và giá trị.

Ví dụ:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "OrderId value must not be null");
    }

    public static OrderId newId() {
        return new OrderId(UUID.randomUUID());
    }

    public static OrderId parse(String raw) {
        return new OrderId(UUID.fromString(raw));
    }

    public String asString() {
        return value.toString();
    }
}
~~~

Các ID khác có cấu trúc tương tự:

~~~java
public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value);
    }
}

public record PaymentId(UUID value) {
    public PaymentId {
        Objects.requireNonNull(value);
    }
}
~~~

Có thể tạo factory hoặc helper dùng chung để tránh lặp, nhưng không nên hy sinh tính rõ ràng của từng kiểu chỉ để giảm vài dòng code.

### 3.1. ID nên bất biến

Một định danh không nên thay đổi sau khi Aggregate được tạo. Java record mặc định là immutable đối với component tham chiếu; UUID cũng là immutable. Vì vậy record là lựa chọn ngắn gọn cho kiểu ID.

Không nên cung cấp setter để thay đổi value:

~~~java
// Không nên
public class OrderId {
    private UUID value;

    public void setValue(UUID value) {
        this.value = value;
    }
}
~~~

Nếu ID của Aggregate thay đổi tùy ý, các tham chiếu, repository key, event và liên kết giữa context có thể trở nên không nhất quán.

### 3.2. Chọn UUID, Long hay String

Strong typing độc lập với cách sinh giá trị:

| Giá trị nền | Khi phù hợp | Ví dụ |
|---|---|---|
| UUID | Sinh ID phân tán, không cần sequence trung tâm | OrderId(UUID) |
| Long | Hệ thống dùng sequence/database identity | CustomerId(Long) |
| String | Mã nghiệp vụ có cấu trúc hoặc do hệ thống ngoài cấp | ShipmentId(String) |

Không nên chọn UUID chỉ vì đang dùng Strongly Typed ID. Hãy giữ chiến lược định danh hiện tại nếu nó đáp ứng yêu cầu. Kiểu riêng vẫn đem lại an toàn ngay cả khi giá trị bên trong là Long.

## 4. Đặt Strongly Typed ID trong Domain Model

Aggregate Root nên khai báo ID đúng loại:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private OrderStatus status;

    public Order(OrderId id, CustomerId customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = OrderStatus.DRAFT;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }
}
~~~

Order giữ CustomerId như một tham chiếu đến Aggregate Customer. Nó không cần giữ toàn bộ Customer object nếu Customer là Aggregate Root độc lập.

### 4.1. Tham chiếu Aggregate bằng ID

Một nguyên tắc phổ biến trong DDD là Aggregate tham chiếu Aggregate khác bằng identity, thay vì giữ object graph lớn.

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
}
~~~

Order sở hữu vòng đời của OrderLine, nhưng không sở hữu vòng đời của Customer. Customer có repository và consistency boundary riêng.

Strongly Typed ID làm rõ ranh giới đó:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
}

public interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);
}
~~~

Một phương thức tìm Order không thể vô tình nhận CustomerId. Đồng thời, chữ ký repository thể hiện rõ Aggregate nào đang được truy xuất.

### 4.2. Tránh một ID chung cho toàn hệ thống

Một class như EntityId hoặc AggregateId có thể hữu ích ở một số hạ tầng tổng quát, nhưng nếu mọi phương thức nghiệp vụ đều nhận EntityId thì lợi ích phân biệt loại ID bị mất.

~~~java
// Quá tổng quát cho API nghiệp vụ
Order findOrder(EntityId id);
Customer findCustomer(EntityId id);
~~~

Hãy dùng OrderId và CustomerId tại các chữ ký miền. Có thể chuyển sang kiểu chung ở một abstraction kỹ thuật thực sự cần xử lý mọi loại ID, nhưng cần giữ ranh giới đó hẹp.

## 5. Dùng Strongly Typed ID trong Application Service

Application Service nhận ID đã có kiểu:

~~~java
public final class ConfirmOrderService {
    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFound(command.orderId()));

        order.confirm();
        orders.save(order);
    }
}

public record ConfirmOrderCommand(OrderId orderId) {}
~~~

Nếu code tạo command bằng CustomerId, compiler báo lỗi:

~~~java
new ConfirmOrderCommand(customerId); // Không biên dịch
~~~

Lỗi được phát hiện ngay tại nơi xây dựng command, thay vì đợi đến lúc truy vấn database.

### 5.1. Nhiều tham số cùng kiểu nền

Một use case chuyển tiền có thể nhận:

~~~java
public record TransferMoneyCommand(
        TransferId transferId,
        AccountId sourceAccountId,
        AccountId destinationAccountId,
        Money amount
) {}
~~~

Compiler không thể thay sourceAccountId bằng TransferId hoặc CustomerId. Với hai tham số cùng loại AccountId, compiler vẫn không biết tài khoản nào là nguồn hay đích nếu lập trình viên đảo thứ tự. Có thể cải thiện bằng factory có tên hoặc object riêng:

~~~java
public record TransferRoute(
        AccountId source,
        AccountId destination
) {
    public TransferRoute {
        if (source.equals(destination)) {
            throw new IllegalArgumentException(
                    "Source and destination must differ"
            );
        }
    }
}
~~~

Strong typing giải quyết nhầm loại định danh; nó không tự giải quyết mọi sai sót về vai trò giữa hai giá trị cùng loại.

## 6. Tích hợp với Spring MVC

HTTP path thường truyền ID dưới dạng chuỗi:

~~~http
GET /orders/550e8400-e29b-41d4-a716-446655440000
~~~

Spring MVC cần chuyển chuỗi path thành OrderId. Có thể làm bằng Converter.

### 6.1. Tạo Converter

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public final class StringToOrderIdConverter
        implements Converter<String, OrderId> {

    @Override
    public OrderId convert(String source) {
        return OrderId.parse(source);
    }
}
~~~

Trong cấu hình Spring MVC thông thường, converter bean có thể được đăng ký vào hệ thống conversion tùy cách ứng dụng cấu hình. Nếu muốn khai báo tường minh, dùng WebMvcConfigurer:

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final StringToOrderIdConverter orderIdConverter;

    public WebConfig(StringToOrderIdConverter orderIdConverter) {
        this.orderIdConverter = orderIdConverter;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(orderIdConverter);
    }
}
~~~

Tạo converter tương ứng cho CustomerId hoặc các ID khác. Có thể dùng một converter tổng quát nếu cách parse thống nhất và đăng ký rõ ràng, nhưng không được biến kết quả thành một ID type chung.

### 6.2. Controller nhận kiểu ID trực tiếp

~~~java
@RestController
@RequestMapping("/orders")
public final class OrderController {
    private final GetOrderService getOrder;

    public OrderController(GetOrderService getOrder) {
        this.getOrder = getOrder;
    }

    @GetMapping("/{orderId}")
    public OrderResponse get(@PathVariable OrderId orderId) {
        OrderDetails details = getOrder.handle(
                new GetOrderQuery(orderId)
        );
        return OrderResponse.from(details);
    }
}
~~~

Controller không cần nhận UUID rồi tự chuyển ở nhiều nơi. Spring conversion xử lý ranh giới HTTP, còn Application chỉ nhận OrderId.

### 6.3. Xử lý ID sai định dạng

Nếu UUID trong path sai định dạng, converter có thể ném IllegalArgumentException hoặc lỗi chuyển đổi. API nên ánh xạ lỗi đó thành 400 Bad Request với thông điệp ổn định, không trả stack trace.

Đây là lỗi cú pháp đầu vào. Nó khác với ID hợp lệ nhưng không tồn tại, thường được xử lý thành 404 Not Found theo hợp đồng API.

## 7. JSON serialization và deserialization

Nếu DTO dùng OrderId trực tiếp, cần quyết định JSON sẽ biểu diễn ID như chuỗi UUID hay object có field value.

Thường hợp đồng API đơn giản hơn nếu ID được biểu diễn bằng chuỗi:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Không nên vô tình trả:

~~~json
{
  "orderId": {
    "value": "550e8400-e29b-41d4-a716-446655440000"
  }
}
~~~

nếu API contract mong đợi chuỗi.

### 7.1. Giữ DTO dùng String ở ranh giới

Một lựa chọn đơn giản là Request/Response DTO dùng String:

~~~java
public record OrderResponse(
        String orderId,
        String status
) {}
~~~

Mapper chuyển đổi:

~~~java
public OrderResponse toResponse(Order order) {
    return new OrderResponse(
            order.id().asString(),
            order.status().name()
    );
}
~~~

Ưu điểm là API contract không phụ thuộc Jackson configuration của domain type. Domain vẫn giữ Strongly Typed ID.

### 7.2. Dùng Jackson annotation khi muốn serialize ID type trực tiếp

Nếu muốn DTO dùng OrderId và JSON vẫn là chuỗi, có thể định nghĩa creator/value:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public OrderId(String raw) {
        this(UUID.fromString(raw));
    }

    @JsonValue
    public String asString() {
        return value.toString();
    }
}
~~~

Jackson có thể đọc và ghi kiểu ID như một giá trị chuỗi đơn. Cách này phụ thuộc Jackson được dùng trong ứng dụng; hãy có serialization test để khóa hợp đồng JSON.

Không nhất thiết phải annotate Domain Model nếu muốn Domain độc lập với thư viện web. Khi đó giữ DTO String và mapper thường là lựa chọn ít coupling hơn.

## 8. Mapping Strongly Typed ID với JPA

Domain Model dùng OrderId, nhưng database có thể tiếp tục lưu UUID trong cột:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

Không cần tạo bảng riêng cho OrderId. Kiểu riêng là bảo vệ ở code; database vẫn dùng kiểu lưu trữ phù hợp.

Có hai hướng mapping phổ biến:

1. Persistence Entity dùng UUID, mapper chuyển sang Domain OrderId.
2. Persistence Entity dùng ID type cho thuộc tính tham chiếu và JPA AttributeConverter chuyển đổi; với primary key, cân nhắc @EmbeddedId hoặc giữ UUID trong persistence model.

### 8.1. Persistence Entity giữ UUID

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
~~~

Repository của Spring Data:

~~~java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderJpaEntity, UUID> {
}
~~~

Adapter chuyển đổi giữa persistence model và domain model:

~~~java
public final class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository jpa;
    private final OrderMapper mapper;

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value()).map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        jpa.save(mapper.toJpaEntity(order));
    }
}
~~~

Hướng này giữ Domain độc lập với JPA. Spring Data làm việc với UUID; Domain repository nhận OrderId. Đây là lựa chọn rõ ràng khi persistence model đã được tách khỏi Domain Model.

### 8.2. Dùng AttributeConverter cho thuộc tính tham chiếu

Nếu Persistence Entity muốn dùng CustomerId cho cột customer_id, có thể viết converter:

~~~java
@Converter
public class CustomerIdJpaConverter
        implements AttributeConverter<CustomerId, UUID> {

    @Override
    public UUID convertToDatabaseColumn(CustomerId attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public CustomerId convertToEntityAttribute(UUID dbData) {
        return dbData == null ? null : new CustomerId(dbData);
    }
}
~~~

Áp dụng trên field:

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {
    @Id
    private UUID id;

    @Convert(converter = CustomerIdJpaConverter.class)
    @Column(name = "customer_id", nullable = false)
    private CustomerId customerId;
}
~~~

Không dùng CustomerIdJpaConverter cho mọi loại ID chỉ vì chúng cùng chứa UUID.

Theo quy tắc JPA portable, AttributeConverter không được áp dụng cho thuộc tính primary key. Vì vậy ví dụ giữ UUID ở khóa chính trong Persistence Entity rồi chuyển sang OrderId ở adapter. Nếu muốn kiểu ID làm primary key ngay trong persistence model, hãy xem xét @EmbeddedId/@Embeddable tương thích với phiên bản JPA provider đang dùng; không dựa vào @Convert trên @Id mà chưa xác minh.

### 8.3. Không để JPA quyết định ngữ nghĩa ID

JPA chỉ chuyển đổi cách lưu trữ. Nó không thay thế việc thiết kế loại ID trong Domain. Repository domain vẫn nên có chữ ký:

~~~java
Optional<Order> findById(OrderId id);
~~~

Ngay cả khi Spring Data repository nội bộ nhận UUID, Application không nên phải chuyển mọi ID sang UUID chỉ để truy cập dữ liệu.

## 9. Foreign key và quan hệ giữa Aggregate

Strongly Typed ID ở Java không loại bỏ foreign key ở database:

~~~sql
CREATE TABLE customers (
    id UUID PRIMARY KEY
);

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Database bảo vệ tính toàn vẹn tham chiếu. Java bảo vệ việc dùng đúng loại ID trong code. Hai lớp bảo vệ bổ sung cho nhau.

Nếu Order tham chiếu Customer thuộc Bounded Context khác, cách triển khai thực tế có thể không dùng foreign key vật lý xuyên service/database. Dù vậy, Order vẫn có thể giữ CustomerId như một opaque reference theo contract đã thống nhất.

Không nên nhầm Strongly Typed ID với authorization. Biết CustomerId đúng kiểu không có nghĩa actor được phép xem hoặc sửa Customer đó.

## 10. Strongly Typed ID trong Spring Data repository

Có thể phân biệt repository theo Aggregate:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}

public interface PaymentRepository {
    Optional<Payment> findById(PaymentId id);
    void save(Payment payment);
}
~~~

Nếu dùng Spring Data trực tiếp ở infrastructure:

~~~java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderJpaEntity, UUID> {
}

public interface SpringDataPaymentRepository
        extends JpaRepository<PaymentJpaEntity, UUID> {
}
~~~

Hai interface có thể cùng nhận UUID ở tầng persistence. Domain-facing repository adapter chuyển đổi từ OrderId hoặc PaymentId. Điều này không làm mất type safety ở Application và Domain.

### 10.1. Đừng để Application gọi repository với UUID

Một thiết kế kém nhất quán:

~~~java
Order order = orderRepository.findById(command.orderId().value());
~~~

Nếu Application thường xuyên phải gọi value(), kiểu riêng chỉ còn là lớp bọc trang trí. Hãy giữ chuyển đổi ở adapter hoặc ranh giới persistence.

## 11. Tạo ID ở đâu?

Có một số cách sinh ID:

- Aggregate factory gọi OrderId.newId().
- Application truyền ID được tạo bởi một ID generator port.
- Database cấp ID theo sequence và repository trả ID sau khi lưu.

Chọn theo yêu cầu của hệ thống.

### 11.1. Tự sinh UUID trong Domain factory

~~~java
public static Order place(CustomerId customerId) {
    return new Order(OrderId.newId(), customerId);
}
~~~

Phù hợp khi Domain được phép sử dụng UUID và không cần phụ thuộc dịch vụ sinh ID bên ngoài.

### 11.2. Truyền ID generator

Nếu muốn kiểm soát việc sinh ID hoặc dễ deterministic test:

~~~java
public interface OrderIdGenerator {
    OrderId next();
}
~~~

Application có thể yêu cầu generator tạo ID rồi truyền vào factory. Domain chỉ biết OrderId, không biết UUID generator hoặc framework.

### 11.3. Database-generated ID

Nếu ID được tạo bởi database, adapter có thể nhận ID sau insert và chuyển thành OrderId. Tuy nhiên, nếu Aggregate cần ID trước khi phát Domain Event hoặc tạo các tham chiếu liên quan, application-generated ID có thể thuận tiện hơn.

Không có lựa chọn duy nhất cho mọi hệ thống. Điều cần giữ là kiểu ID trong Domain không bị mất chỉ vì cách sinh ID khác nhau.

## 12. Generic ID wrapper có nên dùng không?

Có thể viết một kiểu tổng quát:

~~~java
public record Id<T>(UUID value) {}

final class OrderTag {}
final class CustomerTag {}

Id<OrderTag> orderId;
Id<CustomerTag> customerId;
~~~

Về mặt compile time, hai kiểu tham số khác nhau giúp phân biệt một số trường hợp. Tuy nhiên, cách này có trade-off:

- Type erasure khiến generic type không tồn tại đầy đủ ở runtime.
- Serialization và reflection có thể cần cấu hình bổ sung.
- Tên kiểu trong log hoặc debugger ít diễn đạt ngôn ngữ miền.
- Marker type có thể làm code phức tạp hơn.
- Raw type hoặc unchecked cast có thể làm suy yếu bảo vệ.
- Hai tham số generic khác nhau vẫn có cùng raw class ở runtime; equals() của record Id chỉ so sánh UUID, không tự phân biệt OrderTag và CustomerTag.

Với đa số mô hình nghiệp vụ, các record riêng như OrderId, CustomerId và PaymentId dễ đọc, dễ debug và dễ mapping hơn.

Generic wrapper phù hợp khi đội ngũ có một abstraction chung thực sự cần thiết và đã chuẩn hóa cách serialize, persist, validate. Không nên chọn chỉ để giảm số lượng file.

## 13. ID có tiền tố hoặc mã nghiệp vụ

Không phải ID nào cũng là UUID. Một số hệ thống dùng mã có tiền tố:

~~~text
ORD-2026-000123
CUST-000045
PAY-2026-009876
~~~

Có thể tạo kiểu riêng:

~~~java
public record ShipmentId(String value) {
    public ShipmentId {
        if (value == null || !value.matches("SHP-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid shipment id");
        }
    }
}
~~~

Validation format nên phản ánh quy ước thật của mã. Nếu mã có thể thay đổi format theo thời gian hoặc được cấp bởi hệ thống ngoài, hãy cân nhắc validation ở adapter và giữ domain constructor theo quy tắc ổn định phù hợp.

### 13.1. Không suy ra loại ID từ tiền tố ở mọi nơi

Một chuỗi bắt đầu bằng ORD không nên được truyền khắp codebase rồi kiểm tra prefix thủ công. Khi parse xong, hãy chuyển thành OrderId. Từ đó các phương thức nhận đúng loại kiểu.

## 14. Strongly Typed ID và Bounded Context

Trong DDD, một định danh thường có ngữ nghĩa trong một Bounded Context. Hai context có thể dùng cùng một giá trị UUID nhưng hiểu đối tượng theo mô hình khác nhau.

Ví dụ:

- Sales Context có CustomerId.
- Billing Context có BillingAccountId.
- Identity Context có PrincipalId.

Không nên giả định ba ID này có thể thay thế cho nhau chỉ vì đều trỏ về cùng một người hoặc cùng một UUID.

Nếu Billing cần tham chiếu khách hàng của Sales, contract tích hợp cần nói rõ giá trị đó là SalesCustomerId hay một global customer reference đã được thống nhất. Strong typing buộc code phải thể hiện quyết định này.

### 14.1. Không tạo shared kernel ID tùy tiện

Một thư viện dùng chung chứa mọi ID của mọi context có thể làm các context phụ thuộc vào nhau. Chỉ chia sẻ kiểu khi hai bên thật sự thống nhất ownership và vòng đời contract.

Trong nhiều trường hợp, context tiêu thụ nên có kiểu reference riêng và mapper chuyển từ integration contract sang kiểu cục bộ. Điều đó giữ tính độc lập của mô hình.

## 15. Validation và lỗi ID

ID có thể sai ở nhiều mức:

| Lỗi | Ví dụ | Nơi xử lý |
|---|---|---|
| Sai cú pháp | Chuỗi không parse được UUID | HTTP/message adapter |
| Null | OrderId không có value | Constructor/factory của ID |
| Không tồn tại | UUID hợp lệ nhưng không có Order | Application/Repository |
| Sai loại | Truyền CustomerId vào use case Order | Compiler |
| Không có quyền | ID đúng nhưng actor không được truy cập | Authorization policy |
| Sai ngữ cảnh | ID của hệ thống khác chưa được ánh xạ | Integration adapter |

Không nên dùng một exception chung cho mọi trường hợp. Phân biệt lỗi parse, not found, type mismatch và access denied giúp API trả phản hồi chính xác hơn.

### 15.1. ID đúng kiểu không đồng nghĩa ID đáng tin

Một caller có thể gửi một OrderId đúng định dạng nhưng thuộc về người dùng khác. Strong typing không chứng minh quyền sở hữu.

Application vẫn phải kiểm tra:

- Actor đã xác thực chưa?
- Actor có quyền trên Aggregate này không?
- Aggregate có thuộc tenant hoặc tổ chức của actor không?
- Hành động có hợp lệ theo trạng thái miền không?

Không nên coi UUID khó đoán là cơ chế phân quyền.

## 16. Kiểm thử Strongly Typed ID

Nên kiểm tra cả hành vi kiểu ID và cách tích hợp.

### 16.1. Unit test cho ID

~~~java
class OrderIdTest {
    @Test
    void createsAndParsesId() {
        OrderId generated = OrderId.newId();
        OrderId parsed = OrderId.parse(generated.asString());

        assertEquals(generated, parsed);
    }

    @Test
    void rejectsNullValue() {
        assertThrows(
                NullPointerException.class,
                () -> new OrderId(null)
        );
    }
}
~~~

### 16.2. Kiểm tra khác loại ID

~~~java
@Test
void differentIdTypesAreNotEqual() {
    UUID raw = UUID.randomUUID();

    OrderId orderId = new OrderId(raw);
    CustomerId customerId = new CustomerId(raw);

    assertNotEquals(orderId, customerId);
}
~~~

Test này xác nhận equality ở runtime. Việc compiler từ chối truyền CustomerId vào phương thức nhận OrderId là bảo vệ ở compile time; không cần tạo một unit test cố biên dịch code sai trong bộ test thông thường.

### 16.3. Spring MVC converter test

Kiểm tra path string được chuyển thành đúng kiểu ID và chuỗi sai định dạng được ánh xạ thành lỗi 400 theo API contract.

### 16.4. Jackson serialization test

Nếu Domain ID được serialize trực tiếp, xác nhận JSON là chuỗi UUID theo hợp đồng, không phải object có field value. Nếu DTO dùng String, kiểm tra mapper chuyển đổi đúng.

### 16.5. JPA integration test

Nếu dùng AttributeConverter cho CustomerId, lưu và đọc lại Persistence Entity để xác nhận UUID trong database được chuyển về đúng CustomerId. Với OrderId nằm ở primary key, kiểm tra mapper hoặc cơ chế @EmbeddedId đã chọn. Cần kiểm tra riêng các ID type khác nhau có mapping phù hợp.

## 17. Migration từ UUID/Long sang Strongly Typed ID

Không nhất thiết phải thay đổi schema database để đưa Strongly Typed ID vào code.

Một lộ trình an toàn:

1. Chọn một Aggregate có ranh giới rõ, ví dụ Order.
2. Tạo OrderId bọc kiểu ID hiện tại.
3. Đổi field ID trong Domain Aggregate.
4. Đổi chữ ký Repository từ UUID sang OrderId.
5. Cập nhật Application Command/Query và use case.
6. Chuyển đổi tại persistence adapter hoặc AttributeConverter.
7. Cập nhật Controller converter và DTO mapper.
8. Thêm test cho parse, equality, mapping và repository.
9. Tiếp tục với CustomerId, PaymentId theo từng lát cắt.

Database có thể tiếp tục lưu UUID ở cột hiện tại. Vì vậy migration này thường là thay đổi code và mapping, không nhất thiết cần đổi dữ liệu.

### 17.1. Giữ tương thích API

Nếu API đang nhận UUID dạng chuỗi, vẫn có thể giữ nguyên JSON và URL:

~~~http
GET /orders/550e8400-e29b-41d4-a716-446655440000
~~~

Strong typing là chi tiết nội bộ của code. Không cần bắt client gửi object mới hoặc thay đổi định dạng ID nếu hợp đồng hiện tại đã phù hợp.

## 18. Các sai lầm thường gặp

### Dùng UUID ở mọi tầng

Nếu Domain, Application và Repository đều nhận UUID, compiler không thể phân biệt loại ID. Hãy giữ ID type ở các chữ ký miền.

### Tạo một EntityId dùng chung

Một kiểu chung làm mất ngữ nghĩa của Aggregate. Chỉ dùng abstraction tổng quát ở tầng thực sự cần xử lý nhiều loại ID.

### Bọc ID nhưng liên tục gọi value()

Nếu Application phải tháo wrapper trước mọi lần gọi Repository, kiểu riêng chưa được áp dụng xuyên suốt. Chuyển đổi tại adapter.

### Tạo một ID class quá tổng quát

Generic ID có thể tăng độ phức tạp của serialization, reflection và mapping. Dùng record riêng khi nó làm code rõ hơn.

### Để ID mutable

ID thay đổi sau khi Aggregate được tạo có thể phá vỡ identity và tham chiếu. Dùng kiểu immutable.

### Nhầm Strongly Typed ID với bảo mật

Kiểu ID ngăn nhầm loại trong code, không ngăn caller truy cập dữ liệu không thuộc quyền của họ.

### Dùng cùng một kiểu cho các ID của context khác nhau

Hai Bounded Context có thể có cùng giá trị UUID nhưng khác ngữ nghĩa và ownership. Dùng kiểu reference theo context.

### Tạo wrapper cho mọi chuỗi không có lý do

Không phải mọi chuỗi đều cần một class. Ưu tiên các ID và giá trị có ngữ nghĩa, rủi ro nhầm lẫn hoặc quy tắc riêng.

## 19. Khi nào nên áp dụng?

Strongly Typed ID đặc biệt hữu ích khi:

- Một use case nhận nhiều ID cùng kiểu nền.
- Hệ thống có nhiều Aggregate và Repository.
- Nhiều Bounded Context trao đổi định danh.
- Codebase lớn, nhiều nhóm cùng phát triển.
- Nhầm loại ID có hậu quả nghiệp vụ hoặc bảo mật.
- Muốn chữ ký API nội bộ tự mô tả ý nghĩa tham số.

Có thể chưa cần áp dụng cho một script nhỏ hoặc một CRUD đơn giản chỉ có một loại ID. Hãy cân nhắc chi phí mapping, serialization và sự phức tạp của dự án. Khi số lượng Aggregate và use case tăng, lợi ích compile-time thường rõ hơn.

## 20. Quy trình thiết kế ID type trong Java/Spring

Khi thêm một Aggregate mới:

1. Xác định định danh thuộc Aggregate và Bounded Context nào.
2. Chọn kiểu giá trị nền: UUID, Long hay String.
3. Tạo record ID riêng, immutable và kiểm tra null/format phù hợp.
4. Dùng ID type trong Aggregate và tham chiếu đến Aggregate khác.
5. Dùng ID type trong Repository interface và Application Command/Query.
6. Chuyển đổi HTTP path/query ở Spring Converter.
7. Chuyển đổi JSON ở DTO mapper hoặc Jackson configuration.
8. Chuyển đổi persistence bằng adapter hoặc JPA AttributeConverter.
9. Kiểm tra database foreign key và integration contract nếu có.
10. Viết unit test, serialization test, MVC test và persistence integration test phù hợp.

~~~mermaid
flowchart TD
    A[Aggregate mới] --> B[Xác định ngữ nghĩa định danh]
    B --> C[Tạo OrderId/CustomerId riêng]
    C --> D[Dùng trong Domain và Repository]
    D --> E[Application Command/Query]
    E --> F[Spring MVC Converter / DTO Mapper]
    D --> G[Persistence Adapter / JPA Converter]
    F --> H[HTTP contract giữ dạng chuỗi]
    G --> I[Database giữ UUID/Long/String]
~~~

## 21. Checklist

- [ ] Mỗi Aggregate có ID type riêng khi việc phân biệt mang lại giá trị.
- [ ] ID type immutable và không chấp nhận giá trị null.
- [ ] Equality phân biệt cả loại ID và giá trị.
- [ ] Aggregate tham chiếu Aggregate khác bằng ID phù hợp.
- [ ] Repository domain nhận đúng ID type.
- [ ] Application Command/Query không tháo wrapper thành UUID một cách tùy tiện.
- [ ] Spring MVC chuyển đổi path/query thành đúng ID type.
- [ ] JSON serialization giữ đúng API contract.
- [ ] JPA adapter/converter ánh xạ đúng kiểu lưu trữ.
- [ ] Foreign key và integrity constraint vẫn được bảo vệ ở database khi phù hợp.
- [ ] ID type của Bounded Context khác nhau không bị dùng thay thế tùy tiện.
- [ ] Authorization được kiểm tra riêng; Strongly Typed ID không được xem là bảo mật.
- [ ] Có test cho parse, equality, MVC, JSON và persistence mapping.

## 22. Kết luận

Strongly Typed ID giúp Java thể hiện ngữ nghĩa của định danh ngay trong hệ thống kiểu. Thay vì dùng UUID hoặc Long cho mọi Aggregate, hãy tạo OrderId, CustomerId, PaymentId và dùng chúng trong Domain Model, Application Service và Repository. Compiler sẽ phát hiện nhiều lỗi truyền nhầm ID trước khi chương trình chạy.

Spring và JPA vẫn có thể làm việc với biểu diễn thông thường ở ranh giới: Spring MVC chuyển chuỗi thành ID type, DTO mapper hoặc Jackson kiểm soát JSON, Persistence Adapter hoặc AttributeConverter chuyển ID thành UUID/Long trong database. Cách làm này không yêu cầu thay đổi định dạng API hay schema dữ liệu nếu chúng đang phù hợp.

Điều quan trọng là giữ kiểu riêng xuyên suốt nơi thể hiện ý nghĩa nghiệp vụ, chỉ chuyển sang kiểu nền tại ranh giới kỹ thuật. Strongly Typed ID không thay thế authorization hoặc foreign key, nhưng bổ sung một lớp bảo vệ compile-time giúp mô hình rõ ràng, an toàn và dễ bảo trì hơn.
