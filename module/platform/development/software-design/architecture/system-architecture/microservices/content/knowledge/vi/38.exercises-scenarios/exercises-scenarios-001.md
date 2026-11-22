# Phân rã một hệ thống thương mại điện tử và bảo vệ lựa chọn ranh giới

Thiết kế kiến trúc Microservices thường bắt đầu bằng một câu hỏi tưởng đơn giản: một hệ thống thương mại điện tử nên được chia thành những service nào? Có thể nhìn vào danh sách chức năng rồi tạo Catalog Service, Cart Service, Order Service, Payment Service và Inventory Service. Nhưng tên gọi hợp lý chưa chứng minh ranh giới đó tốt. Một service có thể quá lớn, một service khác quá nhỏ; hai service có thể cùng sửa một dữ liệu, phải triển khai đồng thời hoặc gọi nhau đồng bộ qua nhiều bước. Khi đó hệ thống có nhiều deployment nhưng chưa có tính độc lập thực sự.

Bài tập này đưa ra một tình huống thương mại điện tử và yêu cầu người học **phân rã hệ thống dựa trên domain, luồng giá trị, dữ liệu, consistency, team ownership và yêu cầu vận hành; sau đó bảo vệ từng lựa chọn bằng bằng chứng và trade-off**. Mục tiêu không phải tìm một sơ đồ duy nhất đúng cho mọi cửa hàng. Mục tiêu là trình bày được vì sao ranh giới được chọn phù hợp với bối cảnh, rủi ro nào được chấp nhận và khi nào cần thay đổi quyết định.

Bài học thuộc nhóm **Bài tập và tình huống** trong chủ đề Software Design, Architecture, System Architecture và Microservices.

## 1. Kết quả học tập

Sau khi hoàn thành bài tập, bạn có thể:

- Từ yêu cầu nghiệp vụ xác định các capability và bounded context của một nền tảng thương mại điện tử.
- Phân biệt module, bounded context, service, database ownership và deployment boundary.
- Vẽ context map, dependency graph và các luồng giao dịch quan trọng.
- Đề xuất danh sách service vừa đủ, giải thích lý do gộp/tách từng capability.
- Xác định nguồn sự thật cho catalog, giá, tồn kho, đơn hàng, thanh toán và vận chuyển.
- Thiết kế contract đồng bộ và bất đồng bộ giữa các service.
- Phân tích consistency, transaction boundary, saga và compensation.
- Đánh giá khả năng scale, fault isolation, security, data residency và observability.
- So sánh phương án Microservices với modular monolith và kiến trúc phân lớp.
- Viết Architecture Decision Record (ADR) để ghi lại lựa chọn, phương án thay thế và hệ quả.
- Bảo vệ kiến trúc trước phản biện bằng yêu cầu, dữ liệu, giả định và trade-off thay vì viện dẫn xu hướng công nghệ.

## 2. Bối cảnh hệ thống

Một doanh nghiệp vận hành nền tảng bán lẻ trực tuyến, phục vụ khách hàng cá nhân và một số khách hàng doanh nghiệp. Khách hàng có thể duyệt sản phẩm, tìm kiếm, thêm hàng vào giỏ, áp mã giảm giá, thanh toán, theo dõi giao hàng và yêu cầu trả hàng.

Hệ thống hiện tại là một ứng dụng backend lớn với một relational database. Một số nhóm nghiệp vụ được phát triển độc lập nhưng vẫn dùng chung bảng dữ liệu. Khi có chiến dịch bán hàng lớn, tìm kiếm và reporting làm tăng tải database; checkout bị chậm. Mỗi lần thay đổi giá hoặc quy tắc khuyến mãi thường phải phối hợp nhiều team. Doanh nghiệp muốn tiến hóa kiến trúc để tăng khả năng phát hành độc lập, mở rộng theo tải và giới hạn sự cố.

### 2.1. Năng lực nghiệp vụ hiện có

- Quản lý sản phẩm, danh mục, thuộc tính, hình ảnh và nội dung.
- Tìm kiếm theo từ khóa, bộ lọc, gợi ý và xếp hạng.
- Quản lý giá niêm yết, giá theo phân khúc, chương trình khuyến mãi và coupon.
- Quản lý giỏ hàng của khách đã đăng nhập và khách vãng lai.
- Tạo đơn, chụp snapshot mặt hàng/giá, điều phối checkout.
- Quản lý số lượng tồn theo kho, reservation và giải phóng hàng.
- Authorization, capture, void và refund qua một hoặc nhiều payment provider.
- Quản lý fulfillment, đóng gói, vận chuyển, tracking và giao hàng.
- Gửi email, SMS, push notification.
- Quản lý tài khoản, địa chỉ, danh tính và quyền truy cập.
- Xử lý hủy đơn, đổi trả, hoàn tiền và khiếu nại.
- Báo cáo doanh thu, tồn kho, hành vi và hiệu quả chiến dịch.

### 2.2. Ràng buộc và giả định ban đầu

Để có một bài toán đủ cụ thể, sử dụng các giả định sau. Đây là dữ liệu mô phỏng cho bài tập; khi làm dự án thực, phải thay bằng số đo và chính sách thực tế.

| Thuộc tính | Giả định |
|---|---|
| Người dùng | 2 triệu tài khoản đã đăng ký |
| Hoạt động đồng thời ngày thường | 20.000 session |
| Peak trong chiến dịch | 100.000 session |
| Traffic đọc/ghi | Đọc nhiều hơn ghi, khoảng 8:1 |
| Catalog | 1,5 triệu SKU, nhiều biến thể |
| Kho | 8 kho vật lý và một số đối tác dropship |
| Payment | Hai nhà cung cấp, có timeout và callback bất đồng bộ |
| Khu vực | Phục vụ nhiều tỉnh/thành; có kế hoạch mở thêm thị trường |
| Availability checkout | Quan trọng hơn báo cáo realtime |
| Tìm kiếm | Có thể chấp nhận index trễ vài giây |
| Tồn kho | Không được xác nhận bán vượt số lượng khả dụng theo chính sách |
| Giá | Đơn đã tạo phải giữ snapshot giá và currency |
| Báo cáo | Có thể trễ vài phút, không cần chạy trên database giao dịch |
| Đội ngũ | Bốn nhóm sản phẩm, một nhóm platform và nhóm vận hành/bảo mật |

Không nên coi các con số trên là lý do tự động để dùng Microservices. Chúng chỉ tạo bối cảnh để thảo luận về peak load, read/write pattern, consistency và khả năng tổ chức.

## 3. Làm rõ yêu cầu trước khi vẽ service

Trước khi chia service, hãy phân loại yêu cầu thành bốn nhóm.

### 3.1. Functional requirements

Những hành vi hệ thống phải hỗ trợ:

- Khách hàng tìm sản phẩm theo từ khóa và bộ lọc.
- Xem thông tin sản phẩm và giá áp dụng.
- Tạo, cập nhật và xóa giỏ hàng.
- Kiểm tra khả năng bán và giữ hàng.
- Tạo đơn với snapshot sản phẩm/giá.
- Thanh toán, theo dõi trạng thái và xử lý callback.
- Hủy đơn, hoàn tiền và trả hàng.
- Theo dõi shipment và nhận thông báo.
- Nhân viên quản trị catalog, giá, kho và đơn.
- Nhân viên xem báo cáo và đối soát.

### 3.2. Quality attributes

Các yêu cầu chất lượng cần định lượng hoặc mô tả tình huống:

