# Chia dịch vụ theo bảng dữ liệu hoặc từng lớp kỹ thuật

Một hệ thống được gọi là microservices không chỉ vì nó có nhiều process, nhiều repository hoặc nhiều API. Giá trị của kiến trúc này đến từ những ranh giới năng lực có thể thay đổi, triển khai và vận hành tương đối độc lập. Một sai lầm thường gặp là chia ứng dụng theo **cấu trúc dữ liệu**: mỗi bảng database thành một service, hoặc chia theo **lớp kỹ thuật**: một service chỉ làm controller, một service chỉ làm business logic, một service chỉ truy cập database. Kết quả có thể là rất nhiều service nhỏ, nhưng một thay đổi nghiệp vụ đơn giản vẫn phải đi qua nhiều nhóm, nhiều network call và nhiều lần deploy.

Ví dụ, một chức năng tạo đơn hàng có thể cần ghi Order, cập nhật Inventory, tạo Payment và phát Notification. Nếu kiến trúc được chia thành Table Service, Repository Service, Business Service và Controller Service, các thành phần không phản ánh quyền sở hữu nghiệp vụ. Một thay đổi về trạng thái đơn có thể buộc nhiều service cùng sửa; transaction bị phân tán; khi lỗi xảy ra, mỗi nhóm chỉ nhìn thấy một đoạn của hành trình. Nếu mỗi bảng là một service, ranh giới còn tệ hơn: OrderService có thể phải gọi CustomerTableService, OrderItemTableService, AddressTableService và PaymentTableService chỉ để hoàn thành một thao tác.

Bài này giải thích vì sao **chia theo bảng dữ liệu** và **chia theo lớp kỹ thuật** thường tạo ra distributed monolith, cách nhận diện ranh giới phù hợp theo bounded context và năng lực nghiệp vụ, và cách chuyển đổi từng bước mà không gây gián đoạn hoặc làm mất tính nhất quán dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt phân rã theo bảng, theo lớp kỹ thuật, theo chức năng và theo năng lực nghiệp vụ.
- Nhận diện dấu hiệu một hệ thống nhiều service nhưng vẫn phụ thuộc như monolith.
- Giải thích vì sao database table, entity, controller, repository hoặc utility class không tự động là service boundary.
- Xác định bounded context, aggregate, business capability và quyền sở hữu dữ liệu.
- Đánh giá transaction boundary, consistency, latency, failure isolation và release independence khi tách service.
- Thiết kế API/event contract dựa trên hành vi nghiệp vụ thay vì expose CRUD của bảng.
- Quyết định khi nào giữ module trong modular monolith, khi nào tách service, khi nào hợp nhất các service nhỏ.
- Lập kế hoạch refactor theo hướng strangler/expand-contract, có kiểm soát dữ liệu và khả năng rollback.
- Đo coupling và coordination cost trước/sau khi thay đổi kiến trúc.
- Tránh các anti-pattern như shared database writes, chatty APIs, generic CRUD services và layer services.

## 2. Service boundary nên phản ánh điều gì?

Một service nên được tổ chức quanh một **năng lực nghiệp vụ có ý nghĩa**, với dữ liệu và các quy tắc mà nó chịu trách nhiệm. Người tiêu thụ nên gọi một contract biểu đạt mục đích nghiệp vụ, ví dụ CreateOrder, ReserveInventory, CapturePayment hoặc CalculateQuote, thay vì gọi các thao tác kỹ thuật rời rạc như InsertOrderRow, UpdateAddressTable và SaveOrderItem.

Một ranh giới service hữu ích thường có những đặc điểm:

- Có một nhóm nghiệp vụ hoặc owner hiểu và chịu trách nhiệm về hành vi.
- Có dữ liệu và invariant thuộc quyền sở hữu rõ.
- Có contract công khai đủ ổn định cho consumer.
- Phần lớn thay đổi nội bộ không buộc consumer triển khai cùng lúc.
- Có thể xác định SLO, dashboard, runbook và on-call.
- Có failure behavior và cách phục hồi được mô tả.
- Có quy mô đủ để lợi ích độc lập vượt chi phí network, deployment và vận hành.

Service không cần sở hữu đúng một bảng, một entity hoặc một endpoint. Một bounded context có thể chứa nhiều bảng, nhiều aggregate và nhiều API. Ngược lại, một bảng có thể được đọc bởi nhiều hệ thống qua API hoặc read model, nhưng quyền ghi và định nghĩa ngữ nghĩa nên thuộc một owner.

## 3. Ba kiểu phân rã thường bị nhầm lẫn

| Kiểu phân rã | Cách chia | Ví dụ | Vấn đề thường gặp |
|---|---|---|---|
| Theo bảng dữ liệu | Mỗi bảng hoặc nhóm bảng thành một service | CustomerTableService, OrderTableService | CRUD phân tán, transaction xuyên service, coupling theo schema |
| Theo lớp kỹ thuật | Mỗi tầng ứng dụng thành service riêng | ControllerService, BusinessService, RepositoryService | Mọi request phải đi qua nhiều hop, thay đổi cùng nhau |
| Theo năng lực nghiệp vụ | Mỗi service sở hữu một capability/bounded context | Order, Payment, Inventory | Cần thiết kế domain boundary và contract rõ |
| Theo chức năng kỹ thuật chuyên biệt | Một subsystem có nhu cầu độc lập rõ | Search indexing, media processing | Có thể hợp lý nếu owner, contract và failure behavior rõ |

Không phải mọi service có tên theo một chức năng kỹ thuật đều sai. Search indexing, image processing, identity infrastructure hoặc notification delivery có thể là subsystem hợp lý nếu nó có workload, lifecycle và contract riêng. Vấn đề là **chọn ranh giới chỉ vì cấu trúc code hoặc database**, không xét hành vi và quyền sở hữu.

## 4. Anti-pattern 1: mỗi bảng database là một microservice

Giả sử database ban đầu có các bảng:

~~~text
customers
addresses
orders
order_items
payments
payment_transactions
inventory
products
shipments
~~~

Một cách chia cơ học có thể tạo:

~~~text
CustomerTableService
AddressTableService
OrderTableService
OrderItemTableService
PaymentTableService
PaymentTransactionTableService
InventoryTableService
ProductTableService
ShipmentTableService
~~~

Khi người dùng tạo đơn, OrderTableService phải gọi OrderItemTableService để lưu từng dòng, AddressTableService để xác minh địa chỉ, CustomerTableService để lấy khách hàng, PaymentTableService để tạo payment và InventoryTableService để giữ hàng. Những service này không đại diện cho một hành vi độc lập; chúng chỉ đóng gói thao tác CRUD trên từng bảng.

