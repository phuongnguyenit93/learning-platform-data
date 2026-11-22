# Chia Bounded Context theo bảng hoặc tầng kỹ thuật

Khi bắt đầu tổ chức lại một hệ thống bán hàng, đội phát triển thường nhìn vào database và thấy các nhóm bảng như Customer, Order, Product, Payment. Một cách chia có vẻ tự nhiên là tạo Customer Context, Order Context, Product Context và Payment Context, mỗi context quản lý một nhóm bảng. Một cách khác là tạo Persistence Context chứa toàn bộ repository và entity, Application Context chứa service, rồi Presentation Context chứa controller. Cả hai cách đều dễ triển khai ban đầu vì bám theo cấu trúc kỹ thuật đang có.

Vấn đề là **Bounded Context được xác định bởi ranh giới của một mô hình nghiệp vụ và ngôn ngữ có ý nghĩa nhất quán, không phải bởi bảng database hay tầng kỹ thuật**. Bảng là cách lưu dữ liệu; Controller, Service và Repository là cách tổ chức code. Chúng có thể hỗ trợ một Bounded Context, nhưng không tự quyết định context nằm ở đâu.

Trong Domain-Driven Design (DDD), strategic design tìm các mô hình và ranh giới nghiệp vụ có thể phát triển tương đối độc lập. Tactical design triển khai mô hình bên trong ranh giới đó bằng Entity, Value Object, Aggregate, Repository và Domain Event. Nếu chia context theo từng bảng hoặc theo tầng kỹ thuật, các quy tắc nghiệp vụ thường bị cắt ngang, ngôn ngữ chung bị phân tán và thay đổi nhỏ có thể buộc nhiều nhóm phối hợp.

Sau bài học này, bạn có thể:

- Giải thích vì sao database table và technical layer không phải tiêu chí chính để xác định Bounded Context.
- Nhận diện dấu hiệu của context bị chia quá nhỏ theo bảng hoặc bị trộn nhiều mô hình trong một context lớn.
- Phân biệt Bounded Context với module, Aggregate, database schema và deployment unit.
- Tìm ranh giới dựa trên business capability, ubiquitous language, invariant, workflow và quyền sở hữu.
- Hiểu vì sao cùng một khái niệm có thể có mô hình khác nhau trong các context.
- Dùng Context Map để mô tả quan hệ giữa các context.
- Tổ chức package/module theo năng lực nghiệp vụ thay vì chỉ theo Controller, Service và Repository.
- Chuyển dần một hệ thống đang chia theo bảng hoặc tầng kỹ thuật sang ranh giới domain rõ hơn.

## 1. Bounded Context bảo vệ một mô hình và ngôn ngữ

Bounded Context là ranh giới mà trong đó một mô hình domain và ngôn ngữ dùng để diễn đạt mô hình đó có ý nghĩa nhất quán. Bên trong ranh giới, thuật ngữ cần được hiểu theo cùng một nghĩa; quy tắc và hành vi được thiết kế quanh cách hiểu đó.

Ví dụ, từ Order có thể xuất hiện trong nhiều phần của một doanh nghiệp:

- Sales hiểu Order là cam kết mua bán giữa khách hàng và doanh nghiệp, gồm giá đã chốt, chiết khấu và trạng thái chấp nhận.
- Fulfillment hiểu Order là yêu cầu lấy hàng, đóng gói và giao hàng, gồm địa chỉ giao, kiện hàng và tiến độ giao.
- Finance hiểu Order là căn cứ đối soát doanh thu, khoản phải thu, thuế và chứng từ.

Ba nhóm có thể cùng nói về một đơn hàng trong thế giới thực, nhưng mỗi nhóm quan tâm đến một phần khác nhau và áp dụng quy tắc khác nhau. Ép cả ba dùng một class Order với mọi field và mọi trạng thái thường làm mô hình phình to, phụ thuộc lẫn nhau và khó thay đổi.

Bounded Context cho phép mỗi nhóm có mô hình Order phù hợp:

~~~text
                 Order trong thế giới nghiệp vụ
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
       Sales Context    Fulfillment Context   Finance Context
       SalesOrder       DeliveryOrder         SalesTransaction
       - accepted price - shipment status    - receivable
       - discount       - package             - tax
       - buyer          - delivery address    - reconciliation
~~~

Các mô hình có thể liên kết qua identifier và contract. Chúng không cần chia sẻ cùng một object graph.

## 2. Bounded Context không phải một bảng database

Một bảng biểu diễn cấu trúc lưu trữ. Nó có thể chứa dữ liệu của một mô hình, nhưng không thể hiện đầy đủ ngôn ngữ, hành vi, policy, lifecycle hoặc ranh giới nhất quán của mô hình đó.

Một Bounded Context thường chứa nhiều khái niệm và nhiều bảng. Ví dụ Sales Context có thể quản lý:

- SalesOrder
- SalesOrderLine
- Promotion
- PriceSnapshot
- OrderAdjustment
- OrderStatusHistory

Các khái niệm này cùng tham gia vào một năng lực nghiệp vụ: chấp nhận và quản lý đơn bán. Việc chúng được lưu trong nhiều bảng không tạo ra nhiều context.