| Thuộc tính | Câu hỏi cần làm rõ |
|---|---|
| Availability | Checkout có thể chấp nhận trạng thái PENDING khi một dependency tạm lỗi không? |
| Latency | p95/p99 của search, product detail và checkout là bao nhiêu? |
| Scalability | Thành phần nào tăng tải đột biến theo chiến dịch? |
| Consistency | Giá, tồn kho, payment và order cần consistency ở mức nào? |
| Security | Dữ liệu thanh toán, tài khoản và địa chỉ được bảo vệ ra sao? |
| Resilience | Một payment provider lỗi có làm toàn checkout ngừng không? |
| Maintainability | Team có thể thay đổi một capability mà không deploy toàn hệ thống không? |
| Observability | Có thể truy vết một order xuyên nhiều service không? |
| Recovery | RTO/RPO của order, payment và inventory là gì? |
| Compliance | Dữ liệu cá nhân và dữ liệu thanh toán được lưu ở đâu, bao lâu? |

### 3.3. Constraints

Ghi rõ những điều không thể tùy ý thay đổi:

- Payment provider yêu cầu callback signature verification.
- Không lưu dữ liệu thẻ thô nếu không có phạm vi tuân thủ phù hợp.
- Tồn kho cần được giữ có thời hạn và giải phóng khi checkout thất bại.
- Đơn đã được xác nhận phải giữ snapshot giá đã chấp thuận.
- Các thao tác hoàn tiền phải có audit.
- Hệ thống hiện tại phải tiếp tục phục vụ trong khi migration.
- Team chưa có năng lực trực production cho quá nhiều runtime/database mới.

### 3.4. Giả định cần kiểm chứng

Phân biệt rõ fact, assumption và decision:

- Fact: hệ thống hiện có một database primary.
- Assumption: search index có thể trễ vài giây.
- Decision: checkout không truy vấn search index để xác nhận giá hoặc tồn kho.
- Open question: khách có được đặt hàng khi kho chính không khả dụng nhưng có kho khác không?
- Open question: payment authorization có hết hạn sau bao lâu?
- Open question: khi nào capture tiền — lúc đặt hàng, lúc xuất kho hay lúc giao hàng?

Kiến trúc được bảo vệ tốt bắt đầu bằng cách làm rõ điều chưa biết, không biến giả định thành yêu cầu chính thức.

## 4. Phân tích domain và capability map

Một cách bắt đầu là phân rã theo năng lực nghiệp vụ, không theo tên công nghệ hoặc database table.

~~~text
E-commerce
  |
  +-- Discover products
  |     +-- Catalog
  |     +-- Search
  |     +-- Recommendation
  |
  +-- Decide what to buy
  |     +-- Pricing
  |     +-- Promotion
  |     +-- Cart
  |
  +-- Purchase
  |     +-- Checkout / Order
  |     +-- Inventory reservation
  |     +-- Payment
  |
  +-- Deliver
  |     +-- Fulfillment
  |     +-- Shipping
  |     +-- Notification
  |
  +-- Support customer
  |     +-- Identity / Customer
  |     +-- Return / Refund
  |     +-- Customer support
  |
  +-- Operate business
        +-- Reporting / Analytics
        +-- Reconciliation
        +-- Administration
~~~

Capability map mô tả tổ chức làm gì. Nó chưa phải danh sách Microservices. Một capability có thể thuộc một bounded context hoặc một phần của context lớn hơn; một service có thể triển khai nhiều capability liên quan.

### 4.1. Dùng Event Storming để khám phá domain

Một workshop Event Storming có thể tập trung vào luồng “khách mua một sản phẩm”:

~~~text
ProductViewed
  -> ItemAddedToCart
  -> CartCheckedOut
  -> PriceCalculated
  -> InventoryReserved
  -> PaymentAuthorized
  -> OrderConfirmed
  -> ShipmentCreated
  -> ShipmentDelivered
~~~

Sau đó thêm các nhánh lỗi:

~~~text
InventoryReservationRejected
PaymentDeclined
PaymentResultUnknown
ReservationExpired
PaymentVoided
OrderCancelled
RefundRequested
RefundCompleted
ShipmentFailed
ReturnReceived
~~~

Mỗi event nên biểu diễn một sự kiện nghiệp vụ đã xảy ra. Command như ReserveInventory hoặc AuthorizePayment là yêu cầu hành động, không phải event thành công. Phân biệt hai loại giúp contract có semantics rõ.

### 4.2. Câu hỏi khi tìm bounded context

- Từ ngữ nào có nghĩa khác nhau ở các nhóm?
- Quy tắc nào thay đổi cùng nhau?
- Dữ liệu nào có một owner nghiệp vụ tự nhiên?
- Transaction nào cần atomic trong cùng một context?
- Capability nào có SLO, scale hoặc security khác biệt?
- Những nhóm nào thường phải phối hợp để thay đổi một quy tắc?
- Một context có thể cung cấp contract ổn định cho consumer không?

Không bắt đầu bằng “mỗi bảng một service”. Database schema hiện tại thường phản ánh lịch sử triển khai hơn là domain boundary.

## 5. Đề xuất bounded contexts

Một phân rã ban đầu có thể gồm:

| Bounded context | Trách nhiệm chính | Dữ liệu nguồn sự thật |
|---|---|---|
| Catalog | Sản phẩm, biến thể, danh mục, nội dung | Product, category, attributes |
| Search | Index và truy vấn tìm kiếm | Search projection; không phải nguồn catalog |
| Pricing | Giá áp dụng, price list, currency | Price rules và price lists |
| Promotion | Coupon, campaign, discount eligibility | Campaign, coupon, redemption |
| Cart | Giỏ hàng, item selection, cart lifecycle | Cart state |
| Order/Checkout | Order, snapshot, checkout workflow | Order, saga state |
| Inventory | Stock, warehouse, reservation | Stock ledger/reservations |
| Payment | Authorization, capture, void, refund | Payment operations |
| Fulfillment | Pick/pack, shipment request, fulfillment status | Fulfillment task |
| Shipping | Carrier integration, label, tracking | Shipment/tracking reference |
| Identity/Customer | Principal, profile, address, consent | Identity/customer profile |
| Notification | Delivery preferences và message status | Notification jobs/status |
| Returns | Return request, inspection, refund decision | Return case |
| Analytics | Reporting projections và aggregates | Derived analytical data |

Đây là **candidate contexts**, không bắt buộc tất cả trở thành deployment độc lập. Có thể gộp Pricing và Promotion trong giai đoạn đầu nếu cùng team, quy tắc và dữ liệu chưa có nhu cầu độc lập. Search thường là read model được xây từ Catalog/Pricing, không nhất thiết là một nguồn sự thật riêng cho product.

## 6. Từ bounded context đến service boundary

Sau khi có context, mới đánh giá context nào cần deployment độc lập.

### 6.1. Tiêu chí tách service

Một context là ứng viên tốt khi có nhiều yếu tố:

- Có domain model và invariant riêng.
- Có owner và dữ liệu nguồn sự thật rõ.
- Có nhịp thay đổi khác với context khác.
- Có yêu cầu scale/SLO/security riêng.
- Có contract có thể duy trì tương thích.
- Có thể triển khai và vận hành độc lập.
- Lợi ích của độc lập lớn hơn network, observability và consistency overhead.

### 6.2. Tiêu chí nên giữ chung hoặc bắt đầu bằng module

- Hai capability luôn thay đổi cùng nhau.
- Một transaction quan trọng phải giữ atomic và chưa có saga hợp lý.
- Chúng dùng chung một model nghiệp vụ chặt chẽ.
- Chưa có team/owner đủ khả năng vận hành riêng.
- Tải và SLO không khác biệt đáng kể.
- Việc tách chỉ tạo thêm RPC hoặc database mà không giảm coupling.

### 6.3. Candidate service map

~~~text
                    API Gateway / BFF
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
      Catalog API       Search API          Cart API
          |                 ^                  |
          v                 |                  |
      Catalog DB      Search Index             |
                            ^                  |
                            |                  |
                    Catalog/Pricing events     |
                                               v
                                         Order Service
                                          /    |    \
                                         /     |     \
                                        v      v      v
                                  Inventory  Payment Fulfillment
                                     |          |         |
                                     v          v         v
                                  Stock DB   Payment DB  Shipment flow
