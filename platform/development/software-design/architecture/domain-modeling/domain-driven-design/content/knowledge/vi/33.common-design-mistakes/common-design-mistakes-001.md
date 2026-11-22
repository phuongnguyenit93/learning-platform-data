# Chỉ đổi tên lớp theo DDD nhưng giữ toàn bộ quy tắc ngoài mô hình

Một lỗi thường gặp khi áp dụng Domain-Driven Design (DDD) là đổi tên các lớp hiện có thành những tên nghe có vẻ đúng kiến trúc như `OrderDomainService`, `CustomerAggregate`, `OrderRepository` hoặc `PaymentEntity`, nhưng cách hệ thống thực thi nghiệp vụ vẫn không thay đổi. Controller vẫn kiểm tra trạng thái, service vẫn đọc và ghi từng field, helper vẫn tính tiền, còn entity chỉ là một túi dữ liệu có getter và setter.

Tên gọi mới không tự tạo ra mô hình miền. DDD yêu cầu đội phát triển chuyển hiểu biết nghiệp vụ thành ngôn ngữ chung và cấu trúc code có thể bảo vệ các quy tắc đó. Một lớp chỉ thực sự trở thành Aggregate khi nó sở hữu identity, ranh giới nhất quán và hành vi bảo vệ invariant phù hợp. Một Domain Service phải chứa quy tắc miền không tự nhiên thuộc về Entity hoặc Value Object. Application Service điều phối use case; repository lưu và tải aggregate; infrastructure thực hiện giao tiếp kỹ thuật.

Bài học này giải thích cách nhận diện lỗi “rename-only”, vì sao nó thường tạo ra Anemic Domain Model, cách phân bổ lại quy tắc vào đúng nơi và cách refactor tăng dần mà vẫn giữ hành vi đang chạy. Ví dụ xuyên suốt dùng quy trình xác nhận đơn hàng.

## Sau bài học này

Bạn có thể:

- Phân biệt đổi tên lớp với thay đổi thực sự trong mô hình miền.
- Nhận diện Anemic Domain Model và procedural business logic.
- Phát hiện Domain Service giả chỉ đổi tên từ application service hoặc utility.
- Xác định quy tắc thuộc Value Object, Entity/Aggregate, Domain Service hay Application Service.
- Đưa invariant vào đúng ranh giới mà không nhồi mọi logic vào Aggregate.
- Tách điều phối persistence, transaction và side effect khỏi domain behavior.
- Dùng Ubiquitous Language và bounded context để chọn tên, trách nhiệm và phạm vi.
- Viết test chứng minh hành vi đã chuyển vào mô hình.
- Refactor theo từng bước, giữ compatibility seam và loại bỏ đường logic cũ.

## 1. Đổi tên không đồng nghĩa với mô hình hóa

Giả sử một hệ thống có lớp `OrderService`. Nhóm quyết định đổi tên nó thành `OrderDomainService` vì đang triển khai DDD. Nhưng sau khi đổi tên:

- Lớp vẫn tải dữ liệu bằng repository.
- Nó vẫn kiểm tra mọi trạng thái bằng các câu `if` rải rác.
- Nó vẫn gọi setter để thay đổi từng field.
- Nó vẫn tự tính tổng tiền, chiết khấu và thuế.
- Nó vẫn gọi HTTP client hoặc gửi email.
- Entity `Order` vẫn chỉ chứa dữ liệu.

Tên lớp đã đổi, nhưng quyền sở hữu quy tắc và cách thay đổi trạng thái vẫn y nguyên. Đây là thay đổi từ vựng, chưa phải thay đổi mô hình.

| Thay đổi bề mặt | Thay đổi mô hình thực sự |
| --- | --- |
| `OrderService` đổi thành `OrderDomainService` | Xác định quy tắc nào thuộc Order, quy tắc nào là chính sách miền và quy tắc nào chỉ điều phối use case. |
| `OrderRow` đổi thành `OrderAggregate` | Aggregate bảo vệ invariant và chỉ cho phép trạng thái thay đổi qua hành vi hợp lệ. |
| `OrderDao` đổi thành `OrderRepository` | Repository tải/lưu aggregate theo identity, không chỉ cung cấp CRUD cho mọi bảng. |
| Chuyển class sang package `domain` | Domain code thực sự độc lập với framework, database, HTTP và messaging. |
| Đổi `status = "CONFIRMED"` thành `order.setStatus(CONFIRMED)` | Gọi `order.confirm(...)`, nơi kiểm tra điều kiện và thực hiện chuyển trạng thái. |

### Câu hỏi kiểm tra

Đừng chỉ hỏi “lớp này đã có tên DDD chưa?”. Hãy hỏi:

1. Quy tắc nghiệp vụ nào được lớp này sở hữu?
2. Ai có thể thay đổi trạng thái của đối tượng?
3. Có đường code nào bỏ qua quy tắc đó không?
4. Nếu invariant bị vi phạm, object có thể được tạo hoặc lưu ở trạng thái sai không?
5. Lớp có phụ thuộc vào database, framework hoặc hệ thống ngoài vì lý do kỹ thuật không?
6. Tên và hành vi có khớp với cách chuyên gia nghiệp vụ nói về khái niệm này không?

Nếu không trả lời được những câu hỏi đó, việc đổi tên chưa đủ để kết luận thiết kế đã theo DDD.

## 2. Anemic Domain Model: entity chỉ còn dữ liệu

Anemic Domain Model là mô hình trong đó Entity và Value Object chủ yếu chứa dữ liệu, còn quy tắc nghiệp vụ nằm trong các service thủ tục bên ngoài. Các class có thể mang tên miền rất đẹp, nhưng domain behavior không được đặt cùng nơi sở hữu trạng thái và invariant.

Ví dụ:

~~~java
public class Order {
    private OrderId id;
    private OrderStatus status;
    private List<OrderLine> lines;
    private Instant confirmedAt;

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void setConfirmedAt(Instant confirmedAt) {
        this.confirmedAt = confirmedAt;
    }
}
~~~

Class `Order` không thể tự bảo vệ quy tắc xác nhận. Bất kỳ caller nào có reference đều có thể đặt trạng thái thành CONFIRMED, kể cả khi đơn rỗng hoặc đã hủy.

Quy tắc bị đẩy ra ngoài:

~~~java
public class OrderDomainService {
    private final OrderRepository orders;
    private final Clock clock;

    public void confirm(OrderId id) {
        Order order = orders.findById(id).orElseThrow();

        if (order.getStatus() != OrderStatus.ACCEPTED) {
            throw new IllegalStateException("Cannot confirm");
        }
        if (order.getLines().isEmpty()) {
            throw new IllegalStateException("Order is empty");
        }

        order.setStatus(OrderStatus.CONFIRMED);
        order.setConfirmedAt(clock.instant());
        orders.save(order);
    }
}
~~~

Đổi tên service thành `OrderDomainService` không giải quyết vấn đề. Lớp này vẫn điều phối repository và cập nhật trạng thái thay cho aggregate. Nó đang thực hiện trách nhiệm application service, trong khi domain object vẫn anemic.

### Vì sao mô hình anemic gây khó khăn?

- Quy tắc bị phân tán khi nhiều service cùng thao tác trên một Entity.
- Mỗi caller có thể kiểm tra điều kiện theo một cách khác.
- Setter cho phép trạng thái không hợp lệ.
- Khó biết object đang ở trạng thái nào là hợp lệ.
- Test phải dựng nhiều service và mock dependency để kiểm tra một quy tắc đơn giản.
- Thay đổi nghiệp vụ có thể yêu cầu sửa nhiều nơi.
- Code không diễn đạt rõ ngôn ngữ mà chuyên gia nghiệp vụ sử dụng.

Không phải mọi ứng dụng có service đều là Anemic Domain Model. Application Service là thành phần cần thiết. Vấn đề xuất hiện khi service bên ngoài quyết định và thực hiện các quy tắc vốn thuộc về domain object.

## 3. Domain Service giả: đổi tên application service hoặc utility

Domain Service là nơi đặt một quy tắc nghiệp vụ có ý nghĩa trong domain nhưng không tự nhiên thuộc về một Entity hoặc Value Object cụ thể. Nó thường stateless và được đặt tên theo một hành động/chính sách nghiệp vụ.

Một lớp không trở thành Domain Service chỉ vì tên có chữ Domain.

Ví dụ lớp dưới đây:

~~~java
@Service
public class OrderDomainService {
    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final PaymentGateway paymentGateway;
    private final EmailClient emailClient;

    @Transactional
    public void placeOrder(PlaceOrder command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow();
        Order order = new Order(command.orderId(), customer.id());
        order.addLines(command.lines());
        orders.save(order);
        paymentGateway.authorize(order.total());
        emailClient.sendOrderReceived(customer.email(), order.id());
    }
}
~~~

Lớp này điều phối một use case, quản lý transaction, truy cập repository và gọi hệ thống ngoài. Đó là trách nhiệm của Application Service/Command Handler. Đặt nó trong package domain hoặc thêm hậu tố DomainService không làm thay đổi bản chất.

### Domain Service thực sự trông như thế nào?

Ví dụ, chính sách định giá có thể phụ thuộc vào khách hàng, sản phẩm và thời điểm, nhưng không thuộc riêng một OrderLine:

~~~java
public final class OrderPricingPolicy {
    public Money calculateUnitPrice(
        Product product,
        CustomerPricingProfile customer,
        PricingDate date
    ) {
        Money basePrice = product.listPrice();
        DiscountRate rate = customer.discountFor(product.category(), date);
        return basePrice.apply(rate);
    }
}
~~~