### 4.1. Vì sao cách chia này gây vấn đề?

**Một thao tác nghiệp vụ biến thành chuỗi network calls.** Một transaction SQL nội bộ có thể trở thành nhiều request qua mạng. Mỗi hop thêm latency, timeout, retry và khả năng lỗi riêng.

**Transaction ACID bị chia cắt.** Trước đây Order và OrderItem có thể được ghi trong một transaction database. Sau khi tách, Order được tạo nhưng OrderItem call timeout; hệ thống có thể để lại order dở dang.

**Schema trở thành API ngoài ý muốn.** Consumer phải hiểu cấu trúc bảng, tên cột, quan hệ và quy tắc cập nhật. Thay đổi schema nội bộ buộc nhiều service thay đổi.

**Business rule bị phân tán.** Điều kiện “đơn phải có ít nhất một item hợp lệ” có thể nằm ở OrderTableService, OrderItemTableService hoặc cả hai. Không có một nơi chịu trách nhiệm invariant.

**Khó xác định owner.** Ai chịu trách nhiệm khi đơn có header nhưng thiếu item? Owner của bảng orders hay order_items? Người dùng không quan tâm bảng nào lỗi; họ cần một đơn hoàn chỉnh.

### 4.2. CRUD service không phải domain service

CRUD service thường cung cấp:

~~~text
POST   /orders
GET    /orders/{id}
PUT    /orders/{id}
DELETE /orders/{id}
~~~

Nếu API chỉ chuyển tiếp thao tác database và expose mọi field, nó thường là một lớp remote persistence. Domain service có thể cung cấp các thao tác đọc/ghi, nhưng API nên thể hiện business intent và bảo vệ invariant:

~~~text
POST /orders
POST /orders/{id}/confirm
POST /orders/{id}/cancel
GET  /orders/{id}/summary
~~~

Ví dụ, ConfirmOrder có thể kiểm tra trạng thái, inventory reservation, payment authorization và điều kiện nghiệp vụ. Consumer không được tự update status column để bỏ qua state machine.

## 5. Thiết kế tốt hơn: Order Service sở hữu aggregate Order

Một Order Service có thể sở hữu nhiều bảng liên quan:

~~~text
Order Service
  - orders
  - order_items
  - order_addresses_snapshot
  - order_status_history
  - order_outbox
~~~

Các bảng này cùng phục vụ một bounded context và được cập nhật theo invariant của Order. Service cung cấp API/event có ngữ nghĩa nghiệp vụ:

~~~text
CreateOrder(command)
ConfirmOrder(orderId)
CancelOrder(orderId, reason)
GetOrder(orderId)
OrderCreated(event)
OrderConfirmed(event)
OrderCancelled(event)
~~~

Các service khác không truy cập trực tiếp bảng nội bộ. Payment sở hữu payment attempts/ledger; Inventory sở hữu reservations/stock; Catalog sở hữu product information. Order có thể lưu snapshot các thuộc tính cần thiết tại thời điểm đặt hàng, ví dụ tên sản phẩm, giá được chấp nhận hoặc địa chỉ giao hàng, theo quy tắc dữ liệu của domain.

### 5.1. Một service có thể có nhiều aggregate

Không nên biến mỗi aggregate hoặc mỗi bảng thành một service. Nếu các aggregate cần thay đổi cùng nhau trong một transaction, có cùng owner và cùng lifecycle, chúng có thể nằm trong một service/bounded context. Chỉ tách khi có lý do về quyền sở hữu, consistency, scale, security hoặc tốc độ thay đổi độc lập.

## 6. Anti-pattern 2: chia service theo từng lớp kỹ thuật

Một ứng dụng phân tầng truyền thống thường có:

~~~text
Presentation / Controller
        |
Business / Service
        |
Repository / Data Access
        |
Database
~~~

Các tầng này là cách tổ chức code hợp lý **bên trong một ứng dụng**. Nhưng nếu biến từng tầng thành một microservice độc lập:

~~~text
Browser
   |
Controller Service
   |
Business Logic Service
   |
Repository Service
   |
Database Service
~~~

thì một request đơn giản phải đi qua nhiều process chỉ để thực hiện cùng một luồng. Đây là remote procedure chain được tạo ra từ cấu trúc nội bộ, không phải ranh giới năng lực.

### 6.1. Hậu quả của layer services

- **Network hop tăng:** mỗi lần gọi có latency, connection management và serialization.
- **Failure propagation:** Repository Service lỗi khiến mọi business operation phía trên lỗi.
- **Deployment coupling:** thay đổi method signature ở Business Service có thể buộc Controller Service và Repository Service nâng cùng.
- **Ownership mờ:** Controller Team, Business Team và Repository Team đều cùng chịu trách nhiệm cho một hành vi.
- **Debug phân tán:** trace phải nối qua nhiều service dù logic thuộc cùng một năng lực.
- **Scale sai:** một tầng có thể bị scale độc lập nhưng không giải quyết bottleneck ở tầng khác.
- **Security surface rộng:** mỗi lớp remote tạo thêm endpoint, identity, authorization và network policy.
- **Test phức tạp:** unit/integration test phải khởi động hoặc giả lập nhiều process không tạo giá trị nghiệp vụ.

### 6.2. Giữ phân tầng bên trong service

Một service vẫn có thể dùng kiến trúc layered hoặc hexagonal:

~~~text
Order Service
  API / Controller
        |
  Application Use Cases
        |
  Domain Model
        |
  Ports / Interfaces
        |
  Adapters
    - PostgreSQL repository
    - Kafka publisher
    - Payment client
~~~

Các tầng giao tiếp qua interface hoặc function call trong cùng deployable unit. Chúng có thể được test độc lập mà không cần tách thành network services. Khi một adapter có nhu cầu vận hành độc lập thực sự, có thể cân nhắc tách sau khi contract đã rõ.

## 7. Modular monolith không phải kiến trúc thất bại

Nếu domain boundary chưa ổn định, một modular monolith có thể là lựa chọn tốt:

~~~text
Commerce Application
  +-- Catalog Module
  +-- Order Module
  +-- Payment Module
  +-- Inventory Module
  +-- Notification Module
       |
  Shared runtime / one deployment
       |
  Database với schema/ownership boundaries
~~~

Mỗi module có API nội bộ, dependency rules và quyền sở hữu dữ liệu logic. Module không được truy cập trực tiếp implementation nội bộ của module khác. Có thể dùng package/module boundary, architecture tests và module build để bảo vệ.