~~~

Diagram này là một phương án để tranh luận, không phải sơ đồ đã được chứng minh tối ưu. Bước tiếp theo phải làm rõ luồng dữ liệu, ownership và các dependency.

## 7. Bảo vệ từng boundary bằng lý do cụ thể

Một ranh giới nên được giải thích bằng bốn câu:

1. **Capability:** service chịu trách nhiệm nghiệp vụ nào?
2. **Ownership:** dữ liệu và quyết định nào thuộc về service?
3. **Independence:** thay đổi/scale/recovery nào cần độc lập?
4. **Contract:** service khác tương tác qua API/event nào?

Ví dụ:

| Boundary | Lý do tách | Bằng chứng cần có | Rủi ro/chi phí |
|---|---|---|---|
| Search khỏi Catalog | Search read-heavy, index có thể stale | Query volume, indexing lag, scaling profile | Projection consistency và reindex |
| Inventory khỏi Order | Stock invariant, reservation concurrency | Oversell incidents, warehouse rules | Saga và reservation lifecycle |
| Payment khỏi Order | PCI/security, provider integration, payment lifecycle | Audit, gateway behavior, refund workflow | Unknown outcome/reconciliation |
| Fulfillment khỏi Order | Pick/pack có vòng đời riêng | Shipment workflow, carrier integration | Order/fulfillment consistency |
| Notification khỏi Checkout | Delivery có thể bất đồng bộ | Retry/backlog, provider quotas | Eventual delivery |
| Pricing khỏi Catalog | Giá/campaign thay đổi theo policy riêng | Pricing rules, promotion cadence | Price snapshot và rule coordination |

Không được ghi “dễ scale hơn” nếu chưa xác định component nào cần scale và metric nào chứng minh. Không ghi “bảo mật tốt hơn” nếu service vẫn dùng chung credential và database.

## 8. Thiết kế ranh giới Catalog và Search

Catalog sở hữu thông tin sản phẩm chính thức: SKU, tên, mô tả, thuộc tính, danh mục, trạng thái bán. Search phục vụ query theo từ khóa, filter và relevance. Search index là projection có thể được rebuild từ nguồn dữ liệu chính.

### 8.1. Contract

Catalog phát event khi sản phẩm thay đổi:

~~~json
{
  "eventId": "evt-catalog-001",
  "eventType": "ProductPublished",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T04:00:00Z",
  "aggregateId": "SKU-1001",
  "payload": {
    "sku": "SKU-1001",
    "name": "Wireless Headphones",
    "categoryId": "audio",
    "attributes": {
      "brand": "Example",
      "color": "black"
    }
  }
}
~~~

Search consumer cập nhật index. Nếu event đến trễ, kết quả tìm kiếm có thể chưa phản ánh sản phẩm mới; product detail vẫn đọc Catalog để xác nhận trạng thái và thông tin chính xác.

### 8.2. Vì sao Search không phải nguồn sự thật?

- Search index có thể được xóa và rebuild.
- Indexing có độ trễ.
- Mapping/analysis có thể thay đổi theo phiên bản.
- Một số field bị lược bỏ hoặc chuẩn hóa để phục vụ truy vấn.
- Query relevance không phải business rule của Catalog.

Nếu search trả về SKU đã ngừng bán, bước add-to-cart/checkout phải xác minh với nguồn có thẩm quyền.

## 9. Thiết kế ranh giới Pricing, Promotion và Cart

Pricing tính giá áp dụng theo customer segment, region, currency và thời điểm. Promotion quyết định điều kiện chiến dịch/coupon. Cart giữ lựa chọn của khách hàng, nhưng không nên là nơi quyết định giá cuối cùng.

Một cách phân chia:

- Catalog cung cấp product identity và thuộc tính cơ bản.
- Pricing cung cấp quote hoặc price calculation.
- Promotion cung cấp eligibility/discount decision, có thể được gọi bởi Pricing hoặc phối hợp qua contract.
- Cart giữ SKU, quantity và các lựa chọn người dùng.
- Checkout yêu cầu tính lại giá tại thời điểm đặt đơn và lưu snapshot.

### 9.1. Quote và snapshot

Giá trong cart có thể thay đổi trước khi checkout. Vì vậy, cart nên hiển thị giá và thời hạn quote nếu cần, nhưng Order phải lưu snapshot được chấp nhận tại thời điểm tạo order:

~~~json
{
  "sku": "SKU-1001",
  "quantity": 2,
  "unitPriceMinor": 1250000,
  "currency": "VND",
  "discountMinor": 100000,
  "priceVersion": "price-2026-11-12-07"
}
~~~

Giá trị chỉ minh họa. Snapshot cần giữ đủ thông tin để giải thích tổng tiền về sau: đơn giá, discount, thuế/phí theo policy, currency, version hoặc reference của rule và thời điểm tính.

### 9.2. Câu hỏi bảo vệ boundary

- Promotion là một context độc lập hay chỉ là module trong Pricing?
- Coupon redemption cần atomic với order hay có thể reserve coupon trước?
- Một campaign có giới hạn số lượt toàn hệ thống không?
- Giá được khóa khi thêm vào cart hay khi tạo order?
- Khi campaign thay đổi giữa lúc quote và checkout, khách được xử lý thế nào?

Nếu chưa có nhu cầu độc lập, bắt đầu bằng Pricing/Promotion module chung có thể giảm distributed transaction. Tách sau khi quy tắc, owner và scale profile đủ khác biệt.

## 10. Cart và Order có nên là một service?

Cart và Order có quan hệ gần nhưng lifecycle khác nhau.

**Cart**:
- Thường thay đổi liên tục.
- Có thể tồn tại với dữ liệu chưa hoàn chỉnh.
- Có thể thuộc session khách vãng lai.
- Có thể hết hạn hoặc bị bỏ quên.
- Cần thao tác nhanh, tối ưu đọc/ghi và merge cart.

**Order**:
- Là hồ sơ giao dịch sau khi khách xác nhận.
- Cần snapshot item, price và customer details cần thiết.
- Có lifecycle, audit và retention.
- Không được thay đổi tùy tiện sau khi xác nhận.
- Kích hoạt inventory, payment và fulfillment workflow.

Hai capability có thể bắt đầu trong cùng một deployment nhưng cần model và state transition riêng. Khi nhịp thay đổi, SLO hoặc ownership khác biệt, có thể tách deployment.

### 10.1. Cart-to-order handoff

Checkout gửi cart version hoặc nội dung đã xác nhận; Order tạo snapshot bất biến theo quy tắc. Sau khi tạo order thành công, cart có thể được đánh dấu checked out hoặc clear theo policy. Nếu request lặp do client retry, idempotency key phải ngăn tạo hai order.

Không nên cho Order Service truy vấn trực tiếp Cart DB hoặc Cart sửa Order DB. Dùng contract và xác định thời điểm chuyển ownership.

## 11. Order và Inventory: ranh giới quan trọng

Order là nguồn sự thật của trạng thái đơn. Inventory là nguồn sự thật của stock và reservation. Hai service cần phối hợp nhưng không chia sẻ bảng.

### 11.1. Reservation thay vì chỉ kiểm tra stock

Một thao tác “check available” rồi sau đó “decrement” có race condition: hai checkout cùng thấy còn một sản phẩm và cả hai cùng đặt. Inventory cần một thao tác reserve atomic:

~~~text
available = 1

Request A: reserve 1 -> success
Request B: reserve 1 -> rejected

Không thực hiện:
A: check available -> 1
B: check available -> 1
A: decrement
B: decrement
~~~

Reservation có ID, order reference, expiry và state. Khi Payment decline hoặc workflow hủy, Order gửi release command. Khi đơn tiếp tục fulfillment, reservation có thể được commit/consume theo chính sách.

### 11.2. Không giữ transaction xuyên service