Ngược lại, một bảng có thể được dùng để lưu một projection, một read model hoặc dữ liệu phục vụ nhiều mục đích kỹ thuật. Việc một bảng chứa các cột liên quan đến nhiều khái niệm cũng không chứng minh rằng các khái niệm đó thuộc cùng một Bounded Context.

### Ví dụ chia theo bảng

Giả sử hệ thống có các bảng:

~~~text
customer
customer_address
orders
order_line
payment
shipment
product
inventory
~~~

Nếu tạo một context cho mỗi bảng hoặc mỗi nhóm bảng:

~~~text
Customer Context
Order Context
Payment Context
Shipment Context
Product Context
Inventory Context
~~~

đội phát triển có thể vô tình tạo ra quá nhiều ranh giới. Một use case Place Order phải gọi qua nhiều context nhỏ để kiểm tra khách hàng, sản phẩm, tồn kho, giá và thanh toán. Nếu những context đó không có autonomy nghiệp vụ thực sự, việc chia nhỏ chỉ thêm API, mapping và phối hợp.

Mặt khác, nếu gom mọi bảng vào một context chỉ vì chúng nằm trong cùng database, mô hình có thể trở thành một Big Ball of Mud: Sales, Inventory, Payment và Fulfillment cùng sửa một tập entity và cùng phụ thuộc vào một bộ quy tắc.

### Bảng không xác định ownership

Tên bảng không cho biết team nào sở hữu invariant. Ví dụ, bảng orders có thể được Reporting đọc để tạo báo cáo, Fulfillment dùng để chuẩn bị giao hàng và Finance dùng để đối soát. Điều đó không có nghĩa cả ba cùng sở hữu Order.

Cần xác định:

- Context nào có quyền quyết định trạng thái đơn bán?
- Context nào quyết định hàng được giữ hay không?
- Context nào quyết định thanh toán đã được capture hoặc hoàn tiền?
- Context nào chịu trách nhiệm tạo shipment?
- Những context khác nhận thông tin qua contract nào?

Ownership xuất phát từ trách nhiệm nghiệp vụ, không xuất phát từ quyền SELECT hoặc vị trí bảng.

## 3. Bounded Context không phải một tầng kỹ thuật

Một lỗi khác là chia hệ thống theo technical layer:

~~~text
application/
  controllers/
  services/
  repositories/
  entities/
  dtos/
~~~

Hoặc tách thành các module:

~~~text
presentation-module
application-module
domain-module
infrastructure-module
~~~

Cấu trúc này có thể biểu diễn các lớp kiến trúc bên trong một ứng dụng, nhưng không nhất thiết thể hiện các Bounded Context. Mỗi thay đổi nghiệp vụ thường đi xuyên qua tất cả các tầng. Khi các tầng được chia thành module hoặc team riêng, một use case đơn giản có thể cần nhiều lần bàn giao.

Ví dụ thay đổi quy tắc chiết khấu:

~~~text
Controller team
      |
      v
Application service team
      |
      v
Domain model team
      |
      v
Repository / database team
~~~

Nếu mỗi tầng do một nhóm khác nhau sở hữu, thay đổi nghiệp vụ phải đi qua nhiều team dù toàn bộ thay đổi cùng phục vụ một capability.

### Tầng kỹ thuật vẫn có vai trò

DDD không yêu cầu loại bỏ các tầng Presentation, Application, Domain và Infrastructure. Chúng hữu ích để quản lý dependency bên trong một Bounded Context:

~~~text
Sales Context
  api/
  application/
  domain/
  infrastructure/

Inventory Context
  api/
  application/
  domain/
  infrastructure/
~~~

Tầng kỹ thuật trả lời câu hỏi code được tổ chức thế nào; Bounded Context trả lời câu hỏi mô hình nghiệp vụ nào có hiệu lực ở đâu. Hai chiều tổ chức có thể cùng tồn tại.

## 4. Những dấu hiệu đang chia context theo bảng hoặc tầng

Hãy xem lại ranh giới nếu hệ thống có các dấu hiệu sau:

- Mỗi bảng hoặc mỗi Aggregate đều được biến thành một microservice riêng dù không có nhu cầu nghiệp vụ độc lập.
- Một use case phải gọi qua nhiều service chỉ để hoàn tất một quyết định domain đơn giản.
- Các service thường xuyên truy cập trực tiếp database của nhau.
- Một thay đổi tên field hoặc schema buộc nhiều context cùng deploy.
- Cùng một thuật ngữ được định nghĩa bằng một DTO chung dù các team hiểu khác nhau.
- Một context chỉ chứa CRUD cho một bảng và không sở hữu quy tắc nghiệp vụ rõ.
- Các team được chia theo Controller, Service, Repository hoặc Database thay vì theo capability.
- Domain logic bị rải trong controller, mapper, repository callback và message consumer.
- Có nhiều interface/service trung gian nhưng không có boundary hoặc policy rõ.
- Một thay đổi nghiệp vụ phải sửa hàng loạt package chỉ vì code được chia ngang theo tầng.

Một dấu hiệu riêng lẻ chưa đủ kết luận thiết kế sai. Ví dụ, một service chỉ quản lý một bảng có thể hợp lý nếu nó thực sự là một capability nhỏ có lifecycle và ownership riêng. Cần xem xét ngữ nghĩa và cách thay đổi, không chỉ đếm số bảng hoặc class.