Lợi ích:

- Function call nội bộ nhanh và dễ debug.
- Transaction có thể đơn giản hơn khi business invariant thật sự cần.
- Deployment/on-call overhead thấp hơn.
- Team học domain boundary trước khi phân tán runtime.
- Có thể tách module thành service sau khi hiểu rõ contract và nhu cầu độc lập.

Một modular monolith lộn xộn vẫn có coupling như monolith truyền thống. Giá trị đến từ module boundaries được thực thi, không chỉ từ việc đặt package name.

## 8. Bounded context là cơ sở tốt hơn cho service boundary

Bounded context là phạm vi trong đó một mô hình domain và ngôn ngữ nghiệp vụ có ý nghĩa nhất quán.

Ví dụ thương mại điện tử:

| Context | Mô hình và trách nhiệm |
|---|---|
| Catalog | Thông tin sản phẩm, thuộc tính, danh mục và trạng thái xuất bản |
| Pricing/Promotion | Quote, giá, thuế/phí theo policy và khuyến mãi |
| Cart | Lựa chọn tạm thời của người mua |
| Order | Vòng đời đơn, item snapshot và trạng thái đơn |
| Payment | Payment attempt, authorization, capture, refund và ledger |
| Inventory | Tồn kho, allocation và reservation |
| Shipping | Shipment, carrier và tracking |
| Notification | Delivery của email/SMS/push theo consent và template |

Tên gọi có thể khác theo doanh nghiệp. Một context có thể chứa nhiều service nếu có nhu cầu phân tách rõ, nhưng đừng tạo service boundary chỉ vì một entity có tên khác.

### 8.1. Cùng một khái niệm có thể khác nhau giữa context

“Customer” trong Order có thể là snapshot người mua và địa chỉ tại thời điểm đặt đơn. “Customer” trong Identity là principal đăng nhập. “Customer” trong Billing là đối tượng hóa đơn và công nợ. Ép tất cả dùng một CustomerEntity chung có thể kéo theo một schema và lifecycle không phù hợp.

Dùng API/event hoặc read model để chia sẻ dữ liệu cần thiết; mỗi context giữ model nội bộ theo mục đích của mình.

## 9. Aggregate và transaction boundary

Aggregate là một ranh giới nhất quán nghiệp vụ trong domain model. Nó giúp xác định những thay đổi nào cần được bảo vệ cùng nhau.

Ví dụ Order aggregate có thể gồm Order và OrderItems. Invariant:

- Đơn phải có ít nhất một item.
- Số lượng item phải dương.
- Tổng tiền phải khớp với các line item theo snapshot giá.
- Chỉ trạng thái hợp lệ mới được chuyển sang CONFIRMED.
- Đơn đã SHIPPED không thể hủy theo cùng luồng hủy thông thường.

Những invariant này có thể được kiểm tra trong một transaction của Order database. Không cần tạo OrderHeaderService và OrderItemService riêng chỉ vì có hai bảng.

Ngược lại, Payment và Inventory có thể là bounded contexts khác, với database và transaction riêng. Khi một workflow cần phối hợp, dùng saga/process manager, outbox/inbox, idempotency và compensation theo contract, thay vì giả vờ có một transaction phân tán ACID.

## 10. Ranh giới theo dữ liệu: ai là owner của sự thật?

Một nguyên tắc quan trọng là **service sở hữu dữ liệu có thẩm quyền của bounded context**. Consumer có thể đọc qua API hoặc nhận event để xây read model, nhưng không tự ghi vào bảng nội bộ của owner.

Ví dụ:

~~~text
Order Service
  owns orders, order_items, order lifecycle

Payment Service
  owns payment_attempts, ledger, refunds

Inventory Service
  owns stock and reservations

Catalog Service
  owns product catalog and publication state
~~~

Nếu Order cần hiển thị trạng thái thanh toán, có thể lưu projection/read model nhận PaymentStatusChanged event. Projection này phục vụ đọc và không biến Order thành owner của Payment ledger.

### 10.1. Database vật lý và logical ownership

Nhiều service có thể dùng cùng một PostgreSQL cluster vật lý nhưng nên tách schema/role/quyền truy cập theo owner. Việc dùng chung hạ tầng database không tự nó là sai; **ghi xuyên schema hoặc chia sẻ quyền update bảng nghiệp vụ** mới tạo coupling nguy hiểm.

Mô hình:

~~~text
PostgreSQL cluster (platform operated)
  +-- order_schema      -> Order Team owns logical schema
  +-- payment_schema    -> Payment Team owns logical schema
  +-- inventory_schema  -> Inventory Team owns logical schema
~~~

Platform/DBA có thể sở hữu backup, patching, replication và capacity. Domain team sở hữu semantics, schema migration, query behavior và business invariants.

## 11. API theo hành vi, không expose database CRUD

Một API tốt phản ánh use case:

~~~http
POST /orders
Content-Type: application/json

{
  "customerId": "C-100",
  "items": [
    { "productId": "P-10", "quantity": 2 }
  ],
  "quoteId": "Q-88"
}
~~~

Order Service có thể kiểm tra command, lưu snapshot cần thiết, tạo order và outbox event trong transaction. Consumer không phải biết order có bao nhiêu bảng.

API nên tránh:

~~~http
POST /tables/orders
PATCH /tables/order_items/123
GET /database/customer/100
~~~

Tên endpoint tự nó không quyết định kiến trúc; điều quan trọng là contract không để consumer phụ thuộc schema persistence nội bộ và không cho phép bỏ qua domain invariants.

### 11.1. Command và query có thể khác nhau

- Command biểu diễn ý định thay đổi trạng thái: ConfirmOrder, CancelOrder.
- Query biểu diễn dữ liệu cần đọc: GetOrderSummary, SearchOrders.
- Event biểu diễn sự kiện đã xảy ra: OrderConfirmed.

Không bắt buộc mọi hệ thống dùng CQRS đầy đủ. Nhưng phân biệt intent giúp API dễ hiểu và giảm việc consumer thao tác trực tiếp vào bảng.

## 12. Anti-pattern 3: một service cho mỗi HTTP endpoint hoặc function

Chia service quá nhỏ cũng gây overhead:

~~~text
GetOrderIdService
CalculateTaxService
FormatAddressService
ValidateQuantityService
ConvertCurrencyService
~~~