Order không mở transaction database rồi gọi Inventory qua HTTP và chờ Payment. Mỗi service commit trạng thái cục bộ; saga điều phối các bước. Nếu cần strong consistency cho số lượng một SKU, invariant phải được bảo vệ bên trong Inventory bằng conditional update, locking hoặc cơ chế concurrency phù hợp.

### 11.3. Ví dụ saga

~~~text
Create Order PENDING
       |
       v
Reserve Inventory
       |
       +---- reject ----> Cancel Order
       |
       v
Authorize Payment
       |
       +---- decline ---> Release Reservation ---> Cancel
       |
       +---- unknown --> Reconcile Payment
       |
       v
Confirm Order
       |
       v
Publish OrderConfirmed
~~~

Compensation có thể là release reservation hoặc void authorization. Không phải mọi side effect đều đảo ngược hoàn toàn; nếu đã capture hoặc giao hàng, cần refund/return workflow riêng.

## 12. Payment là context độc lập vì sao?

Payment thường có lifecycle và yêu cầu bảo mật/audit riêng:

- Authorization, capture, void, refund.
- Idempotency và chống giao dịch trùng.
- Callback/webhook signature.
- Reconciliation với provider.
- Timeout không rõ kết quả.
- Tokenization và quản lý payment method reference.
- Quyền truy cập dữ liệu và audit trail.
- Tích hợp nhiều provider và routing theo phương thức thanh toán.

Payment Service sở hữu trạng thái giao dịch và external reference. Order chỉ lưu paymentId, amount snapshot và kết quả cần thiết cho order workflow.

### 12.1. Timeout không phải decline

Nếu gateway đã authorize nhưng response bị mất, Payment phải biểu diễn UNKNOWN hoặc RECONCILIATION_REQUIRED. Retry bằng key mới có thể tạo giao dịch trùng. Order giữ trạng thái đang xử lý và không tự khẳng định thất bại cho đến khi kết quả được xác định.

### 12.2. Tách payment khỏi order không có nghĩa gọi payment ở mọi nơi

Các service nghiệp vụ khác nên đi qua Payment API hoặc contract phù hợp. Không để mỗi team tích hợp trực tiếp với gateway, vì khi provider đổi protocol hoặc security policy, nhiều service phải cập nhật đồng loạt.

## 13. Fulfillment, Shipping và Returns

Fulfillment bắt đầu sau khi order được phép thực hiện. Nó có thể quản lý pick/pack, phân bổ kho, đóng gói và tạo shipment request. Shipping quản lý carrier, label, tracking và trạng thái vận chuyển. Returns quản lý yêu cầu trả hàng, nhận hàng, kiểm tra và quyết định hoàn tiền.

Có thể bắt đầu với một Fulfillment context chứa shipping integration nếu quy mô nhỏ. Tách Shipping khi carrier integration, tracking volume, SLA và owner đủ khác biệt. Returns có thể nằm trong Order/Support lúc đầu, nhưng khi có quy tắc inspection, restocking và refund riêng, nó có thể trở thành bounded context.

### 13.1. Vì sao không gộp toàn bộ hậu mãi vào Order?

Order cần biết trạng thái tổng quát của giao dịch. Nhưng shipment, return, refund có lifecycle và các sự kiện riêng. Nhồi mọi quy tắc vào Order sẽ làm aggregate quá lớn, nhiều team cùng thay đổi và khó vận hành. Order có thể giữ reference/trạng thái tổng hợp; từng context sở hữu chi tiết của mình.

## 14. Identity và Customer data

Identity chịu trách nhiệm principal, authentication, credential và token lifecycle. Customer context có thể quản lý profile, địa chỉ, consent và preference. Hai phần này có thể dùng chung provider hoặc tách theo nhu cầu bảo mật và domain.

Một số dữ liệu như địa chỉ giao hàng cần được snapshot vào order tại thời điểm xác nhận để tránh thay đổi profile sau này làm thay đổi lịch sử giao dịch. Order chỉ lưu phần dữ liệu cần thiết và tuân thủ retention/privacy policy.

Không dùng email hoặc số điện thoại làm khóa nội bộ xuyên mọi service nếu có thể dùng customerId ổn định. Quyền truy cập cần được kiểm tra ở mỗi boundary; API gateway không thay thế authorization nghiệp vụ ở service.

## 15. Notification và Analytics

Notification là tác vụ delivery có thể retry, có quota provider và trạng thái gửi riêng. Checkout không nên chờ email được gửi xong mới xác nhận order. Order phát event, Notification tạo job và xử lý bất đồng bộ.

Analytics cần truy vấn tổng hợp và scan dữ liệu lớn; không nên chạy report nặng trên transactional database của Order hoặc Inventory. Có thể nhận event/CDC, xây warehouse/read model và chấp nhận độ trễ đã công bố.

### 15.1. Reporting không phải nguồn sự thật giao dịch

Nếu báo cáo doanh thu có độ trễ vài phút, đó là trade-off chấp nhận được theo giả định. Khi cần đối soát tài chính, phải xác định nguồn giao dịch chính thức và quy trình reconciliation; không lấy một dashboard eventual consistent làm căn cứ cuối cùng cho hoàn tiền.

## 16. Context map và dependency direction

Một context map có thể mô tả provider/consumer và các quan hệ:

~~~text
Catalog ---------> Search Projection
   |
   v
Pricing <-------- Promotion
   |
   v
Cart -----------> Order/Checkout
                       |
               +-------+-------+
               |               |
               v               v
           Inventory         Payment
               |               |
               +-------+-------+
                       |
                       v
                  Fulfillment
                       |
                       v
                    Shipping

Order / Payment / Fulfillment
             |
             v
        Notification
             |
             v
          Customer

Domain Events / CDC
        |
        v
    Analytics
~~~

Sơ đồ cần được tinh chỉnh theo business flow thật. Ví dụ Promotion có thể được Pricing gọi, hoặc hai capability có thể nằm trong cùng context. Search nhận projection từ Catalog và Pricing; Analytics nhận dữ liệu từ nhiều nguồn. Mỗi mũi tên cần chỉ rõ API/event, owner, consistency và failure behavior.

### 16.1. Tránh dependency vòng

Nếu Catalog gọi Pricing, Pricing gọi Promotion, Promotion lại gọi Catalog trong cùng request, dễ tạo cycle. Xem xét:
- Dữ liệu nào cần được snapshot vào quote?
- Có thể publish event để cập nhật projection?
- Có thể đưa một rule về đúng bounded context?
- Có cần một orchestration use case thay vì ba service gọi nhau vòng tròn?

Dependency graph có chu trình không luôn sai, nhưng synchronous cycle trong critical path làm khó deploy, debug và phục hồi.

## 17. Thiết kế contract giữa service

Mỗi service nên công bố contract theo nhu cầu consumer, không expose database entity.

### 17.1. API contract

Ví dụ Inventory API:

~~~http
POST /api/v1/reservations
Idempotency-Key: reserve-order-9001
Content-Type: application/json

{
  "reservationId": "res-order-9001",
  "orderId": "order-9001",
  "items": [
    {"sku": "SKU-001", "quantity": 2}
  ],
  "expiresAt": "2026-11-12T04:15:00Z"
}
~~~

Response:

~~~json
{
  "reservationId": "res-order-9001",
  "status": "RESERVED",
  "expiresAt": "2026-11-12T04:15:00Z"
}
~~~

Contract cần quy định validation, error codes, timeout expectations, idempotency, authorization, versioning và semantics của expiry.

### 17.2. Event contract

OrderConfirmed có thể là:

~~~json
{
  "eventId": "evt-order-9001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T04:10:00Z",
  "aggregateId": "order-9001",
  "correlationId": "checkout-9001",
  "payload": {
    "orderId": "order-9001",
    "customerId": "customer-100",
    "totalMinor": 2500000,
    "currency": "VND"
  }
}
~~~

Event chỉ mang dữ liệu consumer cần và được phép dùng. Không serialize toàn bộ JPA entity hoặc dữ liệu cá nhân dư thừa.

