# Chuẩn hóa mô-đun trước khi tách tiến trình khi phù hợp

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Chuyển đổi kiến trúc (Architecture Modernization)  
> **Mục tiêu:** Biết cách làm rõ ranh giới mô-đun, quyền sở hữu dữ liệu, dependency và hợp đồng nội bộ trước khi tách một phần ứng dụng thành tiến trình hoặc service độc lập; hiểu vì sao modularization là bước giảm coupling, cách kiểm chứng boundary và cách chọn đúng thời điểm tách mà không biến một monolith khó bảo trì thành một distributed monolith khó vận hành hơn.

## 1. Vì sao nên chuẩn hóa mô-đun trước khi tách tiến trình?

Một ứng dụng nguyên khối thường được triển khai như một tiến trình, nhưng bên trong có thể chứa nhiều domain và module. Khi tổ chức muốn chuyển sang microservices, phản xạ thường là chọn một nhóm class, tạo một repository mới, dựng container và chuyển code sang service riêng.

Cách làm đó có thể tạo thêm một tiến trình mà **không làm rõ quyền sở hữu, dữ liệu và hợp đồng**. Các module mới vẫn phụ thuộc vào class nội bộ, truy vấn chung database, gọi ngược qua lại hoặc cùng cần release. Kết quả là distributed monolith: hệ thống phân tán qua network nhưng coupling vẫn chặt, trong khi chi phí deploy, tracing, retry, timeout và incident tăng lên.

Chuẩn hóa mô-đun trước giúp tìm ranh giới có ý nghĩa khi code vẫn còn trong cùng một process. Ta có thể thay đổi interface, kiểm soát dependency, tách ownership dữ liệu và kiểm thử contract với chi phí thấp hơn so với lúc đã có network và nhiều deployment unit.

~~~text
Trước khi modularize

+---------------------------------------------------+
|                 Monolithic Application            |
|                                                   |
|  Order code <----> Customer code                  |
|      |                 |                          |
|      +------> Shared database <----- Inventory    |
|      |                 |                          |
|  Billing code <---- Shared utility library        |
|                                                   |
|  Implicit calls, shared tables, hidden coupling   |
+---------------------------------------------------+

Sau khi modularize trong cùng process

+---------------------------------------------------+
|                 Modular Monolith                  |
|                                                   |
|  +-----------+    +-------------+                 |
|  | Order     |--->| Customer    |                 |
|  | Module    |    | Public API  |                 |
|  +-----------+    +-------------+                 |
|       |                                           |
|  +-----------+    +-------------+                 |
|  | Inventory |    | Billing     |                 |
|  | Module    |    | Module      |                 |
|  +-----------+    +-------------+                 |
|                                                   |
|  Explicit interfaces, owned data, checked deps    |
+---------------------------------------------------+

Chỉ tách tiến trình khi boundary đã có bằng chứng

Order Process ---> Customer Process
      |
      +----------> Inventory Process
      |
      +----------> Billing Process
~~~

**Modularization không phải bước trang trí trước microservices.** Đây là quá trình biến các phụ thuộc ngầm thành hợp đồng rõ, để biết phần nào có thể thay đổi độc lập, phần nào cần phối hợp và phần nào chưa nên tách.

Một modular monolith tốt có thể là kiến trúc đích trong thời gian dài. Tách tiến trình là một lựa chọn sau khi có lý do cụ thể như scale độc lập, failure isolation, ownership tổ chức hoặc yêu cầu bảo mật; không phải kết quả bắt buộc của việc modularize.

## 2. Phân biệt module, component, process và service

Các từ này thường được dùng lẫn nhau, nhưng chúng mô tả những ranh giới khác nhau:

| Khái niệm | Ranh giới | Đặc điểm |
|---|---|---|
| Package / namespace | Tổ chức code | Giúp nhóm class; không tự ngăn dependency |
| Module | Ranh giới trách nhiệm và API trong codebase | Có interface, implementation và quy tắc phụ thuộc |
| Component | Đơn vị cấu thành có trách nhiệm rõ | Có thể nằm trong một module hoặc gồm nhiều module |
| Process | Không gian thực thi độc lập của hệ điều hành/container | Có memory, lifecycle, failure và resource riêng |
| Service | Năng lực nghiệp vụ được cung cấp qua contract | Có owner, API/event, vận hành và lifecycle |
| Microservice | Service nhỏ với boundary và ownership độc lập | Thường deploy, scale và vận hành riêng |

Một package tên inventory không chứng minh Inventory là module độc lập. Nếu Order có thể import class implementation, sửa trực tiếp bảng inventory và gọi static method nội bộ, ranh giới chưa được bảo vệ.

Ngược lại, một module có thể là một service nghiệp vụ rõ ràng dù chưa chạy ở process riêng. Nó đã có thể có:
- Public interface được công bố.
- Internal implementation không bị consumer truy cập.
- Data ownership.
- Dependency direction.
- Test cho contract và invariant.
- Owner và cách thay đổi có kiểm soát.

**Ranh giới logic và ranh giới triển khai không bắt buộc phải trùng ngay từ đầu.** Hãy làm rõ logic trước, rồi quyết định deployment topology theo nhu cầu.

## 3. Mục tiêu của modularization

Một module được chuẩn hóa tốt thường đạt những kết quả sau:

1. **Cohesion cao:** các hành vi và dữ liệu phục vụ cùng một trách nhiệm nghiệp vụ ở gần nhau.
2. **Coupling thấp và tường minh:** consumer chỉ phụ thuộc interface được công bố, không truy cập implementation.
3. **Ownership rõ:** biết nhóm nào quyết định semantics, dữ liệu và thay đổi.
4. **Data boundary:** module quản lý dữ liệu của mình và không để module khác sửa trực tiếp.
5. **Dependency direction có kiểm soát:** không có vòng phụ thuộc tùy tiện.
6. **Contract có thể kiểm thử:** behavior ở boundary được mô tả và test.
7. **Thay đổi có phạm vi:** refactor bên trong không buộc mọi module khác sửa theo.
8. **Khả năng vận hành:** biết module cần tài nguyên, telemetry và failure behavior nào.
9. **Khả năng tách có căn cứ:** nếu cần, interface hiện có có thể chuyển từ call nội bộ sang network contract với thay đổi được dự đoán.
10. **Không tạo abstraction vô ích:** số module và lớp interface phản ánh trách nhiệm thực, không chỉ tăng số folder.

Mục tiêu không phải tạo nhiều module nhất có thể. Một module quá nhỏ, chỉ bọc một class và không có ownership riêng, có thể tăng ceremony mà không tạo boundary hữu ích.

## 4. Bắt đầu từ domain và use case, không bắt đầu từ package hiện tại