Đây là ví dụ khái niệm: chính sách phối hợp nhiều dữ kiện miền và trả về kết quả miền. Nó không tải dữ liệu, mở transaction, gửi email hoặc ghi database. Application Service có thể tải các đối tượng/dữ liệu cần thiết rồi gọi policy.

Một Domain Service có thể cần một abstraction để truy cập thông tin miền trong một số thiết kế, nhưng không nên biến thành nơi gom mọi repository, transaction và tích hợp kỹ thuật. Hãy xem xét liệu quy tắc có thể nhận các giá trị đầu vào đã được application layer tải sẵn hay không.

## 4. Phân bổ trách nhiệm theo đúng khái niệm DDD

Một mô hình tốt không có nghĩa là chuyển toàn bộ code vào Entity. Mỗi loại đối tượng có trách nhiệm riêng.

| Thành phần | Sở hữu trách nhiệm | Không nên trở thành |
| --- | --- | --- |
| Value Object | Tính hợp lệ, phép toán và quy tắc nội tại của một giá trị | Một DTO có tên khác nhưng không có semantics |
| Entity | Hành vi gắn với identity và vòng đời của entity | Một row có setter công khai cho mọi field |
| Aggregate Root | Invariant cần nhất quán trong ranh giới aggregate và điểm truy cập thay đổi | Một object graph lớn gom mọi thứ vào một transaction |
| Domain Service | Quy tắc miền không tự nhiên thuộc một Entity/Value Object | Application Service đổi tên hoặc utility tổng hợp |
| Application Service | Điều phối use case, transaction, authorization và các port | Nơi chứa mọi quyết định nghiệp vụ |
| Repository | Tải/lưu aggregate theo identity | DAO CRUD tùy ý cho từng bảng trong domain model |
| Infrastructure Adapter | Database, HTTP, broker, email và framework | Nơi quyết định quy tắc miền |

### Quy tắc nội tại của Value Object

Ví dụ `Money` có thể kiểm tra currency khi cộng:

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new CurrencyMismatchException(currency, other.currency);
        }
        return new Money(amount.add(other.amount), currency);
    }
}
~~~

Không cần một `MoneyDomainService` chỉ để cộng hai Money. Quy tắc thuộc về chính khái niệm Money.

### Hành vi phụ thuộc trạng thái thuộc Entity/Aggregate

Order quyết định liệu nó có thể được xác nhận hay không. Caller không nên tự đọc status rồi tự gán status mới.

### Quy tắc kết hợp nhiều đối tượng có thể thuộc Domain Service

Một chính sách tính phí vận chuyển theo vùng, trọng lượng và phương thức giao hàng có thể không thuộc riêng Order hoặc Address. Domain Service/policy có thể là nơi phù hợp nếu đó thực sự là quy tắc nghiệp vụ.

### Điều phối use case thuộc Application Service

Application Service tải aggregate, kiểm tra quyền, gọi hành vi, lưu thay đổi và ghi outbox. Nó không cần tự biết chi tiết từng invariant mà aggregate đã bảo vệ.

## 5. Ví dụ trước và sau: xác nhận đơn hàng

### Trước: logic nghiệp vụ nằm ngoài mô hình

~~~java
@Service
public class OrderDomainService {
    private final OrderRepository orders;
    private final Clock clock;

    @Transactional
    public void confirm(OrderId id) {
        Order order = orders.findById(id).orElseThrow();

        if (order.getStatus() == OrderStatus.CANCELLED) {
            throw new IllegalStateException("Cancelled order");
        }
        if (order.getStatus() != OrderStatus.ACCEPTED) {
            throw new IllegalStateException("Unexpected status");
        }
        if (order.getLines().isEmpty()) {
            throw new IllegalStateException("Empty order");
        }

        order.setStatus(OrderStatus.CONFIRMED);
        order.setConfirmedAt(clock.instant());
        orders.save(order);
    }
}
~~~

Các vấn đề:

- Tên `OrderDomainService` gây hiểu nhầm về trách nhiệm.
- Service phải biết chi tiết trạng thái và cấu trúc nội bộ Order.
- Bất kỳ caller nào cũng có thể bỏ qua service và gọi setter.
- Quy tắc có thể bị sao chép trong API, batch hoặc message consumer.
- Object không tự bảo vệ invariant.

### Sau: Aggregate sở hữu hành vi

~~~java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private OrderStatus status;
    private Instant confirmedAt;
    private final List<DomainEvent> events = new ArrayList<>();

    public void confirm(Instant now) {
        if (status != OrderStatus.ACCEPTED) {
            throw new OrderCannotBeConfirmedException(id, status);
        }
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeConfirmedException(id);
        }

        status = OrderStatus.CONFIRMED;
        confirmedAt = Objects.requireNonNull(now);
        events.add(new OrderConfirmed(id, now));
    }

    public OrderStatus status() {
        return status;
    }

    public List<DomainEvent> pullEvents() {
        List<DomainEvent> pending = List.copyOf(events);
        events.clear();
        return pending;
    }
}
~~~