### 17.3. Versioning và compatibility

- Thêm field optional với semantics rõ.
- Consumer cũ cần xử lý field lạ theo schema policy.
- Không đổi ý nghĩa field hiện tại mà giữ version.
- Breaking change có kế hoạch migrate hoặc version mới.
- Contract tests phải chạy ở provider và consumer.
- Deprecation có thời hạn và telemetry xác nhận consumer đã chuyển.

## 18. Chọn giao tiếp đồng bộ hay bất đồng bộ

| Tình huống | Giao tiếp gợi ý | Lý do |
|---|---|---|
| Product detail cần phản hồi nhanh | HTTP/gRPC | Query đồng bộ và latency rõ |
| Search query | HTTP | Cần trả kết quả trực tiếp |
| Add to cart | HTTP | Client cần phản hồi thao tác |
| Reserve inventory | HTTP hoặc command/reply | Tùy latency và workflow |
| Payment authorization | HTTP với timeout/idempotency hoặc async command | Gateway có thể chậm/không rõ kết quả |
| OrderConfirmed notification | Event | Không chặn checkout |
| Search indexing | Event | Projection có thể trễ |
| Analytics ingestion | Event/CDC/batch | Tách workload đọc phân tích |
| Shipment tracking updates | Webhook/event | Update đến bất đồng bộ |

Không nên chọn broker chỉ vì Microservices “phải event-driven”. Messaging có chi phí schema, ordering, replay, DLQ và observability. HTTP cũng có chi phí timeout, retry và temporal coupling. Chọn theo semantics.

## 19. Data ownership và consistency

Một nguyên tắc quan trọng: **mỗi dữ liệu nghiệp vụ có một owner chính thức**. Service khác có thể giữ cache, snapshot hoặc read model nhưng phải biết dữ liệu đó là bản sao.

| Dữ liệu | Nguồn sự thật | Bản sao/consumer có thể giữ |
|---|---|---|
| Product details | Catalog | Search index, product cache |
| Price rules | Pricing | Quote snapshot, cache |
| Coupon eligibility/redemption | Promotion | Checkout result/reference |
| Cart | Cart | Client cache có kiểm soát |
| Order state | Order | Customer order read model |
| Stock/reservation | Inventory | Availability cache có TTL |
| Payment transaction | Payment/provider reconciliation | Order payment summary |
| Shipment tracking | Shipping/carrier integration | Order tracking projection |
| Notification status | Notification | Support read model |
| Analytics aggregates | Analytics pipeline | Dashboard/cache |

### 19.1. Strong consistency ở đâu?

Giữ consistency mạnh trong bounded context nơi invariant cần atomic:

- Không reserve vượt available quantity.
- Không tạo hai payment operation cùng idempotency key.
- Không confirm order khi điều kiện workflow chưa đạt.
- Không áp coupon vượt giới hạn nếu rule cần atomic quota.

### 19.2. Eventual consistency ở đâu?

Có thể chấp nhận eventual consistency cho:

- Search index sau khi sản phẩm thay đổi.
- Analytics dashboard.
- Notification delivery status.
- Order tracking projection.
- Customer activity feed.

Độ trễ tối đa cần được định nghĩa theo trải nghiệm và vận hành. “Eventual” không có nghĩa không giới hạn thời gian hoặc không có cơ chế phát hiện backlog.

## 20. Saga và compensation cho checkout

Một workflow có thể:

1. Tạo Order PENDING.
2. Reserve Inventory.
3. Authorize Payment.
4. Confirm Order.
5. Phát OrderConfirmed.
6. Fulfillment nhận yêu cầu thực hiện.

Nếu Payment decline, release reservation và cancel order. Nếu Payment timeout, trạng thái UNKNOWN cần reconciliation. Nếu authorization thành công nhưng order confirmation lỗi, có thể void authorization. Nếu đã capture, có thể phải refund theo policy.

### 20.1. Chọn orchestration hay choreography?

**Orchestration**: Order/Saga coordinator quản lý thứ tự, timeout, retry và compensation. Dễ nhìn trạng thái workflow, nhưng coordinator có thêm trách nhiệm.

**Choreography**: service phản ứng với event của nhau. Giảm central coordinator, nhưng workflow có thể khó theo dõi khi nhiều event/consumer và nhánh lỗi.

Với checkout có các bước tài chính và reservation quan trọng, orchestration thường dễ giải thích hơn. Tuy nhiên, có thể dùng choreography cho notification, search indexing và analytics vì các consumer không quyết định kết quả checkout.

### 20.2. Outbox và inbox

Transactional outbox ghi business state và event intent trong cùng transaction local. Relay publish sau commit. Consumer dùng inbox/deduplication hoặc xử lý idempotent để chịu duplicate delivery.

Không giả định broker đảm bảo exactly-once end-to-end. Mọi side effect cần idempotency và cách xử lý replay.

## 21. Non-functional design: scale và isolation

Xác định workload profile:

- Search: read-heavy, CPU/IO cho index và ranking.
- Catalog admin: write ít hơn, cần consistency của product state.
- Cart: nhiều thao tác nhỏ, dữ liệu có thể ephemeral/TTL.
- Checkout: latency nhạy cảm, nhiều dependency và cần correctness.
- Inventory: contention trên SKU nóng, transaction concurrency.
- Payment: phụ thuộc provider, timeout và audit.
- Analytics: scan/aggregate nặng, có thể batch.
- Notification: bursty, queue và provider quota.

Từ đó thiết kế scale độc lập nếu có bằng chứng. Không scale từng service chỉ vì chúng là service riêng.

### 21.1. Noisy neighbor và hot key

Một SKU bán chạy có thể tạo contention trong Inventory. Một campaign có thể làm Pricing/Promotion tăng tải. Một tenant doanh nghiệp có thể tạo nhiều report. Cần:
- Quota/concurrency theo workload.
- Cache/read replica phù hợp.
- Partition hoặc sharding khi có số đo.
- Queue và bounded worker pools.
- Rate limiting và backpressure.
- Dashboard theo service, SKU cohort hoặc tenant tier khi cardinality cho phép.

### 21.2. Blast radius

Một lỗi Search không nên làm checkout không thể tạo đơn nếu khách đã có SKU hoặc truy cập product detail qua đường khác và các dữ liệu cần thiết vẫn có sẵn. Một lỗi Notification không nên rollback payment. Một lỗi Analytics không nên làm nghẽn Order DB. Đây là các yêu cầu isolation cần kiểm thử.

## 22. Security boundaries

Bảo vệ theo data owner và trust boundary:

- Gateway xác thực request, nhưng service vẫn kiểm tra authorization phù hợp.
- Service-to-service identity có audience/scope tối thiểu.
- Payment giữ provider credentials và dữ liệu giao dịch nhạy cảm.
- Inventory chỉ cho caller được phép reserve/release.
- Order kiểm tra quyền customer/tenant trước khi hiển thị đơn.
- Event broker có ACL theo producer/consumer.
- Webhook phải xác minh chữ ký, timestamp và chống replay.
- Secret không nằm trong source, log hoặc event payload.
- PII có retention, masking và deletion policy.
- Audit log ghi thao tác quan trọng như capture, void, refund và thay đổi stock.

Tách service chỉ giúp security khi credential, network access, authorization và dữ liệu cũng được giới hạn. Nhiều service dùng một database user có toàn quyền có thể không cải thiện security boundary.

## 23. Team ownership và Conway's Law

Một ranh giới service tốt cần có người sở hữu capability, contract, dữ liệu và production behavior.

Ví dụ tổ chức:

| Team | Capability sở hữu | Trách nhiệm vận hành |
|---|---|---|
| Discovery | Catalog, Search | Product publication, search indexing |
| Commerce | Cart, Pricing/Promotion | Quote và cart workflow |
| Checkout | Order, saga coordination | Order lifecycle, checkout SLO |
| Supply | Inventory, Fulfillment | Reservation, warehouse flow |
| Payments | Payment, reconciliation | Provider integration, audit/refund |
| Platform | Runtime, CI/CD, observability | Paved road và nền tảng dùng chung |

Đây chỉ là một cách tổ chức. Nếu đội ngũ nhỏ, có thể gộp Discovery và Commerce hoặc để Order/Checkout cùng team. Không cần một team cho từng service.

### 23.1. Bảo vệ boundary bằng ownership

- Ai quyết định schema và API?
- Ai trực khi service lỗi?
- Ai có quyền release?
- Ai xử lý breaking change?
- Ai chịu trách nhiệm SLO?
- Consumer cần support qua kênh nào?
- Khi incident xuyên service, ai điều phối?

Một service không có owner hoặc không có người đủ kỹ năng vận hành có thể là ứng viên giữ trong modular monolith hoặc chuyển cho team có năng lực.

## 24. Các phương án kiến trúc để so sánh

Không nên chỉ so sánh những sơ đồ Microservices khác nhau. Cần đưa cả phương án ít phân tán hơn vào phân tích.

### Phương án A — Modular monolith

Một deployment, module Catalog, Pricing, Cart, Order, Inventory, Payment, Fulfillment với module interfaces và data ownership rõ. Có thể dùng schema/database chung về vật lý nhưng tách quyền truy cập logic.

**Ưu điểm:** transaction nội bộ đơn giản, debug dễ hơn, ít deployment overhead, phù hợp team nhỏ.

**Nhược điểm:** scale và release theo module bị giới hạn bởi deployment chung; lỗi runtime có thể ảnh hưởng rộng; ownership dễ bị phá nếu module boundaries không được bảo vệ.

### Phương án B — Microservices theo domain

Các bounded context có service/database/contract riêng; workflow xuyên service dùng API/event/saga.

**Ưu điểm:** scale, deploy và recovery theo capability; ownership rõ nếu tổ chức tương ứng.

**Nhược điểm:** network failure, eventual consistency, contract evolution, distributed tracing, platform và on-call phức tạp hơn.

### Phương án C — Tách theo lớp kỹ thuật

Ví dụ một service frontend, một backend, một database service và một service integrations.

**Ưu điểm:** có thể phù hợp tổ chức chuyên môn hóa theo công nghệ ở quy mô nhỏ.

**Nhược điểm:** mỗi thay đổi nghiệp vụ đi qua nhiều lớp/team; backend hoặc database trở thành bottleneck; ranh giới không nhất thiết phản ánh domain.

### Phương án D — Hybrid theo workload

Giữ phần lớn nghiệp vụ trong một hoặc vài modular services; tách Search, Payment, Inventory hoặc Analytics khi có yêu cầu độc lập rõ.

**Ưu điểm:** chỉ trả distributed-system cost ở nơi có lợi ích đo được.

**Nhược điểm:** cần quản lý boundary giữa module nội bộ và service bên ngoài; kiến trúc có thể phức tạp nếu không có quy ước nhất quán.

### 24.1. Ma trận so sánh

| Tiêu chí | Modular monolith | Domain Microservices | Technical-layer services | Hybrid |
|---|---|---|---|---|
| Tính độc lập deploy | Thấp hơn | Cao nếu contract tốt | Thường thấp theo feature | Theo capability được tách |
| Transaction nội bộ | Đơn giản | Local transaction + saga | Có thể khó | Kết hợp |
| Vận hành | Ít thành phần hơn | Nhiều thành phần | Nhiều cross-layer dependency | Trung bình |
| Scale độc lập | Hạn chế | Tốt theo service | Không bám workload tốt | Có chọn lọc |
| Ownership | Dễ tập trung | Rõ nếu team phù hợp | Dễ handoff nhiều nhóm | Có thể rõ |
| Phù hợp | Team nhỏ, domain chưa ổn định | Nhiều capability độc lập | Một số tổ chức chuyên môn | Tiến hóa từng bước |

Không có cột nào thắng mọi tiêu chí. Lựa chọn phải dựa trên constraint và mục tiêu đã xác định.

## 25. Đưa ra một phương án mục tiêu

Với các giả định của bài tập, một phương án mục tiêu có thể là:

- **Catalog** sở hữu product master và phát event thay đổi.
- **Search** giữ index/projection độc lập, có thể rebuild.
- **Pricing/Promotion** có thể bắt đầu cùng context hoặc module; chỉ tách khi quy tắc/ownership/scale cần.
- **Cart** giữ state người dùng và chuyển dữ liệu đã xác nhận sang checkout.
- **Order/Checkout** sở hữu order snapshot và saga.
- **Inventory** sở hữu stock/reservation theo kho.
- **Payment** sở hữu payment lifecycle và provider integrations.
- **Fulfillment/Shipping** có thể cùng context lúc đầu; tách theo carrier/workload khi cần.
- **Notification** tiêu thụ event và xử lý delivery độc lập.
- **Analytics** nhận event/CDC và xây read model/warehouse.
- **Identity/Customer** có owner và security boundary phù hợp; không để mọi service truy cập bảng profile trực tiếp.

Đây là một baseline để tranh luận. Không cần triển khai tất cả cùng lúc. Một lộ trình có thể giữ Cart, Pricing và Promotion trong một modular commerce service, đồng thời tách Search, Payment và Inventory trước vì có khác biệt workload, security và consistency rõ hơn.

## 26. Bảo vệ quyết định bằng ADR

Một ADR nên nêu context, decision, alternatives, consequences và evidence.

~~~markdown
# ADR-001: Tách Inventory thành bounded service

## Context
Inventory có reservation concurrency và quy tắc theo warehouse.
Checkout peak load có thể tranh chấp stock SKU nóng.
Order hiện truy cập trực tiếp bảng stock.

## Decision
Inventory sở hữu stock và reservation.
Order gửi ReserveInventory command qua contract.
Inventory phát ReservationReserved/Rejected event.
Không cho service khác ghi trực tiếp Inventory database.

## Alternatives
A. Giữ stock trong Order module.
B. Tách Inventory service.
C. Dùng managed inventory platform.

## Rationale
Ranh giới data ownership và concurrency nằm trong Inventory.
Tách cho phép kiểm soát stock invariant và scale riêng.

## Consequences
Checkout cần saga, idempotency và compensation.
Cần theo dõi reservation expiry và backlog.
Có thêm network failure và deployment cost.

## Review triggers
Peak traffic tăng, reservation contention thay đổi,
hoặc team không còn đủ năng lực vận hành service.
~~~

Đây là mẫu ADR minh họa. Một ADR thực tế nên đính kèm số đo contention, incident, workload profile, SLO và chi phí vận hành.

### 26.1. Cấu trúc lập luận cho mọi boundary

Có thể dùng bảng sau:

| Thành phần lập luận | Nội dung cần trả lời |
|---|---|
| Problem | Hiện tại điều gì đang gây đau? |
| Domain | Capability và invariant nào thuộc service? |
| Data | Ai là source of truth? |
| Change | Những thay đổi nào cần độc lập? |
| Runtime | Có nhu cầu scale/recovery riêng không? |
| Contract | Consumer gọi/nhận dữ liệu thế nào? |
| Alternatives | Có thể giữ module hoặc dùng managed service không? |
| Cost | Thêm deployment, DB, on-call và observability bao nhiêu? |
| Risk | Consistency, availability, security và migration rủi ro gì? |
| Evidence | Metric/test/incident nào hỗ trợ quyết định? |
| Revisit | Điều kiện nào khiến cần xem lại? |

## 27. Những phản biện thường gặp và cách trả lời

### Phản biện 1: “Tại sao không giữ một monolith? Microservices quá phức tạp.”