Một cách phân chia theo kỹ thuật như controller, service, repository có thể giúp tổ chức code, nhưng chưa chắc tạo boundary nghiệp vụ. Ví dụ mọi controller ở một module, mọi repository ở module khác khiến một thay đổi nghiệp vụ phải đi qua nhiều package và các module phụ thuộc lẫn nhau.

Hãy bắt đầu bằng các capability và use case:
- Quản lý catalog và giá.
- Quản lý tồn kho và reservation.
- Tạo và theo dõi đơn hàng.
- Tính phí và xử lý thanh toán.
- Quản lý tài khoản khách hàng.
- Giao hàng và theo dõi fulfillment.
- Gửi thông báo.

Sau đó tìm các nhóm dữ liệu, quy tắc và hành vi thay đổi cùng nhau. Một bounded context có thể chứa nhiều use case nhưng chia sẻ một mô hình nhất quán.

### 4.1. Dùng domain language để phát hiện boundary

Từ ngữ giống nhau không nhất thiết có cùng semantics. “Customer” trong Sales, Billing, Support và Fulfillment có thể mô tả những vai trò khác nhau. Đừng tạo một Customer module khổng lồ chỉ vì các bảng đều có customer_id.

Một workshop domain có thể ghi:
- Actor và mục tiêu nghiệp vụ.
- Command hoặc hành động.
- Event phát sinh.
- Invariant phải bảo vệ.
- Dữ liệu được sở hữu.
- Các thuật ngữ gây nhầm.
- Hệ thống/nhóm đang thực hiện trách nhiệm.
- Tần suất thay đổi và điểm xung đột.

### 4.2. Event storming và domain mapping

Một sơ đồ sự kiện đơn giản:

~~~text
Customer places order
       |
       v
OrderRequested
       |
       v
Inventory reserves items
       |
       +-- ReservationRejected
       |
       v
ReservationConfirmed
       |
       v
Payment authorized
       |
       +-- PaymentRejected
       |
       v
OrderConfirmed
       |
       +--> FulfillmentRequested
       |
       +--> CustomerNotified
~~~

Sơ đồ giúp nhận ra:
- Ai sở hữu từng trạng thái?
- Event nào là sự kiện nghiệp vụ đã xảy ra?
- Ai chỉ phát lệnh, ai xác nhận kết quả?
- Có bước nào cần transaction đồng bộ?
- Có bước nào phù hợp async?
- Khi lỗi, ai chịu trách nhiệm compensation hoặc reconciliation?

Không lấy tên event làm boundary một cách máy móc. Một event có thể được nhiều consumer sử dụng; ownership nằm ở domain tạo ra ý nghĩa sự kiện.

## 5. Tìm dấu hiệu coupling trong code hiện tại

Trước khi sửa, lập bản đồ dependency ở mức module và các điểm truy cập dữ liệu. Tìm những dấu hiệu:

- Module A import class implementation của module B.
- Nhiều module ghi cùng bảng hoặc cùng aggregate.
- Shared utility chứa nghiệp vụ của nhiều domain.
- Static global state được nhiều module sử dụng.
- Circular dependencies giữa package/module.
- Một module cần biết cấu trúc bảng nội bộ của module khác.
- Consumer đọc field nội bộ thay vì gọi API.
- Một thay đổi thường chạm nhiều nhóm class không liên quan.
- Một test cần khởi động gần như toàn ứng dụng để kiểm tra logic nhỏ.
- Một module không thể triển khai hoặc rollback mà không ảnh hưởng nhiều phần.

### 5.1. Dependency graph

Có thể mô hình hóa module như node, dependency như edge:

~~~text
Web API
   |
   v
Order Module ------> Inventory Module
   |                       |
   v                       v
Customer Module       Inventory Store
   |
   v
Customer Store

Billing Module ------> Payment Provider
~~~

Đây là ví dụ topology, không phải gợi ý để Order được phép truy cập Inventory Store. Dependency nên hướng tới public API của module, không phải storage implementation.

### 5.2. Dùng static analysis và build graph

Công cụ có thể giúp:
- Phát hiện package cycles.
- Tìm import vượt boundary.
- Xác định module không có consumer.
- Tìm class được dùng xuyên nhiều domain.
- Kiểm tra module chỉ phụ thuộc API module khác.
- Xác định module có dependency graph quá rộng.
- Tìm shared mutable state.
- Phát hiện module có test/build phụ thuộc toàn bộ monolith.

Các công cụ Java có thể gồm Maven/Gradle module graph, ArchUnit, jQAssistant hoặc dependency analysis. Chọn công cụ phù hợp codebase; không cần cài tất cả. Kết quả static analysis cần review ngữ nghĩa, vì một dependency hợp lệ không phải lúc nào cũng nên bị chặn.

### 5.3. Không chỉ đếm số import

Một module có ít import nhưng gọi một shared database procedure có thể coupling rất mạnh. Một module có nhiều dependency qua interface ổn định có thể ít coupling hơn. Hãy đánh giá **chi phí thay đổi và semantics**, không chỉ số cạnh trong graph.

## 6. Xác định public API và internal implementation

Mỗi module nên có một bề mặt công khai nhỏ, ổn định, mô tả những hành động consumer được phép yêu cầu và kết quả được đảm bảo.

Ví dụ Order Module:

~~~text
order/
  api/
    OrderCommands
    OrderQueries
    OrderCreated
    OrderStatus
  internal/
    application/
    domain/
    persistence/
    adapters/
~~~

Consumer được phép gọi OrderCommands hoặc OrderQueries. Consumer không được import internal.persistence.OrderRepository hoặc tự thao tác bảng orders.

### 6.1. API module nên diễn đạt use case

Ví dụ:

~~~java
public interface OrderCommands {
    OrderConfirmation placeOrder(PlaceOrder command);
    void cancelOrder(CancelOrder command);
}

public interface OrderQueries {
    Optional<OrderSummary> findById(OrderId orderId);
}
~~~

Các kiểu dữ liệu ở đây là contract. Chúng nên nhỏ và có ý nghĩa nghiệp vụ, không expose entity ORM hoặc class framework cụ thể.

### 6.2. Không expose implementation detail

Tránh public:
- Entity JPA gắn với schema nội bộ.
- Repository interface cho phép query tùy ý.
- Mutable collection dùng chung.
- Internal exception class gắn framework.
- Cấu hình connection hoặc transaction manager.
- Table/column names.
- Internal domain service mà consumer không nên điều khiển.

Nếu public API trả JPA entity, consumer có thể vô tình dựa vào lazy loading, quan hệ và cột mới; việc đổi ORM hoặc schema sẽ trở thành breaking change.

### 6.3. Interface không tự tạo ra boundary