Ví dụ lược giản constructor và collection policy. Trong code thực tế, không trả collection mutable ra ngoài; các phương thức thêm/xóa dòng cũng phải bảo vệ invariant tương ứng. Việc tái tạo aggregate từ persistence cần một đường reconstitution có kiểm soát.

### Application Service điều phối use case

~~~java
@Service
public class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;
    private final IntegrationEventOutbox outbox;
    private final Clock clock;

    @Transactional
    public void handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        accessPolicy.ensureCanConfirm(command.actorId(), order);
        order.confirm(clock.instant());
        orders.save(order);
        outbox.append(IntegrationEvents.from(order.pullEvents()));
    }
}
~~~

Application Service chịu trách nhiệm orchestration và transaction. Aggregate bảo vệ quy tắc chuyển trạng thái. Outbox ghi integration message cùng transaction để publisher xử lý sau commit. Authorization policy kiểm tra actor có quyền trên resource; đó không phải invariant nội tại của Order.

### Luồng sau refactor

~~~mermaid
flowchart TD
    A[HTTP / Message / Scheduler Adapter]
    B[ConfirmOrderHandler]
    C[OrderRepository]
    D[Order Aggregate]
    E[Order.confirm]
    F[Save Order]
    G[Append Outbox]
    H[(Database Transaction)]
    I[Outbox Publisher]
    J[External Consumers]
    A --> B
    B --> C --> D --> E
    E --> F --> H
    B --> G --> H
    H --> I --> J
~~~

## 6. Đừng chuyển mọi quy tắc vào Aggregate

Khi nhận ra entity anemic, một phản ứng cực đoan là đưa tất cả logic vào Aggregate Root. Điều đó dễ tạo ra aggregate quá lớn, phụ thuộc nhiều dịch vụ và transaction kéo dài.

Hãy phân biệt:

- Invariant phải đúng ngay sau mỗi transaction trong aggregate boundary.
- Quy tắc nội tại của một Value Object.
- Chính sách miền kết hợp nhiều khái niệm.
- Điều phối nhiều aggregate hoặc bounded context.
- Quyền truy cập, giao tiếp và tác động kỹ thuật.

### Ví dụ: tính giá đơn hàng

Một Order có thể sở hữu hành vi thêm/xóa dòng và tính subtotal từ các dòng. Nhưng giá niêm yết hiện hành có thể do Product Catalog quản lý, chiết khấu theo phân khúc khách hàng do Pricing Context quản lý, còn thuế phụ thuộc địa chỉ và luật tại thời điểm đặt hàng.

Không nên để Order tự gọi HTTP sang Catalog, Customer hoặc Tax service. Application Service lấy dữ liệu cần thiết qua các port; pricing policy tính toán theo quy tắc miền; Order giữ snapshot/giá đã chốt và bảo vệ invariant của đơn.

### Ví dụ: tồn kho và đơn hàng

Order không nên tự sửa số lượng tồn kho trong một aggregate khác. Nếu giữ hàng là một use case thuộc Inventory Context, hãy gửi command/reservation request đến context đó và xử lý kết quả theo quy trình nhất quán phù hợp. Không tạo một object graph khổng lồ chỉ để mọi thứ nằm trong cùng một transaction.

### Dấu hiệu Aggregate đang quá lớn

- Cần tải nhiều đối tượng không liên quan cho mọi command.
- Một thay đổi nhỏ gây lock hoặc conflict trên nhiều dữ liệu.
- Nhiều team phải sửa cùng một aggregate.
- Aggregate gọi trực tiếp nhiều dịch vụ ngoài.
- Quy tắc nhất quán thực tế chỉ cần eventual consistency giữa các context.
- Test một hành vi đơn giản phải dựng một object graph rất lớn.

## 7. Phân biệt Domain Service và Application Service bằng câu hỏi trách nhiệm

Hai loại service có thể cùng có method tên `calculate` hoặc `confirm`, nhưng mục đích khác nhau.

| Câu hỏi | Domain Service | Application Service |
| --- | --- | --- |
| Nó biểu diễn điều gì? | Một quy tắc/chính sách nghiệp vụ | Một use case của hệ thống |
| Có thể nói bằng ngôn ngữ chuyên gia? | Có | Có, nhưng thường là mục tiêu thao tác |
| Có nên phụ thuộc HTTP, ORM, broker? | Không | Không trực tiếp; dùng port/adapter |
| Có điều phối repository và transaction? | Thường không | Có |
| Có thể gọi hành vi Entity/Value Object? | Có | Có |
| Kết quả chính là gì? | Kết quả hoặc quyết định miền | Use case hoàn tất, bị từ chối hoặc đang chờ |