Câu trả lời cần thừa nhận distributed complexity là có thật. Chỉ tách khi có nhu cầu độc lập về scale, release, ownership, security hoặc fault isolation. Nếu bằng chứng chưa đủ, modular monolith là phương án hợp lý. Nêu rõ capability nào thực sự cần tách trước.

### Phản biện 2: “Tại sao không tách từng chức năng thành một service?”

Một service cho mỗi chức năng có thể tạo quá nhiều network calls, database và team overhead. Những quy tắc thay cùng nhau nên được giữ gần nhau. Nêu tiêu chí bounded context và change coupling để chứng minh.

### Phản biện 3: “Sao Inventory không nằm trong Order? Đặt hàng phải trừ kho.”

Order điều phối checkout, Inventory sở hữu stock invariant và reservation. Hai domain phối hợp qua saga; ownership không đồng nghĩa một domain phải quản lý toàn bộ workflow. Chỉ gộp nếu quy mô và consistency yêu cầu cho thấy distributed boundary không đáng chi phí.

### Phản biện 4: “Search có thể đọc thẳng Catalog database cho nhanh.”

Đọc trực tiếp tạo coupling schema và tải. Search index là read model; có thể dùng projection hoặc API phù hợp. Nếu cần latency thấp, tối ưu index/cache và đo freshness, không bỏ qua data ownership.

### Phản biện 5: “Sao Payment không cập nhật Order DB trực tiếp sau callback?”

Payment sở hữu trạng thái giao dịch; Order sở hữu trạng thái đơn. Callback cập nhật Payment, sau đó Payment phát event hoặc gửi kết quả qua contract. Nếu Payment ghi Order DB, quyền sở hữu và transaction boundary bị phá, làm migration/incident khó hơn.

### Phản biện 6: “Tách nhiều service có làm hệ thống an toàn hơn không?”

Không tự động. Security cần workload identity, authorization, least privilege, secret isolation và audit. Nếu tất cả service dùng chung credential/database user, boundary có thể chỉ là hình thức.

### Phản biện 7: “Có thể retry mọi lỗi mạng không?”

Không. Timeout sau side effect có thể có kết quả UNKNOWN. Cần idempotency key, query/reconciliation, bounded retry và compensation. Retry mù có thể tạo duplicate payment hoặc oversell.

### Phản biện 8: “Một service mới có thật sự giảm chi phí?”

Đưa TCO vào lập luận: compute, DB, pipeline, monitoring, on-call, security patch, hiring và migration. Nếu service không có lợi ích đo được, giữ module có thể tốt hơn.

## 28. Kế hoạch migration từ hệ thống hiện tại

Không nên big-bang rewrite. Có thể dùng Strangler pattern để chuyển từng capability.

### Giai đoạn 1 — Kiểm kê và bảo vệ module boundary

- Lập dependency map của monolith.
- Xác định bảng và quy tắc do từng domain sở hữu.
- Tách package/module và cấm truy cập repository chéo.
- Thêm characterization tests và business flow tests.
- Đo baseline latency, error và DB load.

### Giai đoạn 2 — Tách read-heavy projection

- Xây Search index từ Catalog events/CDC.
- Chuyển search queries sang Search API.
- Theo dõi indexing lag và rebuild.
- Giảm truy vấn search/reporting trên database giao dịch.

### Giai đoạn 3 — Tách Payment hoặc Inventory theo rủi ro

- Chọn capability có ownership/security/concurrency khác biệt.
- Thiết kế contract và idempotency.
- Dùng adapter/facade trong monolith khi cần.
- Migrate dữ liệu theo từng phần.
- Canary traffic và đối soát.

### Giai đoạn 4 — Chuyển Order/Checkout workflow

- Tách order state và saga state.
- Thiết kế outbox/inbox.
- Thực hiện inventory reservation và payment authorization qua contract.
- Kiểm thử compensation và trạng thái UNKNOWN.
- Chuyển traffic từng cohort.

### Giai đoạn 5 — Tách các capability còn lại theo bằng chứng

- Fulfillment/Shipping khi lifecycle và workload đủ khác.
- Notification thành consumer bất đồng bộ.
- Analytics ra pipeline/warehouse.
- Pricing/Promotion khi domain và ownership rõ.

### 28.1. Quy tắc migration dữ liệu

- Có một source of truth tại mỗi giai đoạn.
- Không để hai service cùng ghi một dữ liệu mà không có protocol rõ.
- Dùng backfill, CDC hoặc event replay có checkpoint.
- Có kiểm tra count, checksum và business invariants.
- Chuyển đọc trước khi chuyển ghi khi phù hợp.
- Dùng dual-read/compare trong phạm vi an toàn.
- Có cutover, rollback và thời gian bảo lưu dữ liệu cũ.
- Loại bỏ đường truy cập cũ sau khi xác nhận.

## 29. Kiểm thử kiến trúc đã chọn

Một sơ đồ không chứng minh hệ thống hoạt động. Cần các bài test:

### 29.1. Domain tests

- Order snapshot giữ đúng giá/currency.
- Inventory không reserve vượt stock.
- Coupon không vượt quota theo rule.
- Payment operation không xử lý trùng idempotency key.
- Order state không lùi khi event cũ đến.

### 29.2. Contract tests

- Search consumer đọc ProductPublished.
- Order gọi Inventory với request hợp lệ.
- Payment callback/event có schema và signature semantics.
- Fulfillment nhận OrderConfirmed.
- Consumer cũ xử lý schema mới theo compatibility policy.

### 29.3. Workflow tests

- Happy path checkout.
- Inventory reject.
- Payment decline.
- Payment timeout nhưng provider đã authorize.
- Duplicate callback/event.
- Reservation hết hạn.
- Broker downtime/outbox backlog.
- Compensation retry thất bại.
- Order Service restart giữa saga.

### 29.4. Non-functional tests

- Load test search và checkout riêng.
- SKU nóng gây contention.
- Một payment provider chậm.
- Notification backlog không làm checkout chậm.
- Analytics query không gây saturation database giao dịch.
- Một service lỗi không làm các capability độc lập ngừng theo.
- Restore database và replay event có thể thực hiện.

## 30. Observability và vận hành

Một order phải có correlation ID xuyên các bước:

~~~text
API Gateway
   |
   v
Order / Saga
   |----> Inventory reservation
   |----> Payment authorization
   |----> Order confirmation
   |----> Fulfillment
   |----> Notification
~~~

Các metric nên theo dõi:

| Context | Chỉ số |
|---|---|
| Catalog | publish rate, update errors |
| Search | query latency, indexing lag, zero-result rate |
| Pricing/Promotion | quote latency, calculation errors, coupon rejection |
| Cart | active carts, update errors, expiry |
| Order | creation success, pending age, saga duration |
| Inventory | reserve success/reject, hot SKU contention, expiry |
| Payment | authorize/decline/unknown, provider latency, refund backlog |
| Fulfillment | pick/pack time, task backlog |
| Shipping | label errors, tracking freshness |
| Notification | queue age, provider failures, delivery status |
| Analytics | ingestion lag, freshness, job duration |

Không đưa orderId, customerId hoặc SKU cardinality rất lớn vào mọi metric label. Dùng trace/log có quyền truy cập và retention phù hợp để truy vấn chi tiết.

## 31. Checklist bảo vệ kiến trúc trước hội đồng review

### Bối cảnh và yêu cầu

- [ ] Có mô tả business capabilities và luồng mua hàng.
- [ ] Fact, assumption, constraint và open question được phân biệt.
- [ ] Quality attributes có tình huống và mục tiêu đo được.
- [ ] Các peak workload và data consistency requirements được mô tả.

### Domain và ownership

- [ ] Bounded contexts có language, rules và owner rõ.
- [ ] Mỗi dữ liệu chính có một source of truth.
- [ ] Search/reporting projection không bị nhầm với dữ liệu giao dịch.
- [ ] Service boundary có lý do về domain/change/scale/security.
- [ ] Những capability nên gộp hoặc giữ module đã được xem xét.