Một function nhỏ có thể là module, class hoặc library nội bộ. Tách thành service chỉ khi có lý do vận hành hoặc ownership đủ mạnh: workload riêng, security boundary, lifecycle độc lập, khả năng tái sử dụng qua contract ổn định hoặc cần isolation.

Một endpoint không đồng nghĩa một microservice. Một service có thể cung cấp nhiều endpoint cho cùng capability.

## 13. Chatty APIs và network call chains

Nếu một request cần gọi 12 service theo chuỗi, latency và failure probability tăng. Ví dụ:

~~~text
GET /order-summary
  -> CustomerTableService
  -> AddressTableService
  -> OrderTableService
  -> OrderItemTableService
  -> ProductTableService
  -> PricingTableService
  -> PaymentTableService
  -> ShipmentTableService
~~~

Đây là dấu hiệu consumer phải ghép các bảng qua network. Một Order Summary API thuộc Order context có thể trả snapshot và trạng thái cần thiết; các thông tin live khác có thể được lấy từ read model hoặc một query composition layer có chủ đích.

### 13.1. Khi nào API composition hợp lý?

Một BFF hoặc query composition service có thể gọi nhiều domain API để phục vụ màn hình cụ thể. Điều đó hợp lý nếu:

- Nó có owner và SLO rõ.
- Nó chỉ tổng hợp dữ liệu theo nhu cầu read.
- Không làm thay đổi business state của các domain.
- Có timeout/degraded behavior và cache/freshness contract.
- Không trở thành nơi chứa logic quyết định thay cho domain owner.

Không nên biến BFF thành một lớp CRUD trung gian cho mọi bảng.

## 14. Coupling qua release: distributed monolith

Một hệ thống có thể có 15 service nhưng phải deploy đồng thời mọi lần thay đổi. Dấu hiệu:

- Shared DTO/Entity thay đổi buộc tất cả consumer build lại.
- Consumer yêu cầu field mới ngay lập tức, producer không thể phát trước.
- Mọi service dùng chung database schema và migration.
- Một common library thay đổi behavior của mọi service.
- Endpoint nội bộ không có version/compatibility contract.
- Integration test chỉ chạy được khi toàn bộ hệ thống khởi động cùng lúc.
- Rollback một service làm hỏng service khác.

Đó là distributed monolith: nhiều process nhưng vẫn có một release boundary lớn. Muốn có độc lập, cần contract ổn định, additive changes, versioning, consumer compatibility tests, data ownership và deployment có thể tách.

## 15. Coupling qua transaction và consistency

Trong monolith, một transaction có thể cập nhật Order, Payment và Inventory cùng database. Khi tách thành service, không thể giữ transaction ACID xuyên các database theo cách đơn giản đó nếu không dùng distributed transaction, vốn có trade-off vận hành và availability.

Thay vì chia theo bảng, cần quyết định **invariant nào thuộc một context** và **workflow nào có thể eventual consistency**.

Ví dụ checkout:

~~~text
Checkout workflow
   |
   +--> Order: create PENDING
   |
   +--> Inventory: reserve
   |
   +--> Payment: authorize/capture
   |
   +--> Order: confirm
~~~

Nếu Payment thất bại, cần release reservation hoặc giữ trạng thái pending theo policy. Nếu provider timeout nhưng đã capture, cần reconciliation. Các hành động này cần business owner và state machine; không thể giải quyết bằng cách tách mỗi bảng thành một CRUD service.

### 15.1. Saga và compensation

Saga chia workflow thành các local transactions với hành động bù trừ khi bước sau thất bại. Ví dụ:

- Create order.
- Reserve inventory.
- Authorize payment.
- Confirm order.
- Nếu authorize thất bại, release inventory và đánh dấu order không thể tiếp tục.

Compensation không phải rollback vật lý hoàn hảo. Refund sau capture là một nghiệp vụ riêng, có thể bất đồng bộ và có phí. Thiết kế saga phải mô tả trạng thái trung gian, retry, timeout, idempotency và manual review.

## 16. Đánh giá service boundary bằng change scenarios

Thay vì hỏi “bảng này có thể là service không?”, hãy hỏi:

- Khi đổi quy tắc này, nhóm nào cần tham gia?
- Thay đổi có cần transaction với dữ liệu nào?
- Ai có thẩm quyền quyết định tính đúng?
- Consumer cần dữ liệu hay cần một quyết định nghiệp vụ?
- Nếu dependency unavailable, hành vi mong muốn là gì?
- Service có thể triển khai phiên bản mới khi consumer cũ còn chạy không?
- Dữ liệu có thể di chuyển hoặc sở hữu độc lập không?
- Có thể kiểm tra contract tự động không?
- Có owner đủ năng lực trực production không?
- Chi phí network/observability có hợp lý so với lợi ích?

Một ranh giới tốt thường gom những thay đổi thường xảy ra cùng nhau và tách những thay đổi có lý do độc lập.

## 17. Một ví dụ so sánh: thiết kế Order

### Thiết kế theo bảng

~~~text
OrderController
  -> OrderHeaderService
  -> OrderItemService
  -> CustomerService
  -> AddressService
  -> PaymentTableService
  -> InventoryTableService
~~~

Mỗi service expose CRUD và database. Một request tạo đơn cần nhiều lần gọi và không có một owner chịu trách nhiệm toàn bộ invariant của Order.

### Thiết kế theo lớp

~~~text
OrderControllerService
  -> OrderBusinessService
  -> OrderRepositoryService
  -> DatabaseService
~~~

Mỗi lớp là một process riêng. Thay đổi logic Order kéo theo API và deploy nhiều lớp; các lớp kỹ thuật không có giá trị nghiệp vụ độc lập.

### Thiết kế theo domain

~~~text
Order Service
  - API / application use cases
  - Order domain model
  - Order repository
  - Order schema
  - Outbox
  - SLO / runbook / owner

Payment Service
Inventory Service
Catalog/Pricing Services
~~~

Order giữ các thay đổi nhất quán nội bộ; tương tác với Payment/Inventory qua contract nghiệp vụ. Các tầng kỹ thuật vẫn tồn tại bên trong service.

## 18. Chia service theo team và ownership

Ranh giới service phải phù hợp với tổ chức. Nếu mỗi bảng có một team, một feature có thể phải qua 5 nhóm. Nếu mỗi layer có một team, Controller Team không thể hoàn thành feature nếu Business Team chưa sửa và Repository Team chưa deploy.

Tổ chức theo năng lực:

- Order Team sở hữu order lifecycle, schema, API/event, SLO và on-call.
- Payment Team sở hữu payment lifecycle, ledger và provider integration.
- Inventory Team sở hữu stock/reservation.
- Platform Team cung cấp database/broker/runtime/observability như năng lực tự phục vụ.