Ví dụ:

- `OrderPricingPolicy.calculate(...)`: Domain Service nếu quy tắc không thuộc tự nhiên về một object.
- `ConfirmOrderHandler.handle(...)`: Application Service điều phối xác nhận đơn.
- `Order.confirm(...)`: domain behavior của Aggregate.
- `OrderRepository.findById(...)`: persistence abstraction.

### Không dùng Domain Service như một “thùng chứa”

Nếu một class có hàng chục method cho tạo, sửa, xóa, xác nhận, hủy, gửi email và xuất báo cáo, nhiều khả năng nó đang gom nhiều use case và chính sách khác nhau. Tách theo hành vi và trách nhiệm thực tế, không chỉ theo entity name.

## 8. Ubiquitous Language và Bounded Context quyết định mô hình nào

DDD không bắt đầu bằng việc chọn stereotype annotation. Nó bắt đầu bằng việc hiểu nghiệp vụ và xác định mô hình có ý nghĩa trong một bounded context.

Cùng từ “Customer” có thể mang nghĩa khác nhau:

- Trong Sales Context: người mua, phân khúc, điều kiện thương mại.
- Trong Support Context: người yêu cầu hỗ trợ, lịch sử ticket và mức ưu tiên.
- Trong Billing Context: bên chịu trách nhiệm thanh toán, mã số thuế và địa chỉ hóa đơn.

Không nên tạo một `CustomerAggregate` dùng chung cho tất cả context chỉ vì tên class giống nhau. Mỗi context sở hữu mô hình và invariant riêng, kết nối qua contract/ACL hoặc context map.

### Đổi tên nhưng không đổi ngôn ngữ là dấu hiệu nguy hiểm

Nếu class vẫn dùng những từ kỹ thuật như `DataRecord`, `Manager`, `Processor` trong khi nghiệp vụ có khái niệm rõ hơn như `RefundRequest`, `CreditLimit`, `DeliveryWindow`, mô hình chưa phản ánh Ubiquitous Language.

Ngược lại, không nên đổi tên hàng loạt theo từ vựng của một context sang context khác. Một thuật ngữ chỉ có ý nghĩa khi được đặt trong đúng boundary và được các thành viên thống nhất.

### Bản đồ trách nhiệm trước khi đổi cấu trúc

Với mỗi quy tắc, ghi rõ:

| Quy tắc | Context sở hữu | Mô hình thực thi | Boundary điều phối |
| --- | --- | --- | --- |
| Đơn chỉ xác nhận khi ACCEPTED và có dòng hàng | Order Management | Order Aggregate | ConfirmOrderHandler |
| Hai Money phải cùng currency khi cộng | Context sở hữu phép toán tiền | Money Value Object của context đó | Caller dùng phép cộng |
| Giá theo phân khúc và thời điểm | Pricing | Pricing Policy/Domain Service | Quote/PlaceOrder handler |
| Actor có quyền xác nhận đơn | Security/Authorization policy | Access policy | ConfirmOrderHandler |
| Ghi Integration Event sau khi đơn commit | Order Management integration | Outbox record | ConfirmOrderHandler transaction |

### Subdomain quyết định mức đầu tư mô hình hóa

Khi chia hệ thống thành subdomain, hãy xác định phần nào là Core Domain, Supporting Subdomain và Generic Subdomain. Với Core Domain, mô hình và hành vi miền thường tạo lợi thế cạnh tranh nên cần đầu tư sâu vào ngôn ngữ, invariant và thiết kế. Supporting Subdomain cần mô hình đủ rõ để hỗ trợ nghiệp vụ đặc thù. Generic Subdomain có thể dùng giải pháp phổ biến hoặc sản phẩm có sẵn nếu phù hợp.

Điều này giúp tránh một kiểu “DDD hóa” khác: tạo Aggregate, Domain Service và Value Object cho mọi module với cùng mức độ phức tạp. Một module generic như gửi email có thể chỉ cần adapter và contract; quy tắc định giá cốt lõi lại cần mô hình miền giàu hành vi.

### Context Map xác định ranh giới của quy tắc

Nếu Order Management sử dụng thông tin giá từ Pricing Context, hãy xác định rõ quan hệ upstream/downstream và contract trao đổi. Order Management có thể lưu snapshot giá được chốt tại thời điểm đặt hàng; Pricing vẫn sở hữu chính sách tính giá. Không đưa toàn bộ Pricing Aggregate vào Order chỉ để tránh gọi qua context boundary.

Khi upstream có mô hình không phù hợp với ngôn ngữ downstream, ACL có thể chuyển đổi contract. Khi downstream chấp nhận mô hình upstream, có thể chọn quan hệ Conformist nếu đó là quyết định có chủ đích. Điều quan trọng là ownership của quy tắc phải rõ; đổi tên class trong một context không chuyển quyền sở hữu nghiệp vụ từ context khác.