Một interface tên IOrderService nhưng nhận mọi bảng và trả object chung có thể chỉ là lớp bọc. Boundary thực sự cần:
- Hành vi có trách nhiệm.
- Data ownership.
- Invariant.
- Quy tắc dependency.
- Contract và test.
- Consumer không truy cập phần nội bộ.

## 7. Enforce dependency direction

Một cấu trúc module có thể quy định:
- Application layer gọi domain và port.
- Adapter triển khai port để nối DB/API.
- Module khác chỉ gọi public API.
- Domain không phụ thuộc framework hoặc module ngoài nếu kiến trúc yêu cầu.
- Infrastructure không được import ngược business implementation.

Ví dụ:

~~~text
Order Public API
       ^
       |
Order Application
       |
       v
Order Domain
       ^
       |
Order Adapters implement ports
       |
       +---- Database
       +---- Message Broker
       +---- External Payment API
~~~

Sơ đồ có thể thay đổi tùy kiến trúc; điểm quan trọng là dependency có hướng và được kiểm tra.

### 7.1. Dependency inversion

Domain/application không cần biết JDBC, Kafka hay HTTP client cụ thể. Nó định nghĩa port cho nhu cầu của mình; adapter triển khai port.

Ví dụ:

~~~java
public interface InventoryReservationPort {
    ReservationResult reserve(ReservationRequest request);
}

public final class PlaceOrderHandler {
    private final InventoryReservationPort inventory;

    public PlaceOrderHandler(InventoryReservationPort inventory) {
        this.inventory = inventory;
    }

    public OrderConfirmation handle(PlaceOrder command) {
        // Validate command, coordinate domain behavior,
        // and use the port without depending on transport details.
        return null; // Pseudocode placeholder for domain-specific logic.
    }
}
~~~

Đoạn mã là minh họa boundary, không phải implementation hoàn chỉnh. Trong code thực tế cần xử lý transaction, idempotency, errors và domain invariants. Port nên thuộc về consumer/domain cần capability, không nhất thiết được đặt trong module provider nếu điều đó tạo dependency ngược.

### 7.2. Tránh abstraction quá sớm

Không tạo interface cho mọi class chỉ để “dễ tách service”. Interface có ích khi mô tả contract, tạo điểm thay thế có ý nghĩa hoặc cô lập dependency. Một interface một implementation, không có boundary và không có consumer độc lập, có thể chỉ tăng indirection.

## 8. Data ownership là phần quan trọng nhất của modularization

Một module không thực sự sở hữu domain nếu mọi module khác có thể sửa trực tiếp dữ liệu của nó.

Trong modular monolith, các module có thể cùng dùng một database server, nhưng cần phân biệt:
- **Shared database infrastructure:** có thể dùng chung engine/cluster.
- **Owned schema/table:** một module chịu trách nhiệm về cấu trúc và invariant.
- **Cross-module query:** qua API hoặc projection đã công bố.
- **Cross-module write:** qua command/API hoặc event workflow được quản lý.
- **Shared transaction:** dấu hiệu cần xem lại boundary và business invariant.

Ví dụ:

~~~text
One PostgreSQL cluster
  |
  +-- order schema
  |     owner: Order Module
  |
  +-- inventory schema
  |     owner: Inventory Module
  |
  +-- customer schema
        owner: Customer Module

Order code cannot UPDATE inventory tables directly.
Inventory changes its own state and returns a contract result.
~~~

Schema riêng không tự bảo vệ nếu mọi code dùng cùng database user có quyền ghi tất cả. Có thể tăng enforcement bằng DB grants, separate repositories, module APIs và CI checks.

### 8.1. Không dùng shared entity làm mô hình liên module

Nếu Order, Billing và Fulfillment cùng import CustomerEntity, thêm field mới hoặc thay mapping có thể ảnh hưởng tất cả. Mỗi module nên dùng representation phù hợp mục đích:
- CustomerRef.
- BillingParty.
- DeliveryRecipient.
- SupportContact.

Các representation có thể ánh xạ về cùng một người nhưng không có nghĩa phải là một class dùng chung.

### 8.2. Module có thể sở hữu read projection

Một module cần hiển thị thông tin từ module khác có thể giữ projection được phép để tối ưu query, nhưng phải có:
- Contract field rõ.
- Source/version.
- Quy tắc cập nhật.
- Semantics eventual consistency.
- Deletion/correction propagation.
- Owner và retention.

Projection không phải quyền tự do copy toàn bộ bảng. Nó là một bản sao có mục đích và hợp đồng.

### 8.3. Cross-module transaction

Nếu một use case cần cập nhật hai schema trong cùng process, có thể tạm dùng một transaction DB chung. Tuy nhiên hãy hỏi:
- Có invariant nào thực sự đòi atomic update không?
- Hai module có đang sở hữu cùng một aggregate?
- Có thể tách workflow thành reservation/confirmation với compensation không?
- Khi chuyển sang process riêng, semantics có thay đổi không?

Không nên vội thay mọi transaction bằng event async. Nhưng cũng không nên giữ một transaction xuyên nhiều domain chỉ vì code hiện nằm cùng process, nếu boundary tương lai cần độc lập.

## 9. Quy tắc chống circular dependency

Circular dependency làm cho module không thể thay đổi riêng. Ví dụ:

~~~text
Order Module ---> Customer Module
     ^                 |
     |                 v
     +------------- Notification Module
~~~

Một vòng có thể khiến build/test/deploy phải hiểu nhiều module cùng lúc. Cách xử lý:
- Xác định capability nào thuộc domain nào.
- Chuyển interface về phía consumer cần nó.
- Dùng domain event cho thông báo sau khi sự kiện đã xảy ra.
- Tạo shared kernel nhỏ chỉ khi semantics thật sự ổn định và ownership chung được chấp nhận.
- Tách orchestration ra application/workflow module khi có trách nhiệm riêng.
- Loại bỏ tiện ích “shared” nhưng chứa logic domain.

Không phải mọi vòng import đều có thể sửa bằng event. Nếu hai module luôn cần một transaction/invariant duy nhất, có thể chúng chưa phải hai boundary độc lập.

### 9.1. Kiểm tra vòng dependency trong CI

Một architecture test có thể xác nhận module A không phụ thuộc module B internal, hoặc graph không có cycle. Test nên dựa trên boundary có chủ sở hữu, không chỉ cấm mọi dependency.

Khi có ngoại lệ, ghi rõ lý do, phạm vi và kế hoạch xem lại. Không để suppression annotation tồn tại vô thời hạn mà không ai quản lý.

## 10. Chuẩn hóa build và repository structure

Có thể tổ chức modular monolith theo Maven multi-module:

~~~text
commerce/
  pom.xml
  app/
    pom.xml
  order-api/
    pom.xml
  order-impl/
    pom.xml
  inventory-api/
    pom.xml
  inventory-impl/
    pom.xml
  customer-api/
    pom.xml
  customer-impl/
    pom.xml
~~~

Hoặc Gradle multi-project:

~~~text
commerce/
  settings.gradle
  app/
  modules/
    order/
      api/
      implementation/
    inventory/
      api/
      implementation/
    customer/
      api/
      implementation/
~~~

Đây là hai lựa chọn, không phải cấu trúc bắt buộc. Có thể bắt đầu với một build và package boundary rồi tách build module khi cần. Mục tiêu là enforce dependency và build nhanh, không phải tạo nhiều artifact nhất.

### 10.1. Chọn granularity vừa phải

Một module quá lớn có thể chứa nhiều domain không liên quan; module quá nhỏ tạo hàng chục API module và build dependency không cần thiết.

Đánh giá:
- Một nhóm trách nhiệm có thể mô tả rõ không?
- Các class có thay đổi cùng nhau không?
- Có owner rõ không?
- Có dữ liệu và invariant riêng không?
- Consumer cần API nào?
- Có lý do scale/deploy độc lập trong tương lai không?
- Module có quá nhiều phụ thuộc chéo không?

Một bounded context có thể chứa nhiều package; một module build có thể chứa vài component. Không ép một bounded context = một Maven artifact = một microservice trong mọi trường hợp.

## 11. Chuẩn hóa các contract nội bộ trước khi có network

Call nội bộ thường nhanh và không có serialization. Khi tách process, các giả định ngầm sẽ lộ ra:
- Call có thể timeout.
- Response có thể mất dù server đã xử lý.
- Caller có thể retry và tạo duplicate.
- Payload cần versioning.
- Network latency và partial failure xuất hiện.
- Authentication/authorization phải qua boundary.
- Schema evolution cần backward compatibility.

Vì vậy API module nên được thiết kế với semantics đủ rõ:
- Command và query khác nhau.
- Input validation và error classification.
- Idempotency cho command có side effect.
- Deadline/timeout expectation.
- Pagination/size limits.
- Consistency guarantee.
- Event publication semantics.
- Data classification và consumer purpose.

Không cần mô phỏng network cho mọi method. Nhưng các use case có khả năng thành service boundary nên tránh dựa vào object mutable, thread-local, shared transaction hoặc exception framework không thể biểu diễn qua contract.

### 11.1. Command/query separation ở mức phù hợp

Ví dụ:
- PlaceOrder là command có side effect.
- FindOrderSummary là query.
- OrderConfirmed là event mô tả điều đã xảy ra.

Không dùng một method kiểu process(data) vừa đọc, ghi, phát event và trả mọi trạng thái. Contract rõ giúp consumer hiểu semantics, test được và sau này chuyển transport dễ hơn.

### 11.2. Error contract

Phân biệt:
- Validation/business rejection.
- Resource not found.
- Conflict hoặc state transition không hợp lệ.
- Authentication/authorization failure.
- Dependency unavailable/timeout.
- Internal unexpected failure.

Khi tách process, các exception trong JVM không thể đi nguyên trạng qua network. Hãy định nghĩa error code/domain result và retryability. Không retry lỗi business permanent như OUT_OF_STOCK theo cách vô hạn.

## 12. Tách dần bằng adapter thay vì viết lại toàn bộ

Một chiến lược hữu ích là giữ module boundary ổn định và thay implementation phía sau interface.

~~~text
Before extraction

Order Module
    |
    v
InventoryReservationPort
    |
    v
LocalInventoryAdapter
    |
    v
Inventory Module (same process)


After extraction

Order Module
    |
    v
InventoryReservationPort
    |
    v
RemoteInventoryAdapter
    |
    v
Inventory API (separate process)
~~~

Consumer vẫn phụ thuộc cùng port; chỉ adapter thay đổi từ local call sang HTTP/gRPC/message client. Điều này giảm phạm vi refactor, nhưng **không có nghĩa mọi local method đều nên trở thành remote API**. Chỉ những use case có contract và failure semantics phù hợp mới nên chuyển.

### 12.1. Anti-corruption layer

Adapter có thể chuyển đổi mô hình nội bộ sang contract bên ngoài:
- Domain value objects ↔ wire DTO.
- Domain errors ↔ HTTP/gRPC errors.
- Local transaction context ↔ request deadline.
- Internal IDs ↔ public opaque references.
- Event semantics ↔ schema version.

Lớp chuyển đổi giữ domain không phụ thuộc framework/network và cho phép provider đổi implementation mà không lan thay đổi.

### 12.2. Không để adapter trở thành một service locator

Một interface chung kiểu invoke(serviceName, methodName, payload) có thể che giấu dependency và mất type safety. Dùng port theo capability và adapter cụ thể, để consumer biết rõ nó phụ thuộc năng lực nào.

## 13. Test boundary trước khi tách

Một bộ test nhiều tầng:

| Loại test | Điều cần xác nhận |
|---|---|
| Unit test | Domain rules và invariant của module |
| Module integration test | API module và implementation phối hợp đúng |
| Architecture test | Dependency direction, no cycle, internal package isolation |
| Contract test | Consumer và provider đồng ý về behavior/schema |
| Persistence test | Mapping, transaction, migration và data ownership |
| Workflow test | Saga/transaction behavior qua các module |
| Performance test | Query count, latency và resource profile |
| Failure simulation | Timeout, duplicate command, dependency unavailable |
| Security test | Authorization, tenant isolation, data minimization |
| Migration test | Phiên bản cũ/mới cùng hoạt động trong rollout |

Không cần chạy mọi test ở mọi commit nếu chi phí quá lớn; nhưng các contract và architecture rules có thể chạy thường xuyên, còn full workflow/performance/failure tests theo pipeline phù hợp.

### 13.1. Test nội bộ không được phụ thuộc implementation detail

Consumer test nên gọi public API và kiểm behavior, không mock private repository hoặc assert tên table của module khác. Nếu test cần biết implementation, có thể boundary đang bị xuyên qua.

### 13.2. Test dữ liệu và side effects

Đặc biệt với command:
- Cùng idempotency key gửi hai lần không tạo hai reservation/payment.
- Duplicate event không áp dụng side effect lặp.
- Out-of-order event không làm state lùi sai.
- Rollback/compensation xử lý trạng thái không xác định.
- Projection cập nhật version đúng.
- Deletion/correction propagation hoạt động.
- Error không làm mất dữ liệu hoặc báo thành công giả.

## 14. Đưa architecture fitness functions vào CI

