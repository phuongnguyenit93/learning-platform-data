# Dùng chung mô hình miền và thư viện nghiệp vụ quá rộng

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Sai lầm thiết kế. README phân tích anti-pattern dùng một mô hình miền hoặc thư viện nghiệp vụ chung cho quá nhiều bounded context. Nội dung giải thích vì sao việc tái sử dụng class, enum, value object và business rules xuyên service có thể tạo coupling ngầm, buộc các nhóm release đồng bộ, làm sai ngữ nghĩa domain và khiến thay đổi nhỏ lan rộng. Tài liệu trình bày cách nhận diện, ranh giới chia sẻ hợp lý, ví dụ Java/Spring, contract/API/event, anti-corruption layer và lộ trình tách phụ thuộc an toàn.

## 1. Vấn đề bắt đầu từ ý định tái sử dụng tốt

Khi một hệ thống được tách thành nhiều microservice, các nhóm thường phát hiện những khái niệm xuất hiện ở nhiều nơi: `Customer`, `Address`, `Money`, `OrderStatus`, `Product`, `Discount`, `Payment`, `Tax`, `ShippingAddress`. Để tránh viết lặp, nhóm tạo một thư viện như `common-domain`, `shared-model` hoặc `business-core`, rồi đưa các class đó vào nhiều service.

Ban đầu, cách làm này có vẻ hiệu quả:

- Không phải định nghĩa lại class ở mỗi repository.
- Các nhóm dùng cùng một enum và một bộ validation.
- Một lỗi trong business rule có thể sửa tại một nơi.
- API và database mapping trông thống nhất.
- IDE và compiler giúp phát hiện thay đổi không tương thích.

Nhưng khi các domain phát triển độc lập, mô hình chung thường trở thành điểm ràng buộc:

- Order muốn thêm trạng thái `PARTIALLY_FULFILLED`, nhưng Payment không hiểu trạng thái đó.
- Pricing cần biểu diễn giá niêm yết, giá sau khuyến mại và giá quy đổi; Payment lại cần số tiền đã capture, refund và settlement.
- Customer Profile cho phép địa chỉ liên hệ chưa xác minh; Shipping chỉ chấp nhận địa chỉ giao hàng đã kiểm tra.
- Inventory cần quantity theo SKU, warehouse và reservation; Catalog chỉ cần thông tin sản phẩm để hiển thị.
- Một thay đổi nhỏ trong thư viện làm nhiều service phải nâng version và deploy lại.
- Các nhóm phải xin review từ team sở hữu thư viện dù thay đổi chỉ phục vụ một domain.

Đây là **shared domain model / shared business library quá rộng**: nhiều bounded context phụ thuộc trực tiếp vào cùng một mô hình hoặc quy tắc nghiệp vụ dù chúng có mục tiêu, ngôn ngữ và vòng đời thay đổi khác nhau.

Điểm cần chú ý là vấn đề không nằm ở việc có thư viện dùng chung. Vấn đề xuất hiện khi thư viện dùng chung trở thành **nguồn sự thật cho ngữ nghĩa nghiệp vụ của nhiều domain độc lập**.

## 2. Phân biệt tái sử dụng kỹ thuật và tái sử dụng mô hình miền

Không phải mọi code lặp đều nên được hợp nhất. Có hai nhóm rất khác nhau:

| Nhóm chia sẻ | Ví dụ | Rủi ro khi dùng chung |
| --- | --- | --- |
| Primitive kỹ thuật | Logging wrapper, tracing setup, retry helper, HTTP client configuration | Có thể tạo coupling phiên bản/tooling nhưng thường không áp đặt business semantics |
| Business model | `Order`, `Payment`, `Customer`, `DiscountPolicy`, `InventoryStatus` | Có thể buộc nhiều domain dùng chung một ngữ nghĩa |
| Transport contract | OpenAPI schema, event schema, generated API client | Có coupling contract; cần versioning và compatibility policy |
| Persistence model | JPA entity, database row model, ORM mapping | Có thể làm service phụ thuộc schema và lifecycle dữ liệu của nhau |
| Domain rule | Tax calculation, payment eligibility, order transition | Một domain thay đổi có thể làm domain khác thay đổi theo |
| Cross-cutting policy | Authorization primitives, audit metadata, tenant context | Cần owner và contract rõ; không được mang business state tùy tiện |

Một thư viện kỹ thuật có thể giúp nhiều service dùng cùng cách cấu hình Micrometer, HTTP timeout hoặc JSON serialization. Một thư viện domain lại quyết định điều gì được coi là Order, Payment, Customer hoặc Refund. Những định nghĩa này thường không giống nhau chỉ vì chúng có cùng tên.

**Nguyên tắc:** Chia sẻ cơ chế kỹ thuật khi semantics thực sự giống nhau; giữ mô hình nghiệp vụ trong bounded context sở hữu nó, rồi giao tiếp qua contract có chủ đích.

## 3. Bounded context: cùng một từ không đồng nghĩa cùng một mô hình

Trong Domain-Driven Design, bounded context là ranh giới nơi một mô hình và ubiquitous language có ý nghĩa nhất quán. Một thuật ngữ có thể xuất hiện ở nhiều context nhưng mang các quy tắc khác nhau.

Ví dụ thương mại điện tử:

| Thuật ngữ | Catalog Context | Order Context | Payment Context | Shipping Context |
| --- | --- | --- | --- | --- |
| Customer | Hồ sơ để cá nhân hóa hiển thị | Người mua gắn với đơn tại thời điểm đặt | Chủ thể thanh toán và phương thức được phép | Người nhận hàng và thông tin giao |
| Address | Địa chỉ tham khảo hoặc cửa hàng | Snapshot địa chỉ được chọn lúc đặt | Địa chỉ billing theo yêu cầu provider | Địa chỉ giao đã chuẩn hóa và xác minh |
| Money | Giá niêm yết và currency hiển thị | Tổng tiền phải thu tại thời điểm chốt đơn | Authorized/captured/refunded amount | COD amount hoặc phí giao |
| Status | Trạng thái công bố sản phẩm | Vòng đời đơn hàng | Trạng thái authorization/capture | Trạng thái fulfillment/delivery |
| Product | Nội dung và thuộc tính để tìm kiếm | Dòng hàng đã chốt SKU, giá, quantity | Mô tả tham chiếu khi xử lý charge | Hàng hóa cần đóng gói/giao |

Các context có thể cùng dùng từ `Customer` nhưng Order cần một snapshot ổn định để giữ lịch sử giao dịch, trong khi Customer Profile phản ánh thông tin hiện tại. Nếu Order giữ tham chiếu tới object `Customer` mutable trong thư viện chung, việc cập nhật địa chỉ profile có thể làm thay đổi cách diễn giải một đơn cũ.

Tương tự, `Money` trong nhiều domain đều có amount và currency, nhưng phép làm tròn, precision, quy tắc FX, tax inclusion và thời điểm chốt giá có thể khác. Một value object nhỏ có thể chia sẻ nếu hợp đồng toán học thật sự giống; business policy bao quanh nó vẫn nên thuộc context riêng.

## 4. Những dạng coupling do shared model gây ra

### 4.1. Compile-time coupling

Service A import class từ shared library. Khi library đổi method, constructor hoặc enum, compiler của A có thể fail dù A không cần thay đổi business behavior.

### 4.2. Semantic coupling

Một class giữ cùng tên nhưng domain khác hiểu khác nhau. Ví dụ `OrderStatus.CANCELLED` ở Order có thể có nghĩa đơn bị hủy; Payment `CANCELLED` có thể chỉ authorization bị void; Shipping `CANCELLED` có thể là shipment chưa dispatch. Dùng chung enum tạo cảm giác nhất quán nhưng làm mất ngữ nghĩa riêng.

### 4.3. Release coupling

Một thay đổi trong shared library buộc nhiều service nâng version. Các nhóm mất khả năng phát hành độc lập, hoặc phải duy trì nhiều nhánh version trong thời gian dài.

### 4.4. Data coupling

Shared entity hoặc ORM mapping khuyến khích nhiều service đọc/ghi cùng một bảng, cùng quan hệ hoặc cùng transaction boundary. Một nhóm thay schema có thể làm hỏng service khác.

### 4.5. Governance coupling

Một team duy trì shared library trở thành gatekeeper của nhiều domain. Roadmap của các nhóm bị chặn bởi lịch review, release và ưu tiên của một team khác.

### 4.6. Runtime coupling

Một thư viện chung có thể gọi một service, cache hoặc remote configuration trong quá trình xử lý. Khi đó một dependency tưởng như local lại kéo nhiều service vào cùng failure mode.

### 4.7. Security coupling

Shared model có thể mang các field nhạy cảm như email, phone, payment metadata hoặc tenant context tới những service không cần chúng. Một class quá rộng làm tăng khả năng truy cập dữ liệu ngoài mục đích.

Các dạng coupling thường xuất hiện cùng nhau. Chỉ tách repository hoặc đổi tên package không giải quyết được nếu semantics, dữ liệu và release process vẫn dùng chung.