## 5. Vì sao chia theo bảng thường tạo coupling?

### Một quyết định nghiệp vụ bị phân tán

Giả sử quy tắc chấp nhận Order cần kiểm tra:

- Khách hàng có đủ điều kiện mua không?
- Sản phẩm còn được phép bán không?
- Giá và promotion có hợp lệ không?
- Tồn kho có thể được giữ không?
- Payment method có được chấp nhận không?

Nếu mỗi bảng được quản lý bởi một context độc lập nhưng không có capability boundary rõ, Sales phải gọi nhiều API và tự kết hợp dữ liệu. Quyết định nghiệp vụ bị chia ra ngoài các context, nơi không có context nào chịu trách nhiệm toàn bộ.

### Transaction trở thành workflow phân tán

Trong một database, nhiều thay đổi có thể được commit trong một transaction. Khi mỗi bảng được tách thành service và database riêng, một thao tác trước đây nguyên tử có thể trở thành chuỗi request, event và compensation.

Điều này không nhất thiết sai. Nhưng nếu ranh giới được tạo chỉ vì bảng khác nhau, hệ thống phải trả chi phí distributed transaction mà không nhận được lợi ích ownership tương xứng.

### Contract phơi bày cấu trúc lưu trữ

Nếu API trả trực tiếp một row hoặc JPA entity, consumer có thể phụ thuộc vào tên cột, quan hệ ORM và cấu trúc object graph. Khi schema thay đổi, contract cũng thay đổi theo.

Contract nên diễn đạt capability hoặc sự kiện nghiệp vụ, chẳng hạn ReserveStock, StockReserved, PaymentCaptured, OrderAccepted. Không nên biến API thành một lớp truy cập từ xa vào bảng.

## 6. Vì sao chia theo tầng kỹ thuật thường tạo coupling?

Khi toàn hệ thống được tổ chức theo layer, code của cùng một capability nằm rải rác:

~~~text
controllers/
  OrderController
  StockController
  PaymentController

services/
  OrderService
  StockService
  PaymentService

repositories/
  OrderRepository
  StockRepository
  PaymentRepository

entities/
  OrderEntity
  StockEntity
  PaymentEntity
~~~

Người đọc phải chuyển qua nhiều thư mục để hiểu một hành vi. Nếu package được chia thành các module kỹ thuật độc lập, module Sales không thể sở hữu trọn vẹn use case của mình mà phải gọi sang Application Layer, Domain Layer và Persistence Layer chung.

Một thay đổi ở Order có thể vô tình ảnh hưởng các module khác vì chúng dùng chung entity, mapper hoặc repository base class.

### Không phải cứ package theo feature là có Bounded Context

Tổ chức package theo feature giúp code gần nhau hơn:

~~~text
sales/
  controller/
  service/
  repository/
  model/

inventory/
  controller/
  service/
  repository/
  model/
~~~

Nhưng đây mới là dấu hiệu của module theo capability. Để trở thành Bounded Context rõ ràng, mỗi module còn cần mô hình và ngôn ngữ nhất quán, ownership, contract và quy tắc tương tác với context khác.

## 7. Tiêu chí tìm Bounded Context phù hợp

Không có một thuật toán duy nhất để tìm Bounded Context. Hãy kết hợp nhiều tín hiệu nghiệp vụ và kỹ thuật.

### Business capability

Hãy hỏi doanh nghiệp đang thực hiện những năng lực nào để tạo ra giá trị. Ví dụ:

- Quản lý bán hàng.
- Quản lý tồn kho.
- Xử lý thanh toán.
- Chuẩn bị và giao hàng.
- Quản lý quan hệ khách hàng.
- Kế toán và đối soát.

Capability mô tả điều doanh nghiệp cần làm, không phải màn hình hoặc bảng cần lưu. Một capability có thể sử dụng nhiều bảng và nhiều Aggregate.

### Ubiquitous Language

Phỏng vấn chuyên gia và quan sát công việc để tìm thuật ngữ, định nghĩa và cách dùng. Nếu cùng một từ có nghĩa khác nhau theo nhóm, đó là tín hiệu cần xem xét các model boundary.

Ví dụ Available Stock:

- Inventory có thể định nghĩa là số lượng có thể giữ sau khi trừ reservation.
- Sales có thể chỉ quan tâm một thông tin ước lượng để hiển thị cho khách.
- Warehouse Operations có thể quan tâm số lượng thực đếm, hàng lỗi và hàng đang di chuyển.

Không nên ép các nhóm dùng một thuộc tính availableQuantity nếu cách tính và thời điểm cập nhật khác nhau.

### Invariant và consistency boundary

Hãy xác định những quy tắc nào phải được bảo vệ cùng nhau. Ví dụ:

- Một reservation không được vượt số lượng khả dụng.
- Một payment capture không được vượt số tiền đã authorize.
- Một Order chỉ được xác nhận khi các điều kiện cần thiết đã hoàn tất.

Các invariant cho thấy những đối tượng nào cần phối hợp chặt. Chúng giúp xác định Aggregate và có thể gợi ý context boundary. Tuy nhiên, một Bounded Context thường chứa nhiều Aggregate; không nên đồng nhất Aggregate boundary với Bounded Context boundary.

### Lifecycle và ownership