Quy tắc boundary nên có cách thực thi tự động:
- Module A không import module B internal.
- Không có cycle giữa bounded contexts.
- Public API không expose persistence entity.
- Domain package không phụ thuộc web/framework nếu đó là nguyên tắc đã chọn.
- Event schema có compatibility check.
- API diff phát hiện breaking change.
- Các module không dùng shared database repository ngoài owner.
- Không có secret/PII trong event hoặc log fixture.
- Build/test của module có thể chạy độc lập trong phạm vi cần thiết.

Ví dụ với ArchUnit có thể mô tả:

~~~java
@AnalyzeClasses(packages = "com.example")
class ModuleBoundaryTest {

    @ArchTest
    static final ArchRule order_must_not_depend_on_inventory_internal =
        noClasses()
            .that().resideInAPackage("..order..")
            .should().dependOnClassesThat()
            .resideInAPackage("..inventory.internal..");
}
~~~

Đoạn mã minh họa ý tưởng và cần điều chỉnh package/rule theo phiên bản ArchUnit. Nó không chứng minh module boundary hoàn chỉnh: reflection, SQL, shared database và runtime configuration có thể tạo coupling không thấy qua import.

### 14.1. Fail fast hay cảnh báo?

- Vi phạm bảo mật, data ownership hoặc contract breaking: thường cần chặn.
- Vi phạm convention nhẹ: có thể cảnh báo trong giai đoạn chuyển đổi.
- Legacy exception: cần owner, ticket/ADR, phạm vi và thời hạn.
- Rule mới: chạy ở report mode trước, đánh giá false positives rồi bật enforcement theo lộ trình.

Không bật một architecture rule trên toàn codebase legacy rồi chặn mọi release mà không có migration plan. Nhưng cũng không để warning tồn tại mãi mà không ai xử lý.

## 15. Chuẩn hóa database migration và schema ownership

Một module sở hữu dữ liệu phải sở hữu cả thay đổi schema:
- Migration scripts.
- Index và constraint.
- Data migration.
- Backup/restore assumptions.
- Performance profile.
- Retention/deletion.
- Version compatibility với code cũ/mới.

Nếu nhiều module cùng chạy migration vào một shared schema mà không có owner, một release có thể phá module khác.

### 15.1. Expand-and-contract cho schema

~~~text
Phase 1: Expand
  Add new column/table/index
  Keep old readers and writers working

Phase 2: Migrate
  Dual-read or dual-write where necessary
  Backfill in bounded batches
  Validate data and switch consumers

Phase 3: Contract
  Remove old field/index only after no consumer needs it
~~~

Dual-write có thể tạo consistency issues; nếu dùng phải có cách reconcile và metric. Không giữ hai nguồn sự thật lâu dài mà không định nghĩa source of truth.

### 15.2. Migration khi vẫn là một process

Ngay cả modular monolith cần hỗ trợ code cũ và schema mới trong rolling deployment nếu có nhiều instance. Dùng migration có thể chạy an toàn theo thứ tự và rollback/forward-fix plan rõ.

### 15.3. Chuẩn hóa data access boundary

Một module khác có thể cần dữ liệu từ owner:
- Gọi public query API.
- Subscribe event và xây projection tối thiểu.
- Dùng reporting/read model được phê duyệt.
- Chia sẻ một schema read-only có contract rõ trong trường hợp đặc biệt.

Không cho phép truy cập trực tiếp bảng vì “cùng database nên nhanh hơn” mà không đánh giá coupling và ownership.

## 16. Khi nào module đã đủ sẵn sàng để tách process?

Không có một con số duy nhất, nhưng các tín hiệu mạnh gồm:

**Domain clarity**
- Trách nhiệm và language rõ.
- Invariant được sở hữu.
- Không cần sửa trực tiếp data của module khác.

**Interface stability**
- Public API nhỏ, có semantics và version.
- Consumer được inventory.
- Contract tests có bằng chứng.
- Error/idempotency/timeout được định nghĩa.

**Data autonomy**
- Module sở hữu schema hoặc data store.
- Migration và backup có owner.
- Cross-module data needs được giải quyết bằng API/event/projection.
- Không có hidden shared writes.

**Operational readiness**
- Có SLO/SLI và dashboard.
- Có log/trace/correlation.
- Có runbook, alert, on-call owner.
- Có deploy/rollback và resource budget.
- Biết behavior khi dependency chậm/lỗi.

**Organizational readiness**
- Có team hoặc owner đủ năng lực.
- Có trách nhiệm vận hành sau tách.
- Có ngân sách platform/support.
- Lý do tách được thống nhất.

**Business/technical benefit**
- Có nhu cầu scale khác biệt.
- Có lợi ích failure isolation/security isolation.
- Có release autonomy thực tế.
- Có constraint pháp lý/region phù hợp.
- Lợi ích lớn hơn chi phí network và vận hành.

### 16.1. Không bắt buộc đạt 100% mọi tiêu chí

Một số tiêu chí là hard guardrails như bảo mật, quyền dữ liệu và correctness. Những tiêu chí khác có thể được cải thiện sau khi tách, miễn có mitigation và owner. Hãy phân loại rủi ro:
- Không thể chấp nhận nếu thiếu.
- Có thể chấp nhận tạm thời với kiểm soát bù trừ.
- Có thể hoàn thiện sau vì blast radius thấp.
- Không cần cho use case này.

## 17. Khi nào chưa nên tách?

Giữ module trong cùng process thường hợp lý nếu:
- Hai phần luôn cần một transaction atomic chung.
- Domain model còn biến động và boundary chưa rõ.
- Các phần thay đổi cùng nhau.
- Không có owner/team vận hành độc lập.
- Workload chưa cần scale khác biệt.
- Tách tạo thêm latency và failure modes nhưng không giải quyết vấn đề.
- Chưa có monitoring, deployment và incident capability.
- Shared data access chưa được xử lý.
- Service mới chỉ là CRUD facade quanh cùng bảng.
- API nội bộ chưa có semantics, error và idempotency.
- Tổ chức chưa có khả năng xử lý distributed tracing và on-call.

Không tách bây giờ không phải thất bại. Một modular monolith có boundary tốt giúp giữ lựa chọn mở mà không phải gánh chi phí process phân tán quá sớm.

## 18. Lợi ích và chi phí của process boundary

| Lợi ích tiềm năng | Chi phí/rủi ro đi kèm |
|---|---|
| Scale độc lập | Network, deployment và resource overhead |
| Failure isolation | Partial failure, timeout, retry |
| Team ownership độc lập | On-call, skill và operational toil |
| Security boundary riêng | Identity, mTLS, secret rotation |
| Release riêng | Versioning, compatibility và migration |
| Runtime/storage riêng | Data synchronization và consistency |
| Blast radius nhỏ hơn | Distributed tracing và incident coordination |
| Chọn công nghệ phù hợp | Supply chain, patching, platform support |
| Deploy/rollback độc lập | Backward/forward compatibility |
| Khả năng phân vùng dữ liệu | Cross-service query/transaction phức tạp |

