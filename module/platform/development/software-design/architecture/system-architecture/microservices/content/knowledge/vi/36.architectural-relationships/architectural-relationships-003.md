# Microservices với DDD trong thiết kế ranh giới nghiệp vụ

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Quan hệ kiến trúc.  
> **Mục tiêu:** sử dụng Domain-Driven Design (DDD) để tìm ranh giới microservice dựa trên nghiệp vụ; phân biệt subdomain, bounded context, aggregate và service boundary; thiết kế ubiquitous language, context map, integration contracts và ownership dữ liệu; nhận diện các cách chia service sai khiến hệ thống trở thành distributed monolith.

## 1. Bài toán: chia service theo bảng dữ liệu chưa tạo ra ranh giới nghiệp vụ

Một nền tảng thương mại điện tử có các bảng Customer, Order, OrderItem, Payment, Inventory, Shipment và Product. Nhóm phát triển tách mỗi nhóm bảng thành một service:

- Customer Service sở hữu bảng Customer.
- Order Service sở hữu Order và OrderItem.
- Payment Service sở hữu Payment.
- Inventory Service sở hữu Inventory.
- Shipping Service sở hữu Shipment.
- Product Service sở hữu Product.

Sơ đồ ban đầu trông có vẻ hợp lý, nhưng các câu hỏi nghiệp vụ nhanh chóng làm lộ vấn đề:

- Order Service cần đọc và cập nhật Customer address trực tiếp để xác nhận đơn.
- Payment Service import OrderEntity để kiểm tra trạng thái.
- Inventory Service phải tham gia transaction cùng Order để giữ hàng.
- Shipping Service cập nhật trực tiếp Order.status khi tạo vận đơn.
- Một thay đổi nhỏ ở Customer schema buộc nhiều service cùng release.
- Các service dùng chung enum OrderStatus nhưng mỗi nơi hiểu trạng thái khác nhau.

Hệ thống có nhiều process và deployment, nhưng quyền sở hữu nghiệp vụ vẫn bị chia sẻ. Một thay đổi ở một domain lan sang các nhóm khác; transaction xuyên database và shared model làm giảm khả năng triển khai độc lập.

**Domain-Driven Design (DDD)** cung cấp cách suy nghĩ để xác định ranh giới theo mô hình và ngôn ngữ nghiệp vụ. Mục tiêu là tìm những vùng mà một nhóm có thể sở hữu quy tắc, dữ liệu và vòng đời thay đổi một cách nhất quán.

DDD không phải công thức tự động biến mỗi bounded context thành một microservice. Nó giúp hiểu domain trước, rồi mới quyết định cách triển khai.

## 2. DDD là gì?

**Domain-Driven Design** là cách tiếp cận phát triển phần mềm đặt domain nghiệp vụ làm trung tâm. Nhóm kỹ thuật và chuyên gia nghiệp vụ cùng xây dựng mô hình phản ánh cách doanh nghiệp vận hành, dùng ngôn ngữ chung và điều chỉnh mô hình khi hiểu biết thay đổi.

DDD thường được trình bày qua hai nhóm:

- **Strategic design:** hiểu domain, chia subdomain, xác định bounded context, quan hệ giữa context và ownership.
- **Tactical design:** xây dựng entity, value object, aggregate, repository, domain service, domain event và application service bên trong một context.

Trong thiết kế microservices, strategic design đặc biệt quan trọng vì nó giúp tìm service boundary. Tactical patterns giúp giữ các invariant bên trong boundary đó.

Không nên bắt đầu bằng việc chọn framework, số lượng container hoặc số database. Bắt đầu bằng câu hỏi: **nghiệp vụ nào có mô hình, quy tắc và ngôn ngữ riêng?**

## 3. Domain, subdomain và bounded context

Ba khái niệm liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ thương mại điện tử |
| --- | --- | --- |
| **Domain** | Toàn bộ lĩnh vực nghiệp vụ mà hệ thống phục vụ | Bán hàng trực tuyến |
| **Subdomain** | Một phần bài toán nghiệp vụ có mục tiêu và quy tắc riêng | Catalog, Order, Payment, Inventory |
| **Bounded Context** | Ranh giới nơi một model và ubiquitous language có ý nghĩa nhất quán | Context Fulfillment dùng mô hình shipment riêng |
| **Microservice** | Đơn vị triển khai và vận hành phần mềm | Shipping Service |
| **Aggregate** | Nhóm đối tượng được quản lý như một đơn vị consistency trong domain model | Shipment aggregate |

Một subdomain là khái niệm phân tích nghiệp vụ. Bounded context là ranh giới mô hình và ngôn ngữ. Microservice là lựa chọn triển khai. Chúng thường được ánh xạ gần nhau, nhưng không bắt buộc quan hệ một-một.

Một bounded context có thể được triển khai bằng modular monolith trước, sau đó tách thành service khi có nhu cầu độc lập. Ngược lại, một microservice đôi khi phục vụ nhiều context rất nhỏ nếu chúng có cùng ownership và lifecycle; cần xem xét kỹ trước khi gộp.

## 4. Phân loại subdomain

DDD thường phân biệt:

### 4.1. Core domain

Đây là năng lực tạo lợi thế cạnh tranh và có ảnh hưởng trực tiếp tới chiến lược kinh doanh.

Ví dụ:

- Thuật toán định giá hoặc khuyến mãi độc quyền.
- Quy tắc phân bổ hàng theo mạng lưới kho.
- Cách tối ưu trải nghiệm mua hàng và fulfillment.