## 5. Dấu hiệu nhận biết thư viện nghiệp vụ đã quá rộng

Các dấu hiệu thường gặp:

- Một package `common-domain` chứa class thuộc Order, Payment, Inventory, Customer và Shipping.
- Thay đổi enum trong một domain tạo compile errors ở nhiều service không liên quan.
- Một class có nhiều field nullable vì mỗi service dùng một phần khác nhau.
- Các method trong thư viện có nhiều nhánh `if (context == ...)`.
- Thư viện phụ thuộc vào Spring, JPA, Kafka hoặc vendor cụ thể dù chỉ muốn chia sẻ value object.
- Team phải phát hành version thư viện chung cho một thay đổi nhỏ.
- Các service phải deploy theo một thứ tự cố định dù không có giao dịch xuyên service.
- Một team không thể sửa business rule vì library owner chưa có capacity review.
- DTO API được dùng trực tiếp làm domain entity.
- Consumer truy cập trực tiếp vào field hoặc bảng nội bộ của producer.
- Shared library chứa `OrderService`, `PaymentPolicy`, `CustomerRepository` và các interface business của nhiều domain.
- Một thay đổi field trong Customer làm mọi service rebuild dù chỉ một service thực sự cần field đó.
- Có nhiều adapter chuyển đổi từ shared model sang model riêng, nhưng không ai dám bỏ shared model.
- Version dependency tăng liên tục nhưng các service không thể nâng đồng bộ.
- Test của thư viện phải khởi tạo database/broker/application context lớn dù chỉ thay một value object.

Một dấu hiệu quan trọng là **ngôn ngữ của thư viện ngày càng tổng quát**: `BaseEntity`, `BaseStatus`, `UniversalCustomer`, `GenericTransaction`, `CommonAddress`. Những abstraction này thường che giấu sự khác biệt thực tế giữa domain.

## 6. Vì sao một mô hình chung ban đầu có vẻ hợp lý?

Có một số nguyên nhân tổ chức và kỹ thuật:

1. **DRY bị áp dụng quá rộng:** nhóm xem mọi đoạn code giống nhau là duplication cần loại bỏ.
2. **Thiết kế từ schema:** một database hoặc class diagram ban đầu được coi là mô hình chung cho toàn hệ thống.
3. **Monolith legacy:** các module từng dùng cùng entity vì nằm trong một process và một transaction.
4. **Tiện lợi của build:** shared Maven/Gradle module dễ tạo hơn việc thiết kế contract.
5. **Thiếu ownership:** không rõ team nào chịu trách nhiệm cho semantics của từng domain.
6. **Tối ưu cục bộ:** nhóm giảm vài class lặp nhưng làm tăng chi phí release và phối hợp toàn hệ thống.
7. **Áp lực chuẩn hóa:** muốn tất cả service có một `Status`, `Money` hoặc `Customer` duy nhất.
8. **Thiếu consumer contract:** nhóm không có quy trình quản lý API/event schema nên dùng class Java chung như giao thức.
9. **Sợ dữ liệu không đồng nhất:** nhầm lẫn giữa consistency của một domain và việc mọi context phải dùng cùng object.
10. **Thiếu công cụ tạo contract:** không có schema registry, code generation hoặc compatibility tests.

DRY nên giảm sự lặp lại của **quy tắc có cùng lý do thay đổi**. Hai đoạn code giống nhau hôm nay có thể phục vụ hai policy khác nhau ngày mai. Nếu hai nhóm thường xuyên thay đổi độc lập, việc sao chép một value object nhỏ có thể rẻ hơn việc duy trì một abstraction chung.

## 7. Ví dụ anti-pattern: một shared-domain JAR cho mọi service

Cấu trúc không tốt:

~~~text
shared-domain/
  model/
    Customer.java
    Address.java
    Order.java
    Payment.java
    Product.java
    Inventory.java
    Transaction.java
  enums/
    Status.java
    Type.java
    State.java
  services/
    DiscountCalculator.java
    TaxCalculator.java
    PaymentPolicy.java
    ShippingPolicy.java
  repository/
    CustomerRepository.java
    OrderRepository.java
    PaymentRepository.java
~~~

Các service cùng phụ thuộc:

~~~text
order-service ---------+
payment-service -------+
inventory-service -----+----> shared-domain.jar
shipping-service ------+
catalog-service -------+
customer-service ------+
~~~

Một thay đổi `Customer.java` có thể ảnh hưởng tất cả consumer. `shared-domain.jar` trở thành một mini-monolith ở compile-time: các domain không cùng deploy process nhưng bị nối bởi cùng mô hình và chu kỳ release.

Một số triệu chứng trong code:

~~~java
public class Customer {
    private String id;
    private String email;
    private String phone;
    private Address billingAddress;
    private Address shippingAddress;
    private String loyaltyTier;
    private String paymentCustomerToken;
    private boolean verified;
    private boolean blocked;
    private Instant createdAt;
    private Instant lastOrderAt;
}
~~~

Không phải mọi service cần toàn bộ field. Payment có thể cần token tham chiếu; Shipping cần recipient/address; Marketing cần consent và preference; Order cần snapshot. Một object quá rộng làm lộ dữ liệu và quy tắc ngoài context.

Ví dụ method tổng quát:

~~~java
public boolean isAllowed(Customer customer, String operation) {
    if ("PAYMENT".equals(operation)) {
        return customer.isVerified() && !customer.isBlocked();
    }
    if ("SHIPPING".equals(operation)) {
        return customer.getShippingAddress() != null;
    }
    if ("MARKETING".equals(operation)) {
        return customer.isMarketingConsent();
    }
    return true;
}
~~~

Method này gom nhiều policy khác nhau vào một nơi. Khi Payment thay đổi KYC, Shipping thay đổi địa chỉ hợp lệ và Marketing thay đổi consent, shared library trở thành nơi phối hợp release của ba domain.

## 8. Thiết kế tốt hơn: mỗi bounded context sở hữu domain model của mình

Một cấu trúc gợi ý:

~~~text
order-service/
  order-domain/
    Order.java
    OrderLine.java
    OrderMoney.java
    OrderStatus.java
    OrderPolicy.java
  order-application/
  order-adapters/
  order-api/

payment-service/
  payment-domain/
    Payment.java
    Authorization.java
    Capture.java
    Refund.java
    PaymentStatus.java
  payment-application/
  payment-adapters/
  payment-api/

inventory-service/
  inventory-domain/
    StockItem.java
    Reservation.java
    InventoryQuantity.java
    ReservationStatus.java
  inventory-application/
  inventory-adapters/
~~~

Mỗi context có thể biểu diễn cùng một khái niệm theo nhu cầu của nó. Một `OrderMoney` và `PaymentAmount` có thể đều chứa `BigDecimal` và currency, nhưng constructor, precision, invariants và lifecycle khác nhau.

Điều này tạo **local autonomy**: Order thay đổi vòng đời đơn mà không buộc Payment phải hiểu enum mới. Payment thay đổi refund model mà không sửa Order entity. Giao tiếp giữa chúng diễn ra qua API/event contract có version và semantics rõ.

Không cần nhân bản toàn bộ logic. Hãy xác định phần nào thật sự là primitive ổn định, phần nào là business rule, phần nào là dữ liệu trao đổi.

## 9. Chia sẻ value object khi nào là hợp lý?

Một value object có thể chia sẻ nếu tất cả consumer thực sự đồng ý về:

- Ý nghĩa và bất biến.
- Phạm vi giá trị hợp lệ.
- Quy tắc equality/hash code.
- Precision, scale và rounding.
- Serialization format.
- Validation và normalization.
- Backward compatibility.
- Ownership và lifecycle.

Ví dụ `CurrencyCode` theo ISO 4217 có thể là primitive tương đối ổn định nếu các domain dùng cùng semantics. Tuy nhiên `Money` không chỉ là `amount + currency`: một domain có thể yêu cầu rounding theo currency minor unit, domain khác giữ precision cao trong tính toán thuế, domain khác dùng tỷ giá theo thời điểm settlement.

Một quyết định chia sẻ nên trả lời:
1. Nếu consumer A muốn đổi rule, consumer B có phải đổi cùng không?
2. Có một chuẩn độc lập, ổn định và có owner rõ không?
3. Class có chứa business policy hay chỉ biểu diễn primitive?
4. Việc copy nhỏ có thực sự gây rủi ro lớn hơn coupling không?
5. Có thể chia sẻ schema/contract thay vì Java class không?

Nếu không trả lời được, hãy giữ type trong context trước. Có thể trích xuất sau khi semantics ổn định và có bằng chứng nhiều consumer thật sự cần cùng một contract.

## 10. Các loại thư viện nên chia sẻ và giới hạn của chúng