Lợi ích chỉ tồn tại khi tổ chức thực sự khai thác được boundary. Một service có database riêng nhưng không có owner, không có SLO và vẫn release đồng bộ có thể chỉ tăng chi phí.

### 18.1. Cost model tối thiểu

Trước khi tách, ước lượng:
- Runtime/container và memory overhead.
- Network calls và data serialization.
- Database connections, storage và replication.
- Broker, retry/DLQ, schema registry.
- Logging, metrics, tracing.
- Build/deploy pipeline.
- Security scanning, secrets và IAM.
- On-call/support time.
- Migration/backfill.
- Failure handling và reconciliation.

So với lợi ích:
- Giảm lead time.
- Giảm shared release coupling.
- Scale cost hiệu quả hơn.
- Giảm blast radius.
- Tăng security isolation.
- Cho phép team ownership rõ.

Không nhất thiết tính mọi khoản chính xác từ đầu; cần nêu assumptions, range và cách kiểm chứng sau rollout.

## 19. Chiến lược tách dần: strangler và branch by abstraction

### 19.1. Branch by abstraction

Tạo interface ổn định trước, chuyển các caller sang interface, sau đó thay implementation:
1. Xác định use case cần tách.
2. Tạo port/interface và DTO.
3. Bọc implementation cũ trong adapter.
4. Chuyển caller sang interface.
5. Chạy contract/behavior tests.
6. Thêm remote adapter song song.
7. Route traffic theo feature flag/canary.
8. So sánh kết quả và chuyển dần.
9. Gỡ implementation cũ khi an toàn.

Điều này giúp tránh big-bang rewrite và giữ đường rollback.

### 19.2. Strangler pattern

Một façade hoặc routing layer chuyển từng capability sang implementation mới:

~~~text
Clients
   |
   v
Stable Facade / API
   |
   +----> Legacy implementation
   |
   +----> New service
~~~

Ban đầu một số request đi legacy, một số đi service mới. Khi migration hoàn tất, bỏ đường legacy. Cần đảm bảo không có hai nơi cùng xử lý một side effect và có source of truth rõ.

### 19.3. Tránh dual-write không kiểm soát

Nếu ứng dụng ghi cả database cũ và database mới trên request path, một write có thể thành công ở một nơi và thất bại ở nơi khác. Có thể dùng:
- Outbox + CDC.
- Backfill và reconciliation.
- Idempotent consumer.
- Version/timestamp theo semantics đáng tin.
- Shadow reads.
- Cutover theo key/tenant khi có khả năng.
- Rollback plan xác định source of truth.

Không giả định hai database commit đồng thời chỉ vì code gọi cả hai. Một distributed transaction có thể được thiết kế nhưng có chi phí và failure semantics riêng.

## 20. Ví dụ từng bước: tách Inventory khỏi monolith

### Hiện trạng

~~~text
Monolith
  OrderController
  OrderService
  InventoryRepository
  InventoryService
  CustomerService
  PaymentService
  SharedDatabase
~~~

OrderService gọi InventoryService nội bộ, nhưng cũng trực tiếp cập nhật bảng inventory. Một batch job khác trừ stock trực tiếp. InventoryService không có owner rõ.

### Bước 1 — Xác định invariant và source of truth

Inventory sở hữu:
- SKU/location stock.
- Reservation state.
- Quy tắc không oversell.
- Expiry/cancel reservation.
- Stock adjustment audit.

Order chỉ gửi lệnh reserve/release/confirm và nhận kết quả.

### Bước 2 — Tạo public API

~~~java
public interface InventoryReservations {
    ReservationResult reserve(ReserveStock command);
    void release(ReleaseReservation command);
    void confirm(ConfirmReservation command);
}
~~~

DTO chứa quantity, SKU, location, order reference, idempotency key và semantics cần thiết. Không expose InventoryEntity.

### Bước 3 — Chuyển mọi write về owner

- Order không update inventory table.
- Batch job gọi Inventory API hoặc được chuyển thành job do Inventory sở hữu.
- Admin adjustment đi qua command có audit.
- Read model được cấp rõ nếu cần.

### Bước 4 — Kiểm dependency

- Cấm import Inventory internal.
- Cấm query inventory tables từ module khác.
- Test không oversell khi hai request cạnh tranh.
- Test duplicate reserve command.
- Kiểm transaction và event semantics.

### Bước 5 — Đo baseline

- Reservation p95/p99.
- Lock wait và DB throughput.
- Oversell/duplicate rate.
- Tỷ lệ release/cancel bị kẹt.
- Thời gian deploy các thay đổi liên quan stock.
- Số nhóm phải phối hợp.

### Bước 6 — Quyết định có tách process không

Nếu Inventory có tải độc lập, cần scale khác, có owner và operational readiness, có thể tạo Inventory process. Nếu chưa, tiếp tục modular monolith vẫn là lựa chọn tốt.

### Bước 7 — Tạo remote adapter và rollout

Order tiếp tục gọi interface. Adapter HTTP/gRPC thay adapter local. Canary theo traffic có kiểm soát, idempotency giữ side effect an toàn, timeout/retry theo contract. So sánh latency, correctness và failure.

### Bước 8 — Chuyển data ownership

Migration dữ liệu, backfill, validate, switch read/write, giữ rollback window. Gỡ shared writes sau khi xác nhận không còn consumer.

**Kết quả mong đợi:** Inventory trở thành một domain có ownership trước khi trở thành một deployment unit. Tách process chỉ là bước thay đổi topology của boundary đã được chuẩn hóa.

## 21. Ví dụ cấu trúc Java theo module

Một layout minh họa:

~~~text
src/
  main/
    java/
      com.example.app/
        bootstrap/
        order/
          api/
          application/
          domain/
          internal/
            persistence/
            messaging/
        inventory/
          api/
          application/
          domain/
          internal/
            persistence/
            messaging/
        customer/
          api/
          application/
          domain/
          internal/
            persistence/
            messaging/
  test/
    java/
      architecture/
      order/
      inventory/
~~~

Tùy framework, module boundaries có thể được enforce bằng Java module system, Maven/Gradle subprojects hoặc package-level architecture tests.

### 21.1. Public API và implementation visibility

Nếu dùng Java modules (JPMS), có thể export package API và giữ package internal không export. Nếu dùng Maven/Gradle, có thể tách artifact api/implementation. Nếu chỉ dùng package conventions, cần architecture tests để tránh code khác import internal.