Một team có thể sở hữu nhiều service thuộc cùng context; không cần 1:1 giữa service và team. Mục tiêu là giảm số phối hợp bắt buộc cho thay đổi thông thường và làm rõ trách nhiệm khi incident.

## 19. Khi nào chia theo lớp kỹ thuật vẫn hợp lý?

Một số subsystem kỹ thuật có thể là service độc lập:

- Identity provider phục vụ nhiều sản phẩm và có security lifecycle riêng.
- Centralized search/indexing có workload và data pipeline riêng.
- Media processing cần GPU/worker scaling khác ứng dụng chính.
- Notification delivery có tích hợp nhiều provider và retry policy riêng.
- API gateway/edge routing có failure domain và operational ownership riêng.
- Developer platform cung cấp provisioning, deployment và observability.

Điều làm chúng hợp lý là **năng lực kỹ thuật hoàn chỉnh có người dùng, contract, owner và SLO**, không phải vì chúng tương ứng với một layer trong sơ đồ MVC.

Ví dụ một Authentication Service có thể là platform capability; nhưng rule “người dùng được hoàn tiền trong 30 ngày” vẫn thuộc domain Refund/Payment. Tách công cụ xác thực khỏi quyết định nghiệp vụ.

## 20. Khi nào một bảng có thể xứng đáng thành service?

Một bảng riêng lẻ hiếm khi đủ lý do, nhưng có thể là dấu hiệu của một capability độc lập nếu:

- Nó đại diện một aggregate/domain có lifecycle riêng.
- Có owner và policy độc lập.
- Có API/event contract riêng.
- Có nhu cầu scale hoặc bảo mật khác.
- Có dữ liệu và invariant riêng.
- Consumer thực sự cần một năng lực, không chỉ CRUD.
- Có thể vận hành/recover độc lập.

Ví dụ Inventory stock có thể nằm trong Inventory Service vì tồn kho có reservation, allocation, reconciliation và concurrency rules phức tạp. Lý do không phải vì có bảng inventory; lý do là **năng lực quản lý tồn kho có mô hình và hành vi riêng**.

## 21. Anti-pattern 4: database schema trở thành contract công khai

Nếu consumer đọc trực tiếp bảng của service khác, các chi tiết nội bộ trở thành API:

- Tên cột và nullability.
- Join structure và foreign keys.
- Enum/status values.
- Index và partition strategy.
- Cách lưu JSON.
- Thời điểm transaction commit.
- Migration sequence.

Consumer có thể phụ thuộc vào một chi tiết không được công bố, khiến owner không thể thay đổi nội bộ. Cách giảm coupling:

1. Chỉ cho owner ghi schema.
2. Công bố API/event/read model với semantics rõ.
3. Consumer không dựa vào bảng nội bộ.
4. Data sharing dùng snapshot hoặc projection có freshness contract.
5. Migration có expand-contract và compatibility window.
6. Catalog ghi owner của schema và contract.

## 22. Anti-pattern 5: tạo generic Data Service cho toàn hệ thống

Một Data Service cung cấp endpoint kiểu:

~~~text
GET /data/{table}/{id}
POST /data/{table}
PATCH /data/{table}/{id}
DELETE /data/{table}/{id}
~~~

Nó có vẻ giảm số service, nhưng thường tạo một database facade khổng lồ:

- Bỏ qua domain validation.
- Authorization khó gắn với từng hành động nghiệp vụ.
- Mọi service phụ thuộc vào schema chung.
- Data service trở thành bottleneck và blast radius lớn.
- Business owner không còn kiểm soát dữ liệu của mình.
- API thay đổi theo cấu trúc database.

Một data platform cho analytics, governance hoặc query federation có thể hợp lý, nhưng nó cần mục đích và access policy riêng. Không dùng nó làm đường ghi chung cho mọi transaction nghiệp vụ.

## 23. Anti-pattern 6: service theo CRUD operation

Ví dụ CreateOrderService, UpdateOrderService, DeleteOrderService thành ba deployable services. Các thao tác này cùng thay đổi order lifecycle và dùng chung invariant; chia ra tạo coupling không cần thiết.

Giữ các use cases trong Order Service hoặc module Order. Chỉ tách khi một capability có owner, data và lifecycle độc lập thật sự, không vì mỗi method có thể đặt vào một class.

## 24. Anti-pattern 7: shared library chứa domain model của mọi team

Một common.jar có OrderEntity, PaymentEntity, CustomerEntity, InventoryEntity và business rules dễ tạo compile-time coupling. Mỗi thay đổi domain phải phát hành library mới và consumer nâng version. Có thể tách:

- Technical primitives ổn định: tracing context, serialization utility, error envelope.
- Domain contracts: event schemas/API DTOs được version riêng.
- Domain model: nằm trong owner service.
- Mapping/anti-corruption layer: nằm ở consumer khi chuyển đổi mô hình.

Không phải mọi DTO đều phải thành một shared Java class. OpenAPI/AsyncAPI/Avro/Protobuf schema có thể là contract artifact; consumer generate client/model theo phiên bản phù hợp.

## 25. Refactor từ table services sang domain services

Giả sử hệ thống đang có CustomerTableService, OrderTableService và OrderItemTableService. Chuyển đổi nên theo từng bước:

**Bước 1 — Inventory hành vi.** Liệt kê API, consumer, bảng, transaction, business rule và incident liên quan. Tìm những thao tác luôn được gọi cùng nhau.

**Bước 2 — Xác định bounded context.** Gom các bảng và quy tắc cùng phục vụ một năng lực. Ví dụ orders, order_items và order_status_history thuộc Order context.

**Bước 3 — Chọn owner.** Giao một team chịu trách nhiệm API, schema, migration, SLO, runbook và release.

**Bước 4 — Thiết kế contract nghiệp vụ.** Thay endpoint CRUD bằng command/query có semantics. Xác định lỗi, idempotency, versioning và data ownership.

**Bước 5 — Xây service/module mới bên cạnh.** Đọc dữ liệu cũ theo một adapter, triển khai logic mới và test tương thích.

**Bước 6 — Chuyển traffic từng phần.** Dùng routing/feature flag/cohort. Đối chiếu kết quả và metrics. Tránh dual-write không kiểm soát.

**Bước 7 — Chuyển quyền ghi.** Xác định một nguồn authoritative. Chuyển consumer sang API/event mới. Chặn dần direct writes vào bảng cũ.