Core domain cần đầu tư mô hình và đội ngũ hiểu sâu. Không nên đưa toàn bộ quy tắc tạo lợi thế vào một shared library generic.

### 4.2. Supporting subdomain

Năng lực cần cho doanh nghiệp nhưng không phải điểm khác biệt chính.

Ví dụ:

- Quản lý yêu cầu hoàn trả theo policy.
- Điều phối thông báo.
- Quy trình quản trị catalog nội bộ.

Có thể xây dựng nội bộ hoặc dùng sản phẩm phù hợp, tùy độ đặc thù và chi phí.

### 4.3. Generic subdomain

Năng lực phổ biến, có thể mua hoặc dùng giải pháp chuẩn nếu phù hợp.

Ví dụ:

- Xác thực danh tính.
- Gửi email/SMS thông dụng.
- Lưu trữ file cơ bản.
- Một số chức năng lập lịch hoặc audit chuẩn.

Phân loại này giúp ưu tiên đầu tư. Nó không phải bảng xếp hạng giá trị của service; một generic subdomain vẫn có thể rất quan trọng về availability hoặc security.

## 5. Bounded Context: ranh giới của mô hình và ngôn ngữ

Một bounded context xác định nơi mô hình domain có nghĩa nhất quán. Cùng một từ có thể mang ý nghĩa khác nhau ở các context:

| Từ | Sales Context | Warehouse Context | Finance Context |
| --- | --- | --- | --- |
| Product | Sản phẩm khách hàng chọn mua | SKU và đơn vị lưu kho | Mặt hàng trên chứng từ |
| Order | Cam kết bán hàng | Yêu cầu picking | Cơ sở ghi nhận doanh thu |
| Customer | Người mua và trải nghiệm | Người nhận hàng | Bên thanh toán/công nợ |
| Available | Có thể bán theo chính sách | Tồn có thể cấp phát | Số lượng được ghi nhận theo kỳ |

Nếu ép mọi context dùng một class Product chung, một context có thể phải chứa field không có ý nghĩa hoặc phụ thuộc vào logic của context khác.

**Bounded context không chỉ là package namespace.** Nó cần ownership, model, rules, language và integration boundary được xác định.

## 6. Ubiquitous Language: một ngôn ngữ chung trong từng context

**Ubiquitous Language** là ngôn ngữ mà domain experts và developers cùng dùng trong một bounded context, thể hiện nhất quán trong thảo luận, tài liệu, code và tests.

Ví dụ trong Order Context:

- PlaceOrder
- ConfirmOrder
- CancelOrder
- OrderLine
- OrderTotal
- OrderConfirmed

Trong Payment Context:

- AuthorizePayment
- CapturePayment
- RefundPayment
- PaymentAttempt
- Settlement
- Chargeback

Không cần mọi context dùng cùng một từ hoặc cùng một class. Cần đảm bảo **mỗi context có ngôn ngữ rõ**, còn khi giao tiếp giữa context thì contract giải thích ý nghĩa và mapping.

Một dấu hiệu model yếu là nhóm phát triển liên tục hỏi “status này nghĩa là gì?” hoặc dùng một enum có giá trị không được mọi consumer hiểu giống nhau.

### 6.1. Ngôn ngữ trong code

Tên class, method, event và test nên phản ánh nghiệp vụ:

~~~java
public final class Order {
    public void confirm(ConfirmationPolicy policy) {
        if (!policy.canConfirm(this)) {
            throw new OrderCannotBeConfirmedException(id);
        }
        this.status = OrderStatus.CONFIRMED;
    }
}
~~~

Đây là ví dụ minh họa. Trong model thật, policy có thể thuộc aggregate hoặc domain service tùy quy tắc. Điểm chính là method nói về hành vi nghiệp vụ thay vì chỉ cung cấp setter để bên ngoài tùy ý đổi trạng thái.

## 7. Tìm boundary qua capability và business workflow

Một cách thực tế để khám phá context là phân tích business capability và workflow.

Ví dụ workflow mua hàng:

~~~mermaid
flowchart LR
  B[Browse catalog] --> C[Place order]
  C --> I[Reserve inventory]
  I --> P[Authorize payment]
  P --> O[Confirm order]
  O --> S[Create shipment]
  S --> D[Deliver]
~~~

Sơ đồ thể hiện chuỗi nghiệp vụ, không nhất thiết là một distributed transaction. Mỗi bước có owner và có thể trao đổi bằng command/event.

Hãy hỏi:

- Ai quyết định một đơn đủ điều kiện xác nhận?
- Ai sở hữu số lượng tồn và reservation?
- Ai quyết định payment được capture/refund?
- Ai sở hữu shipment và trạng thái giao?
- Quy tắc nào thay đổi cùng nhau?
- Những team nào cần phối hợp để thay đổi một feature?
- Dữ liệu nào phải nhất quán ngay lập tức?
- Dữ liệu nào có thể cập nhật bất đồng bộ?

Boundary tốt thường bao quanh một nhóm quy tắc thay đổi cùng nhau và có thể thực thi invariant nội bộ.

## 8. Không chia service theo danh từ hoặc bảng

Các cách chia thường gây vấn đề:

- Một service cho mỗi table.
- Một service cho mỗi entity.
- Một service cho mỗi CRUD endpoint.
- Một service cho mỗi team mà không xét workflow.
- Một service cho mỗi bounded context nhỏ đến mức không tự có ý nghĩa.
- Gộp mọi thứ vào Common Service vì các nhóm cùng dùng một class.

Ví dụ tách OrderHeader Service và OrderItem Service thường không tạo hai capability độc lập. Mỗi lần thêm/xóa line item có thể cần kiểm tra tổng tiền, discount, shipping và trạng thái order; hai service phải phối hợp thường xuyên.