Mỗi cách có trade-off:
- JPMS giúp encapsulation ở runtime/build nhưng cần cấu hình module system.
- Build subprojects enforce dependency mạnh hơn nhưng thêm build complexity.
- Package convention đơn giản nhưng phụ thuộc test/lint.
- Một repository với module ownership có thể đủ cho giai đoạn đầu.

### 21.2. Không lạm dụng shared-kernel module

Một shared-kernel chỉ nên chứa khái niệm ổn định được các context đồng sở hữu. Nếu nó trở thành nơi gom mọi DTO, utility, enum và entity, nó sẽ thành dependency trung tâm khiến mọi thay đổi lan rộng.

Ưu tiên duplication nhỏ, có chủ đích ở boundary hơn là tạo coupling mạnh chỉ để tránh vài dòng mapping.

## 22. Đánh giá module boundary bằng thay đổi thực tế

Một cách hữu ích là chọn 3–5 thay đổi gần đây và xem:
- Những module nào bị sửa?
- Những nhóm nào phải phối hợp?
- Có phải đổi schema dùng chung?
- Test nào phải cập nhật?
- Deploy nào phải đồng bộ?
- Incident/risk nào có thể phát sinh?
- Những thay đổi nào chỉ là implementation detail nhưng đã lan ra ngoài?

Nếu một module được cho là độc lập nhưng mọi feature đều sửa 5 module khác, có thể:
- Boundary sai.
- API quá thấp cấp.
- Domain ownership mờ.
- Shared data model quá lớn.
- Event semantics không ổn định.
- Orchestration đặt sai chỗ.

### 22.1. Change coupling

Có thể đo tỷ lệ hai module thường xuyên thay đổi cùng nhau trong các commit/PR liên quan. Đây chỉ là tín hiệu gợi ý: một PR refactor lớn có thể sửa nhiều module nhưng không chứng minh coupling runtime. Kết hợp với dependency graph, issue/feature mapping và phỏng vấn team.

### 22.2. Consumer count và API stability

Một public API có 20 consumer không nhất thiết sai; nhưng thay đổi nó sẽ có coordination cost cao. Có thể:
- Tách contract theo use case.
- Thêm adapter.
- Giảm consumer phụ thuộc field không cần thiết.
- Dùng event/projection cho một số read use case.
- Giữ API cũ trong migration window.
- Không cho consumer truy cập internal schema.

## 23. Những quyết định cần ghi vào ADR

Khi chuẩn hóa boundary có tác động lớn, ADR nên ghi:
- Vấn đề hiện tại và evidence.
- Module/domain được đề xuất.
- Invariant và data ownership.
- Public APIs/events.
- Dependency direction.
- Những consumer bị ảnh hưởng.
- Transaction/consistency semantics.
- Failure/timeout/idempotency behavior.
- Deployment topology hiện tại và mục tiêu.
- Migration/backfill/rollback.
- SLO và observability.
- Security/data classification.
- Chi phí và trade-off.
- Người quyết định, owner và thời điểm review.

Không cần ADR cho mọi package. Tập trung các quyết định khó đảo ngược, có tác động liên team hoặc làm thay đổi ranh giới dữ liệu.

## 24. Những dấu hiệu cần dừng và thiết kế lại

Trong quá trình modularization hoặc extraction, dừng để xem lại nếu:
- Module API có hàng trăm method chung chung.
- Mọi module đều import shared-kernel.
- Một module không thể test nếu khởi động toàn ứng dụng.
- Nhiều module ghi cùng aggregate.
- Một command cần synchronous call qua quá nhiều service.
- Một thay đổi đơn giản buộc release hàng loạt.
- Remote adapter chỉ chuyển nguyên internal entity.
- Retry tạo duplicate side effects.
- Read projection không có version hoặc reconciliation.
- Module không có owner/on-call sau khi tách.
- Chi phí tracing/incident tăng mà không có lợi ích nghiệp vụ.
- Số service tăng nhưng lead time, reliability và unit cost xấu đi.

Không cố hoàn thành extraction chỉ vì đã có roadmap. Có thể dừng ở modular monolith và thu được phần lớn lợi ích từ boundary.

## 25. Anti-pattern khi chuẩn hóa và tách mô-đun

**Tách theo layer kỹ thuật:** tạo Controller Service, Repository Service riêng khiến mọi thay đổi nghiệp vụ phải gọi qua nhiều tiến trình. Tách theo domain/capability và ownership.

**Một class = một module:** granularity quá nhỏ làm dependency graph và build phức tạp. Module phải có trách nhiệm có ý nghĩa.

**Chỉ đổi package name:** code vẫn truy cập shared table, static state và internal class. Cần enforce interface/data boundary.

**Shared database không có owner:** mọi nhóm sửa schema, migration và invariant lẫn nhau. Chỉ định owner và giới hạn quyền ghi.

**Expose ORM entity:** storage model trở thành public API. Dùng DTO/contract có semantics.

**Một shared-kernel khổng lồ:** mọi domain phụ thuộc cùng model và release. Giữ shared concepts nhỏ và ổn định.

**Tách process trước khi hiểu transaction:** chuyển call thành network nhưng vẫn giả định atomic. Xác định saga, compensation và consistency trước.

**Big-bang rewrite:** thay cả domain, data store và API cùng lúc. Dùng branch-by-abstraction, strangler và migration từng bước.

**Dual-write không reconciliation:** hai nguồn dữ liệu lệch nhau sau lỗi. Dùng outbox, idempotency và đối soát.

**Đưa mọi method thành HTTP endpoint:** tạo chatty network và API quá thấp cấp. Chọn coarse-grained use case có semantics.

**Giả định local call và remote call tương đương:** remote có latency, timeout, duplicate và partial failure. Thiết kế adapter/failure contract.

**Tách service không có owner:** không ai trực on-call hoặc quản schema. Chỉ tách khi ownership và năng lực vận hành rõ.

**Tối ưu số module:** chia package để báo cáo tiến độ. Đánh giá coupling, change scope và outcome.

**Chỉ dùng static analysis:** import graph sạch nhưng vẫn query chung DB hoặc share event payload. Kết hợp runtime/data/operational evidence.

**Không có migration plan:** cutover xong mới phát hiện consumer cũ hoặc dữ liệu sai. Có inventory, shadow validation và rollback.

## 26. Bài tập: chuẩn hóa Catalog trước khi tách

Một monolith có:
- ProductController.
- ProductService.
- PriceService.
- InventoryService.
- SearchRepository.
- Một bảng product được nhiều module cập nhật.
- Search index nhận full product object.
- Một batch job sửa price trực tiếp.
- Một số API trả JPA entity.