**Bước 8 — Reconcile dữ liệu.** So sánh record count, totals, status transitions, foreign keys và business invariants.

**Bước 9 — Loại bỏ adapter cũ.** Chỉ sau khi không còn consumer, có backup/recovery và rollback window đã kết thúc.

## 26. Refactor từ layer services sang một deployable theo domain

Giả sử ControllerService, BusinessService và RepositoryService luôn phải release cùng nhau.

Một cách chuyển:

1. Xác định API nội bộ giữa các layer và các consumer thực sự bên ngoài.
2. Chọn một capability nhỏ, ví dụ Order.
3. Đưa controller, application service, domain logic và repository về cùng deployable Order Service.
4. Giữ interface nội bộ để module vẫn tách trách nhiệm.
5. Chuyển cấu hình, telemetry và health checks về một owner.
6. Giữ contract public cho consumer bên ngoài.
7. Canary/route một phần traffic tới deployable mới.
8. So sánh response, DB writes và SLO.
9. Dừng các layer service cũ khi đã chuyển hết consumer.

Có thể giữ controller và repository trong các module/package riêng. Refactor chỉ thay đổi network/deployment boundary, không nhất thiết làm code thành một lớp khổng lồ.

## 27. Strangler pattern và routing migration

Strangler pattern cho phép thay thế dần một phần hệ thống cũ:

~~~text
                 API Gateway
                      |
             Routing / Feature Flag
                /           \
               v             v
        Legacy table API   New Order Service
               |             |
               +---- data ---+
                 migration
~~~

Các điều kiện quan trọng:

- Chỉ một nguồn authoritative cho mỗi write path tại một thời điểm.
- Read/write routing nhất quán theo key hoặc cohort.
- Có cách đối chiếu kết quả giữa cũ và mới.
- Không dual-write tùy tiện; nếu cần, phải có outbox/reconciliation.
- Có rollback route và schema compatibility.
- Có telemetry để phát hiện sai lệch.
- Xác định rõ khi nào legacy path được tắt.

Một feature flag chỉ đổi endpoint chưa đủ nếu hai bên có state divergence. Migration phải có chiến lược dữ liệu.

## 28. Expand-contract cho schema và API

Một thay đổi field có thể làm consumer cũ fail nếu xóa ngay. Quy trình:

~~~text
Phase 1: Expand
  Thêm field/schema mới, giữ cấu trúc cũ.

Phase 2: Migrate
  Code mới đọc được cả cũ và mới.
  Backfill dữ liệu, chuyển consumer.

Phase 3: Verify
  Đối chiếu traffic, dữ liệu, error rate và consumer usage.

Phase 4: Contract
  Chỉ xóa field cũ sau deprecation window.
~~~

Đây là cách giảm synchronized releases. Với database, cần cân nhắc lock/downtime của DDL. Với event/API, cần compatibility policy và contract tests. Với business semantics, thêm field không tự động tương thích nếu ý nghĩa thay đổi.

## 29. Dual-read, dual-write và data migration

**Dual-read** có thể dùng tạm để fallback giữa nguồn cũ và mới, nhưng cần quyết định nguồn nào có thẩm quyền và cách xử lý khác biệt.

**Dual-write** nguy hiểm hơn vì hai nguồn có thể diverge khi một write thành công và một write thất bại. Nếu bắt buộc, cần:

- Một nguồn commit chính.
- Outbox/change data capture để phát thay đổi.
- Idempotency và retry có kiểm soát.
- Reconciliation job.
- Metric phát hiện write gap.
- Cutover/rollback criteria.
- Kế hoạch ngừng dual-write.

Không coi việc gọi hai API trong cùng request là transaction nguyên tử. Network timeout có thể làm một bên đã ghi, bên kia chưa ghi hoặc chưa biết kết quả.

## 30. Đánh giá kết quả sau refactor

Đo trước và sau trên cùng loại workload:

| Khía cạnh | Trước | Kết quả mong đợi |
|---|---|---|
| Số hop cho use case | Nhiều CRUD service calls | Ít boundary calls có ý nghĩa |
| Release coordination | Nhiều service deploy cùng lúc | Owner deploy độc lập khi contract tương thích |
| Data ownership | Nhiều service ghi cùng bảng | Một logical owner cho write |
| Transaction | Trạng thái dở dang khó xử lý | Invariant nội bộ rõ, workflow phân tán có saga |
| Incident routing | Tìm nhiều team để hiểu bảng | Owner của capability nhận alert |
| Change lead time | Nhiều chờ đợi | Giảm wait time/handoff |
| Failure isolation | Lỗi lan qua nhiều hop | Failure behavior và timeout rõ |
| Observability | Trace nhiều hop kỹ thuật vô nghĩa | Trace theo user journey và domain operation |
| Cognitive load | Nhiều service nhỏ phải hiểu | Team sở hữu năng lực trọn vẹn |
| Cost | Nhiều runtime/pipeline | Tổng chi phí vòng đời phù hợp hơn |

Không kỳ vọng mọi metric đều tốt lên ngay. Khi chuyển sang service boundary đúng, có thể tăng công sức ban đầu cho data migration, contract và reconciliation. Đánh giá theo lợi ích dài hạn và độ an toàn của quá trình.

## 31. Test kiến trúc để ngăn tái diễn

Có thể dùng architecture tests để bảo vệ module boundary:

- Order module không import Payment persistence entity.
- Payment không truy cập Order repository.
- Controller không gọi trực tiếp JDBC.
- Repository chỉ nằm trong adapter/infrastructure package.
- Domain model không phụ thuộc framework web.
- Cross-context communication đi qua public API/event contract.
- Service không dùng chung credentials ghi nhiều schema nếu không có lý do.
- Không import common module chứa domain entity không thuộc owner.

Các công cụ như ArchUnit có thể kiểm tra dependency giữa package/class trong Java. Module system của Java hoặc Gradle multi-project có thể tăng cường boundary. Test chỉ hữu ích nếu phản ánh kiến trúc mong muốn và được chạy trong CI.

Ví dụ ý tưởng ArchUnit:

~~~java
@AnalyzeClasses(packages = "com.example")
class ArchitectureRulesTest {

    @ArchTest
    static final ArchRule domainShouldNotDependOnWeb =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("org.springframework.web..");
}
~~~

Cú pháp/import cần phù hợp phiên bản ArchUnit. Ví dụ chỉ minh họa một rule; không thể kiểm tra bounded context hoàn chỉnh chỉ bằng package name.

## 32. Quan sát hệ thống sau khi thay đổi boundary