Ngược lại, Payment thường có security, ledger, idempotency, external provider integration và lifecycle riêng. Nó có lý do nghiệp vụ để sở hữu boundary riêng.

**Một bảng không phải một service boundary.** Hãy xem ai sở hữu invariant và ai có quyền thay đổi dữ liệu.

## 9. Context map: mô tả quan hệ giữa bounded contexts

Context map là bản đồ thể hiện cách các bounded contexts phụ thuộc và hợp tác.

Các quan hệ phổ biến trong DDD gồm:

- **Partnership:** hai nhóm phụ thuộc và phối hợp chặt, cùng điều chỉnh model.
- **Shared Kernel:** một phần model nhỏ được nhiều context đồng sở hữu.
- **Customer–Supplier:** upstream cung cấp model/contract, downstream tiêu thụ.
- **Conformist:** downstream chấp nhận model upstream mà ít khả năng ảnh hưởng.
- **Anti-Corruption Layer (ACL):** downstream chuyển đổi model bên ngoài thành model nội bộ.
- **Open Host Service:** upstream cung cấp một protocol/interface ổn định cho nhiều consumer.
- **Published Language:** schema/contract công khai dùng để giao tiếp.
- **Separate Ways:** hai context không cần tích hợp trực tiếp.

Các tên quan hệ này mô tả organizational/semantic relationship; chúng không bắt buộc phải dùng một công nghệ cụ thể.

### 9.1. Ví dụ context map

~~~mermaid
flowchart LR
  C[Catalog Context] -->|Published API| S[Sales Context]
  S -->|OrderPlaced event| I[Inventory Context]
  S -->|Payment request| P[Payment Context]
  P -->|Payment result| S
  I -->|Reservation result| S
  S -->|OrderConfirmed event| F[Fulfillment Context]
  EXT[External tax provider] -->|ACL| S
~~~

Sales có thể là upstream của một số event nhưng downstream của Catalog. Quan hệ không nhất thiết là một chiều cố định cho cả hệ thống; cần ghi rõ theo từng contract.

## 10. Customer–Supplier và Open Host Service

Trong quan hệ Customer–Supplier, nhóm upstream cung cấp API/schema, còn nhóm downstream cần nó. Downstream có thể truyền yêu cầu contract, nhưng upstream vẫn sở hữu model và lịch phát hành.

**Open Host Service** là giao diện ổn định được upstream thiết kế để nhiều consumer sử dụng, thay vì buộc từng consumer truy cập database hoặc internal classes.

Ví dụ Catalog cung cấp:

- GET product summary.
- GET price display data theo currency/region.
- ProductUpdated event theo schema version.

Order không truy cập bảng Catalog trực tiếp. Nếu cần dữ liệu snapshot tại thời điểm mua, Order có thể lưu các field cần thiết trong order line theo contract của nghiệp vụ.

Điều này giảm runtime/build coupling vào storage nội bộ của Catalog.

## 11. Anti-Corruption Layer: bảo vệ model của downstream

Khi tích hợp legacy hoặc một provider có model khác, ACL chuyển đổi dữ liệu và hành vi:

~~~text
Legacy ERP API
      |
      v
ACL adapter
      |
      v
Order domain model
~~~

Ví dụ ERP dùng status A, B, X; Order dùng CREATED, CONFIRMED, CANCELLED. ACL chịu trách nhiệm mapping và xử lý trạng thái không biết.

ACL giúp:

- Tránh model legacy lan vào domain mới.
- Cô lập protocol/auth/serialization của provider.
- Có thể thay provider mà ít ảnh hưởng domain.
- Viết tests cho mapping và lỗi.
- Bảo vệ semantics khi upstream đổi field.

ACL không nên biến thành một lớp chứa toàn bộ business logic của downstream. Quy tắc thuộc Order vẫn nên ở Order.

## 12. Shared Kernel: dùng khi ownership chung thật sự

Shared Kernel là phần model/code nhỏ được hai context cùng quản lý. Ví dụ hai context có thể chia sẻ một value object ổn định về **PostalCode** nếu semantics thực sự giống nhau.

Nhưng cần:

- Phạm vi nhỏ và được liệt kê rõ.
- Owner/decision process chung.
- Compatibility tests cho tất cả consumer.
- Lịch phát hành và deprecation.
- Không đưa entity/repository toàn hệ thống vào kernel.

Nếu hai nhóm không có cách phối hợp thay đổi, Shared Kernel dễ trở thành một common library làm mọi nhóm bị khóa cùng version.

Không phải mọi type giống tên đều có cùng semantics. Một CustomerId trong Sales có thể không tương đương AccountId trong Finance.

## 13. Aggregate: ranh giới consistency bên trong context

**Aggregate** là nhóm entity/value object được quản lý như một đơn vị consistency. Một aggregate có root để bảo vệ invariant và điều phối thay đổi nội bộ.

Ví dụ Order aggregate:

~~~text
Order (Aggregate Root)
  - orderId
  - customerReference
  - status
  - lineItems[]
  - shippingAddressSnapshot
  - total
~~~

Order root có thể bảo vệ:

- Không thêm line item khi order đã cancelled.
- Số lượng mỗi line phải hợp lệ.
- Tổng tiền được tính theo policy.
- Chỉ cho phép transition trạng thái hợp lệ.

Các thao tác qua aggregate root giúp không để caller thay đổi entity con tùy ý và phá invariant.

### 13.1. Aggregate không đồng nghĩa database table