Nhóm muốn tách Catalog thành service mới.

### Câu hỏi

1. Catalog sở hữu những invariant và dữ liệu nào?
2. Price có cùng bounded context với Catalog hay là capability riêng? Cần bằng chứng gì?
3. Inventory có nên sửa bảng product không?
4. Search cần những trường nào và có cần nhận mọi PII/field nội bộ không?
5. API nào là public use case và API nào chỉ là repository access?
6. Những transaction nào hiện xuyên domain?
7. Consumer nào phụ thuộc JPA entity hoặc column names?
8. Làm sao chuyển batch job về owner?
9. Có thể tách Catalog process trước hay cần modularize/contract test?
10. Những metric nào xác nhận việc tách mang lại lợi ích?

### Hướng giải gợi ý

- Vẽ data ownership và invariant trước khi chọn deployment.
- Tách product catalog facts, pricing rules và inventory availability theo semantics thật; không mặc định tất cả một module chỉ vì cùng trang sản phẩm.
- Cấm direct writes xuyên module; batch job gọi owner API/command.
- Tạo DTO/event projection tối thiểu cho Search, versioned và có invalidation/rebuild policy.
- Thay public JPA entities bằng contract DTO.
- Kiểm dependency graph, module tests và cross-module transactions.
- Đo change coupling, catalog p99, search freshness, release lead time, data mismatch và operational cost.
- Chỉ tách process nếu cần scale/release/isolation và đã có owner, SLO, runbook.

## 27. Lộ trình thực hiện theo từng giai đoạn

### Giai đoạn 1 — Discover

- Chọn một domain có pain point rõ.
- Lập dependency graph và data map.
- Xác định use cases, invariant, owner và consumers.
- Đo baseline: change scope, latency, incidents, query/data access.
- Ghi các hidden coupling và risk.

### Giai đoạn 2 — Define boundary

- Xác định public API và internal packages.
- Xác định data owner và schema/table ownership.
- Phân loại command, query và event.
- Đặt dependency direction.
- Định nghĩa error, idempotency và consistency.
- Thống nhất contract với consumer liên quan.

### Giai đoạn 3 — Enforce inside the monolith

- Tạo module/package/build boundary.
- Chuyển consumer sang public API.
- Xóa direct imports và direct table writes.
- Tách DTO khỏi ORM entities.
- Thêm architecture tests và contract tests.
- Xử lý circular dependencies.
- Tổ chức migration và test dữ liệu.

### Giai đoạn 4 — Prove modularity

- Thực hiện vài thay đổi chỉ trong module.
- Xác nhận module test/build được độc lập trong phạm vi phù hợp.
- Kiểm tra data ownership.
- Đo cross-module change coupling.
- Thử lỗi dependency giả lập qua adapter.
- Đánh giá SLO, security và operational readiness.

### Giai đoạn 5 — Decide extraction

- Viết ADR với lý do cụ thể.
- So sánh giữ cùng process với tách process.
- Tính chi phí network, deployment, observability và on-call.
- Xác nhận team owner và capacity.
- Chọn rollout/migration/rollback.
- Đặt success criteria và review date.

### Giai đoạn 6 — Extract gradually

- Xây service/adapter mới.
- Backfill và validate data.
- Canary traffic.
- Kiểm correctness, latency, failure và cost.
- Chuyển dần read/write theo source-of-truth plan.
- Loại bỏ implementation cũ khi có bằng chứng.
- Cập nhật service catalog, contracts và runbooks.

## 28. Checklist trước khi tách module thành process

1. **Domain:** Trách nhiệm và thuật ngữ có nhất quán, có invariant rõ?
2. **Ownership:** Một nhóm chịu trách nhiệm code, data, deploy và on-call?
3. **Cohesion:** Hành vi/dữ liệu thay đổi cùng nhau nằm trong boundary?
4. **Public API:** Consumer chỉ phụ thuộc contract nhỏ và ổn định?
5. **Internal encapsulation:** Không import implementation hoặc ORM entities xuyên module?
6. **Dependency graph:** Không có cycle hoặc dependency ẩn không được chấp thuận?
7. **Data ownership:** Một owner kiểm soát write path, schema và migration?
8. **Cross-module access:** Query/write qua API/event/projection có contract?
9. **Transaction:** Atomicity, saga/compensation và consistency đã được hiểu?
10. **Contract semantics:** Error, timeout, idempotency, pagination, versioning rõ?
11. **Compatibility:** Old/new consumer/provider có thể cùng hoạt động khi rollout?
12. **Testing:** Unit, module, architecture, contract, persistence và failure tests?
13. **Observability:** SLO, trace, metrics, log redaction, dashboard và alert?
14. **Security:** Identity, authorization, secret, tenant isolation và data minimization?
15. **Capacity:** Load, concurrency, rate limits, connection pool và headroom?
16. **Operations:** Runbook, on-call, deploy, rollback, readiness và graceful shutdown?
17. **Migration:** Backfill, shadow read, reconciliation, cutover và rollback?
18. **Benefit:** Scale/failure/release/security isolation có lợi ích được mô tả?
19. **Cost:** Network, infra, monitoring, cognitive load và support được tính?
20. **Review:** Có success criteria, owner, deadline và quyết định giữ/gộp/tách lại?

## 29. Ghi nhớ cốt lõi

- **Chuẩn hóa mô-đun trước khi tách process giúp biến dependency ngầm thành boundary rõ**, giảm rủi ro tạo distributed monolith.
- **Module được xác định bằng trách nhiệm, invariant, ownership và contract**, không chỉ bởi package hoặc số lượng class.
- **Public API phải che giấu implementation**, consumer không truy cập internal class, ORM entity hoặc database table của module khác.
- **Data ownership là nền tảng:** một module chịu trách nhiệm write path, schema, migration và tính đúng của dữ liệu mình sở hữu.
- **Dependency direction, cycle checks và architecture tests** biến boundary thành quy tắc có thể kiểm chứng.
- **Local call và remote call có failure semantics khác nhau.** Trước khi tách, làm rõ timeout, retry, idempotency, consistency, error và event behavior.
- **Branch by abstraction và strangler pattern** cho phép chuyển dần mà vẫn giữ đường rollback và source of truth rõ.
- **Không phải module nào cũng cần thành microservice.** Giữ modular monolith là lựa chọn trưởng thành nếu process boundary không mang lại lợi ích lớn hơn chi phí.
- **Chỉ tách khi có lý do và bằng chứng:** scale độc lập, failure/security isolation, release autonomy hoặc ownership có lợi ích thực.
- **Đo kết quả sau mỗi bước:** change coupling, lead time, reliability, correctness, operational toil và unit cost; số service chỉ là inventory.