Khi hợp nhất nhiều layer service, số network hop giảm nhưng cần xác nhận:

- Latency end-to-end có cải thiện?
- Throughput/connection pool có thay đổi?
- Một deployable lớn hơn có tăng blast radius?
- Scale profile có còn phù hợp?
- Database contention có tăng?
- SLO của capability có phản ánh đúng hành trình?
- Logs/traces có giữ correlation?
- Rollback có tương thích schema và data không?

Khi tách một domain service, cần thêm:

- Service-level SLI/SLO và owner.
- Timeout/deadline/retry/circuit breaker.
- API/event contract tests.
- Capacity và dependency monitoring.
- Backup/restore và disaster recovery.
- On-call, runbook và escalation.
- Cost của network, compute, telemetry và platform usage.

Đừng coi việc chuyển code sang một repository mới là hoàn tất refactor. Ranh giới runtime cần có khả năng vận hành thực tế.

## 33. Incident do phân rã sai

### 33.1. Order được tạo nhưng item bị thiếu

OrderTableService commit header; OrderItemTableService timeout. Không có transaction chung. Người dùng nhận orderId nhưng đơn không có item.

Cải tiến: gom header/items vào Order transaction boundary; nếu có workflow phân tán, dùng trạng thái rõ và compensation. Alert nên đo order completeness, không chỉ HTTP 200.

### 33.2. Repository Service outage làm toàn hệ thống dừng

Mọi domain service gọi một RepositoryService tập trung. Một thay đổi connection pool gây outage cho tất cả.

Cải tiến: giữ repository adapter bên trong owner service hoặc cung cấp database platform ở cấp hạ tầng. Không tạo một remote persistence hop cho mọi truy vấn.

### 33.3. Layer release không tương thích

BusinessService phát response field mới, ControllerService cũ không parse. Release phải đồng bộ và rollback khó.

Cải tiến: nếu các layer không có lifecycle độc lập, hợp nhất deployable. Nếu có ranh giới thực sự, thiết kế contract versioned và compatibility window.

### 33.4. Direct database access phá ownership

Payment ghi Order status trực tiếp. Order đổi enum và migration, Payment bắt đầu lỗi âm thầm.

Cải tiến: Payment phát PaymentCaptured; Order consumer cập nhật state qua domain handler. Consumer không phụ thuộc bảng nội bộ.

### 33.5. Một CRUD service trở thành bottleneck

Mọi service gọi GenericDataService, database pool cạn và latency tăng. Không ai biết query nào thuộc domain nào.

Cải tiến: xác định owner và workload theo domain, tách quyền, query path và quota; không expose generic database API làm contract nghiệp vụ.

## 34. Các trade-off cần cân nhắc

| Quyết định | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Một service cho mỗi bảng | Ranh giới code có vẻ đơn giản | Nhiều hop, transaction phân tán, CRUD coupling |
| Một service cho mỗi layer | Tách trách nhiệm kỹ thuật | Deploy/network coupling, failure propagation |
| Gom nhiều bảng theo bounded context | Giữ invariant và ownership | Service có thể lớn hơn, cần module discipline |
| Modular monolith | Ít network overhead, dễ transaction | Deploy chung, cần quản lý module boundaries |
| Domain microservices | Release/scale/ownership độc lập | Distributed systems, on-call và contract cost |
| Shared database cluster | Tối ưu vận hành hạ tầng | Phải tách schema/role/owner để tránh shared writes |
| Domain API | Một nguồn quyết định | Runtime dependency và latency |
| Event-driven integration | Giảm temporal coupling | Eventual consistency, replay, duplicate và schema evolution |

Không có quy tắc “càng nhiều service càng tốt” hoặc “càng ít service càng tốt”. Cần tối ưu tổng chi phí delivery, runtime, reliability, coordination và cognitive load.

## 35. Quy trình review một đề xuất tách service

Trước khi tạo service mới, hãy viết một proposal ngắn:

1. Capability hoặc bounded context mới là gì?
2. Người dùng/consumer nào cần nó?
3. Business invariants nào nằm trong ranh giới?
4. Dữ liệu nào sẽ thuộc owner mới?
5. Những thao tác nào cần transaction cùng nhau?
6. API/event contract nào được công bố?
7. Consumer có thể nâng độc lập không?
8. Failure mode, timeout, retry và fallback ra sao?
9. SLO, dashboard, runbook và on-call ai sở hữu?
10. Có năng lực platform để deploy, secure, observe và recover không?
11. Chi phí hạ tầng và cognitive load mới là bao nhiêu?
12. Vì sao module nội bộ hoặc modular monolith chưa đủ?
13. Migration và rollback dữ liệu thế nào?
14. Tiêu chí thành công sau 30/60/90 ngày là gì?

Nếu chưa trả lời được data owner, failure behavior và on-call, có thể cần làm rõ domain/module boundary trước khi tách runtime.

## 36. Bài thực hành: tái thiết kế ứng dụng bán hàng

### Thiết kế ban đầu

Một ứng dụng có các service:

- CustomerTableService
- AddressTableService
- ProductTableService
- OrderHeaderService
- OrderItemService
- PaymentTableService
- InventoryTableService
- ControllerService
- BusinessLogicService
- RepositoryService

Mỗi request đi qua ControllerService, BusinessLogicService, RepositoryService rồi gọi các table services.

### Nhiệm vụ

1. Nhóm các bảng theo bounded context.
2. Xác định aggregate và invariant của Order, Payment và Inventory.
3. Đề xuất service boundary và owner team.
4. Chọn API/event cho CreateOrder, ReserveInventory và CapturePayment.
5. Xác định transaction nội bộ và saga workflow.
6. Lập danh sách consumer đang ghi trực tiếp bảng.
7. Đề xuất expand-contract và strangler migration.
8. Thiết kế dashboard/SLO và incident routing.
9. Chỉ ra những module nên giữ trong cùng deployable.
10. Đưa ra tiêu chí khi nào migration hoàn tất.

### Một hướng thiết kế tham khảo

~~~text
                 API Gateway / BFF
                         |
                     Checkout
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       Catalog         Order          Payment
                         |
                         v
                     Inventory

Platform capabilities:
  Runtime, CI/CD, secrets, observability,
  database provisioning, message broker
~~~

Sơ đồ chỉ là một điểm khởi đầu. Catalog/Pricing có thể tách hoặc kết hợp; Checkout có thể là orchestration module trong Order tùy domain và transaction requirements. Điều quan trọng là các team không ghi xuyên dữ liệu của nhau.