Một aggregate có thể trải qua nhiều tables; một table có thể lưu field của aggregate. Ranh giới được xác định bởi consistency requirement và domain behavior, không phải cách ORM mapping.

### 13.2. Aggregate nhỏ và transaction ngắn

Aggregate quá lớn làm mọi thay đổi tranh chấp lock và transaction. Aggregate quá nhỏ có thể khiến invariant xuyên aggregate khó bảo vệ.

Một nguyên tắc thường hữu ích: **một transaction cập nhật một aggregate**; nếu cần thay đổi nhiều aggregate/service, cân nhắc domain event, saga hoặc quy trình eventual consistency thay vì mở transaction xuyên mọi database.

Đây là guideline, không phải luật tuyệt đối. Cần dựa vào invariant và khả năng của persistence.

## 14. Entity và Value Object

**Entity** có identity và lifecycle. Hai entity có cùng thuộc tính nhưng ID khác vẫn là hai đối tượng khác nhau.

**Value Object** được xác định bởi giá trị, thường immutable và không có identity riêng.

Ví dụ:

~~~java
public record Money(
    long amountMinor,
    String currency
) {
    public Money {
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("currency is required");
        }
        if (amountMinor < 0) {
            throw new IllegalArgumentException("amount cannot be negative");
        }
    }
}
~~~

Đây là ví dụ đơn giản; domain thật phải xử lý refund/negative amounts, currency scale, overflow và rounding theo nghiệp vụ.

Một Order là entity; Money, AddressSnapshot hoặc Quantity có thể là value objects. Không nên biến mọi object thành JPA entity chỉ vì cần persist.

## 15. Domain Service và Application Service

Hai loại service thường bị nhầm:

- **Domain Service:** chứa quy tắc nghiệp vụ không tự nhiên thuộc một entity/aggregate cụ thể.
- **Application Service:** điều phối use case, transaction, authorization context, repository và external ports.

Ví dụ:

~~~java
public final class PlaceOrderHandler {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final PaymentPort payments;

    public PlaceOrderHandler(
            OrderRepository orders,
            InventoryPort inventory,
            PaymentPort payments
    ) {
        this.orders = orders;
        this.inventory = inventory;
        this.payments = payments;
    }

    public OrderResult handle(PlaceOrderCommand command) {
        // Điều phối use case; production cần transaction,
        // idempotency, retry và workflow policy rõ ràng.
        return OrderResult.pending(command.orderId());
    }
}
~~~

Đây là skeleton, không phải implementation đầy đủ. Application service điều phối; aggregate/domain service bảo vệ quy tắc nội bộ. Không đẩy toàn bộ logic vào controller hoặc application service rồi gọi đó là DDD.

## 16. Repository thuộc về aggregate/domain

Repository cung cấp abstraction để domain/application làm việc với aggregate persistence:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Implementation có thể dùng JPA, JDBC hoặc document database. Domain không cần import Hibernate annotations hoặc entity của Payment.

Một repository thường nên tập trung vào aggregate root; không tạo repository chung cho mọi bảng chỉ để có CRUD endpoint.

Với read-heavy queries, có thể dùng query model/projection riêng thay vì ép mọi query đi qua aggregate repository. Command model và read model có thể khác nhau nếu contract rõ.

## 17. Domain Event: thông báo điều đã xảy ra

Domain event biểu diễn một sự kiện có ý nghĩa trong domain, thường ở quá khứ:

- OrderPlaced
- OrderConfirmed
- PaymentCaptured
- StockReserved
- ShipmentDispatched

Ví dụ:

~~~java
public record OrderPlaced(
    String eventId,
    String orderId,
    String customerId,
    long occurredAtEpochMillis
) {}
~~~

Một domain event thường được tạo bởi aggregate/use case. Khi publish ra ngoài context, cần định nghĩa integration event contract. Hai khái niệm liên quan nhưng không bắt buộc giống nhau; integration event có thể là schema được thiết kế để consumer không phụ thuộc internal model.

### 17.1. Domain event và integration event

- **Domain event:** mô tả thay đổi trong domain model nội bộ.
- **Integration event:** thông điệp public gửi sang bounded context khác.

Integration event cần versioning, ownership, schema compatibility, event ID, timestamp/sequence và quy tắc duplicate/order phù hợp.

Không phát toàn bộ object aggregate thành event. Điều đó làm lộ internal model và khiến consumer phụ thuộc sâu.

## 18. Context boundary và microservice boundary

Một bounded context có thể được triển khai thành một service khi:

- Có ownership team rõ.
- Có model và language riêng.
- Có lifecycle thay đổi đủ độc lập.
- Có data ownership.
- Có API/event contract ổn định.
- Có lý do vận hành để deploy/scale/isolate riêng.

Có thể giữ nhiều bounded contexts trong modular monolith khi:

- Chưa có nhu cầu scale/deploy độc lập.
- Team còn nhỏ.
- Giao dịch nghiệp vụ cần consistency cục bộ.
- Chi phí vận hành distributed system lớn hơn lợi ích tách service.

**DDD không yêu cầu phải có nhiều microservices.** Một modular monolith có module boundary tốt thường là bước trung gian hiệu quả và có thể tách sau.

## 19. Một bounded context có luôn bằng một microservice?

Không nhất thiết.

### 1:1

Một context được triển khai bằng một service. Đây là mapping dễ hiểu khi ownership và lifecycle rõ.

### 1:N

Một context lớn có thể được triển khai thành nhiều process/service vì yêu cầu scale, isolation hoặc team ownership, nhưng phải giữ model và authority nhất quán. Ví dụ read/query component có thể tách khỏi write model.