| Thư viện | Thường có thể chia sẻ | Cần tránh |
| --- | --- | --- |
| Platform/runtime | Logging, tracing, metrics setup, health conventions | Business-specific metrics và state machine |
| Resilience | Timeout, retry budget, circuit breaker integration | Quyết định retry nghiệp vụ không idempotent |
| Serialization | JSON/Avro/Protobuf support, date/time format | Dùng transport object làm domain model |
| Security integration | Token verification adapter, authorization client | Chia sẻ toàn bộ user/customer profile |
| API client | Generated transport models và client methods | Expose JPA entities hoặc internal domain classes |
| Event contract | Schema, event envelope, compatibility metadata | Dùng một `UniversalEvent` không có semantics |
| Test utilities | Test clock, fixtures infrastructure, container setup | Business fixture chứa mọi domain assumptions |
| Domain primitives | Type nhỏ có semantics thật sự đồng nhất | Gộp policy riêng vào một `common-domain` |

Thư viện kỹ thuật cũng cần versioning, support policy và ownership. Nhưng nó thường thay đổi theo cơ chế runtime; shared business library thay đổi theo quy tắc của nhiều domain, nên mức coupling cao hơn.

## 11. Tách domain model, API DTO và persistence entity

Một nguyên nhân phổ biến của coupling là dùng một Java class cho cả ba mục đích:

- Domain model để bảo vệ invariants và thực thi business behavior.
- API DTO để trao đổi qua HTTP.
- Persistence entity để map database schema.

Ba mô hình có lifecycle khác nhau:

| Mô hình | Ưu tiên | Có thể thay đổi khi |
| --- | --- | --- |
| Domain | Ngữ nghĩa nghiệp vụ, invariants, behavior | Business rule đổi |
| API DTO | Contract với caller | API version/compatibility đổi |
| Persistence entity | Mapping và query storage | Schema/index/ORM đổi |

Ví dụ không nên:

~~~java
@Entity
public class Order {
    @Id
    private UUID id;
    private String customerEmail;
    private BigDecimal total;
    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
~~~

Class này vừa là entity vừa có thể bị serialize trực tiếp thành response. Khi thêm relationship lazy hoặc đổi cột database, API response có thể thay đổi ngoài ý muốn.

Có thể tách:

~~~java
// Domain model owned by Order context
public record OrderId(UUID value) {}

public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("Order has no lines");
        }
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Order cannot be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

~~~java
// API response contract
public record OrderResponse(
    String orderId,
    String status,
    BigDecimal total,
    String currency
) {}
~~~

~~~java
// Persistence adapter maps database rows to domain
@Entity
@Table(name = "orders")
class OrderJpaEntity {
    @Id
    UUID id;
    String status;
}
~~~

Ví dụ rút gọn; code thực cần constructor/factory, immutable collection, mapping và transaction boundaries phù hợp. Mục tiêu là thay đổi persistence hoặc transport không buộc domain và consumer thay đổi cùng lúc.

## 12. Không dùng JPA entity chung giữa microservices

JPA entity thường phản ánh quan hệ và cách lưu trữ của một database. Nếu nhiều service import entity từ shared JAR, chúng có thể vô tình phụ thuộc:
- Tên bảng và cột.
- Lazy/eager relationships.
- Cascade rules.
- Enum persistence representation.
- ORM lifecycle callbacks.
- Versioning/optimistic locking.
- Schema migration order.
- Transaction boundaries.

Một service có thể đọc database của service khác qua entity chung mà không gọi API. Khi owner đổi schema, consumer có thể hỏng dù endpoint public không đổi.

**Database ownership phải theo bounded context.** Service sở hữu dữ liệu có quyền quyết định schema; service khác dùng API/event hoặc một read model được công bố. Nếu cần shared database vì lý do vận hành, vẫn phải có schema/table owner và access policy, không chia sẻ entity để tạo coupling ngầm.

## 13. Dùng API contract thay cho Java domain class chung

Giả sử Order cần thông báo trạng thái cho Shipping. Thay vì để Shipping import `Order` từ `shared-domain`, công bố contract:

~~~json
{
  "orderId": "ord-123",
  "fulfillmentReference": "ful-456",
  "deliveryAddress": {
    "recipient": "Example",
    "postalCode": "700000",
    "country": "VN"
  },
  "lines": [
    {
      "sku": "SKU-001",
      "quantity": 2
    }
  ]
}
~~~

Đây là DTO minh họa. Shipping nhận đúng các field cần cho fulfillment. Nó không cần toàn bộ loyalty tier, payment token, customer preferences hoặc internal status transitions của Order.

Lợi ích:
- Producer kiểm soát contract được công bố.
- Consumer chỉ nhận thông tin cần thiết.
- Transport model không rò domain internals.
- Có thể version contract độc lập với implementation.
- Consumer có thể viết adapter để chuyển contract sang model nội bộ.
- API schema compatibility có thể kiểm tra trong CI.

Không nên biến API contract thành một shared domain model mới. Contract chỉ nên biểu diễn điều producer cam kết trao đổi, không chứa mọi class nội bộ.

## 14. Dùng event contract cho giao tiếp bất đồng bộ

Một event như `OrderPlaced` nên biểu đạt sự kiện đã xảy ra trong Order context:

~~~json
{
  "eventId": "evt-123",
  "eventType": "com.example.order.OrderPlaced",
  "eventVersion": 1,
  "occurredAt": "2026-11-12T03:15:00Z",
  "orderId": "ord-123",
  "currency": "VND",
  "totalAmount": "250000.00",
  "lines": [
    {
      "sku": "SKU-001",
      "quantity": 2,
      "unitPrice": "125000.00"
    }
  ]
}
~~~

Shipping có thể chuyển thành `ShipmentRequest`; Analytics có thể chuyển thành `OrderFact`; Payment có thể chuyển thành `PaymentIntent`. Mỗi consumer sở hữu model riêng và chỉ phụ thuộc event contract.

Một event cần:
- Tên và semantics rõ: điều gì đã xảy ra, không phải chỉ một object dump.
- Event ID và occurred time.
- Aggregate/business reference phù hợp.
- Schema version hoặc compatibility policy.
- Producer owner.
- Consumer expectations.
- PII/data classification.
- Idempotency/replay semantics.
- Retention và deprecation policy.

Không phát event chứa toàn bộ object `Order` vì “consumer có thể cần sau này”. Hãy publish dữ liệu tối thiểu cần thiết hoặc thiết kế event enrichment có kiểm soát.

## 15. Anti-corruption layer: bảo vệ domain của consumer

Một consumer có thể nhận API/event contract từ upstream nhưng không nên để mô hình upstream lan vào domain nội bộ.

Ví dụ Shipping nhận `OrderPlacedEvent`:

~~~java
public record OrderPlacedEvent(
    String orderId,
    String currency,
    BigDecimal totalAmount,
    List<OrderLineEvent> lines
) {}

public record OrderLineEvent(
    String sku,
    int quantity
) {}
~~~

Shipping chuyển sang model riêng:

~~~java
public record ShipmentId(UUID value) {}

public record ShipmentItem(
    Sku sku,
    Quantity quantity
) {}

public record DeliveryOrder(
    ExternalOrderReference orderReference,
    List<ShipmentItem> items,
    DeliveryAddress destination
) {}
~~~

Adapter:

~~~java
@Component
class OrderEventTranslator {
    DeliveryOrder toDeliveryOrder(
        OrderPlacedEvent event,
        DeliveryAddress destination
    ) {
        List<ShipmentItem> items = event.lines().stream()
            .map(line -> new ShipmentItem(
                new Sku(line.sku()),
                new Quantity(line.quantity())
            ))
            .toList();

        return new DeliveryOrder(
            new ExternalOrderReference(event.orderId()),
            items,
            destination
        );
    }
}
~~~

Đây là minh họa. `OrderEventTranslator` là anti-corruption layer: nó dịch contract bên ngoài sang ngôn ngữ Shipping. Nếu Order thay đổi một field không ảnh hưởng semantics của Shipping, translator có thể hấp thụ thay đổi mà domain Shipping không cần sửa.

ACL hữu ích khi upstream có mô hình legacy hoặc semantics khác. Không cần tạo lớp adapter phức tạp cho mọi field nếu contract và domain đã trùng nhau; giữ đúng mức cần thiết.

## 16. Shared kernel: trường hợp chia sẻ domain có chủ đích

DDD có khái niệm **Shared Kernel**: một phần nhỏ của mô hình được hai context cùng sở hữu và thay đổi theo cơ chế phối hợp rõ. Đây không phải giấy phép tạo một `common-domain` chứa mọi thứ.

Shared Kernel chỉ nên được chọn khi:
- Có phần semantics thật sự chung và tương đối ổn định.
- Các team đồng ý về cách thay đổi và review.
- Phạm vi nhỏ, dễ hiểu, có test contract.
- Tần suất thay đổi thấp hơn lợi ích chia sẻ.
- Có owner và release policy.
- Cả hai context chấp nhận phối hợp khi kernel đổi.

Ví dụ một bộ định nghĩa đơn vị đo đã chuẩn hóa có thể là Shared Kernel. Nhưng `OrderStatus`, `PaymentStatus` và `ShipmentStatus` không nên gộp chỉ vì đều là trạng thái.

**Chi phí của Shared Kernel là chi phí đồng thuận.** Nếu mỗi thay đổi cần nhiều team họp và chờ release, phần chia sẻ đã vượt lợi ích.

## 17. Context map và quan hệ giữa các nhóm