Hỏi ai tạo, thay đổi, xác nhận, hủy và lưu trữ dữ liệu. Hai khái niệm cùng tên nhưng có lifecycle khác nhau có thể thuộc hai model. Một nhóm có quyền quyết định và chịu trách nhiệm rõ thường là tín hiệu của ownership.

### Change pattern

Quan sát những phần nào thay đổi cùng nhau và những phần nào có nhịp thay đổi riêng:

- Sales thay đổi promotion và pricing policy.
- Inventory thay đổi reservation strategy.
- Fulfillment thay đổi quy trình đóng gói và giao nhận.
- Finance thay đổi cách ghi nhận thuế và đối soát.

Nếu hai nhóm thường xuyên thay đổi cùng nhau vì cùng một quy tắc, có thể chúng thuộc cùng một capability hoặc cần làm rõ contract. Nếu thay đổi độc lập, đó là tín hiệu có thể tách mô hình.

## 8. Phân biệt Subdomain, Bounded Context, Aggregate và Module

Các khái niệm có liên hệ nhưng không thay thế nhau.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Subdomain | Phần vấn đề nghiệp vụ của doanh nghiệp | Sales, Inventory, Billing |
| Bounded Context | Ranh giới mà một domain model và ngôn ngữ có hiệu lực | Sales Context, Inventory Context |
| Aggregate | Ranh giới nhất quán của một cụm object domain | Order Aggregate |
| Module | Ranh giới tổ chức code và dependency | sales module trong Java |
| Database schema | Namespace/cấu trúc lưu trữ | sales_schema |
| Deployment unit | Đơn vị build và chạy độc lập | sales-service |

Một subdomain có thể được triển khai qua một hoặc nhiều Bounded Context tùy độ phức tạp và lịch sử hệ thống. Một Bounded Context có thể được tổ chức thành nhiều module code nội bộ. Một module có thể chứa nhiều Aggregate. Một database schema có thể chứa nhiều bảng của cùng một context.

Không nên áp dụng ánh xạ một-một một cách máy móc:

~~~text
1 table = 1 Aggregate = 1 Bounded Context = 1 microservice
~~~

Đây không phải quy tắc của DDD. Các ranh giới được xác định theo những câu hỏi khác nhau.

## 9. Ví dụ: Order trong Sales và Fulfillment

Giả sử một nền tảng thương mại điện tử có quy trình từ đặt hàng đến giao hàng.

### Sales Context

Sales chịu trách nhiệm về quyết định bán:

- Khách hàng và điều kiện bán.
- Dòng hàng, giá đã chốt và discount.
- Chấp nhận hoặc từ chối Order.
- Hủy đơn theo policy bán hàng.
- Ghi nhận sự kiện OrderAccepted.

Một mô hình rút gọn:

~~~java
public class SalesOrder {
    private SalesOrderId id;
    private BuyerId buyerId;
    private List<SalesOrderLine> lines;
    private Money acceptedTotal;
    private SalesOrderStatus status;

    public void accept() {
        ensureDraft();
        ensureHasLines();
        status = SalesOrderStatus.ACCEPTED;
    }
}
~~~

### Fulfillment Context

Fulfillment chịu trách nhiệm về việc thực hiện giao:

- Nhận yêu cầu giao hàng.
- Phân bổ hàng vào shipment.
- Pick, pack và dispatch.
- Theo dõi delivery.
- Xử lý giao thất bại hoặc hoàn hàng.

Mô hình riêng:

~~~java
public class DeliveryOrder {
    private DeliveryOrderId id;
    private SalesOrderReference salesOrderReference;
    private DeliveryAddress destination;
    private List<PackageLine> packageLines;
    private DeliveryStatus status;

    public void dispatch() {
        ensurePacked();
        status = DeliveryStatus.DISPATCHED;
    }
}
~~~

SalesOrder và DeliveryOrder cùng liên quan một giao dịch mua bán nhưng có trách nhiệm khác nhau. Fulfillment không cần import SalesOrder Aggregate để thay đổi trạng thái shipment. Nó nhận một contract như SalesOrderAccepted với dữ liệu cần thiết.

### Integration Event

~~~json
{
  "eventType": "SalesOrderAccepted",
  "eventId": "evt-1001",
  "orderReference": "SO-2026-1001",
  "acceptedAt": "2026-11-18T09:00:00Z",
  "delivery": {
    "recipient": "Nguyen Van A",
    "address": "12 Example Street"
  },
  "lines": [
    {
      "sku": "SKU-01",
      "quantity": 2
    }
  ]
}
~~~

Đây là ví dụ minh họa contract. Trong thực tế cần xác định dữ liệu cá nhân nào được phép truyền, schema version, idempotency và retention. Fulfillment chuyển event thành model nội bộ của mình thay vì coi payload là SalesOrder entity.

## 10. Một khái niệm có thể có nhiều mô hình

DDD chấp nhận rằng cùng một sự vật ngoài đời có thể được mô hình hóa khác nhau trong từng Bounded Context. Điều quan trọng là mapping giữa các mô hình phải rõ.

Ví dụ Customer:

| Context | Customer có nghĩa gì? | Dữ liệu quan trọng |
|---|---|---|
| Sales | Người mua và điều kiện thương mại | Buyer identity, tier, credit terms |
| Support | Người đang cần hỗ trợ | Contact preference, support history |
| Finance | Chủ thể thanh toán hoặc công nợ | Tax identity, invoice address, balance |
| Marketing | Đối tượng nhận chiến dịch | Consent, segment, campaign preference |