## 37. Bài tập tự luyện

### Bài A — Phân rã theo bảng

Một hệ thống có 20 bảng và nhóm đề xuất 20 microservices. Hãy nêu ít nhất năm vấn đề dự kiến, nhóm bảng theo domain và xác định dữ liệu authoritative.

### Bài B — Phân rã theo layer

ControllerService, BusinessService và RepositoryService phải release cùng lúc. Hãy giải thích vì sao đó là distributed monolith và đưa phương án hợp nhất deployable nhưng vẫn giữ separation of concerns trong code.

### Bài C — Transaction boundary

Order header và items cần commit nguyên tử. Payment và Inventory có database riêng. Hãy xác định aggregate boundary, saga steps, compensation và trạng thái unknown outcome.

### Bài D — Shared database

Payment, Order và Inventory cùng ghi một bảng transaction. Hãy đề xuất cách phân quyền, contract, migration và kế hoạch chặn direct writes.

### Bài E — API thiết kế theo intent

Thay API CRUD trên bảng orders bằng API biểu đạt CreateOrder, ConfirmOrder, CancelOrder và GetOrderSummary. Mô tả validation, idempotency và error semantics.

### Bài F — Service boundary decision

Một bảng inventory có logic reservation, expiry, allocation và reconciliation. Hãy giải thích vì sao có thể xứng đáng là Inventory Service và những năng lực nào cần nằm cùng boundary.

### Bài G — Modular monolith

Một nhóm 6 người quản lý 8 service nhỏ nhưng deploy cùng nhau. Hãy thiết kế modular monolith với package/module boundaries và architecture tests.

### Bài H — Strangler migration

Chuyển OrderTableService sang Order Service trong khi hệ thống cũ vẫn chạy. Thiết kế routing, data migration, source of truth, reconciliation và rollback.

### Bài I — Chatty API

Một màn hình gọi 12 service để hiển thị Order Summary. Hãy xác định dữ liệu snapshot, read model, API composition và freshness requirements.

### Bài J — Incident

Order header được tạo nhưng item thiếu do OrderItemService timeout. Hãy viết triage, mitigation, data repair, root cause và architecture action items.

### Bài K — Release coupling

Một shared entity library khiến 15 service phải nâng cùng lúc. Hãy thiết kế contract/schema versioning và kế hoạch tách domain model khỏi shared library.

### Bài L — Đo kết quả

Đề xuất metric trước/sau refactor: number of hops, wait time, coordinated deploys, incident time to owner, data inconsistency và user journey SLI.

## 38. Checklist nhận diện ranh giới sai

Hãy xem xét lại kiến trúc nếu có nhiều dấu hiệu sau:

- Service tương ứng trực tiếp với một bảng hoặc một CRUD operation.
- Một user action cần gọi nhiều service chỉ để đọc/ghi các bảng liên quan.
- Controller, business logic và repository chạy ở các process riêng nhưng luôn deploy cùng nhau.
- Nhiều service cùng ghi một schema hoặc bảng.
- Consumer biết cấu trúc persistence nội bộ của producer.
- Thay đổi một field nội bộ buộc nhiều service sửa.
- Một transaction nghiệp vụ thường xuyên bị chia thành nhiều request.
- Business invariant không có một owner rõ.
- Service nhỏ không có SLO/on-call/runbook độc lập.
- API chủ yếu expose CRUD thay vì business intent.
- Một shared data service trở thành bottleneck cho mọi domain.
- Incident mất nhiều thời gian tìm owner hoặc tái dựng trạng thái.
- Team phải hiểu quá nhiều service không cùng domain.
- Tách service làm tăng deploy coordination thay vì giảm.
- Hệ thống cần release train đồng bộ cho thay đổi thường xuyên.

Một dấu hiệu riêng lẻ không chứng minh kiến trúc sai. Hãy xem tần suất, tác động, chi phí và khả năng sửa trong phạm vi hiện tại.

## 39. Nguyên tắc thiết kế để tránh tái diễn

1. Chia theo capability và bounded context, không theo bảng hoặc tầng code.
2. Giữ các invariant cần transaction cùng nhau trong một owner boundary khi phù hợp.
3. Mỗi logical data set có một owner authoritative cho writes.
4. Expose business API/event, không expose schema nội bộ.
5. Giữ controller/application/domain/repository layers bên trong service khi chúng không có lifecycle độc lập.
6. Dùng contract/versioning và automated compatibility tests để giảm synchronized release.
7. Chỉ tạo service mới khi có lý do về ownership, scale, security, release hoặc failure isolation.
8. Thiết kế timeout, retry, idempotency và reconciliation trước khi phân tán workflow.
9. Bảo đảm service có owner, SLO, dashboard, runbook và on-call.
10. Dùng modular monolith khi domain boundary chưa ổn định hoặc team chưa cần phân tán runtime.
11. Tách platform capabilities khỏi domain rules; platform không trở thành generic CRUD/business engine.
12. Đo tổng chi phí thay đổi và vận hành, không đo trưởng thành bằng số microservice.

## 40. Kết luận

Chia mỗi bảng database thành một service hoặc tách controller, business logic và repository thành các process riêng thường làm tăng số network hop, release dependencies và điểm có thể xảy ra lỗi. Cấu trúc đó phản ánh cách code được lưu hoặc cách tầng kỹ thuật được tổ chức, nhưng không nhất thiết phản ánh cách doanh nghiệp tạo giá trị và bảo vệ dữ liệu.

Một service boundary tốt thường nằm quanh **bounded context hoặc business capability**: nhóm sở hữu hiểu hành vi, quản lý dữ liệu và invariant, công bố contract có phiên bản, vận hành SLO và có thể thay đổi nội bộ độc lập. Nhiều bảng có thể thuộc cùng một service; nhiều lớp kỹ thuật có thể cùng chạy trong một deployable; các context khác nhau giao tiếp qua API/event và xử lý consistency theo contract.

Khi refactor, hãy chuyển từng hành vi và quyền ghi có kiểm soát: xác định owner, thiết kế contract, giữ tương thích, chuyển traffic, đối chiếu dữ liệu và chỉ loại bỏ đường cũ sau khi đã chứng minh hệ thống mới đúng. Nếu lợi ích độc lập chưa vượt chi phí distributed operations, giữ một modular monolith có module boundary rõ cũng là quyết định kiến trúc tốt. Mục tiêu là giảm tổng chi phí thay đổi, giữ dữ liệu đúng và giúp đội chịu trách nhiệm trọn vẹn về năng lực mà người dùng thực sự cần.