Context map mô tả quan hệ giữa bounded contexts:

- **Customer/Supplier:** downstream consumer có thể đưa yêu cầu, upstream vẫn sở hữu model và contract.
- **Conformist:** downstream chấp nhận mô hình upstream; cần nhận thức rủi ro phụ thuộc.
- **Anti-corruption layer:** downstream dịch mô hình bên ngoài sang domain riêng.
- **Open Host Service:** upstream công bố interface rõ để nhiều consumer dùng.
- **Published Language:** schema/contract chung cho trao đổi.
- **Separate Ways:** hai context không tích hợp nếu chi phí tích hợp lớn hơn giá trị.
- **Shared Kernel:** phần nhỏ được cùng sở hữu.

Ví dụ:

~~~text
Order Context (upstream)
    |
    | OrderPlaced v1 event
    v
Published event contract
    |
    +------> Shipping Context
    |            |
    |            +--> ACL --> DeliveryOrder
    |
    +------> Analytics Context
    |            |
    |            +--> Translator --> OrderFact
    |
    +------> Payment Context
                 |
                 +--> Adapter --> PaymentIntent
~~~

Mỗi consumer có thể chọn semantics riêng. Event schema là ngôn ngữ trao đổi, không phải domain model bắt buộc phải dùng trong toàn hệ thống.

## 18. Thiết kế thư viện dùng chung theo lớp

Một cách phân loại package:

~~~text
platform-libraries/
  observability-spring/
  security-spring/
  resilience-http/
  testcontainers-support/
  json-support/

contracts/
  order-events/
  payment-api/
  inventory-api/

order-service/
  order-domain/
  order-application/
  order-adapters/
  order-api/

payment-service/
  payment-domain/
  payment-application/
  payment-adapters/
  payment-api/
~~~

**Platform libraries** chứa tích hợp kỹ thuật, cấu hình và helper có semantics ổn định. **Contracts** chứa schema/DTO trao đổi đã công bố. **Domain modules** thuộc service sở hữu business behavior.

Không nên tạo một tầng `common` duy nhất để mọi thứ dồn vào. Chia theo lý do thay đổi và owner:
- `observability-spring` thay đổi khi platform telemetry đổi.
- `order-events` thay đổi khi Order public event contract đổi.
- `order-domain` thay đổi khi business rule Order đổi.
- `payment-domain` thay đổi khi business rule Payment đổi.

Tên package không tự tạo boundary; dependency direction và ownership mới quyết định.

## 19. Java package design: tránh import domain từ service khác

Một ví dụ cấu trúc module Maven:

~~~text
order-service/
  pom.xml
  order-domain/
  order-application/
  order-adapter-persistence/
  order-adapter-web/
  order-contracts/
~~~

Dependency direction nội bộ:

~~~text
web adapter --------+
persistence adapter -+--> application --> domain
messaging adapter ---+
~~~

Domain không nên phụ thuộc Spring MVC, JPA entity hoặc client của service khác. Application điều phối use case và gọi port; adapter hiện thực giao tiếp ngoài.

Với service khác, chỉ phụ thuộc vào published contract/client hoặc adapter tương ứng:

~~~text
shipping-service
  shipping-domain
  shipping-application
  shipping-adapter-order-events
        |
        v
  order-events-contract (published artifact)
~~~

Shipping không import `com.example.order.domain.Order`. Nếu cần dữ liệu, nó nhận event/API DTO rồi dịch sang model của Shipping.

## 20. Ví dụ Gradle: module business và contract có phạm vi riêng

Không tốt:

~~~kotlin
dependencies {
    implementation(project(":common-domain"))
}
~~~

Mọi service phụ thuộc một module rộng, khó biết class nào là public contract và class nào là nội bộ.

Tốt hơn:

~~~kotlin
dependencies {
    implementation(project(":order-events-contract"))
    implementation(project(":platform-observability"))
}
~~~

Trong `shipping-service`, dependency vào `order-events-contract` chỉ để deserialize event đã công bố; domain Shipping vẫn sở hữu `DeliveryOrder`, `ShipmentStatus` và quy tắc fulfillment.

Nếu dùng generated client, chỉ expose DTO/client transport. Không kéo theo persistence entities hoặc application services của producer.

## 21. Ví dụ Java: enum chung gây rò semantics

Anti-pattern:

~~~java
public enum Status {
    NEW,
    ACTIVE,
    PENDING,
    COMPLETED,
    FAILED,
    CANCELLED,
    REFUNDED,
    SHIPPED,
    DELIVERED
}
~~~

Enum này được dùng cho Order, Payment, Shipment và Inventory. Khi một domain thêm `PARTIALLY_REFUNDED`, các consumer khác phải nâng version hoặc bắt đầu có giá trị không hiểu.

Thiết kế riêng:

~~~java
public enum OrderStatus {
    PENDING_CONFIRMATION,
    CONFIRMED,
    FULFILLING,
    COMPLETED,
    CANCELLED
}

public enum PaymentStatus {
    CREATED,
    AUTHORIZED,
    CAPTURED,
    PARTIALLY_REFUNDED,
    REFUNDED,
    DECLINED
}

public enum ShipmentStatus {
    LABEL_CREATED,
    READY_FOR_PICKUP,
    IN_TRANSIT,
    DELIVERED,
    DELIVERY_FAILED,
    RETURNED
}
~~~

Khi trao đổi qua event, producer công bố trạng thái phù hợp contract hoặc event type cụ thể. Consumer ánh xạ sang enum nội bộ. Một enum trùng tên không chứng minh semantics giống nhau.

## 22. Ví dụ Java: Money dùng chung quá sớm

Một class `Money` dùng trong mọi domain có thể bắt đầu như sau:

~~~java
public record Money(BigDecimal amount, Currency currency) {}
~~~

Nhưng các câu hỏi nghiệp vụ vẫn chưa được giải quyết:
- Có cho phép amount âm không?
- Scale được giữ nguyên hay chuẩn hóa?
- Rounding mode nào áp dụng?
- Có cho phép currency chưa được hỗ trợ không?
- Có so sánh hai amount khác currency không?
- Tax/discount được tính trước hay sau rounding?
- FX rate lấy tại thời điểm quote, order hay settlement?
- Refund có thể nhỏ hơn capture không?

Nếu shared library tự chọn một policy, nó áp đặt lên các domain. Nếu không chọn, mỗi service phải tự đoán và behavior có thể lệch.

Có thể chia:
- Primitive `CurrencyCode` nếu semantics ổn định.
- `OrderTotal` với quy tắc chốt giá và rounding của Order.
- `PaymentAmount` với precision/settlement rules của Payment.
- `RefundAmount` với giới hạn theo capture.
- `ShippingFee` với currency và rule của Logistics.

Có thể dùng cùng `BigDecimal`/JDK `Currency` nhưng giữ type và invariant riêng. Code lặp nhỏ ở constructor không đáng lo bằng việc thay đổi một policy gây ảnh hưởng cả hệ thống.

## 23. Tránh Universal BaseEntity và generic domain framework

Một thư viện có thể tạo:

~~~java
public abstract class BaseEntity<ID> {
    private ID id;
    private Instant createdAt;
    private Instant updatedAt;
    private long version;
    private boolean deleted;
}
~~~

Rồi mọi domain entity kế thừa. Tuy nhiên:
- Có domain dùng event-sourced identity.
- Có domain không có soft delete.
- Có domain cần audit fields khác.
- Có domain versioning theo aggregate, domain khác theo record.
- `updatedAt` có thể mang semantics khác giữa business time và persistence time.

Một base class quá rộng làm model bị ràng buộc vào lifecycle persistence. Có thể chia sẻ technical interface nhỏ hoặc composition cho metadata thật sự chung, nhưng không ép mọi aggregate kế thừa một model duy nhất.

Ưu tiên composition và explicit mapping. Chỉ tạo abstraction khi có nhiều consumer với cùng semantics và cùng lý do thay đổi.

## 24. Dùng contract versioning thay cho shared binary versioning

Shared JAR tạo binary dependency; một thay đổi class có thể buộc consumer compile lại. Published API/event contract có thể tiến hóa với compatibility rules.

Các quy tắc thường dùng:
- Thêm field optional có default/semantics rõ thường dễ tương thích hơn đổi field hiện có.
- Không đổi meaning của field mà giữ nguyên tên.
- Không tái sử dụng enum value đã bị deprecate cho nghĩa mới.
- Consumer phải chịu được field mới nếu contract cho phép.
- Producer duy trì backward compatibility trong thời gian migration.
- Breaking changes có version mới hoặc deprecation window.
- Event cũ trong broker có thể được replay sau khi consumer đã nâng cấp.
- Schema registry compatibility mode phải phù hợp với retention/replay policy.

SemVer của thư viện không đủ thay cho contract governance. Một thay đổi có thể không phá binary compatibility nhưng vẫn phá business semantics.

## 25. Expand-contract cho API và schema

Một migration thường có ba pha:

**Expand**
1. Producer bổ sung field/endpoint/event mới theo cách tương thích.
2. Consumer được cập nhật để đọc cả dạng cũ và mới.
3. Test compatibility trong CI.