Không nên tạo một Customer entity dùng chung chứa mọi field và policy. Việc chia sẻ một model chung khiến context phải đồng thuận về semantics và thay đổi dù nhu cầu khác nhau.

### Dùng identifier và contract để liên kết

Các context có thể dùng một identifier ổn định như CustomerId để tham chiếu. Khi cần dữ liệu, chúng dùng API hoặc event contract. Mỗi context chuyển dữ liệu nhận được sang kiểu domain của mình.

Không phải mọi field cần được đồng bộ tức thời. Ví dụ Support có thể giữ snapshot tên hiển thị; Finance cần địa chỉ hóa đơn chính xác tại thời điểm phát hành invoice. Semantics và thời điểm của dữ liệu cần được ghi rõ.

## 11. Context Map mô tả quan hệ giữa các context

Sau khi tìm được các context, cần mô tả cách chúng tương tác. Context Map giúp thể hiện upstream/downstream, quyền ảnh hưởng lên contract và cách mô hình được chuyển đổi.

Ví dụ:

~~~text
Sales Context
    |
    | SalesOrderAccepted
    v
Fulfillment Context

Payment Context
    |
    | PaymentCaptured / PaymentFailed
    v
Sales Context

Inventory Context
    |
    | StockReserved / StockUnavailable
    v
Sales Context
~~~

Sơ đồ này mô tả các quan hệ tích hợp. Nó không có nghĩa các context phải là microservice hoặc mỗi event cần một broker riêng.

### Một số kiểu quan hệ thường gặp

| Quan hệ | Ý nghĩa | Khi cân nhắc |
|---|---|---|
| Partnership | Hai team phối hợp chặt và cùng điều chỉnh model/contract | Cần đồng bộ quyết định và lịch thay đổi |
| Customer-Supplier | Upstream cung cấp capability/contract cho downstream | Downstream cần nêu yêu cầu rõ, upstream cân nhắc ưu tiên |
| Conformist | Downstream chấp nhận model upstream | Chi phí chuyển đổi lớn hoặc upstream là chuẩn bắt buộc |
| Anti-Corruption Layer | Downstream chuyển đổi contract bên ngoài sang model nội bộ | Cần bảo vệ domain khỏi semantics không phù hợp |
| Open Host Service | Upstream công bố API/service contract dùng chung | Nhiều consumer cần tích hợp ổn định |
| Published Language | Contract hoặc schema chung để trao đổi | Cần một ngôn ngữ trao đổi được quản lý |
| Shared Kernel | Một phần model được hai context cùng sở hữu | Chỉ khi phạm vi nhỏ và có quản trị thay đổi |

Không cần dùng mọi pattern cho mọi cặp context. Chọn quan hệ dựa trên quyền sở hữu, mức độ phụ thuộc và khả năng thay đổi.

## 12. Anti-Corruption Layer bảo vệ mô hình nội bộ

Nếu một context phải tích hợp với hệ thống cũ hoặc upstream có model không phù hợp, Anti-Corruption Layer (ACL) chuyển đổi contract trước khi dữ liệu đi vào domain model.

Ví dụ hệ thống ERP cũ gửi:

~~~json
{
  "CUST_NO": "000123",
  "ORD_STAT": "C",
  "NET_AMT": 1250000
}
~~~

Sales Context có thể nhận qua adapter, chuyển đổi thành:

~~~java
public record ImportedOrder(
    BuyerId buyerId,
    SalesOrderStatus status,
    Money acceptedTotal
) {}
~~~

ACL chịu trách nhiệm mapping code trạng thái, đơn vị tiền và semantics cũ. Domain model không nên mang tên cột hoặc quy tắc kỳ lạ của hệ thống ngoài.

ACL không chỉ là một mapper kỹ thuật. Nó bảo vệ ngôn ngữ và quy tắc của context khỏi ảnh hưởng từ một mô hình khác.

## 13. Tổ chức code theo Bounded Context và giữ layer bên trong

Một modular monolith có thể tổ chức:

~~~text
application/
  sales/
    api/
    application/
    domain/
    infrastructure/
  inventory/
    api/
    application/
    domain/
    infrastructure/
  fulfillment/
    api/
    application/
    domain/
    infrastructure/
~~~

Hoặc theo Gradle module:

~~~text
modules/
  sales/
  inventory/
  fulfillment/
  shared-contracts/
~~~

Mỗi module có thể dùng Controller, Application Service, Domain Model và Repository riêng. Public API chỉ công bố capability mà module khác cần.

### Ví dụ dependency rule

~~~text
Sales
  -> Sales public API
  -> Sales application
  -> Sales domain
  -> Sales infrastructure adapters

Fulfillment
  -> Fulfillment public API
  -> Fulfillment application
  -> Fulfillment domain
  -> Fulfillment infrastructure adapters

Cross-context:
  Sales -> Fulfillment contract
~~~

Tránh:

~~~text
Sales -> Fulfillment internal JPA entity
Sales -> Fulfillment repository implementation
Fulfillment -> Sales private domain object
~~~

Nếu hai module phải chia sẻ một contract, hãy đặt contract ở ranh giới có owner rõ hoặc tạo published language nhỏ. Không chuyển toàn bộ domain entity vào shared module.