### Giao tiếp và consistency

- [ ] API/event contracts có owner và version.
- [ ] Sync/async được chọn theo semantics và latency.
- [ ] Saga có state, idempotency, compensation và reconciliation.
- [ ] Không có cross-service database writes.
- [ ] Timeout, retry, duplicate và out-of-order được xử lý.
- [ ] Eventual consistency có freshness expectation.

### Vận hành và bảo mật

- [ ] SLO, capacity và blast radius được định nghĩa.
- [ ] Có service identity, least privilege, secret isolation và audit.
- [ ] Có tracing, logs, metrics và runbook.
- [ ] Có backup/restore và data migration plan.
- [ ] Team owner có khả năng deploy/on-call hoặc support model rõ.

### Lập luận quyết định

- [ ] Có ít nhất một phương án thay thế được phân tích.
- [ ] Lợi ích và chi phí được nêu cân bằng.
- [ ] Có bằng chứng hoặc kế hoạch đo cho giả định quan trọng.
- [ ] ADR ghi context, decision, alternatives và consequences.
- [ ] Có điều kiện review lại khi tải, team hoặc business thay đổi.

## 32. Bài tập chính: nộp bộ hồ sơ kiến trúc

Người học cần chuẩn bị một bộ hồ sơ có thể được review bởi team khác.

### Deliverable 1 — Context map

- Bounded context.
- Upstream/downstream relationship.
- Owner của dữ liệu và contract.
- Các dependency sync/async.

### Deliverable 2 — Service decomposition

Với từng service/module, ghi:

- Trách nhiệm.
- Invariant.
- Data owner.
- API/event.
- Scale profile.
- SLO.
- Team owner.
- Lý do tách hoặc giữ chung.

### Deliverable 3 — Workflow design

Vẽ ít nhất ba luồng:

1. Search và product detail.
2. Checkout với inventory reservation và payment authorization.
3. Hủy đơn/hoàn tiền/trả hàng.

Mỗi luồng cần thể hiện success, timeout, retry và compensation.

### Deliverable 4 — Architecture Decision Records

Viết tối thiểu ba ADR:

- Có tách Inventory khỏi Order không?
- Search là service riêng hay read model trong Catalog?
- Pricing và Promotion nên chung hay riêng?

Mỗi ADR phải ghi ít nhất một phương án thay thế và hệ quả.

### Deliverable 5 — Migration plan

- Thứ tự chuyển capability.
- Cách đồng bộ dữ liệu.
- Cutover/rollback.
- Test và metric.
- Rủi ro và người chịu trách nhiệm.

### Deliverable 6 — Defense presentation

Chuẩn bị phần trình bày ngắn:

1. Bối cảnh và vấn đề.
2. Domain boundaries.
3. Sơ đồ mục tiêu.
4. Hai workflow quan trọng.
5. Các quyết định gây tranh luận.
6. Trade-off và chi phí.
7. Kế hoạch migration.
8. Rủi ro còn mở và cách đo.

## 33. Câu hỏi phản biện mở rộng

1. Nếu doanh nghiệp chỉ có tám kỹ sư backend, bạn có triển khai mười hai service ngay không? Vì sao?
2. Nếu search index trễ 30 giây, hành vi checkout có bị ảnh hưởng không?
3. Nếu một SKU có một đơn vị tồn kho cuối cùng và hai checkout đồng thời, Inventory đảm bảo gì?
4. Nếu payment provider timeout sau khi authorize, ai là owner của reconciliation?
5. Nếu Pricing và Promotion thay đổi trong cùng 80% PR, có nên tách hai service?
6. Nếu Reporting cần dữ liệu order đầy đủ, bạn cung cấp qua API, event, CDC hay warehouse?
7. Nếu một shipment đã giao nhưng Order Service chưa nhận event, trạng thái nào là source of truth?
8. Nếu khách đổi địa chỉ sau khi đặt hàng, snapshot nào được giữ?
9. Nếu một team không đủ năng lực trực service riêng, ranh giới có cần thay đổi?
10. Nếu traffic tăng gấp mười lần chỉ ở Search, phương án nào cho phép scale mà không tăng database checkout?
11. Nếu cần mở thị trường mới với data residency, context nào phải thay đổi?
12. Nếu một service bị compromise, dữ liệu và quyền nào có thể bị truy cập?
13. Nếu broker outage trong 20 phút, outbox/backlog có thể được phục hồi thế nào?
14. Nếu doanh nghiệp chuyển từ một warehouse sang nhiều warehouse, Inventory boundary có còn phù hợp?
15. Khi nào nên hợp nhất hai service đã tách?

## 34. Mẫu câu trả lời bảo vệ quyết định

Một lập luận kiến trúc nên đi theo cấu trúc:

**Bối cảnh:** mô tả yêu cầu hoặc vấn đề quan sát được.

**Ranh giới đề xuất:** nêu capability, dữ liệu và invariant thuộc service.

**Bằng chứng:** số liệu workload, incident, change coupling, SLO hoặc chính sách.

**Phương án thay thế:** nêu lựa chọn ít phân tán hơn và một lựa chọn khác.

**Lý do chọn:** giải thích lợi ích quan trọng nhất trong bối cảnh này.

**Trade-off:** ghi rõ consistency, latency, cost, security và operational overhead.

**Mitigation:** contract, saga, observability, automation và migration plan.

**Điều kiện xem lại:** nêu thay đổi nào khiến quyết định có thể không còn phù hợp.

Ví dụ lập luận ngắn:

> Chúng tôi đề xuất tách Inventory khỏi Order vì reservation và stock availability có invariant riêng, contention tập trung vào SKU nóng và cần được bảo vệ khỏi tải checkout không liên quan. Inventory sẽ là nguồn sự thật duy nhất cho stock; Order gửi reservation command và theo dõi kết quả qua contract. Phương án giữ chung module giảm network overhead và vẫn có thể phù hợp khi team nhỏ, nhưng hiện tại nó làm ownership stock và checkout lẫn nhau. Tách service tạo eventual consistency và yêu cầu saga, idempotency, expiry và reconciliation; chúng tôi chấp nhận chi phí này để bảo vệ stock invariant và scale độc lập. Nếu workload hoặc team ownership thay đổi, boundary sẽ được review lại.

Đây là ví dụ cách lập luận, không phải đáp án duy nhất. Một câu trả lời khác có thể giữ Inventory trong modular monolith nếu chứng minh được transaction, team và scale hiện chưa cần deployment độc lập.

## 35. Kết luận

Phân rã hệ thống thương mại điện tử không phải bài tập đếm chức năng rồi biến mỗi chức năng thành một Microservice. Cần bắt đầu từ **domain, capability, invariant, data ownership và luồng giá trị**; sau đó mới quyết định module nào cần deployment độc lập. Search có thể tách vì workload đọc và projection khác Catalog. Inventory có thể tách vì stock/reservation có invariant và concurrency riêng. Payment có thể tách vì transaction lifecycle, provider integration và security. Nhưng Pricing/Promotion, Cart/Checkout hoặc Fulfillment/Shipping có thể cần bắt đầu chung nếu chưa có bằng chứng về nhu cầu độc lập.

Một lựa chọn boundary tốt phải giải thích được ai sở hữu dữ liệu, consumer giao tiếp bằng contract nào, consistency ra sao, khi lỗi thì điều gì xảy ra và team nào chịu trách nhiệm. Cũng phải so sánh với modular monolith hoặc phương án hybrid, tính chi phí vận hành và đưa ra lộ trình migration an toàn.

Khi bảo vệ kiến trúc, hãy trình bày **bằng chứng, giả định, phương án thay thế, lợi ích và trade-off**. Kiến trúc có thể tiến hóa khi traffic, domain, team hoặc yêu cầu bảo mật thay đổi. Điều quan trọng là quyết định hiện tại có lý do rõ, có thể kiểm chứng và có điều kiện để xem xét lại.