**Migrate**
1. Deploy producer và consumer theo thứ tự an toàn.
2. Chuyển dần traffic/feature flag.
3. Backfill hoặc dual-read/dual-write nếu có lý do và kiểm soát.
4. Theo dõi consumer versions và lỗi mapping.

**Contract**
1. Xác nhận không còn consumer dùng field cũ.
2. Hết deprecation window.
3. Bỏ field/endpoint/schema cũ.
4. Xóa adapter tương thích sau khi có bằng chứng.
5. Ghi lại contract version và migration outcome.

Không deploy breaking change chỉ vì tất cả consumer nằm trong cùng một monorepo. Trong production, version cũ/mới có thể cùng tồn tại ở nhiều Pod, region, queue hoặc mobile client.

## 26. Consumer-driven contract testing

Contract test giúp producer và consumer thống nhất giao tiếp mà không phải chia sẻ domain class.

Quy trình:
1. Consumer định nghĩa request/response hoặc event fields mà nó phụ thuộc.
2. Contract được publish vào broker/repository.
3. Producer verification chạy với các contract active.
4. CI chặn thay đổi breaking trước khi deploy.
5. Consumer test adapter mapping vào domain model riêng.
6. Compatibility được kiểm tra với các version còn tồn tại.

Contract test nên kiểm tra behavior cần thiết, không khóa producer vào toàn bộ implementation detail. Nếu contract test assert mọi field của JSON dù consumer không dùng, nó sẽ tạo coupling mới ở mức transport.

Đối với event, cần test message cũ được consumer hiện tại xử lý; retention có thể khiến event version cũ xuất hiện nhiều ngày sau release.

## 27. Anti-corruption layer và mapping có chi phí

Tách domain model sẽ tạo mapping code. Đó là chi phí có chủ đích để giữ boundary.

Ví dụ:

~~~java
@Component
class PaymentIntentMapper {
    PaymentIntent toDomain(CreatePaymentRequest request) {
        return PaymentIntent.create(
            new PaymentId(UUID.fromString(request.paymentId())),
            new OrderReference(request.orderId()),
            PaymentAmount.from(
                request.amount(),
                CurrencyCode.of(request.currency())
            )
        );
    }
}
~~~

Mapper nên:
- Nằm ở adapter/integration boundary.
- Chỉ chuyển dữ liệu và kiểm tra contract.
- Không chứa business policy của hai domain cùng lúc.
- Ghi rõ trường nào bị bỏ hoặc default.
- Có test cho missing/unknown fields và enum values.
- Không tạo side effects bất ngờ.

Nếu mapping phức tạp vì hai model có semantics khác, đó là tín hiệu boundary đang bảo vệ hai domain. Nếu mapping chỉ copy 40 field giống nhau, hãy xem lại contract có đang quá rộng hay không.

## 28. Tránh dùng shared library để đồng bộ business rule

Một ví dụ khác là `DiscountCalculator` được import vào Cart, Pricing và Order. Các domain có thể cần tính giảm giá ở những thời điểm khác nhau:

- Cart tính ước lượng để hiển thị.
- Pricing tạo quote có expiry và rule eligibility.
- Order chốt giá tại thời điểm xác nhận.
- Finance tính doanh thu/chiết khấu sau hoàn tiền.

Nếu cùng gọi một method `calculateDiscount()`, nhóm có thể vô tình dùng kết quả ước lượng của Cart làm giá cuối trong Order.

Cách tiếp cận:
- Pricing context sở hữu policy quote chính thức.
- Cart gọi Pricing API hoặc dùng một estimate contract có nhãn rõ.
- Order lưu snapshot quote/price breakdown được chấp nhận.
- Finance nhận event/snapshot để ghi nhận theo accounting rules.
- Các consumer không tự suy diễn lại business rule bằng thư viện chung.

Nếu business rule cần dùng lại thật sự, có thể công bố một service/API chuyên trách hoặc một domain capability rõ ràng. Điều đó vẫn có chi phí network/runtime và cần SLO; không phải mọi rule đều cần trở thành microservice.

## 29. Quyết định giữa copy, library, API và event

| Phương án | Phù hợp khi | Rủi ro |
| --- | --- | --- |
| Copy một đoạn nhỏ | Logic đơn giản, ít thay đổi, semantics có thể khác dần | Có thể drift nếu rule thực sự cần thống nhất |
| Shared technical library | Cơ chế kỹ thuật ổn định và nhiều service cần cùng behavior | Version/tooling coupling |
| Shared Kernel nhỏ | Một phần domain được các context cùng đồng thuận và cùng thay đổi | Coordination/release coupling |
| API/service call | Một domain sở hữu capability/rule authoritative | Network latency, availability, runtime dependency |
| Event contract | Consumer cần phản ứng với sự kiện, không cần gọi đồng bộ | Eventual consistency, schema/replay |
| Consumer-owned read model | Consumer cần query nhanh và hình dạng riêng | Projection lag, data duplication |
| Anti-corruption layer | Consumer cần bảo vệ domain trước mô hình upstream | Mapping code và maintenance |

Không có một phương án tối ưu cho mọi trường hợp. Quyết định phải dựa trên **lý do thay đổi, ownership, consistency, latency, availability và mức độ độc lập cần có**.

## 30. Khi nào nên giữ một shared library?

Có thể giữ một thư viện nếu:
- Phạm vi rất nhỏ.
- Semantics rõ và ổn định.
- Không chứa policy của nhiều domain.
- Consumer thật sự cần cùng behavior.
- Có maintainer, release cadence và compatibility policy.
- Không kéo theo framework/persistence dependency không cần thiết.
- Không buộc service release đồng thời.
- Có test chứng minh consumer compatibility.
- Có kế hoạch deprecate nếu mục đích không còn.

Ví dụ thư viện `currency-code` chỉ biểu diễn mã currency chuẩn và validation format có thể hợp lý. Nhưng nếu nó quyết định tax rounding, FX source, payment capture hoặc order pricing thì đã đi vào business policy.

Một thư viện dùng chung tốt thường nhỏ hơn kỳ vọng ban đầu và có API hẹp hơn.

## 31. Khi nào nên tạo API thay vì import JAR?

Nên cân nhắc API khi một domain sở hữu capability mà các domain khác cần sử dụng, ví dụ:
- Pricing quote chính thức.
- Payment authorization/capture.
- Inventory reservation.
- Customer identity verification.
- Tax determination theo jurisdiction.

API tạo boundary rõ và cho owner quyền thay đổi implementation. Nhưng cần tính:
- Latency và timeout.
- Retry/idempotency.
- Availability dependency.
- Versioning và consumer compatibility.
- Caching và freshness.
- Failure/degraded behavior.
- Security/authorization.
- Observability và cost.

Không chuyển mọi method trong shared library thành HTTP endpoint. Nếu method chỉ là pure primitive nhỏ và ổn định, API network có thể tạo complexity không cần thiết. Một domain capability có state, policy và owner rõ mới thường phù hợp làm service boundary.

## 32. Khi nào nên dùng event thay vì gọi API?

Event phù hợp khi consumer cần biết một điều đã xảy ra và có thể xử lý bất đồng bộ:
- `OrderPlaced`
- `PaymentCaptured`
- `InventoryReserved`
- `ShipmentDispatched`
- `RefundCompleted`

API phù hợp khi caller cần câu trả lời hiện tại hoặc yêu cầu một hành động đồng bộ có kết quả cần thiết ngay.

Không dùng event chỉ để né một API đang chậm nếu consumer vẫn cần quyết định ngay. Event mang eventual consistency, retry, duplicate delivery và replay semantics. Consumer cần idempotency và có thể phải xử lý event đến trễ hoặc sai thứ tự.

## 33. Lộ trình refactor từ shared model rộng

Không nên xóa shared library trong một lần nếu nhiều service đang dùng. Một lộ trình an toàn:

### Giai đoạn 1: Inventory và phân loại

- Liệt kê các package/class và consumer thực tế.
- Gắn mỗi class với bounded context hoặc platform concern.
- Tìm các business rules và mutable state.
- Xác định class nào chỉ là transport DTO, persistence entity hoặc primitive.
- Ghi dependency graph và version hiện tại.
- Xác định consumer không còn active.

### Giai đoạn 2: Chốt ownership và semantics

- Chỉ định owner cho mỗi domain concept.
- Ghi các cách hiểu khác nhau của cùng thuật ngữ.
- Chốt public API/event contract cần tồn tại.
- Xác định invariants và nguồn sự thật dữ liệu.
- Phân loại breaking changes và consumer risk.

### Giai đoạn 3: Tạo model riêng ở consumer

- Consumer định nghĩa domain type nội bộ.
- Thêm mapper/ACL tại boundary.
- Thay import shared domain bằng contract/DTO hoặc adapter.
- Chạy contract tests và integration tests.
- Giữ adapter tương thích với version đang chạy.

### Giai đoạn 4: Di chuyển từng consumer