## 14. Database schema nên theo ownership, không theo cách chia context máy móc

Sau khi xác định Bounded Context, database schema có thể phản ánh ownership:

~~~text
Database cluster
  sales_schema
    sales_order
    sales_order_line
    promotion

  inventory_schema
    stock_item
    reservation

  fulfillment_schema
    delivery_order
    shipment
    package
~~~

Đây là một cách triển khai, không phải quy tắc bắt buộc. Các context có thể dùng database vật lý riêng hoặc cùng cluster. Điều quan trọng là chỉ owner được phép thay đổi dữ liệu và invariant của mình.

### Một Bounded Context có thể có nhiều schema/table

Sales Context có thể cần nhiều bảng, view, event store hoặc read model. Chúng vẫn thuộc một context nếu cùng phục vụ một mô hình và ownership.

### Một database có thể chứa nhiều context

Trong modular monolith, dùng chung một database instance có thể giảm chi phí vận hành. Có thể tách schema, database user hoặc quyền truy cập để ngăn module khác ghi trực tiếp dữ liệu nội bộ.

### Projection không tạo ra Bounded Context mới

Một bảng báo cáo hoặc read model được tạo từ event của Sales có thể thuộc Reporting/Data Platform. Nó không nhất thiết trở thành owner của SalesOrder. Phải phân biệt dữ liệu nguồn, dữ liệu dẫn xuất và quyền quyết định nghiệp vụ.

## 15. Không tách một context chỉ vì một bảng tăng tải

Một bảng có thể trở thành điểm nghẽn về hiệu năng. Điều đó là tín hiệu để xem xét partitioning, indexing, caching, read replica, archive hoặc thay đổi data access. Nó không tự động chứng minh cần một Bounded Context mới.

Ví dụ bảng order_line có lượng đọc lớn do báo cáo:

- Nếu truy vấn báo cáo không cần transaction với Sales, có thể tạo projection/read model.
- Nếu write contention cao, xem lại Aggregate, transaction và index.
- Nếu dữ liệu lịch sử quá lớn, có thể archive theo policy.
- Nếu workload khác biệt rõ và có ownership riêng, mới cân nhắc một capability hoặc service độc lập.

Tách bảng thành service có thể tạo thêm API và consistency problem trong khi nguyên nhân gốc chỉ là query chưa tối ưu.

## 16. Không gom mọi thứ vào một context vì cùng dùng database

Chiều ngược lại cũng nguy hiểm. Một database chung có thể chứa dữ liệu Sales, Inventory, Payment và HR. Điều đó không làm chúng thành một domain model.

Một context quá lớn thường có:

- Một mô hình chứa nhiều trạng thái không liên quan.
- Một enum được dùng với nhiều nghĩa.
- Nhiều team sửa cùng Aggregate hoặc entity.
- Quy tắc nghiệp vụ nằm trong nhiều service và trigger.
- Mọi thay đổi đều có phạm vi ảnh hưởng rộng.
- Không thể xác định owner của dữ liệu hoặc quyết định.

Hãy chia context khi ngôn ngữ, policy, lifecycle hoặc ownership thực sự khác nhau. Không chia chỉ vì package hoặc bảng có tên khác nhau.

## 17. Quy trình khám phá Bounded Context

Một quy trình thực tế có thể bắt đầu bằng workshop với chuyên gia nghiệp vụ và đội phát triển.

**Bước 1: Xác định business capability.** Liệt kê doanh nghiệp cần làm gì để tạo giá trị, không bắt đầu bằng danh sách bảng.

**Bước 2: Thu thập ngôn ngữ.** Ghi thuật ngữ, định nghĩa, ví dụ và các trường hợp mà chuyên gia hiểu khác nhau.

**Bước 3: Truy dấu workflow.** Theo dõi một use case từ đầu đến cuối: ai khởi tạo, ai quyết định, ai thay đổi trạng thái, kết quả nào được công bố.

**Bước 4: Tìm invariant.** Xác định quy tắc nào phải được bảo vệ cùng nhau và nơi nào có quyền ra quyết định.

**Bước 5: Xác định ownership và lifecycle.** Ai tạo, sửa, hủy, lưu trữ và chịu trách nhiệm khi dữ liệu sai?

**Bước 6: So sánh change pattern.** Những phần nào thường thay đổi cùng nhau? Những phần nào có nhịp thay đổi riêng?

**Bước 7: Đề xuất model boundary.** Vẽ các context, model chính, contract và giả thuyết quan hệ.

**Bước 8: Kiểm tra bằng ví dụ cụ thể.** Chạy thử các use case khó qua ranh giới dự kiến. Nếu cần nhiều truy vấn nội bộ hoặc phải chia sẻ invariant, xem lại boundary.

**Bước 9: Lập Context Map.** Ghi upstream/downstream, ACL, published language và ownership.

**Bước 10: Thử trong code.** Tạo module boundary và architecture test trước khi quyết định tách deployment.

## 18. Ví dụ chuyển từ cấu trúc theo bảng sang Bounded Context

Giả sử ứng dụng ban đầu có package và bảng:

~~~text
CustomerController
CustomerService
CustomerRepository
OrderController
OrderService
OrderRepository
PaymentController
PaymentService
PaymentRepository