### N:1

Một deployment có thể chứa nhiều context nhỏ trong modular monolith hoặc một service khi chúng có lifecycle và ownership gần nhau. Cần giữ module boundaries để tránh shared database logic tràn lan.

Đừng dùng số service làm thước đo maturity. Đo bằng khả năng thay đổi, reliability, ownership và mức coupling.

## 20. Data ownership: service sở hữu dữ liệu của mình

Một service nên là authority cho dữ liệu domain mà nó sở hữu. Consumer truy cập qua API, event hoặc read model được cung cấp có chủ đích.

Ví dụ:

- Order sở hữu order state và snapshot thông tin mua hàng.
- Payment sở hữu payment attempt, capture/refund status và ledger references.
- Inventory sở hữu stock/reservation/movement.
- Shipping sở hữu shipment/tracking.

Không để Order update trực tiếp Payment table hoặc Shipping sửa Order row. Hãy gửi command/request hoặc phát event và để owner thực thi invariant.

### 20.1. Database-per-service không nhất thiết là server riêng

Mỗi service có thể dùng database/schema/collection riêng trên cùng hạ tầng managed, nếu quyền truy cập và ownership được tách rõ. Điều quan trọng là service khác không phụ thuộc vào cấu trúc nội bộ hoặc tự ghi dữ liệu của owner.

Nếu shared DB server gây contention hoặc failure domain chung, đó là vấn đề vận hành cần đánh giá riêng.

## 21. Cross-context workflow: đừng mở transaction toàn hệ thống

Đặt hàng có thể cần Order, Inventory và Payment. Một transaction ACID xuyên ba service/database thường tạo coupling và khó vận hành.

Có thể dùng **Saga**:

~~~mermaid
flowchart LR
  O[Create pending order] --> I[Reserve inventory]
  I --> P[Authorize payment]
  P --> C[Confirm order]
  P -. failure .-> RI[Release inventory]
  I -. failure .-> CO[Cancel pending order]
  C --> E[Emit OrderConfirmed]
~~~

Nếu Payment thất bại, workflow có thể release inventory và cancel pending order. Đây là **compensation**, không phải rollback vật lý một transaction toàn cục.

Cần định nghĩa timeout, retry, idempotency, state machine, compensation failure và manual recovery. Một saga có thể chạy dài hơn HTTP request ban đầu.

## 22. Orchestration và choreography

**Orchestration:** một coordinator điều phối các bước và lưu workflow state.

Ưu điểm: flow dễ quan sát, logic timeout/compensation tập trung. Nhược điểm: coordinator có thể trở thành nơi chứa quá nhiều domain logic hoặc điểm nghẽn.

**Choreography:** services phản ứng với events và phát events tiếp theo.

Ưu điểm: ít coordinator trung tâm, mỗi context phản ứng với event của nó. Nhược điểm: flow phân tán, khó nhìn toàn bộ và dễ tạo event chain phức tạp.

Chọn theo workflow:

- Nhiều bước, compensation rõ và cần theo dõi trạng thái: orchestration có thể phù hợp.
- Phản ứng đơn giản với domain events: choreography có thể phù hợp.
- Tránh để một event dẫn đến chuỗi 15 service khó debug mà không có workflow visibility.

Dù chọn cách nào, mỗi context vẫn sở hữu state và invariant của mình.

## 23. Integration patterns giữa bounded contexts

| Pattern | Dùng khi | Lưu ý |
| --- | --- | --- |
| Synchronous API | Cần kết quả ngay hoặc query theo nhu cầu | Timeout, availability, coupling runtime |
| Command | Yêu cầu owner thực hiện một hành động | Idempotency và outcome |
| Domain/integration event | Thông báo thay đổi bất đồng bộ | Duplicate, ordering, schema evolution |
| Published Language | Nhiều consumer cần contract ổn định | Version và governance |
| ACL | Model upstream/legacy khác domain nội bộ | Mapping và ownership |
| Shared Kernel | Một model nhỏ được đồng sở hữu | Coordination và release coupling |
| Read model/projection | Consumer cần query dữ liệu tổng hợp | Eventual consistency và freshness |
| Separate Ways | Không cần integration trực tiếp | Chấp nhận dữ liệu riêng |

Không chọn event-driven chỉ vì muốn giảm HTTP calls. Nếu client cần biết ngay reservation thành công hay không, synchronous request có thể phù hợp; nếu workflow dài, asynchronous process có thể tốt hơn.

## 24. Thiết kế contract từ domain, không từ ORM

Một API public nên thể hiện use case:

~~~http
POST /orders/ORD-100/confirmation
Content-Type: application/json

{
  "confirmationReason": "PAYMENT_AUTHORIZED"
}
~~~

Response:

~~~json
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "version": 7
}
~~~

Contract không nên để client gửi mọi field nội bộ của OrderEntity rồi server copy thẳng vào database. Owner phải quyết định field nào được sửa và transition nào hợp lệ.

Một contract tốt:

- Dùng terms của bounded context.
- Có validation/error semantics.
- Có idempotency cho command thích hợp.
- Có concurrency/version strategy nếu cần.
- Có backward compatibility.
- Không lộ persistence details.

## 25. Model boundary và versioning

Một public contract có thể evolve theo hướng additive:

- Thêm optional field.
- Thêm endpoint mới.
- Thêm event type mới có consumer fallback rõ.
- Deprecate field cũ trước khi xóa.
- Giữ enum evolution an toàn.