## 9. Repository không phải lý do để domain object thành anemic

Repository là abstraction để tải và lưu aggregate. Nó không nên trở thành nơi chứa quy tắc nghiệp vụ.

Không nên:

~~~java
orders.updateStatus(orderId, OrderStatus.CONFIRMED);
~~~

nếu thao tác đó bỏ qua hành vi và invariant của aggregate.

Thay vào đó:

~~~java
Order order = orders.findById(orderId).orElseThrow();
order.confirm(clock.instant());
orders.save(order);
~~~

Repository không cần phơi bày mọi cột hoặc mọi setter. Nó cung cấp aggregate theo identity và lưu trạng thái sau khi hành vi đã được thực hiện.

### Khi nào query không cần tải Aggregate?

Query hiển thị danh sách đơn có thể đọc projection/DTO trực tiếp qua query service. DDD không bắt buộc mọi thao tác đọc phải tải aggregate. Điều cần bảo vệ là command thay đổi trạng thái phải đi qua boundary có thẩm quyền và invariant không bị bỏ qua.

### Tránh CRUD repository giả danh domain repository

Một interface có tên `OrderRepository` nhưng cung cấp `updateField`, `deleteLineRow`, `setStatus` cho caller tùy ý vẫn có thể phá vỡ aggregate boundary. Hãy thiết kế API repository theo vòng đời aggregate, không theo danh sách cột database.

## 10. Refactor theo từng bước, không đổi mọi thứ trong một lần

Để sửa lỗi rename-only, không cần rewrite module. Hãy chuyển từng quy tắc có giá trị và bảo vệ bằng test.

### Bước 1: Lập danh sách quy tắc hiện có

Tìm các điều kiện trạng thái, validation, phép tính, cập nhật field và side effect đang nằm trong controller, service, mapper hoặc stored procedure. Trao đổi với chuyên gia để xác định quy tắc nào còn hiệu lực, quy tắc nào là bug hoặc ngoại lệ lịch sử.

### Bước 2: Chọn một hành vi có ranh giới rõ

Ví dụ: xác nhận đơn. Xác định trạng thái đầu vào, điều kiện dòng hàng, actor, timestamp, event và kết quả khi không hợp lệ.

### Bước 3: Viết characterization và behavior test

Ghi lại behavior hiện tại trước khi di chuyển. Sau đó viết test domain thể hiện quy tắc mong muốn:

~~~java
@Test
void confirmsAcceptedOrderWithLines() {
    Order order = acceptedOrderWithOneLine();
    Instant now = Instant.parse("2026-01-10T09:00:00Z");

    order.confirm(now);

    assertEquals(OrderStatus.CONFIRMED, order.status());
    assertEquals(now, order.confirmedAt());
    assertTrue(order.pullEvents().stream()
        .anyMatch(OrderConfirmed.class::isInstance));
}

@Test
void rejectsCancelledOrder() {
    Order order = cancelledOrder();

    assertThrows(
        OrderCannotBeConfirmedException.class,
        () -> order.confirm(Instant.now())
    );

    assertEquals(OrderStatus.CANCELLED, order.status());
}
~~~

Test cần dựng aggregate qua factory/test fixture hợp lệ. Tránh mở setter chỉ để test có thể tạo mọi trạng thái tùy ý.

### Bước 4: Chuyển quy tắc vào domain object

Tạo method có tên nghiệp vụ, giữ trạng thái ở mức private và không cung cấp setter công khai cho các field được bảo vệ bởi invariant.

### Bước 5: Thu gọn service cũ thành orchestration

Service còn lại việc tải aggregate, authorization, gọi behavior, lưu thay đổi và ghi outbox. Nếu class cũ thực hiện use case, đổi tên nó thành Application Service/Command Handler cho đúng trách nhiệm.

### Bước 6: Chuyển mọi caller

Tìm API, batch, scheduler, consumer và test đang gọi setter hoặc service method cũ. Chuyển từng nhóm sang hành vi mới. Không để caller mới dùng domain method trong khi caller cũ vẫn cập nhật field trực tiếp.

### Bước 7: Xóa đường logic cũ

Khi không còn caller, xóa setter/method thủ tục cũ và compatibility adapter. Nếu giữ cả hai cách thực hiện, lỗi rename-only vẫn còn.

## 11. Bảo vệ ranh giới bằng test kiến trúc

Unit test chứng minh hành vi ở một vài trường hợp. Architecture test có thể bảo vệ hướng phụ thuộc và ngăn domain layer dần phụ thuộc vào framework.

Ví dụ nguyên tắc:

- Domain package không phụ thuộc Spring, JPA, web framework hoặc messaging client.
- Entity/Aggregate không gọi repository hoặc HTTP client.
- Controller không trực tiếp thay đổi trạng thái aggregate qua setter.
- Application layer được phép phụ thuộc domain và các port.
- Infrastructure implement port và phụ thuộc vào framework.

Có thể dùng ArchUnit hoặc công cụ tương đương để kiểm tra package dependency:

~~~java
@AnalyzeClasses(packages = "com.example.orders")
class DomainArchitectureTest {
    @ArchTest
    static final ArchRule domainMustNotDependOnSpring =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("org.springframework..");
}
~~~

Đây là ví dụ rule tối thiểu; dự án cần bổ sung rule cho JPA, web, broker và các module khác theo cấu trúc thực tế. Test kiến trúc không chứng minh domain behavior đúng, nhưng giúp ngăn phụ thuộc kỹ thuật rò vào domain.

### Test không nên ép mọi class vào stereotype

Không cần yêu cầu mọi package domain đều phải có một class DomainService. Một domain model có thể chỉ cần Entity, Value Object và policy. Architecture test nên bảo vệ dependency và boundary, không ép số lượng class hoặc tên hậu tố.

## 12. Kiểm thử sau khi chuyển quy tắc

Sau refactor, cần kiểm tra cả domain và use case:

| Loại test | Điều cần xác nhận |
| --- | --- |
| Value Object test | Constructor/factory từ chối dữ liệu sai; equality và phép toán đúng. |
| Entity/Aggregate test | Hành vi hợp lệ, từ chối hành vi sai và giữ invariant. |
| Domain Service test | Chính sách miền trả quyết định đúng cho các tổ hợp đầu vào. |
| Application test | Tải aggregate, authorization, transaction và lưu đúng thứ tự. |
| Repository integration test | Reconstitution, mapping và lưu aggregate giữ được invariant. |
| Architecture test | Domain không phụ thuộc infrastructure; boundary không bị bypass. |
| Regression test | API và các caller hiện tại giữ đúng hợp đồng đã thống nhất. |

### Test đường đi không hợp lệ

Không chỉ kiểm tra trường hợp thành công. Hãy thử:

- Xác nhận đơn đã hủy.
- Xác nhận đơn đã xác nhận.
- Xác nhận đơn không có dòng hàng.
- Cộng Money khác currency.
- Cập nhật aggregate từ version cũ.
- Caller không có quyền.
- Lưu aggregate thành công nhưng outbox thất bại.

Test phải xác nhận trạng thái không bị thay đổi một phần khi hành vi bị từ chối hoặc transaction rollback.

### Đừng kiểm thử bằng cách xác nhận tên method

Test kiểu `verify(orderDomainService).confirm(...)` không chứng minh quy tắc đã chuyển vào Order. Hãy kiểm tra trạng thái, exception, event và invariant. Mock có thể hữu ích cho orchestration, nhưng domain behavior cần được kiểm thử trực tiếp trên model.

## 13. Dấu hiệu cho thấy refactor đã thực sự hoàn thành

Một thay đổi từ procedural/anemic sang domain model có thể xem là đạt mục tiêu khi:

- Quy tắc quan trọng có một nơi sở hữu rõ.
- Entity/Aggregate không thể bị caller tùy ý đưa vào trạng thái sai qua public setter.
- Tên method diễn đạt hành động nghiệp vụ.
- Domain model không phụ thuộc database hoặc framework.
- Application Service ngắn gọn, tập trung vào điều phối use case.
- Domain Service chỉ tồn tại khi có quy tắc miền thực sự cần nó.
- Repository làm việc ở mức aggregate, không phơi bày CRUD tùy ý.
- Các caller cũ đã được chuyển hoặc được cô lập có thời hạn.
- Test chứng minh cả hành vi hợp lệ và không hợp lệ.
- Team có thể giải thích mô hình bằng cùng ngôn ngữ với chuyên gia nghiệp vụ.

Không phải mục tiêu là giảm số dòng service hoặc tăng số class domain. Một mô hình có thể có ít class nhưng rõ ràng, hoặc có nhiều class khi domain thực sự phức tạp. Chất lượng nằm ở nơi quy tắc được sở hữu và khả năng bảo vệ invariant.

## 14. Những sai lầm thường gặp