customer
orders
payment
shipment
stock
~~~

Đội muốn tách thành một service cho từng repository. Trước khi làm, hãy truy dấu capability:

| Capability | Quyết định nghiệp vụ | Model có thể sở hữu |
|---|---|---|
| Sell Products | Chấp nhận Order, giá và discount | SalesOrder, Promotion |
| Manage Stock | Giữ và giải phóng hàng | StockItem, Reservation |
| Collect Payment | Authorize, capture, refund | PaymentAttempt, Payment |
| Deliver Goods | Đóng gói và giao | Shipment, DeliveryOrder |
| Support Customer | Tiếp nhận và xử lý yêu cầu hỗ trợ | SupportCase, CustomerContact |

Sau đó tổ chức module:

~~~text
sales/
  domain/
  application/
  api/
  infrastructure/

inventory/
  domain/
  application/
  api/
  infrastructure/

payment/
  domain/
  application/
  api/
  infrastructure/

fulfillment/
  domain/
  application/
  api/
  infrastructure/
~~~

Các module vẫn có thể chạy trong cùng JVM. Khi cần, Sales gọi Inventory qua interface nội bộ hoặc event dispatcher. Việc chuyển sang HTTP/broker chỉ xảy ra sau khi contract và lý do triển khai độc lập được xác nhận.

### Thử một thay đổi

Giả sử chính sách reservation thay đổi: hệ thống cần giữ hàng trong 10 phút thay vì 15 phút.

- Nếu Inventory sở hữu Reservation và timeout policy, thay đổi nằm trong Inventory.
- Sales chỉ cần nhận ReservationAccepted/ReservationExpired nếu contract đã định nghĩa.
- Fulfillment không cần biết cách Inventory tính thời hạn.
- Reporting có thể cập nhật projection nếu cần phân tích thời gian giữ hàng.

Nếu thay đổi này buộc sửa mọi repository hoặc entity chung, ranh giới hiện tại có thể đang phản ánh schema hơn là ownership nghiệp vụ.

## 19. Kiểm tra ranh giới bằng use case và thay đổi

Một ranh giới chỉ đẹp trên sơ đồ chưa chắc hữu ích. Hãy thử nghiệm với những thay đổi thực tế:

### Use case xuyên context

Đặt câu hỏi:

- Context nào ra quyết định?
- Context nào chỉ cung cấp thông tin?
- Kết quả được công bố bằng API hay event?
- Có phải đọc bảng nội bộ của context khác không?
- Nếu một context tạm thời unavailable, workflow chuyển trạng thái thế nào?

### Thay đổi độc lập

Thử mô phỏng:

- Sales đổi discount policy.
- Inventory đổi cách tính available quantity.
- Payment đổi provider.
- Fulfillment thêm trạng thái giao hàng.

Nếu thay đổi một context liên tục buộc sửa mô hình của context khác, hãy xem lại contract hoặc boundary.

### Invariant

Kiểm tra các quy tắc có bị chia qua nhiều context mà không có owner không. Ví dụ, nếu Sales và Inventory cùng ghi số lượng stock, không context nào thực sự bảo vệ invariant.

## 20. Khi nào cần Shared Kernel và khi nào cần ACL?

Không phải lúc nào cũng phải tạo mô hình hoàn toàn khác. Một số khái niệm có thể được chia sẻ nếu semantics ổn định và hai nhóm chấp nhận cùng sở hữu phần đó.

### Shared Kernel

Shared Kernel là một phần mô hình nhỏ được các context cùng thống nhất. Nó cần:

- Phạm vi hẹp.
- Owner và quy trình thay đổi chung.
- Test tương thích.
- Versioning và lịch nâng cấp.
- Sự đồng thuận về semantics.

Không dùng Shared Kernel làm thư viện chứa mọi entity, DTO và enum.

### Anti-Corruption Layer

Dùng ACL khi mô hình upstream/legacy có semantics không phù hợp. ACL chuyển đổi dữ liệu và hành vi sang model nội bộ, giữ domain không bị nhiễm khái niệm ngoài.

Nếu hai context cùng dùng một identifier chuẩn và một contract rất ổn định, có thể chia sẻ contract đó mà không chia sẻ toàn bộ domain object.

## 21. Các lỗi thường gặp

**Một bảng là một Bounded Context.** Bảng chỉ là cấu trúc lưu trữ; một context thường sở hữu nhiều bảng và hành vi.

**Một Aggregate là một Bounded Context.** Aggregate bảo vệ invariant trong một ranh giới nhất quán nhỏ hơn; context thường chứa nhiều Aggregate.

**Một tầng kỹ thuật là một Bounded Context.** Controller, Service và Repository là cách tổ chức code, không phải mô hình nghiệp vụ.

**Một context phải là một microservice.** Context có thể chạy trong modular monolith. Deployment là quyết định khác.

**Dùng một Entity chung cho mọi context.** Cùng tên không có nghĩa cùng semantics hoặc lifecycle.

**Dùng shared database như contract.** Consumer bị ràng buộc vào schema và quy tắc nội bộ của owner.

**Tách quá nhỏ để đạt loose coupling.** Quá nhiều context/service nhỏ làm tăng mapping, network call và phối hợp.