Breaking changes cần version/migration strategy. Nhưng version hóa API không sửa được model boundary sai. Nếu consumer phải biết toàn bộ internal entity của provider, hai service vẫn ghép chặt dù có /v2.

Một số client parser có thể fail khi nhận enum value chưa biết; cần test tolerant/strict policy. Với event consumers, unknown event phải được xử lý có chủ đích, không silently drop event quan trọng.

## 26. Ownership trong team và Conway's Law

Kiến trúc thường phản ánh cấu trúc giao tiếp của tổ chức. Nếu ba team cùng sửa một database/model, ranh giới service có thể không phản ánh ownership thật.

DDD giúp đặt câu hỏi:

- Ai là domain expert?
- Ai chịu trách nhiệm business rule?
- Ai trực on-call khi dữ liệu sai?
- Ai phê duyệt thay đổi contract?
- Ai sở hữu migration và incident?
- Ai quyết định deprecation?

Một service boundary tốt nên có một team có thể đưa ra quyết định và chịu trách nhiệm end-to-end. Có thể có shared platform team, nhưng platform nên cung cấp capabilities chung, không nắm mọi domain rules.

## 27. Context map và tổ chức thay đổi

Context map nên được duy trì như tài liệu sống:

- Context name và owner.
- Mô hình/terms chính.
- Upstream/downstream.
- API/event contracts.
- Data ownership.
- Consistency expectation.
- Team và escalation.
- Known coupling và migration plan.

Khi một service cần thay đổi contract, map giúp xác định consumer bị ảnh hưởng và lịch tương thích. Không nhất thiết vẽ sơ đồ lớn cho mọi class; tập trung vào boundary và dependency quan trọng.

Một context map lỗi thời có thể nguy hiểm như không có map: nhóm tưởng mình sở hữu dữ liệu nhưng thực tế một batch job khác vẫn ghi trực tiếp.

## 28. Cách khám phá bounded context trong workshop

Một workshop thực tế có thể theo trình tự:

1. Chọn một business capability hoặc workflow.
2. Mời domain experts, operators và developers.
3. Liệt kê commands, events, policies, rules và states.
4. Đặt tên theo ubiquitous language.
5. Đánh dấu nơi một từ đổi nghĩa.
6. Xác định invariant cần consistency ngay.
7. Xác định dữ liệu/logic owner.
8. Vẽ context map và integration points.
9. Ghi những phần chưa chắc chắn.
10. Thử boundary bằng một thay đổi nghiệp vụ thật: team nào cần sửa, deploy nào cần phối hợp?
11. Xem xét modular monolith hay service deployment.
12. Chốt ownership và đo coupling sau khi triển khai.

Event Storming là một kỹ thuật workshop hữu ích: người tham gia đặt domain events theo timeline, sau đó xác định commands, policies, aggregates, external systems và bounded contexts. Nó là công cụ khám phá, không tự tạo ra kiến trúc đúng nếu thiếu domain expertise.

## 29. Event Storming: ví dụ đặt hàng

Một đoạn event flow:

~~~text
ProductViewed
AddToCartRequested
CartItemAdded
CheckoutStarted
OrderPlaced
InventoryReservationRequested
InventoryReserved
PaymentAuthorizationRequested
PaymentAuthorized
OrderConfirmed
ShipmentRequested
ShipmentCreated
~~~

Các câu hỏi:

- Command nào có thể bị từ chối?
- Event nào chỉ phát khi transaction commit?
- Ai phát và ai sở hữu event?
- Có policy tự động phản ứng với event không?
- Những event nào là integration contracts?
- Bước nào cần compensation?
- Aggregate nào bảo vệ invariant?
- Những state nào có thể eventual consistent?

Khi workshop phát hiện một event có hai cách hiểu, hãy quay lại ngôn ngữ và ownership. Đừng chỉ đổi tên topic rồi bỏ qua bất đồng semantics.

## 30. Ví dụ thiết kế Order Context

Order Context có thể sở hữu:

- Order aggregate.
- OrderLine value/entity model.
- Order state machine.
- Pricing snapshot tại thời điểm đặt hàng theo policy.
- Shipping address snapshot cần cho đơn.
- Order repository.
- Place/confirm/cancel use cases.
- OrderPlaced/OrderConfirmed integration events.

Order không nhất thiết sở hữu:

- Customer profile hiện tại.
- Payment ledger nội bộ.
- Inventory physical stock.
- Carrier tracking internals.

Order có thể lưu reference và snapshot cần thiết để giữ lịch sử giao dịch. Việc lưu snapshot là quyết định domain: địa chỉ và giá tại lúc đặt hàng có thể phải bất biến theo đơn, dù Customer/Product sau đó thay đổi.

## 31. Ví dụ thiết kế Payment Context

Payment Context có thể sở hữu:

- Payment aggregate/attempt.
- Authorization, capture, refund và chargeback lifecycle.
- Provider adapter.
- Idempotency key và transaction references.
- Payment ledger/audit.
- PaymentAuthorized/PaymentCaptured/PaymentFailed events.

Payment không cần import OrderEntity. Nó nhận command với order reference, amount, currency và idempotency key theo contract. Payment phải tự xác minh các ràng buộc của nó; Order chịu trách nhiệm workflow trạng thái đơn.

Một event PaymentCaptured có thể khiến Order cập nhật state, nhưng Order không tự sửa payment record.

## 32. Ví dụ thiết kế Inventory Context

Inventory Context sở hữu:

- SKU/warehouse stock.
- Reservation aggregate hoặc allocation model.
- Stock movement.
- Reservation expiry/release.
- Available-to-promise policy.
- InventoryReserved/ReservationRejected events.