- **Chỉ đổi tên lớp:** `OrderService` thành `OrderDomainService` nhưng trách nhiệm không đổi.
- **Đổi tên entity nhưng giữ setter công khai:** caller vẫn có thể bỏ qua hành vi miền.
- **Đưa toàn bộ logic vào Domain Service:** tạo một procedural service mới với tên DDD.
- **Đặt transaction và repository trong Domain Service:** trộn điều phối use case với quy tắc miền.
- **Tạo Aggregate chỉ để bọc bảng:** không có invariant hoặc hành vi có ý nghĩa.
- **Chuyển mọi logic vào Aggregate:** aggregate quá lớn và phụ thuộc nhiều context.
- **Tạo Domain Service cho mọi phép tính:** Value Object hoặc Entity bị tước mất hành vi tự nhiên.
- **Để Controller quyết định trạng thái:** giao thức web trở thành nơi sở hữu nghiệp vụ.
- **Giữ hai đường ghi:** một caller dùng hành vi mới, caller khác vẫn sửa field trực tiếp.
- **Đổi package nhưng giữ dependency:** domain vẫn phụ thuộc JPA, Spring hoặc HTTP.
- **Gọi repository từ Entity:** domain model tự điều phối persistence.
- **Đưa authorization vào invariant của Entity:** trộn quyền truy cập theo actor với trạng thái nội tại của aggregate.
- **Bỏ qua bounded context:** dùng một model chung cho các nhóm nghiệp vụ có ngôn ngữ khác nhau.
- **Test chỉ kiểm tra method call:** không chứng minh trạng thái và invariant.
- **Không xóa code cũ:** quy tắc mới và cũ tiếp tục tồn tại, tạo hai nguồn quyết định.

## 15. Quy trình rà soát một lớp vừa được “DDD hóa”

Khi review một pull request đổi tên hoặc chuyển package, hãy làm theo trình tự:

1. **So sánh trách nhiệm trước/sau:** lớp có thực sự sở hữu một quy tắc mới không?
2. **Tìm nơi quyết định nghiệp vụ:** điều kiện và phép tính nằm ở đâu sau thay đổi?
3. **Kiểm tra mutation:** còn setter hoặc repository method cho phép bỏ qua behavior không?
4. **Kiểm tra dependency:** domain có import Spring/JPA/HTTP/broker không?
5. **Kiểm tra boundary:** transaction và orchestration có nằm ở application layer không?
6. **Kiểm tra aggregate:** invariant nào được bảo vệ trong aggregate boundary?
7. **Kiểm tra domain service:** quy tắc có thật sự không thuộc tự nhiên về Entity/Value Object?
8. **Kiểm tra context:** tên và rule có thuộc đúng bounded context?
9. **Kiểm tra caller:** mọi đường ghi đã đi qua hành vi có thẩm quyền chưa?
10. **Kiểm tra test:** test có chứng minh state transition và invalid path không?
11. **Kiểm tra legacy path:** logic cũ có còn hoạt động song song không?
12. **Kiểm tra khả năng tiến hóa:** thay đổi quy tắc tương lai sẽ phải sửa bao nhiêu nơi?

## Checklist rà soát

- [ ] Tên lớp phản ánh đúng trách nhiệm thực tế.
- [ ] Việc đổi tên đi kèm thay đổi ownership của quy tắc khi cần.
- [ ] Entity/Aggregate sở hữu hành vi gắn với identity và trạng thái.
- [ ] Value Object bảo vệ quy tắc nội tại và equality theo giá trị.
- [ ] Domain Service chỉ chứa quy tắc miền không tự nhiên thuộc Entity/Value Object.
- [ ] Application Service điều phối use case, transaction và port.
- [ ] Repository tải/lưu aggregate thay vì phơi bày update field tùy ý.
- [ ] Infrastructure không quyết định invariant nghiệp vụ.
- [ ] Không có public setter cho trạng thái cần được bảo vệ.
- [ ] Mọi caller ghi đều đi qua hành vi có thẩm quyền.
- [ ] Domain model thuộc đúng bounded context và dùng Ubiquitous Language.
- [ ] Có test cho thành công, từ chối và invariant.
- [ ] Có test kiến trúc cho hướng phụ thuộc quan trọng.
- [ ] Không còn hai implementation nghiệp vụ cùng hoạt động.
- [ ] Code tương thích cũ có tiêu chí loại bỏ rõ ràng.

## Kết luận

DDD không phải là việc đổi tên Service thành Domain Service, đổi DAO thành Repository hoặc chuyển Entity sang một package mới. Mô hình chỉ thay đổi khi quy tắc nghiệp vụ được đặt tại nơi có trách nhiệm sở hữu chúng và mọi đường ghi đều phải tôn trọng các quy tắc đó. Value Object bảo vệ tính hợp lệ của giá trị; Entity/Aggregate bảo vệ hành vi và invariant gắn với identity; Domain Service chứa chính sách miền không tự nhiên thuộc một object; Application Service điều phối use case và transaction; Repository cùng infrastructure đảm nhiệm persistence và tích hợp. Hãy refactor từng quy tắc, kiểm thử cả trạng thái hợp lệ lẫn không hợp lệ, chuyển toàn bộ caller và loại bỏ đường logic cũ. Khi đó, tên gọi DDD mới phản ánh một mô hình thực sự có thể diễn đạt và bảo vệ nghiệp vụ.