- Chọn consumer có rủi ro thấp trước.
- Deploy model mới trong khi contract cũ vẫn được hỗ trợ.
- Theo dõi runtime behavior và data consistency.
- Gỡ dependency cũ sau khi không còn references.
- Không thay đổi semantics ngoài scope migration.

### Giai đoạn 5: Thu hẹp thư viện chung

- Chuyển business classes về domain owner.
- Giữ lại primitive/technical helpers đã chứng minh có semantics chung.
- Tách artifact contract khỏi domain implementation.
- Bỏ dependency framework không cần thiết.
- Publish version mới, deprecate module cũ có thời hạn.
- Thêm CI rule ngăn service mới import package nội bộ của domain khác.

### Giai đoạn 6: Hoàn tất và quản trị

- Cập nhật service catalog, dependency graph và CODEOWNERS.
- Xóa code/versions cũ khi không còn consumer.
- Cập nhật runbook, dashboards và release policy.
- Đo số consumer, release coupling và build dependency trước/sau.
- Ghi ADR và quyết định có giữ Shared Kernel hay không.

## 34. Strangler pattern cho shared library

Có thể thay thế từng phần bằng cách bao quanh dependency cũ:

~~~text
Before:
Shipping Service
      |
      v
Shared Customer / Order Model
      |
      v
Shared Business Rules

Transition:
Shipping Adapter
      |
      +--> Legacy Shared Model (temporary)
      |
      +--> New Order Event Contract
                 |
                 v
          Shipping Domain Model