Order gửi yêu cầu reserve theo contract. Inventory tự kiểm tra availability và thực hiện invariant. Không cho Order giảm stock trực tiếp bằng SQL.

Một số hệ cần inventory partition theo warehouse/SKU để scale; ranh giới aggregate và consistency cần xét theo khả năng oversell, reservation và fulfillment.

## 33. Tách read model khỏi domain model

Query cho màn hình có thể cần dữ liệu từ nhiều context. Không nên vì UI muốn một JSON duy nhất mà ép mọi domain dùng chung aggregate.

Có thể tạo projection:

~~~text
Catalog events ----\
Order events --------> Product/Customer dashboard projection
Payment events -----/
Shipping events ----/
~~~

Projection có thể được sở hữu bởi một read/query context và có eventual consistency. Nó không phải source of truth cho các write nghiệp vụ.

Cần định nghĩa freshness, replay, schema version, data lineage và quyền truy cập. Nếu projection lag, UI nên hiển thị trạng thái cập nhật phù hợp.

## 34. Các dấu hiệu boundary sai

- Một use case đơn giản cần sửa 5 service và 4 database.
- Hai service cùng ghi một bảng hoặc cùng quyết định một invariant.
- Shared domain model phình to.
- Consumer đọc trực tiếp database của provider.
- Mỗi deploy yêu cầu nhiều team release đồng thời.
- Một service chỉ làm CRUD proxy không có ownership rõ.
- Service quá nhỏ, mọi request phải gọi nhiều service chỉ để hoàn thành một thao tác nội bộ.
- Một service quá lớn chứa nhiều ngôn ngữ và policy không liên quan.
- API contract phản chiếu JPA entities.
- Event chứa toàn bộ object nội bộ.
- Domain rule nằm trong gateway hoặc shared utility.
- Team không biết ai chịu trách nhiệm khi dữ liệu sai.
- Integration test luôn cần khởi động toàn bộ hệ thống.
- Một thay đổi field nhỏ gây coordinated release trên toàn bộ platform.

Một dấu hiệu riêng lẻ không đủ kết luận; hãy xem tần suất, mức độ ảnh hưởng và business change thực tế.

## 35. Distributed monolith do DDD bị áp dụng sai

Một distributed monolith có thể có:

- Nhiều service/repository/container.
- Một shared database hoặc shared domain library.
- Synchronous calls nối tiếp ở mọi use case.
- Coordinated releases.
- Shared transaction semantics không rõ.
- Một nhóm trung tâm quyết định mọi model.
- Failure ở một service lan qua chain.

Tách deployment mà không tách ownership/model chỉ làm distributed system phức tạp hơn.

Cách giảm:

1. Xác định boundary theo capability/invariant.
2. Thu hồi quyền truy cập trực tiếp dữ liệu owner.
3. Đưa contract rõ vào API/event.
4. Giảm synchronous dependencies.
5. Chọn consistency theo use case.
6. Có team ownership và release lifecycle.
7. Giữ module boundaries nếu chưa cần deploy riêng.

## 36. Modular monolith là bước đi hợp lệ

Có thể triển khai các bounded contexts trong một codebase/process nhưng giữ module boundaries:

~~~text
application
  customer-context
  catalog-context
  order-context
  payment-context
  inventory-context
  shipping-context
  shared-kernel (nếu thật sự cần)
~~~

Quy tắc:

- Module khác không truy cập internal package.
- Giao tiếp qua interface/event nội bộ rõ.
- Persistence ownership theo module.
- Không import entity nội bộ xuyên context.
- Test architecture rules.
- Có thể tách deployment sau khi hiểu operational needs.

Modular monolith giảm network/operational complexity trong giai đoạn domain chưa ổn định, nhưng cần kỷ luật module để tránh trở lại big ball of mud.

## 37. Đo chất lượng ranh giới bằng thay đổi thực tế

Một boundary tốt giúp:

- Feature thuộc một context thường thay đổi trong một team.
- Schema migration có owner.
- Contract changes có danh sách consumer.
- Deploy một service không buộc release không liên quan.
- Failure của dependency có timeout/fallback phù hợp.
- Data invariants được bảo vệ bên trong owner.
- Số lượng cross-context synchronous calls được kiểm soát.

Có thể theo dõi:

- Số service phải đổi cho một business change.
- Số coordinated deployments.
- Số direct database dependencies.
- Số shared entity/model packages.
- Contract breaking changes.
- Cross-service transaction/workflow failures.
- Lead time từ merge đến production.
- MTTR khi một dependency suy giảm.

Không tối ưu bằng cách ép số service hoặc số call xuống một con số bất kỳ; phải hiểu trade-off.

## 38. Migration từ boundary cũ sang boundary DDD mới

Một lộ trình thực tế:

1. **Discover:** map workflow, domain language, tables, teams và dependencies.
2. **Model:** đề xuất subdomains/bounded contexts và invariants.
3. **Validate:** thử với use case thật và domain experts.
4. **Modularize:** tạo module boundaries trong monolith nếu phù hợp.
5. **Expose contract:** API/event thay cho direct DB access.
6. **Backfill/CDC:** chuyển dữ liệu theo owner mới.
7. **Strangler:** route capability sang service mới.
8. **Observe:** đo behavior, latency, data mismatch và team coordination.
9. **Cut ownership:** một owner duy nhất cho writes.
10. **Retire coupling:** gỡ shared entity, direct DB access và compatibility code cũ.

Không cần tách tất cả domain cùng lúc. Chọn capability có boundary rõ, lợi ích rõ và rủi ro migration kiểm soát được.