**Gom mọi thứ vì cùng database.** Một schema chung không chứng minh các mô hình có cùng ngôn ngữ hoặc invariant.

**Chia team theo technical layer.** Một thay đổi capability phải đi qua nhiều nhóm và làm chậm phản hồi.

**Đặt domain rule trong controller hoặc repository.** Hành vi nghiệp vụ không có owner rõ và dễ bị bỏ qua từ đường gọi khác.

**Tạo Shared Kernel quá lớn.** Mọi context bị buộc vào cùng nhịp thay đổi.

**Không lập Context Map.** Ranh giới được vẽ nhưng quan hệ upstream/downstream và trách nhiệm contract không rõ.

## 22. Checklist đánh giá Bounded Context

- [ ] Ranh giới được giải thích bằng capability hoặc mô hình nghiệp vụ.
- [ ] Các thuật ngữ bên trong context có định nghĩa nhất quán.
- [ ] Có chuyên gia/team chịu trách nhiệm cho model.
- [ ] Các invariant quan trọng có owner rõ.
- [ ] Lifecycle của dữ liệu và hành vi được xác định.
- [ ] Context không được tạo chỉ vì một bảng hoặc một package.
- [ ] Aggregate boundary được phân biệt với context boundary.
- [ ] Các context không chia sẻ domain entity chỉ vì tên giống nhau.
- [ ] Giao tiếp qua API/event contract có semantics rõ.
- [ ] Data owner kiểm soát quyền ghi và schema.
- [ ] Context Map thể hiện quan hệ upstream/downstream.
- [ ] ACL hoặc Shared Kernel chỉ được dùng khi có lý do và phạm vi rõ.
- [ ] Use case xuyên context có failure/consistency strategy.
- [ ] Có thể thay đổi một context mà không sửa implementation nội bộ của context khác.
- [ ] Deployment boundary được quyết định riêng dựa trên nhu cầu vận hành.

## 23. Bài tập tự kiểm tra

Một hệ thống thương mại điện tử có các bảng:

~~~text
customer
customer_address
orders
order_line
payment
stock
shipment
support_ticket
~~~

Đội phát triển đề xuất tạo tám Bounded Context tương ứng với tám bảng. Một nhóm khác đề xuất ba module kỹ thuật: API, Business Logic và Database.

Hãy trả lời:

1. Vì sao hai cách chia trên chưa đủ cơ sở để xác định Bounded Context?
2. Những business capability nào có thể tồn tại trong hệ thống?
3. Order trong Sales và Fulfillment có nhất thiết dùng cùng một Entity không?
4. Context nào nên sở hữu Reservation và invariant số lượng khả dụng?
5. Payment cần công bố thông tin nào cho Sales?
6. Support cần dữ liệu Customer nào và có cần dùng Customer Aggregate của Sales không?
7. Reporting có thể đọc dữ liệu mà không phụ thuộc schema nội bộ bằng cách nào?
8. Khi nào một Shared Kernel nhỏ có thể phù hợp?
9. Dùng ACL ở đâu nếu hệ thống cũ gửi mã trạng thái khó hiểu?
10. Những thử nghiệm nào chứng minh ranh giới được đề xuất là hợp lý?

Gợi ý:

| Câu hỏi | Hướng trả lời |
|---|---|
| Chia theo bảng | Không phản ánh ngôn ngữ, invariant, capability hoặc ownership |
| Chia theo tầng | Chỉ phản ánh technical organization; không gom trọn một mô hình nghiệp vụ |
| Capability | Sales, Inventory, Payment, Fulfillment, Customer Support, Reporting |
| Order model | Sales và Fulfillment có thể có model riêng với contract liên kết |
| Reservation | Inventory sở hữu Stock và Reservation |
| Payment | Công bố PaymentAuthorized, PaymentCaptured hoặc PaymentFailed cùng reference cần thiết |
| Support | Dùng CustomerId và snapshot/API contract; chỉ chia sẻ model nếu semantics thực sự thống nhất |
| Reporting | Projection hoặc data pipeline có contract và ownership |
| Shared Kernel | Chỉ cho identifier/value contract nhỏ, ổn định và có đồng thuận |
| ACL | Chuyển mã trạng thái/field legacy sang thuật ngữ domain nội bộ |
| Kiểm chứng | Thử use case xuyên context, thay đổi độc lập, invariant và failure scenario |

## Kết luận

Bounded Context được hình thành quanh một mô hình nghiệp vụ và ngôn ngữ có ý nghĩa nhất quán. Database table và technical layer có thể là cách tổ chức dữ liệu hoặc code bên trong một context, nhưng không phải tiêu chí đủ để xác định ranh giới. Chia theo bảng dễ phân tán một quyết định nghiệp vụ qua nhiều nơi; chia theo tầng kỹ thuật dễ làm một capability bị rải qua nhiều package và team.

Hãy bắt đầu từ business capability, ubiquitous language, invariant, lifecycle, ownership và change pattern. Sau đó mô tả quan hệ bằng Context Map, bảo vệ model bằng contract/ACL khi cần và tổ chức code theo context với các tầng kỹ thuật bên trong. Một Bounded Context tốt không được đo bằng số bảng hay số service; nó được đánh giá qua việc mô hình có rõ nghĩa, có owner và có thể tiến hóa mà không kéo theo những thay đổi không cần thiết ở nơi khác.