After:
Shipping Adapter --> Contract Translator --> Shipping Domain
```

Trong giai đoạn chuyển tiếp:
- Không đổi mọi consumer cùng lúc.
- Adapter giữ tương thích với shared model cũ.
- Test mapping song song với behavior cũ.
- Ghi metric để biết còn consumer nào dùng path legacy.
- Có deadline và owner cho việc gỡ dependency.
- Không để adapter tạm thời trở thành một shared model mới.

Strangler giúp giảm blast radius nhưng cần có điều kiện kết thúc. Nếu giữ cả hai model vô thời hạn, chi phí mapping và test có thể tăng.

## 35. Tránh dual-write và migration dữ liệu không kiểm soát

Khi tách model, có thể cần thay database schema hoặc chuyển dữ liệu. Rủi ro:
- Hai service cùng ghi một record.
- Old model và new model có validation khác.
- Dual-write thành công một phía nhưng thất bại phía kia.
- Backfill bỏ qua record cũ hoặc xử lý trùng.
- Event replay tạo duplicate business effects.
- Rollback code không thể rollback data.

Nguyên tắc:
1. Chốt source of truth trong mỗi pha.
2. Dùng expand-contract cho schema.
3. Ưu tiên transactional outbox/CDC có checkpoint thay vì hai lần ghi không có phối hợp.
4. Backfill idempotent và có batch/checkpoint.
5. Có reconciliation counts/checksums/domain invariants.
6. Đo lag và lỗi mapping.
7. Có rollback/forward-fix strategy.
8. Không xóa cột/bảng cũ trước khi chứng minh không còn consumer.
9. Ghi rõ khi nào chuyển quyền ghi từ service cũ sang owner mới.
10. Kiểm tra backup/restore trước migration có rủi ro dữ liệu.

Tách domain model không nhất thiết đòi hỏi tách database ngay lập tức. Có thể tách code ownership/contract trước rồi di chuyển persistence theo từng bước nếu điều đó giảm rủi ro.

## 36. Dependency rules trong CI để ngăn tái diễn

Có thể áp dụng:
- Module domain chỉ import JDK hoặc thư viện thuần cần thiết.
- Service không import package `.domain` của service khác.
- Transport contracts không chứa JPA entity hoặc Spring application service.
- Platform library không chứa business policy.
- Dependency graph có allowlist/denylist theo bounded context.
- CODEOWNERS yêu cầu review cho contract changes.
- Contract tests chạy khi schema/API thay đổi.
- Architecture tests kiểm tra package boundaries.
- SBOM và dependency scanning cho shared artifacts.
- Version pinning và compatibility matrix.

Ví dụ rule kiến trúc ở mức khái niệm:

~~~text
order-domain:
  allowed:
    - java.*
    - approved-domain-primitives

shipping-domain:
  forbidden:
    - com.example.order.domain.*
    - com.example.payment.domain.*

shipping-adapters:
  allowed:
    - com.example.contracts.order.*
~~~

Công cụ như ArchUnit có thể kiểm tra package dependencies trong Java. Rule cần phản ánh boundary thực tế; đừng cấm một import kỹ thuật hợp lý chỉ vì nó nằm trong package của service khác.

## 37. Ví dụ ArchUnit kiểm tra boundary

Một test minh họa:

~~~java
@AnalyzeClasses(packages = "com.example")
class DomainBoundaryTest {

    @ArchTest
    static final ArchRule shipping_domain_must_not_depend_on_order_domain =
        noClasses()
            .that().resideInAPackage("..shipping.domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("..order.domain..");
}
~~~

Ví dụ dùng ArchUnit API; package names và dependency phải điều chỉnh theo project. Có thể bổ sung rule cho Payment, Inventory và các domain khác. Đừng cấm adapter Shipping phụ thuộc `order.contracts` nếu đó là public integration boundary được phê duyệt.

Architecture tests giúp biến nguyên tắc thành kiểm soát CI. Chúng không thay design review: một package `contracts` vẫn có thể bị thiết kế quá rộng hoặc mang semantics sai.

## 38. Quản lý version và release của shared artifacts

Với thư viện kỹ thuật hoặc contract:
- Có owner rõ.
- Semantic versioning phù hợp loại compatibility.
- Changelog ghi behavior/contract changes.
- Có deprecation window.
- Có consumer inventory.
- Có release automation và immutable artifact.
- Có test trên các version consumer còn hỗ trợ.
- Không dùng `SNAPSHOT`/floating version cho production.
- Không để shared library kéo theo transitive dependencies quá rộng.
- Có quy trình xử lý security patch.

Version tăng không tự chứng minh an toàn. Một thay đổi minor có thể phá business meaning dù API signature không đổi. Hãy phân biệt **binary compatibility, source compatibility, wire compatibility và semantic compatibility**.

## 39. Tổ chức ownership của contract và library

Một bảng ownership minh họa:

| Artifact | Owner | Consumer | Quyền thay đổi |
| --- | --- | --- | --- |
| `order-domain` | Order Team | Chỉ Order Service | Order quyết định |
| `order-events-contract` | Order Team | Shipping, Analytics, Payment | Producer owner theo compatibility policy |
| `payment-domain` | Payment Team | Chỉ Payment Service | Payment quyết định |
| `platform-observability` | Platform Team | Nhiều service | Platform quyết định API kỹ thuật |
| `currency-code` primitive | Platform/Domain Governance theo thỏa thuận | Nhiều domain | Có review chung nếu semantics thực sự chung |
| `shipping-domain` | Shipping Team | Chỉ Shipping Service | Shipping quyết định |

Contract owner phải công bố thay đổi và hỗ trợ migration. Consumer chịu trách nhiệm xử lý contract theo semantics của mình. Không yêu cầu consumer có quyền sửa implementation nội bộ producer.

## 40. Chi phí và lợi ích của duplication có kiểm soát

Duplication thường bị coi là xấu, nhưng cần phân biệt:
- **Accidental duplication:** cùng một bug hoặc thuật toán phức tạp bị copy ở nhiều nơi.
- **Intentional model duplication:** mỗi bounded context có representation riêng cho cùng một khái niệm.
- **Contract duplication:** consumer có DTO nội bộ tương ứng với contract; mapping có chủ đích.
- **Policy duplication:** cùng một business rule được copy dù cần một nguồn authoritative; có thể gây drift.

Một phép so sánh:

| Tiêu chí | Shared business model | Model riêng + contract |
| --- | --- | --- |
| Số class ban đầu | Ít hơn | Nhiều hơn |
| Coupling compile-time | Cao hơn | Thấp hơn |
| Release independence | Thường giảm | Tăng |
| Mapping code | Ít ban đầu | Có ở boundary |
| Khả năng domain evolve | Bị giới hạn bởi consumer | Mỗi context linh hoạt hơn |
| Risk semantic leakage | Cao nếu model rộng | Thấp hơn nếu contract hẹp |
| Coordination | Tập trung ở library owner | Tập trung ở contract changes |
| Runtime dependency | Có thể không có | Có thể phát sinh nếu chuyển thành API |

Duplication có chủ đích giúp domain phát triển độc lập. Tuy nhiên, nếu copy cả thuật toán thuế hoặc authorization policy mà phải thống nhất, có thể tạo sai lệch. Hãy giữ **rule authoritative** ở nơi có owner và cung cấp capability qua API/event/contract phù hợp.

## 41. Không biến contract thành “shared model phiên bản 2”

Sau khi bỏ `common-domain`, nhóm có thể tạo `global-contracts` chứa mọi DTO. Nếu contract này trở thành nơi mọi service import class lẫn nhau, anti-pattern chỉ đổi tên.

Một contract tốt:
- Chỉ chứa nội dung được công bố.
- Có producer owner.
- Có schema/version rõ.
- Không có behavior nghiệp vụ phụ thuộc context.
- Không có persistence annotations.
- Không chứa field “phòng khi cần”.
- Có compatibility test.
- Có deprecation lifecycle.
- Chỉ consumer cần mới import artifact.
- Có thể dùng schema registry/IDL thay vì Java class nếu phù hợp.

Không tạo một `UniversalCustomerDTO` chứa dữ liệu từ Profile, Order, Payment, Marketing và Shipping. Nếu consumer cần nhiều nguồn, hãy compose qua API/read model có owner rõ và data minimization.

## 42. Shared database và shared library thường khuếch đại nhau

Khi nhiều service dùng cùng entity JPA và cùng schema, coupling compile-time và data coupling tăng đồng thời.

Ví dụ:
- Order Service import `CustomerEntity` từ common JAR.
- Payment Service dùng cùng entity để đọc payment profile.
- Customer Service thay quan hệ address hoặc đổi cascade.
- Một migration làm lazy loading/serialization của consumer hỏng.
- Các service có thể vô tình ghi dữ liệu ngoài domain owner.

Giải pháp:
- Database schema có owner.
- Consumer dùng API/event hoặc read model.
- Nếu có shared database vật lý, giới hạn quyền theo schema/table.
- Không chia sẻ ORM entities.
- Migrations backward-compatible.
- Audit query cross-service.
- Tách data model nội bộ khỏi persistence representation của service khác.

Shared database không luôn phải bị loại bỏ ngay; nhưng ownership và quyền truy cập phải được ghi rõ, có lộ trình giảm coupling nếu nó cản trở deploy độc lập.

## 43. API composition và read model thay cho một object khổng lồ

Một màn hình có thể cần thông tin Customer, Order, Payment và Shipment. Không nên tạo một class `GlobalCustomerOrderPaymentShipment` làm mô hình miền chung.

Có thể:
- API composition ở backend-for-frontend.
- Read model/projection chuyên cho màn hình.
- Query service có owner và freshness contract.
- GraphQL/API gateway với schema composition nếu phù hợp.
- Consumer tự lưu projection của các event cần thiết.

Read model có thể chứa dữ liệu được tổng hợp nhưng phải phân biệt với source of truth. Cần ghi:
- Owner và nguồn dữ liệu.
- Freshness/lag objective.
- Rebuild/replay strategy.
- Data retention/privacy.
- Behavior khi một source unavailable.
- Cách sửa dữ liệu sai.

Đây là một model phục vụ query, không ép domain owners dùng chung một aggregate.

## 44. Tác động tới testing

Shared business library rộng khiến test matrix phình:
- Một thay đổi nhỏ phải chạy tests của nhiều service.
- Mock/fixture phụ thuộc class chung.
- Version mismatch chỉ lộ khi integration test.
- Consumer có thể compile nhưng business semantics sai.
- Một class có nhiều branch theo context khó test hết.

Khi tách boundary:
- Unit test invariants trong domain owner.
- Contract tests ở producer/consumer boundary.
- Integration tests cho mapping/ACL.
- Architecture tests ngăn dependency sai.
- Consumer compatibility tests cho schema/version còn tồn tại.
- End-to-end tests cho journey critical, không cần test mọi tổ hợp class.

Không thay toàn bộ test bằng contract tests. Contract test kiểm giao tiếp; domain unit test vẫn phải kiểm business rules. Chọn test theo rủi ro và semantics.

## 45. Tác động tới triển khai và vận hành

Shared library có thể khiến service phải phát hành đồng bộ:
- Một CVE trong library buộc nhiều service nâng version.
- Một breaking API buộc deploy theo thứ tự.
- Rollback khó vì service A dùng model v2, B còn v1.
- Canary không độc lập.
- Incident trace khó phân biệt service version/contract version.

Sau khi tách:
- Platform library có thể nâng theo lịch kỹ thuật.
- Contract artifact nâng theo compatibility.
- Domain implementation deploy riêng.
- Consumer adapter hỗ trợ nhiều wire versions trong deprecation window.
- Service owner chịu trách nhiệm migration của mình.

Tuy nhiên, nhiều version contract tồn tại lâu cũng tạo chi phí. Phải có deprecation policy và telemetry đo consumer versions, không để tương thích ngược kéo dài vô hạn.

## 46. Security và privacy khi model dùng chung

Một shared model thường có xu hướng gom field để phục vụ mọi consumer. Điều này có thể khiến service nhận nhiều dữ liệu hơn cần thiết.

Ví dụ `Customer` chứa email, phone, billing address, shipping address, loyalty score, marketing consent và payment token. Shipping chỉ cần recipient/address; Analytics có thể chỉ cần region và segment; Payment cần provider token reference. Gửi toàn bộ object làm tăng:
- Blast radius khi log/trace vô tình serialize object.
- Số service có thể truy cập PII.
- Khó áp dụng retention và deletion theo mục đích.
- Rủi ro cross-tenant data exposure.
- Khó audit ai cần field nào.

Áp dụng data minimization:
- Contract chỉ mang field cần thiết.
- Tokenize/pseudonymize identifier khi phù hợp.
- Không log full DTO hoặc object graph.
- Phân loại field và quyền consumer.
- Giữ secret/payment credentials trong vault/token provider.
- Có retention, deletion và audit policy.
- Không coi việc import shared JAR là quyền truy cập dữ liệu hợp lệ.

## 47. Performance và runtime implications

Shared JAR thường không tạo network hop, nhưng nó có thể:
- Kéo transitive dependencies lớn vào mọi service.
- Tăng startup time hoặc classpath complexity.
- Gây xung đột version Spring/Jackson/Hibernate.
- Ép nhiều service dùng cùng caching hoặc validation strategy.
- Làm memory footprint tăng dù service chỉ dùng một phần module.

Chuyển sang API có thể giảm compile-time coupling nhưng thêm network latency, timeout và availability dependency. Chuyển sang event có eventual consistency và broker operations. Vì vậy không nên refactor shared library bằng cách biến mọi method thành remote call.

Đánh giá theo:
- Lý do thay đổi.
- Tần suất và tính độc lập của release.
- Latency budget.
- Availability/failure behavior.
- Consistency requirement.
- Operational cost.
- Team ownership.
- Data privacy.

## 48. Quan sát coupling để biết refactor có hiệu quả

Có thể đo:
- Số service phụ thuộc vào shared business artifact.
- Số service phải rebuild/redeploy khi library đổi.
- Số breaking changes và compatibility incidents.
- Thời gian chờ review/release từ shared library owner.
- Tỷ lệ dependency vào package nội bộ domain khác.
- Số class shared có nhiều field nullable/context flags.
- Số service dùng chung persistence entity.
- Số deploy lockstep và cross-team change approvals.
- Build graph fan-out.
- Thời gian từ contract change tới consumer adoption.
- Số consumer version còn tồn tại.
- Incidents do semantic mismatch hoặc schema drift.

Không tối ưu chỉ theo số package. Một thư viện nhỏ có thể được nhiều service dùng mà không tạo coupling đáng kể; một class duy nhất `GlobalOrder` có thể gây rủi ro lớn nếu chứa toàn bộ state machine.

## 49. Kế hoạch review một shared library hiện có

Một review thực tế có thể thực hiện theo từng bước:

1. Liệt kê public classes, methods, transitive dependencies và consumer services.
2. Gắn class vào bounded context hoặc technical platform.
3. Ghi lý do thay đổi của mỗi class: business policy, contract hay runtime utility.
4. Tìm field/method chỉ được một subset consumer dùng.
5. So sánh semantics giữa consumer, đặc biệt status, money, address, identity và lifecycle.
6. Xác định class nào là DTO, entity, domain object hoặc helper.
7. Tìm dependency vào Spring/JPA/Kafka/HTTP và các side effects.
8. Đánh giá release history, version conflicts và coordinated deployments.
9. Chọn phần giữ chung, phần chuyển về domain owner và phần công bố thành contract.
10. Viết migration plan có consumer order, tests và deprecation.
11. Theo dõi sau từng bước; chỉ gỡ module cũ khi không còn consumer.
12. Cập nhật service catalog, CODEOWNERS và ownership.

Kết quả review nên là quyết định cụ thể cho từng module/package, không phải một nhãn chung “shared library xấu”.

## 50. Ví dụ quyết định cho một hệ thống thương mại điện tử

Giả định hiện có `commerce-common-domain` được dùng bởi Cart, Order, Payment, Inventory và Shipping.

| Thành phần hiện tại | Quyết định gợi ý | Lý do |
| --- | --- | --- |
| `TraceContext` helper | Chuyển sang platform observability | Cross-cutting technical concern |
| `CustomerEntity` JPA | Giữ trong Customer/Profile owner | Persistence ownership |
| `OrderStatus` | Chuyển về Order domain | State machine riêng |
| `PaymentStatus` | Chuyển về Payment domain | Authorization/capture/refund lifecycle |
| `ShipmentStatus` | Chuyển về Shipping domain | Fulfillment lifecycle |
| `CurrencyCode` primitive | Có thể giữ chung nếu semantics thống nhất | Primitive nhỏ, ít policy |
| `Money` có rounding/tax rules | Chia thành type theo context | Monetary semantics khác |
| `OrderCreatedDto` | Publish thành event contract hẹp | Consumer cần payload ổn định |
| `DiscountCalculator` | Đưa về Pricing capability | Một owner cho pricing policy |
| `RetryTemplate` wrapper | Platform resilience library | Technical mechanism |
| `CustomerAddress` universal | Chia Profile/Order/Shipping representations | Address purpose khác |
| `BaseEntity` | Đánh giá bỏ hoặc thay bằng composition | Lifecycle persistence khác |

Bảng là ví dụ phân loại, không phải lệnh refactor áp dụng nguyên trạng cho mọi hệ thống. Quyết định cuối cần dựa trên semantics và consumer thực tế.

## 51. Checklist thiết kế trước khi tạo shared library

- [ ] Xác định class phục vụ technical mechanism, transport contract hay business domain.
- [ ] Xác định bounded context và owner của semantics.
- [ ] Có bằng chứng consumer thực sự cần cùng behavior.
- [ ] Xác định lý do thay đổi và khả năng release độc lập.
- [ ] Không gom nhiều business policies chỉ vì cùng tên class.
- [ ] Không chia sẻ JPA entity hoặc repository giữa service.
- [ ] Không đưa application service/business workflow của nhiều domain vào một JAR.
- [ ] Giữ API/event contracts hẹp và có owner.
- [ ] Tách DTO khỏi domain và persistence models.
- [ ] Đặt compatibility/deprecation policy.
- [ ] Có contract tests và architecture tests.
- [ ] Đánh giá security/data minimization.
- [ ] Có release ownership, support và maintenance capacity.
- [ ] Xem xét chi phí mapping so với chi phí coupling.
- [ ] Ghi ADR cho quyết định Shared Kernel hoặc reuse cross-context.

## 52. Checklist refactor shared model hiện có

- [ ] Inventory tất cả consumer và version đang triển khai.
- [ ] Gắn từng class với domain owner hoặc platform owner.
- [ ] Xác định semantics khác nhau giữa các context.
- [ ] Chỉ định source of truth cho mỗi business concept.
- [ ] Thiết kế contract/API/event cần công bố.
- [ ] Tạo model riêng trong consumer và mapper/ACL.
- [ ] Bổ sung contract/compatibility tests.
- [ ] Di chuyển từng consumer theo thứ tự có kiểm soát.
- [ ] Giữ tương thích trong giai đoạn version cũ/mới cùng chạy.
- [ ] Kiểm tra schema, database và message replay.
- [ ] Theo dõi build/deploy coupling và runtime errors.
- [ ] Gỡ dependency cũ sau khi không còn references.
- [ ] Cập nhật catalog, CODEOWNERS, docs và ownership.
- [ ] Đo lại fan-out, lead time và số coordinated releases.
- [ ] Có owner/deadline cho phần legacy còn tồn tại.

## 53. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `common-domain` chứa mọi entity | Mọi domain bị nối compile-time | Domain model riêng theo bounded context |
| Một enum `Status` cho toàn hệ thống | Mất semantics và khó thêm trạng thái | Enum riêng, map qua contract |
| Shared JPA entities | Schema và transaction coupling | Persistence ownership theo service |
| Universal Customer/Address | Field dư thừa và rò dữ liệu | Context-specific representations |
| Business calculator dùng chung | Rule thay đổi kéo nhiều domain | Một owner authoritative, API nếu cần |
| DTO dùng làm domain entity | Contract và business logic lẫn nhau | Tách transport/domain/persistence |
| Shared library có nhiều Spring beans | Runtime/version coupling | Platform library hẹp hoặc module nội bộ |
| Global contracts chứa mọi model | Anti-pattern chuyển sang schema chung | Contract theo capability/event |
| Shared Kernel không có governance | Release coordination kéo dài | Phạm vi nhỏ, owner và policy rõ |
| Copy mọi business rule | Kết quả nghiệp vụ drift | API/capability authoritative |
| Chuyển mọi class thành HTTP API | Network coupling và latency | Chỉ expose domain capability có ý nghĩa |
| Giữ adapter legacy vô thời hạn | Hai mô hình cùng tồn tại, khó gỡ | Deadline, metrics và deprecation |
| Version bump nhưng không contract test | Consumer runtime hỏng | Compatibility gate |
| Chia sẻ cả PII trong model | Tăng blast radius | Data minimization và field-specific contracts |

## 54. Câu hỏi thường gặp

**Dùng chung domain model có luôn sai trong microservices không?**

Không. Shared Kernel nhỏ có thể hợp lý nếu semantics thật sự giống nhau, ít thay đổi, có owner và cơ chế phối hợp. Vấn đề là chia sẻ quá rộng khiến nhiều bounded context phải thay đổi cùng nhau.

**Hai service cùng dùng `Money` thì có nên tạo một class chung?**

Chỉ khi precision, scale, rounding, validation và meaning giống nhau. Nếu Order chốt giá, Payment capture và Finance settlement có quy tắc khác, hãy dùng type riêng dù cùng dựa trên `BigDecimal` và currency code.

**Có nên copy một value object đơn giản sang service khác?**

Có thể. Copy có chủ đích giúp context sở hữu semantics riêng. Cần tránh copy một thuật toán nghiệp vụ phức tạp mà doanh nghiệp yêu cầu một nguồn tính toán authoritative.

**Shared Kernel khác `common-domain` thế nào?**

Shared Kernel là một phần nhỏ được các context cùng đồng thuận, có governance và thay đổi phối hợp. `common-domain` quá rộng thường gom nhiều model khác nhau mà không có ranh giới ownership/semantics.

**Có thể chia sẻ generated API client không?**

Có, nếu artifact chỉ chứa transport client/DTO theo contract được công bố, có version và compatibility. Không kéo domain entities hoặc repository nội bộ của producer vào consumer.

**Dùng event contract có loại bỏ coupling không?**

Không. Nó chuyển coupling sang wire contract và thời điểm xử lý. Cần schema compatibility, consumer idempotency, replay strategy và ownership rõ. Nhưng consumer không cần import domain implementation của producer.

**Tại sao cần anti-corruption layer nếu phải viết thêm mapper?**

Mapper bảo vệ domain consumer khỏi semantics và thay đổi của upstream. Chi phí mapping có thể nhỏ hơn việc để một thay đổi trong Order làm Shipping phải thay model nội bộ.

**Có nên tách database ngay khi tách domain model?**

Không nhất thiết. Có thể tách code/contract trước rồi chuyển persistence từng bước. Nhưng phải xác định schema owner và giới hạn quyền đọc/ghi; shared database không nên trở thành quyền sở hữu mơ hồ.

**Nếu các service nằm trong cùng một team thì dùng chung model có ổn hơn không?**

Cùng team giảm chi phí phối hợp nhưng không làm các business lifecycle giống nhau. Các service vẫn có thể deploy độc lập, chạy nhiều version và có failure boundary khác nhau. Hãy chia sẻ theo semantics, không chỉ theo sơ đồ tổ chức.

**Có nên dùng một thư viện `common-kernel` cho các primitive?**

Có thể, nếu phạm vi hẹp và có lý do thay đổi chung. Không để nó dần chứa status, entity, business rules, repository và workflow. Khi thư viện tăng nhanh, review lại bounded context và ownership.

**Làm sao biết nên dùng copy hay API?**

Nếu logic nhỏ, thuần, ổn định và không có owner authoritative riêng, copy một type nhỏ có thể đơn giản hơn. Nếu cần một capability nghiệp vụ có state/rule authoritative, API hoặc event contract phù hợp hơn. Đánh giá latency, availability, consistency và vận hành.

**Có thể giữ shared library cũ trong lúc migration không?**

Có. Giữ adapter tương thích, chuyển consumer từng bước và đo references. Đặt owner, deadline và điều kiện xóa; tránh để legacy module trở thành dependency mặc định mãi mãi.

**Có cần xóa mọi class `common` khỏi monorepo?**

Không. Tên folder không quyết định chất lượng boundary. Một module kỹ thuật nhỏ, một contract được công bố hoặc utility ổn định có thể hợp lý. Hãy xem nội dung, semantics, dependency direction và owner.

**Làm sao ngăn team mới tạo lại anti-pattern?**

Có architecture rules trong CI, template service, service catalog, contract testing và review câu hỏi “ai sở hữu semantics?”. Đồng thời cung cấp golden paths để team không phải tạo shared JAR chỉ vì thiếu tooling.

---

**Nguyên lý ghi nhớ:** *Mỗi bounded context cần sở hữu mô hình và quy tắc nghiệp vụ phản ánh ngôn ngữ, invariants và vòng đời của chính nó. Chia sẻ primitive kỹ thuật hoặc contract hẹp khi semantics thật sự thống nhất; dùng API, event và anti-corruption layer để giao tiếp giữa domain. Một ít mapping hoặc duplication có chủ đích thường rẻ hơn việc buộc nhiều service phát triển và phát hành cùng một mô hình nghiệp vụ quá rộng.*