## 39. Checklist đánh giá một bounded context

### Domain model

- [ ] Có ubiquitous language được domain experts hiểu.
- [ ] Terms và state có nghĩa nhất quán.
- [ ] Có subdomain classification.
- [ ] Invariants và business rules được xác định.
- [ ] Aggregate boundaries bảo vệ consistency.
- [ ] Entity/value object có identity/semantics rõ.

### Ownership

- [ ] Có một owner team chịu trách nhiệm.
- [ ] Dữ liệu và schema có authority.
- [ ] Service khác không ghi trực tiếp storage nội bộ.
- [ ] Domain rules không nằm trong shared utility/gateway.
- [ ] Có chính sách thay đổi và support.

### Integration

- [ ] Context map và upstream/downstream rõ.
- [ ] API/event contract có version.
- [ ] ACL được dùng khi model ngoài khác nội bộ.
- [ ] Shared Kernel nhỏ và có governance.
- [ ] Timeout/retry/idempotency phù hợp.
- [ ] Eventual consistency và read freshness được công bố.

### Deployment

- [ ] Có lý do vận hành cho deployment boundary.
- [ ] Có thể release độc lập khi cần.
- [ ] Có observability và runbook.
- [ ] Failure domain và scaling needs được xác định.
- [ ] Nếu chưa cần tách, module boundary trong monolith vẫn được bảo vệ.

## 40. Câu hỏi tự kiểm tra

**1. Domain và subdomain khác nhau thế nào?**  
Domain là toàn bộ lĩnh vực; subdomain là phần bài toán có mục tiêu/quy tắc riêng bên trong lĩnh vực đó.

**2. Bounded context có đồng nghĩa microservice?**  
Không. Bounded context là ranh giới model/ngôn ngữ; microservice là lựa chọn triển khai. Một context có thể nằm trong modular monolith.

**3. Vì sao một từ có thể có nhiều model theo context?**  
Vì Sales, Warehouse và Finance quan tâm những thuộc tính/quy tắc khác nhau; ép chung một model tạo coupling và field không có ý nghĩa.

**4. Ubiquitous Language dùng ở đâu?**  
Trong thảo luận domain, tài liệu, code, tests và event/API terms của cùng context.

**5. Core, supporting và generic subdomain giúp gì?**  
Giúp quyết định nơi đầu tư mô hình, nơi tự xây và nơi có thể dùng giải pháp phổ biến.

**6. Context map thể hiện điều gì?**  
Các bounded contexts, upstream/downstream và quan hệ hợp tác/tích hợp giữa chúng.

**7. Anti-Corruption Layer giải quyết vấn đề gì?**  
Chuyển đổi model/protocol bên ngoài để bảo vệ domain nội bộ khỏi semantics không phù hợp.

**8. Shared Kernel có nên chứa tất cả entity chung?**  
Không. Nó chỉ nên là phần model nhỏ thực sự được các context cùng sở hữu và có governance.

**9. Aggregate root bảo vệ điều gì?**  
Invariant của aggregate và kiểm soát các thay đổi hợp lệ qua một entry point.

**10. Vì sao một transaction xuyên ba microservices nguy hiểm?**  
Nó tạo coupling và failure handling phức tạp; thường dùng saga/compensation cho workflow xuyên service.

**11. Domain event và integration event có giống nhau?**  
Không nhất thiết. Integration event là contract public được thiết kế để context khác tiêu thụ.

**12. Khi nào modular monolith phù hợp?**  
Khi domain/team/deployment chưa cần phân tách vận hành nhưng vẫn cần module ownership rõ.

**13. Dấu hiệu distributed monolith?**  
Nhiều service nhưng thay đổi nhỏ phải release đồng loạt, truy cập shared DB và gọi đồng bộ chặt chẽ.

**14. Có nên tạo service riêng cho mỗi table?**  
Không; boundary nên dựa trên capability và invariant, không dựa trên cấu trúc storage.

**15. Làm sao biết boundary tốt?**  
Thử một business change thật: owner, data, model và release có thể thay đổi trong phạm vi hợp lý mà không kéo các context không liên quan.

## 41. Tài liệu tham khảo

- Eric Evans — Domain-Driven Design: https://www.domainlanguage.com/ddd/
- Vaughn Vernon — Implementing Domain-Driven Design: https://vaughnvernon.com/
- Martin Fowler — Bounded Context: https://martinfowler.com/bliki/BoundedContext.html
- Martin Fowler — Context Mapping: https://martinfowler.com/bliki/ContextMapping.html
- Martin Fowler — Microservices: https://martinfowler.com/articles/microservices.html
- Microsoft — Domain analysis for microservices: https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis
- Microsoft — Identify microservice domain model boundaries: https://learn.microsoft.com/en-us/azure/architecture/microservices/model/microservice-boundaries
- Microsoft — Tactical DDD: https://learn.microsoft.com/en-us/azure/architecture/microservices/model/tactical-domain-driven-design
- Microsoft — DDD-oriented microservice: https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/
- EventStorming: https://www.eventstorming.com/
- Domain-Driven Design Community: https://dddcommunity.org/

**Ghi nhớ:** DDD giúp tìm microservice boundary bằng **ngôn ngữ, capability, invariant và ownership nghiệp vụ**. Bounded context định nghĩa model; aggregate bảo vệ consistency nội bộ; context map làm rõ quan hệ; API/event và ACL bảo vệ ranh giới. Chỉ tách thành deployment riêng khi lợi ích về ownership, thay đổi, scaling hoặc isolation đủ lớn để bù chi phí vận hành distributed system.
