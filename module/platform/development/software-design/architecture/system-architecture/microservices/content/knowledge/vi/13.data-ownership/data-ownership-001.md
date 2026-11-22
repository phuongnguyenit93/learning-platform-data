# Dữ liệu thuộc về dịch vụ sở hữu năng lực nghiệp vụ trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Quyền sở hữu dữ liệu.  
> **Mục tiêu:** Hiểu nguyên tắc service sở hữu dữ liệu theo năng lực nghiệp vụ, xác định nguồn dữ liệu có thẩm quyền, bảo vệ bất biến và quyền ghi, thiết kế cách chia sẻ dữ liệu qua API/event/read model, xử lý nhất quán xuyên dịch vụ và xây dựng lộ trình chuyển từ shared database sang ownership rõ ràng.

## 1. Vì sao quyền sở hữu dữ liệu là vấn đề cốt lõi?

Microservices không chỉ là việc tách một ứng dụng thành nhiều process, container hoặc repository. Mục tiêu quan trọng là tạo các ranh giới có thể **ra quyết định, thay đổi, triển khai và vận hành tương đối độc lập** theo năng lực nghiệp vụ.

Nếu Ordering, Inventory và Payment triển khai thành ba service nhưng cả ba cùng đọc-ghi bảng orders, stock và transactions của một database chung, thì các quy tắc nghiệp vụ vẫn bị rải rác:

- Ordering có thể đánh dấu đơn CONFIRMED trước khi Payment thực sự xác nhận.
- Inventory có thể bị ứng dụng khác ghi giảm stock trực tiếp, bỏ qua logic reservation.
- Payment có thể bị sửa cờ paid=true mà không có giao dịch với nhà cung cấp.
- Một thay đổi schema ảnh hưởng nhiều service cùng lúc.
- Lỗi hoặc migration database làm nhiều nhóm không thể phát hành độc lập.
- Không thể trả lời ai chịu trách nhiệm khi dữ liệu không nhất quán.

**Nguyên tắc chính:** Dịch vụ nào sở hữu một năng lực nghiệp vụ và các quy tắc quyết định của năng lực đó thì dịch vụ ấy là nguồn có thẩm quyền đối với dữ liệu cần thiết để bảo vệ những quyết định đó.

Ví dụ:

~~~text
Catalog Service         Pricing Service
  owns product content    owns price rules / quotations
          |                       |
          +----------+------------+
                     |
                Ordering Service
                owns order lifecycle
                     |
          +----------+-----------+
          |                      |
     Inventory Service       Payment Service
     owns reservations       owns payment outcomes
          |                      |
     Inventory data          Payment ledger
~~~

Ordering **không** được sửa stock quantity hoặc payment transaction chỉ vì cần hoàn tất một đơn. Nó yêu cầu năng lực ReserveStock, AuthorizePayment hoặc nhận event xác nhận kết quả do đúng service công bố.

Điều quan trọng là **quyền quyết định nghiệp vụ**, không phải chỉ tên database, tên bảng hoặc vị trí triển khai.

## 2. Định nghĩa chính xác “sở hữu dữ liệu”

Có ít nhất bốn lớp của ownership:

| Lớp | Nội dung | Câu hỏi |
|---|---|---|
| **Business ownership** | Ai định nghĩa ý nghĩa và quy tắc của dữ liệu? | Ai quyết định một reservation còn hiệu lực? |
| **Authoritative write ownership** | Ai được tạo/sửa/xóa trạng thái có thẩm quyền? | Ai được chuyển Payment sang CAPTURED? |
| **Schema/contract ownership** | Ai phát triển model, migration, API và event? | Ai có quyền đổi schema payment? |
| **Operational ownership** | Ai vận hành, giám sát, khôi phục và đối soát? | Ai xử lý khi ledger bị sai? |

Một team có thể sở hữu nhiều service; một service có thể bao trùm nhiều aggregate. Không phải lúc nào “một team = một service = một database server” cũng phù hợp.

### Nguồn dữ liệu có thẩm quyền (source of truth)

**Authoritative data** là dữ liệu được service owner ghi và kiểm soát theo invariants của domain. Ví dụ giá niêm yết hiện hành do Pricing quyết định, không phải một bản sao cache ở Checkout.

**Derived/replicated data** là bản sao phục vụ đọc hoặc tính toán: search index, analytical warehouse, dashboard, order summary projection. Bản sao có thể có chủ sở hữu vận hành khác, nhưng không mặc nhiên trở thành quyền sửa nghiệp vụ nguồn.

**Local data** là dữ liệu riêng hỗ trợ implement: cache, inbox/outbox, job state, database indexes, technical metadata. Không nên để consumer khác lệ thuộc vào cấu trúc này.

### Data ownership không đồng nghĩa data secrecy

Nguyên tắc không phải “chỉ service owner được đọc mọi byte”. Dịch vụ khác có thể được cấp dữ liệu qua API, event, snapshot hoặc projection có kiểm soát. Ranh giới quan trọng nhất là **ai được thay đổi dữ liệu có thẩm quyền và ai định nghĩa semantics của nó**.

Đọc cũng có thể bị giới hạn vì quyền, tải, bảo mật, data residency hoặc coupling. Nhưng việc có read replica/read model không vi phạm ownership nếu nó không tạo thêm nguồn ghi có thẩm quyền cạnh tranh.

## 3. Đặt ranh giới theo business capability

Một capability mô tả **tổ chức có thể làm gì**, không phải “bảng nào tồn tại”. Ví dụ thương mại điện tử:

| Capability | Service owner | Dữ liệu có thẩm quyền | Quy tắc quan trọng |
|---|---|---|---|
| Quản lý danh mục | Catalog | Product definition, publication state | Sản phẩm có được hiển thị/bán không |
| Định giá | Pricing | Price rules, quotes, discounts | Khách này được giá nào ở thời điểm nào |
| Quản lý tồn | Inventory | Stock buckets, reservations | Không cấp phát vượt mức có thể bán |
| Đặt hàng | Ordering | Orders, order lifecycle, item snapshots | Khi nào đơn được submit/cancel/confirm |
| Thanh toán | Payment | Payment intents, captures, refunds | Không xử lý trùng một giao dịch |
| Giao vận | Fulfillment | Shipment plans, tracking state | Hàng đã giao hay có thể điều chỉnh |
| Danh tính | Identity | Accounts, credentials, identity status | Xác thực chủ thể và trạng thái tài khoản |

Nếu một bảng dữ liệu chứa field của nhiều capability, đó là tín hiệu cần **định nghĩa ownership tới mức field/aggregate**, không phải phân công theo tên bảng.

Ví dụ bảng products trong monolith có thể chứa name, description, listedPrice, availableQuantity và supplierCode. Sau khi tách boundary:

- Catalog sở hữu name/description/publication.
- Pricing sở hữu current price/discount rules.
- Inventory sở hữu available quantity/reservation.
- Procurement có thể sở hữu supplier relationships.

Không cố giao cả bảng products cho một service rồi cho mọi service khác cập nhật cột riêng trong cùng bảng. Hãy thiết kế model và đường cập nhật có chủ quyền.

## 4. Bounded Context và ngôn ngữ miền

Trong Domain-Driven Design, bounded context là nơi một mô hình và ngôn ngữ nghiệp vụ có nghĩa nhất quán. Một từ có thể có nhiều nghĩa ở các context khác nhau:

- “Customer” trong Sales: người đang đặt mua.
- “Customer” trong Billing: bên chịu trách nhiệm thanh toán.
- “Customer” trong Support: chủ thể yêu cầu hỗ trợ.
- “Account” trong Identity: danh tính đăng nhập.
- “Account” trong Ledger: tài khoản ghi nhận số dư.

Cố dùng một class Customer/Account chung cho mọi service làm các context không thể tiến hóa độc lập. Thay vào đó, mỗi context sở hữu model của mình và trao đổi bằng contract rõ nghĩa.

### Ranh giới không nhất thiết trùng một process

Một bounded context có thể được triển khai thành một service lớn, nhiều module trong monolith, hoặc vài service nếu có lý do. Ownership là nguyên tắc domain; topology triển khai là lựa chọn kiến trúc có cân nhắc.

Với tổ chức chưa có năng lực vận hành phân tán, **modular monolith có ownership/module boundary rõ** có thể tốt hơn hàng chục microservice sở hữu dữ liệu mơ hồ. Tách deployment chỉ khi lợi ích độc lập và mô hình nhất quán bù được chi phí mạng, quan sát và giao dịch phân tán.

## 5. Ai bảo vệ invariant thì người đó nên sở hữu dữ liệu

**Invariant** là một điều kiện nghiệp vụ không được phá vỡ trong phạm vi quyết định có thẩm quyền.

Ví dụ Inventory:

- Reservation không được cấp vượt khả năng tồn theo chính sách.
- Một reservation phải có order reference và trạng thái hợp lệ.
- Release không được làm tồn “tăng đôi” khi nhận duplicate.
- Tranh chấp giữa hai đơn phải được giải quyết bằng transaction/concurrency policy.

Ordering có thể cần biết “có đủ hàng không”, nhưng câu trả lời chuẩn phải đến từ Inventory, không phải Ordering tự SELECT stock rồi UPDATE số lượng.

Nếu Ordering ghi trực tiếp stock.quantity:

~~~text
Ordering reads stock.available = 5
Another order reserves 4 units concurrently
Ordering writes stock.available = 2
--> Lost update or incorrect reservation
~~~

Inventory owner có thể thực thi atomic compare-and-set, lock, serialization theo stock bucket hoặc reservation ledger để bảo vệ invariant.

### Một phép tính không quyết định ownership

Ordering có thể hiển thị totalAmount, nhưng ai quyết định quy tắc discount/tax? Nếu Pricing định nghĩa báo giá, Ordering có thể lưu **quote snapshot** đã được chấp nhận ở thời điểm tạo đơn để giữ tính nhất quán lịch sử. Snapshot này là dữ liệu có thẩm quyền về **đơn hàng đã chốt**, không thay thế quyền sở hữu **quy tắc giá hiện tại** của Pricing.

Cần phân biệt “nguồn có thẩm quyền về giá hiện hành” và “nguồn có thẩm quyền về giá đã chốt trên đơn”. Cùng một giá trị bằng số có thể thuộc những sự thật nghiệp vụ khác nhau.

## 6. Phân biệt Authoritative, Snapshot, Projection và Cache

| Dạng dữ liệu | Đặc tính | Có thể dùng làm gì? | Không nên dùng làm gì? |
|---|---|---|---|
| Authoritative state | Quyết định nghiệp vụ đã được commit | Chấp nhận/reject command, bảo vệ invariant | Cho service khác viết trực tiếp |
| Immutable snapshot | Giá trị được chốt tại một mốc nghiệp vụ | Hiển thị order history, invoice | Thay giá niêm yết hiện hành |
| Read projection | Bản tổng hợp từ events/API | Trang tổng quan, tìm kiếm, báo cáo | Ra quyết định cần trạng thái mới tuyệt đối khi chưa có consistency contract |
| Cache | Dữ liệu tạm, có TTL/invalidation | Tăng tốc đọc và giảm tải | Thay nguồn sự thật khi stale gây sai nghiệp vụ |
| Analytical copy | Phục vụ BI/warehouse | Phân tích xu hướng | Ghi trực tiếp để sửa business transaction |
| Reconciliation record | Bằng chứng xác minh kết quả phân tán | Xử lý payment unknown, incident | Làm nguồn sửa domain vô kiểm soát |

Một projection có thể là **nguồn có thẩm quyền cho kết quả tính toán riêng của analytics**, nhưng không phải owner của transaction gốc. Quyền sở hữu được định nghĩa theo **mệnh đề nghiệp vụ**, không chỉ physical storage.

## 7. Data-per-service là ranh giới truy cập, không bắt buộc mỗi service một máy DB

Nguyên tắc “database per service” thường được hiểu là mỗi service có dữ liệu riêng và dịch vụ khác không được truy cập schema/table nội bộ như một public contract.

Có nhiều cách triển khai:

1. **Dedicated DB instance:** cách ly mạnh về vận hành và quyền truy cập, nhưng chi phí cao.
2. **Dedicated database trên cùng server/cluster:** tách logical ownership, vẫn chung failure domain.
3. **Dedicated schema cùng database:** có thể phù hợp giai đoạn đầu nếu quyền SQL/DDL được cô lập.
4. **Dedicated tables với role riêng:** mức cách ly yếu hơn, cần kiểm soát kỹ quyền và migration.
5. **Shared physical platform nhiều tenant/service:** chấp nhận khi có isolation, quotas, monitoring và responsibility rõ.

Không cần một database server/container cho mỗi service nhỏ. Yêu cầu quan trọng là service A **không ghi và không lệ thuộc trực tiếp vào private schema của B**. Nếu chia sẻ hạ tầng vật lý, phải thừa nhận coupling về capacity, backup, restore, security và availability.

### Nguyên tắc quyền truy cập

~~~text
ordering_db_role:
  read/write ordering-owned schema
  no direct write on payment or inventory schema

inventory_db_role:
  read/write inventory-owned schema
  no direct write on ordering or payment schema

payment_db_role:
  read/write payment-owned schema
  no direct write on others
~~~

Read-only access xuyên schema cũng có thể tạo coupling mạnh khi nhiều consumer chạy query phức tạp. Nếu cần, hãy coi đó là thỏa thuận chuyển tiếp có owner và ngày loại bỏ, không biến nó thành API ngầm vĩnh viễn.

## 8. Một bảng không nên có nhiều chủ sở hữu quyền ghi

Ví dụ anti-pattern:

~~~text
Database: commerce
Table: orders

Ordering Service:
  UPDATE orders.status
Payment Service:
  UPDATE orders.paid
Shipping Service:
  UPDATE orders.shipped
Support Service:
  UPDATE orders.cancelled
~~~

Mỗi service nghĩ mình chỉ sửa “cột riêng”. Nhưng một business invariant có thể liên quan nhiều cột. Một bản ghi có thể thành shipped=true, cancelled=true hoặc paid=false tùy timing.

Phương án tốt hơn:

~~~text
Ordering owns:
  order lifecycle state

Payment owns:
  payment intent / capture / refund state

Fulfillment owns:
  shipment state

Ordering projection/view:
  order status + payment summary + shipment summary
  read-only from owners' events/contracts
~~~

Ordering có thể hiển thị trạng thái tổng hợp cho UI, nhưng source-of-truth cho payment và shipment vẫn ở owner.

### Nếu hai dịch vụ đều “cần sửa” cùng dữ liệu?

Đây là tín hiệu phải hỏi:

- Chúng có thực sự cùng chịu một business responsibility không?
- Một phần dữ liệu chỉ là view/projection của owner khác?
- Hành vi cần được thể hiện bằng command đến owner?
- Invariant có cần nằm chung một transaction trong cùng boundary?
- Ranh giới tách service có quá nhỏ và gây distributed monolith không?

Không giải quyết bằng quyền superuser lên database chung.

## 9. Command API là cửa ghi qua ranh giới

Khi một service cần thay đổi dữ liệu của owner khác, nó **yêu cầu hành vi**, không gửi lệnh thao tác storage.

Ví dụ không nên làm:

~~~text
Ordering:
  UPDATE inventory.stock SET available = available - 2
  UPDATE payments SET authorized = true
~~~

Thay vào đó:

~~~http
POST /inventory-reservations
Idempotency-Key: order-O101-reserve-v1
Content-Type: application/json

{
  "orderId": "O101",
  "items": [
    {"sku": "BOOK-12", "quantity": 2}
  ]
}
~~~

Inventory kiểm tra stock và policy, ghi reservation trong transaction của nó rồi trả kết quả. Ordering không biết table lock, thuật toán giữ hàng hay mức tồn nội bộ của Inventory.

Payment có API:

~~~http
POST /payment-authorizations
Idempotency-Key: order-O101-auth-v1
Content-Type: application/json

{
  "orderId": "O101",
  "quoteId": "quote-19",
  "amount": {
    "value": "850000.00",
    "currency": "VND"
  }
}
~~~

Payment kiểm tra idempotency, hợp đồng nhà cung cấp, authorization state và lưu transaction reference. Ordering không thể tự viết authorized=true để “giúp” Payment.

Lựa chọn endpoint phải bám semantics: tạo resource, command hay workflow async. **Quyền sở hữu dữ liệu và quyền sở hữu hành vi đi cùng nhau.**

## 10. Read API: chia sẻ dữ liệu nhưng giữ quyền quyết định ở owner

Các consumer thường cần đọc:

- Checkout cần giá và availability.
- Mobile app cần order details, payment status, shipment tracking.
- Support cần order history và trạng thái refund.
- Reporting cần dữ liệu từ nhiều domain.

Các lựa chọn:

| Cách đọc | Lợi ích | Rủi ro/đổi lại |
|---|---|---|
| **Synchronous owner API** | Dữ liệu gần nguồn có thẩm quyền, contract rõ | Network latency, cascading failure |
| **API composition/BFF** | Một response đúng nhu cầu UI | Fan-out, timeout, coupling ở read path |
| **Read model từ events** | Đọc nhanh, giảm RPC runtime | Eventual consistency, replay, schema evolution |
| **Cache** | Tốc độ và giảm tải | Stale data, invalidation, stampede |
| **Data warehouse/ETL** | Phân tích rộng, tách read load | Data freshness, governance, PII |
| **Precomputed snapshot** | Đọc ổn định mốc lịch sử | Không đại diện trạng thái hiện hành |

Không có đáp án cố định. Quan trọng là client biết **dữ liệu có mới đến mức nào**, trường nào là projection và hành vi nào bắt buộc xác nhận từ owner trước khi thực thi.

### API composition không biến gateway thành owner

Một BFF có thể gọi Ordering, Payment và Shipping để tạo màn hình OrderDetails. BFF chỉ tổng hợp representation, không tự quyết định thanh toán đã capture hay đơn có thể refund nếu quy tắc thuộc service khác.

## 11. Chia sẻ dữ liệu bằng domain events

Event biểu đạt một **sự thật nghiệp vụ đã xảy ra**:

~~~text
OrderSubmitted
StockReserved
PaymentAuthorized
ShipmentDelivered
RefundCompleted
~~~

Ordering phát OrderSubmitted sau khi ghi nhận transition. Inventory xử lý event hoặc command phù hợp. Reporting xây projection cập nhật theo events.

Ví dụ event:

~~~json
{
  "eventId": "evt-2947",
  "eventType": "OrderSubmitted",
  "eventVersion": 2,
  "aggregateId": "O101",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-11T08:30:00Z",
  "correlationId": "checkout-8ed2",
  "payload": {
    "orderId": "O101",
    "customerReference": "C923",
    "amount": {
      "value": "850000.00",
      "currency": "VND"
    }
  }
}
~~~

Event contract phải mô tả:

- Sự thật nào đã được ghi bền, owner là ai?
- Payload tối thiểu nào consumer thực sự cần?
- Event ID và version có ý nghĩa gì?
- Có bảo đảm thứ tự theo aggregate không?
- Consumer có thể nhận duplicate, late hoặc out-of-order không?
- Cách đổi schema tương thích?
- Cách thu hồi/chỉnh sửa dữ liệu cá nhân đã nhân bản?
- Replay có an toàn với side effect không?

**Không dùng event như bản dump mọi cột database.** Việc phát một CDC record thô với tên cột nội bộ ra khắp tổ chức khiến private schema vô tình thành public contract.

## 12. Không nhầm domain event với command

- **Command:** yêu cầu service làm điều gì, có thể thành công hoặc từ chối. Ví dụ ReserveStock.
- **Event:** thông báo một sự kiện nghiệp vụ đã xảy ra. Ví dụ StockReserved.
- **Query:** hỏi về dữ liệu. Ví dụ GetReservation.

Các hành vi khác nhau kéo theo ownership khác nhau.

Ví dụ “UpdateStockNow” đưa vào broker vẫn là command dù không gửi qua HTTP. Nó có một owner nhận lệnh và quyết định có hợp lệ không. Một event “StockReserved” không nên yêu cầu consumer khác tự điều chỉnh stock nguồn như một lệnh ẩn.

Khi một service cần hành vi thuộc service khác, dùng command contract. Khi một service muốn thông báo thay đổi đã ghi nhận cho những consumer độc lập, dùng event. Không dùng “publish event” làm cách lách quyền sở hữu dữ liệu.

## 13. Chọn granularity của dữ liệu công bố

Một event chỉ chứa ID khiến consumer phải gọi API owner lại để lấy toàn bộ dữ liệu. Nếu nhiều consumer đồng loạt gọi, có thể tăng fan-out và tải. Nhưng event chứa mọi field lại gây coupling, rủi ro dữ liệu và chi phí lưu trữ.

Cân bằng bằng câu hỏi:

1. Consumer cần những trường nào để hoàn thành trách nhiệm của mình?
2. Những trường đó có ổn định về ngữ nghĩa không?
3. Dữ liệu có nhạy cảm hay có yêu cầu xóa/sửa theo chính sách?
4. Consumer có cần snapshot tại thời điểm event hay giá trị hiện hành?
5. Producer có thể chấp nhận schema evolution đến đâu?
6. Nếu consumer thiếu event, có thể rebuild từ owner không?
7. Có quyền/tenancy constraints khi phát cho nhiều nhóm không?

Ví dụ OrderSubmitted phục vụ Billing cần tổng tiền đã chốt, currency và orderId; Recommendation không nhất thiết được quyền thấy địa chỉ giao hàng hay payment instrument.

**Data minimization** giúp giảm coupling, chi phí, phạm vi lộ lọt và gánh nặng đồng bộ.

## 14. Eventual consistency là hệ quả phải có hợp đồng

Khi Payment cập nhật trạng thái rồi phát PaymentAuthorized, Ordering hoặc OrderSummary projection có thể chưa nhận event ngay.

~~~text
Payment DB:
  payment = AUTHORIZED at T0

Broker:
  event pending between T0 and T1

Ordering projection:
  payment = PENDING until T1
~~~

Đây không nhất thiết là bug. Nó là **eventual consistency** nếu hệ thống có cơ chế đảm bảo kết quả sẽ được chuyển và xử lý trong điều kiện được định nghĩa.

Cần công bố:

- **Freshness:** độ trễ cho phép của projection.
- **Completion semantics:** response ACCEPTED khác business action COMPLETED.
- **Monotonicity:** projection có thể lùi trạng thái do message cũ không?
- **Read-your-writes:** sau khi gửi command, client cần thấy kết quả ngay hay dùng operation ID?
- **Recovery:** message bị mất/đến muộn/duplicate sẽ được xử lý thế nào?
- **SLO:** bao nhiêu phần trăm thay đổi được phản ánh trong bao nhiêu giây?

Ví dụ product search có thể chấp nhận update trễ vài giây, nhưng quyết định capture payment hoặc cấp phát tồn kho không nên dựa vào một cache stale chưa được owner xác nhận.

### UX cần mô tả trạng thái trung gian

Nếu một API chỉ mới nhận yêu cầu:

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-330
Content-Type: application/json

{
  "operationId": "op-330",
  "status": "PENDING",
  "statusUrl": "/operations/op-330"
}
~~~

Client theo dõi cho đến khi có kết quả. Không gọi “thanh toán thành công” khi mới publish command hoặc event.

## 15. Giao dịch nội bộ khác workflow xuyên dịch vụ

Trong một service, có thể dùng transaction ACID để cập nhật aggregate và dữ liệu thuộc quyền sở hữu.

Ví dụ Inventory transaction:

~~~text
BEGIN
  Validate stock bucket and reservation request
  Atomically reserve eligible quantity
  Insert reservation
  Insert outbox event
COMMIT
~~~

Nếu Ordering cần Inventory và Payment cùng thành công, không có một transaction local tự động bao phủ ba database độc lập.

Có thể xây workflow:

~~~text
OrderSubmitted
      |
      v
ReserveStock by Inventory
      |
      +---- rejected ---> OrderRejected
      |
      v
AuthorizePayment by Payment
      |
      +---- rejected ---> ReleaseReservation + OrderRejected
      |
      v
OrderConfirmed
~~~

Một **Saga** là cách tổ chức các local transactions và hành động bù trừ, không phải transaction ACID phân tán tự rollback mọi side effect.

Điểm cần thiết kế:

- Owner của toàn workflow là ai?
- Bước nào có quyền thay đổi dữ liệu thuộc domain nào?
- Bước nào có thể thất bại, timeout hoặc có kết quả chưa xác định?
- Compensation có thực sự đảo được tác động hay là hành động nghiệp vụ mới?
- Có idempotency và operation ID xuyên bước không?
- Khi workflow bị kẹt, ai đối soát và làm sao người dùng biết kết quả?

Việc không chia sẻ database làm transaction xuyên service trở nên rõ ràng hơn, nhưng cũng yêu cầu thiết kế **consistency và recovery** nghiêm túc.

## 16. Transactional Outbox: ghi dữ liệu nguồn và event cùng nhau

Producer có thể gặp dual-write problem:

~~~text
1. Ordering UPDATE order.status = SUBMITTED; COMMIT
2. Ordering publish OrderSubmitted
3. Broker unavailable -> event not published
~~~

Ordering đã thay trạng thái nhưng consumer không biết. Đổi thứ tự publish trước COMMIT cũng có thể khiến event đã phát dù transaction rollback.

**Transactional outbox** ghi event intent và domain state trong cùng DB transaction:

~~~sql
BEGIN;

UPDATE orders
SET status = 'SUBMITTED', version = version + 1
WHERE id = 'O101'
  AND status = 'DRAFT';

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, created_at
) VALUES (
    'evt-2947', 'O101', 'OrderSubmitted', '{...}', CURRENT_TIMESTAMP
);

COMMIT;
~~~

Đây là minh họa; production cần kiểm tra affected row, transaction isolation, idempotency và cấu trúc payload thực.

Dispatcher đọc outbox rồi publish broker, có thể retry khi lỗi. Nếu publish thành công nhưng dispatcher crash trước mark-as-published, event có thể xuất hiện hai lần. Consumer phải idempotent.

**Outbox không tự bảo đảm ordered publication nếu nhiều dispatcher làm việc song song không kiểm soát**; cần sequence/aggregateVersion khi nghiệp vụ phụ thuộc thứ tự.

## 17. Inbox, idempotency và side effect bên ngoài

Consumer có thể xử lý một event rồi chết trước ACK:

~~~text
Consumer receives StockReserved
Consumer commits local DB
Consumer crashes before ACK/offset commit
Broker redelivers StockReserved
~~~

Nếu consumer không dedup, một command hoặc side effect có thể diễn ra hai lần.

Một inbox:

~~~sql
CREATE TABLE processed_messages (
  consumer_name VARCHAR(100) NOT NULL,
  message_id VARCHAR(150) NOT NULL,
  processed_at TIMESTAMP NOT NULL,
  PRIMARY KEY (consumer_name, message_id)
);
~~~

**Quan trọng:** processed marker và thay đổi state nội bộ phải cùng transaction, hoặc sử dụng durable processing state/recovery protocol rõ ràng. Đừng commit marker processed trước khi domain mutation; crash sẽ làm lần redelivery bị bỏ qua dù nghiệp vụ chưa hoàn thành.

Business idempotency có thể cần key khác messageId: hai message ID khác nhau đôi khi vẫn đại diện một ý định ReserveStock cho cùng order. Cần unique business operation ID.

### Payment timeout có thể là outcome unknown

Ordering gửi Payment.authorize, provider đã xử lý nhưng response mất. Ordering không được kết luận chắc chắn thất bại và tạo authorization khác. Payment owner cần stable idempotency key, lookup/reconciliation, trạng thái UNKNOWN/PENDING và outcome cuối đáng tin.

Một transaction DB cục bộ và inbox không tự đem lại exactly-once side effect xuyên external provider.

## 18. Định danh xuyên bounded contexts

Một resource thường có ID nội bộ mà các service khác tham chiếu.

Ví dụ:

~~~text
Order:
  id = O101
  customerReference = C923
  paymentReference = P702
  reservationReference = R490
~~~

Ordering có thể giữ các **opaque references** để phối hợp, nhưng không được dựa vào internal primary key format hoặc join trực tiếp bảng Payment.

Một số nguyên tắc:

- Công bố stable public IDs hoặc business references cần thiết.
- Không dùng raw database row ID nếu nó gắn với implementation và dễ thay đổi/tiết lộ thông tin.
- Không coi có ID là có quyền truy cập; service owner kiểm tra authorization/tenancy.
- Khi owner merge/split resources, cung cấp mapping/migration contract.
- Tránh foreign key xuyên database service như một giả định bắt buộc khi triển khai độc lập.
- Với historical snapshot, xác định lưu ID hay bản sao trường cần bất biến.
- Không dùng email, số điện thoại làm primary cross-service key nếu có opaque ID phù hợp hơn.

Sự liên hệ xuyên context là **business reference**, không đồng nghĩa ownership chung.

## 19. Một dữ liệu có thể có nhiều nghĩa ở các thời điểm

Ví dụ ba khái niệm về giá:

1. **Current list price:** Pricing là nguồn có thẩm quyền.
2. **Quoted price:** Pricing phát quote với điều kiện, currency và expiry.
3. **Accepted order price:** Ordering lưu snapshot tại thời điểm submit.

Khi Pricing thay đổi list price ngày mai, không nên tự thay accepted order price của hôm qua. Hai giá có thể khác nhau nhưng không phải data inconsistency.

Tương tự:

- Catalog sở hữu tên sản phẩm hiện hành.
- Ordering giữ productNameSnapshot để hóa đơn/đơn hàng lịch sử.
- Search lưu projection để truy vấn.
- Reporting lưu dữ liệu analytics theo thời gian.

Data duplication **có chủ đích và có semantics** không vi phạm single authority. Lỗi là có **nhiều writer cạnh tranh cùng một sự thật** mà không có quy tắc quyền sở hữu.

## 20. Tranh chấp “ai sở hữu Customer?”

Một lỗi phổ biến là tạo Customer Service rồi buộc mọi nghiệp vụ dùng mọi trường Customer tại đó.

Hỏi rõ:

- Identity sở hữu login status/credentials?
- CRM sở hữu marketing preferences/lead status?
- Billing sở hữu billing profile, tax identity hoặc payer relationship?
- Support sở hữu support case/contact interaction?
- Customer-facing profile owner sở hữu tên hiển thị/ảnh đại diện?

Một Customer entity khổng lồ thường bị nhiều team chỉnh sửa. Có thể chia thành các bounded context và trao đổi qua ID liên kết/contract.

Ví dụ một trường address cũng có nhiều nghĩa:

- DeliveryAddress hiện tại trong Customer Profile.
- AddressSnapshot của Order đã chốt.
- BillingAddress hợp lệ trên invoice.
- ShipmentDestination do Fulfillment quyết định ở một mốc giao vận.

Không ép tất cả các bản sao liên tục đồng bộ thành cùng một giá trị nếu nghiệp vụ yêu cầu lịch sử bất biến.

## 21. Shared database là anti-pattern về coupling, không chỉ về bảo mật

Khi nhiều service cùng truy cập private tables:

- **Schema coupling:** thay column/index có thể phá consumer vô hình.
- **Deployment coupling:** migration phải phối hợp tất cả service.
- **Transaction coupling:** thao tác “nhanh” của service A gây lock trên service B.
- **Capacity coupling:** query reporting làm chậm checkout.
- **Security coupling:** cấp quyền SQL rộng hơn cần thiết.
- **Failure coupling:** một DB outage kéo nhiều capability xuống.
- **Ownership ambiguity:** không rõ ai có quyền quyết định và phục hồi dữ liệu.
- **Observability gap:** lỗi xuất hiện ở consumer nhưng gốc nằm trong update của một service khác.

Có thể cần shared physical DB trong giai đoạn đầu, nhưng nên ngăn **shared writes** bằng schema/role và contract rõ, rồi dần di chuyển reads trực tiếp qua API/projection.

Không phải mọi shared infrastructure đều là anti-pattern. Shared storage platform với logical isolation và quyền phân tách có thể là quyết định vận hành hợp lý. Vấn đề lớn nhất là **người khác phụ thuộc vào cấu trúc private và sửa trạng thái không qua owner**.

## 22. Quản lý schema và migration độc lập

Một service nên có quyền kiểm soát migration của schema nó sở hữu. Để không phá consumer:

1. Không công bố trực tiếp internal table/column như contract.
2. Dùng public DTO/API/event schema riêng.
3. Thay đổi contract theo hướng additive khi có thể.
4. Sử dụng compatibility rules, consumer contract tests và deprecation policy.
5. Tách migration storage khỏi migration consumer nếu cần.
6. Theo dõi consumer đang sử dụng phiên bản cũ.
7. Không xóa field/endpoint/event cũ khi còn dependency chưa di chuyển.

### Expand-and-contract

Một lộ trình minh họa:

~~~text
Phase A - Expand:
  Add new nullable field or replacement representation
  Keep old behavior working
  Start dual-read or controlled compatibility layer

Phase B - Migrate:
  Backfill data
  Update service owner and consumers
  Compare old/new outputs
  Monitor errors and data drift

Phase C - Contract:
  Stop using old representation
  Remove legacy write path
  Retire old field/API after consumer migration
~~~

“Dual-write” cần rất thận trọng: hai nơi nhận write đồng thời có thể lệch. Khi cần song song trong migration, chọn một authoritative writer và thiết kế replication/outbox/CDC theo hướng một chiều, có reconciliation.

## 23. Tách dữ liệu từ Monolith hoặc Shared Database

Khi chuyển hệ thống cũ, không nên đổi owner toàn bộ bảng trong một ngày. Quy trình thực tế:

**Bước 1 — Kiểm kê:** Liệt kê bảng, cột, read/write call sites và business invariants. Xác định ai đang tạo dữ liệu và ai đang sửa.

**Bước 2 — Chọn capability:** Chẳng hạn Reservation là ứng viên có ranh giới và policy riêng. Xác định service Inventory mới sở hữu reservation lifecycle.

**Bước 3 — Đặt một writer chính:** Dần chuyển mọi write qua Inventory API/use case; chặn write trực tiếp từ ứng dụng cũ khi đã có phương án tương đương.

**Bước 4 — Bảo vệ consistency:** Thiết kế idempotency, versioning, transaction, outbox và reconciliation.

**Bước 5 — Sao chép dữ liệu ban đầu:** Backfill vào storage mới theo mapping có version, lưu watermark/offset.

**Bước 6 — Đồng bộ thay đổi:** Dùng event/CDC có kiểm soát trong giai đoạn chuyển tiếp; theo dõi lag và drift. CDC từ private schema là bridge tạm thời, không nên tự biến thành public event contract vĩnh viễn.

**Bước 7 — Chuyển reads:** Consumer dùng API/projection mới, có thể chạy shadow-read để so sánh trước cutover.

**Bước 8 — Chuyển traffic:** Feature flag/canary, giảm dần đường cũ, có rollback plan.

**Bước 9 — Ngắt đường legacy:** Thu hồi SQL grants và bỏ write path cũ sau khi xác minh không còn consumer.

**Bước 10 — Vận hành:** Chốt owner, SLO, backup/restore, privacy policy và runbook.

### Strangler migration

Có thể đặt một lớp định tuyến (facade) cho thao tác nghiệp vụ để chuyển từng capability từ Monolith sang service mới. Mục tiêu cuối không phải facade tồn tại vĩnh viễn, mà là **một quyền ghi có thẩm quyền và contract ổn định**.

## 24. Backfill, CDC và nguy cơ dữ liệu bị lệch khi migration

Giả sử backfill 10 triệu reservations mất nhiều giờ. Trong lúc sao chép, monolith vẫn sửa reservation.

Một phương án cần xử lý:

~~~text
T0: Start initial snapshot/backfill
T1: New writes continue in legacy DB
T2: Snapshot finishes
T3: Apply CDC changes after chosen consistent point
T4: Validate counts, versions, business invariants
T5: Cut over authoritative write
~~~

Lỗi thường gặp:

- Backfill ghi đè state mới bằng snapshot cũ.
- CDC event thiếu hoặc trùng.
- Timestamp được dùng thay transaction order khiến record lệch.
- New service và monolith cùng ghi trong cutover window.
- Một số consumer vẫn âm thầm truy cập DB legacy.
- Referential data giữa boundaries chưa có mapping.
- Old and new code cùng sử dụng ID format khác nhau.
- Rollback chuyển write về monolith nhưng dữ liệu mới đã sinh trong service mới.

Cần có **version/sequence/watermark và reconciliation**, không chỉ so sánh row count. Một row count bằng nhau vẫn có thể có nội dung sai.

Khi cần rollback, hãy xác định nguồn có thẩm quyền tại từng thời điểm; không chạy hai chiều replication mà không có conflict policy rõ.

## 25. Data contracts để nhiều nhóm dùng dữ liệu an toàn

Data contract không chỉ là schema JSON hay OpenAPI. Nó nên bao gồm:

| Thuộc tính | Ví dụ |
|---|---|
| Owner | Payment team |
| Business meaning | PaymentCaptured nghĩa là provider xác nhận capture |
| Identity | paymentId/operationId |
| Schema | amount decimal string, currency ISO code, occurredAt |
| Invariants | Không có hai capture cho cùng idempotent intent |
| Freshness | Projection cập nhật trong SLO đã công bố |
| Ordering | Per-payment aggregateVersion |
| Delivery semantics | At-least-once, consumer phải idempotent |
| Retention | Theo policy dữ liệu và nghiệp vụ |
| Access control | Consumer nào có quyền nhận trường nào |
| Privacy | PII classification và cách xóa/che |
| Versioning | Additive fields, deprecation window |
| Failure/recovery | Replay, DLQ, reconciliation |
| Observability | Event lag, delivery gaps, business completion |
| Contacts | Owner/on-call và cách escalate |

Nếu service A công bố dữ liệu cho B, cần agreement về semantics. Không để B suy từ tên field paid=true rằng có thể giao hàng khi Payment chưa thực sự hoàn tất settlement theo nghiệp vụ.

## 26. Quan hệ giữa API version và DB schema version

Private database schema có thể thay đổi liên tục khi owner refactor. Public contract không nên bị bắt buộc đổi mỗi khi một cột đổi tên.

Ví dụ:

~~~text
Private DB v12:
  payment_state = "CAPTURED"

Private DB v13:
  status_code = 40
  captured_at = ...

Public API:
  status = "CAPTURED"
  capturedAt = "..."
~~~

Nếu semantics public giữ nguyên, consumer không cần biết migration bên dưới. Khi thay đổi thực sự làm thay đổi nghĩa nghiệp vụ hoặc expected response, phải version/announce phù hợp.

Một service không nên chia sẻ ORM entity package như “common model” cho tất cả service nếu khiến thay đổi private model trở thành breaking change. Shared libraries có thể chứa format phổ quát, error conventions, tracing, authentication; domain schemas cần owner và contract rõ.

## 27. Quyền truy cập dữ liệu và multi-tenancy

Dữ liệu có owner không đồng nghĩa mọi request hợp lệ về kỹ thuật được quyền đọc nó.

Ví dụ Payment owner có thể trả payment status nhưng không tiết lộ payment method details cho mọi consumer. Mỗi API hoặc event cần xác định:

- Actor/workload identity của service gọi.
- Tenant/organization scope.
- Permission đối với resource và hành vi.
- Field-level access/need-to-know khi có dữ liệu nhạy cảm.
- Audit yêu cầu đọc/ghi quan trọng.
- Encryption in transit và at rest phù hợp.
- Retention, data residency và lifecycle deletion.

**Không dùng tenantId lấy tự do từ JSON payload để thay xác thực.** Service owner phải liên kết tenant context với identity/authorization. Read models đa tenant cũng cần phân vùng và lọc quyền; việc tổng hợp events từ nhiều service không tự cung cấp isolation đúng.

## 28. Data deletion và privacy trong hệ thống có nhiều bản sao

Một khách hàng yêu cầu xóa hoặc sửa dữ liệu cá nhân. Dữ liệu có thể đã xuất hiện trong:

- Authoritative account/profile store.
- Order snapshot được lưu theo nghĩa vụ nghiệp vụ.
- Search index, cache, analytics warehouse.
- Logs, backups, message topics và DLQ.
- Read models của các service khác.

Nếu chỉ xóa ở một database nguồn, các bản sao có thể vẫn tồn tại. Cần **data lifecycle contract** gồm:

1. Dữ liệu nào được phép xóa/ẩn danh; dữ liệu nào phải giữ theo nghĩa vụ hợp pháp hoặc nghiệp vụ?
2. Owner nào là nơi khởi tạo quyết định xóa và xác minh quyền?
3. Những downstream systems nào đang giữ bản sao?
4. Có event/command riêng như PersonalDataErasureRequested hay projection tombstone?
5. Consumer thực thi xóa/ẩn danh idempotent và báo hoàn thành thế nào?
6. Cache, search và analytics bị cập nhật trong bao lâu?
7. Backups, immutable logs và retention được xử lý theo chính sách nào?
8. Làm sao chứng minh yêu cầu hoàn tất mà không lưu thêm PII không cần thiết?

Không tự động tuyên bố “đã xóa mọi nơi” chỉ vì một API trả 200. Những quy định cụ thể phụ thuộc khu vực pháp lý và chính sách tổ chức; thiết kế phải phối hợp với nhóm privacy/security.

## 29. Tránh distributed join trên hot path

Một trang OrderDetails cần Order, Payment và Shipment.

Nếu UI gọi ba service trực tiếp, có thể gặp:

~~~text
Browser
  |--> Ordering
  |--> Payment
  |--> Fulfillment
~~~

Thời gian hiển thị và reliability phụ thuộc các lời gọi. Một BFF có thể gom nhưng vẫn tạo fan-out. Nếu traffic lớn, xây read model:

~~~text
Ordering ------ OrderChanged -----\
Payment ------- PaymentChanged ----> OrderSummaryProjection
Fulfillment --- ShipmentChanged --/
                                      |
                                      v
                                 GET /order-summary
~~~

Projection có thể do một service read/query sở hữu, nhưng nó **không có quyền tạo PaymentCaptured hay ShipmentDelivered**. Owner gốc vẫn quyết định.

Cần đo projection lag, missing events, duplicate, ordering và rebuild. Nếu UI cần trạng thái rất mới cho hành động chuyển tiền, gọi owner hoặc dùng operation status thay vì tin read model stale.

## 30. CQRS không đồng nghĩa “hai nguồn sự thật”

Command Query Responsibility Segregation tách model xử lý ghi và model phục vụ đọc khi nhu cầu khác nhau.

~~~text
Command:
  POST /orders/{id}/submit
  -> Ordering aggregate transaction
  -> Outbox event

Query:
  GET /order-summaries/{id}
  -> Read projection updated from events
~~~

Ordering command model là nơi chấp nhận hay từ chối transition. Read projection có thể được rebuild, cache hoặc schema đổi theo nhu cầu UI, nhưng không nên được consumer khác coi là nơi ghi status có thẩm quyền.

CQRS có thể dùng trong cùng application/database hoặc tách service; **không bắt buộc Microservices phải dùng CQRS**, và không phải mọi read cần materialized view.

## 31. Dữ liệu tham chiếu và dữ liệu dùng chung

Một số dữ liệu dường như không có owner rõ: currency list, country codes, timezone, product taxonomy, tax categories hoặc feature configuration.

Hỏi:

- Có một business capability thật sự quản trị thay đổi không?
- Dữ liệu là chuẩn toàn cầu bất biến tương đối hay cấu hình nội bộ?
- Ai phê duyệt value mới?
- Có consumer nào phải phản ứng ngay khi value thay đổi không?
- Việc phát hành một shared library có làm các deployment phụ thuộc nhau không?

Ví dụ country codes có thể lấy từ standard/shared package có version; nhưng **quy tắc thuế** không nên được xử lý như một lookup table chung vô chủ nếu Finance/Tax domain chịu trách nhiệm xác định giá trị áp dụng.

Data shared không nhất thiết cấm; **shared ownership mơ hồ** mới nguy hiểm. Nếu nhiều context cần cùng reference dataset, đặt owner hoặc stewardship/contract cụ thể.

## 32. Ownership trong tổ chức và phân quyền thay đổi

Một service catalog nên ghi:

~~~text
Service: Inventory
Business capability: Stock availability and reservation
Owner team: Inventory Domain Team
Data owner:
  - StockBucket
  - StockReservation
Private storage:
  - inventory schema / database
Authoritative commands:
  - ReserveStock
  - ReleaseReservation
Public queries:
  - GetAvailability
  - GetReservation
Events:
  - StockReserved
  - ReservationRejected
  - StockReleased
Invariants:
  - No over-reservation under configured policy
Consistency:
  - Local transaction strong
  - Downstream read models eventually consistent
Security:
  - Workload authentication + tenant-aware authorization
SLO:
  - Reservation outcome completion and availability
Recovery:
  - Idempotency, outbox, reconciliation
Consumers:
  - Ordering, Fulfillment, Analytics
Contract owner / on-call:
  - Inventory Team
~~~

Việc ghi ownership giúp định tuyến thay đổi và incident. Platform team có thể cung cấp database/broker infrastructure nhưng không tự trở thành owner của nghĩa nghiệp vụ trong từng bảng. Data engineering có thể sở hữu warehouse pipeline nhưng không mặc nhiên được phép sửa các transaction nguồn.

## 33. Ai được phép làm migration, restore và sửa dữ liệu?

Quyền sở hữu nên được thể hiện trong quy trình vận hành:

- Database migration thuộc owner hoặc pipeline được ủy quyền, có review và rollback plan.
- Không cho team khác tự sửa private schema để “chữa nhanh” bug.
- Data repair phải đi qua command/tool được owner phê duyệt, áp invariants và audit.
- Restore cần hiểu time range và tác động tới downstream events/read models.
- Backfill cần checkpoint/version và idempotency.
- Production break-glass access nếu có phải ngắn hạn, có lý do, audit và hậu kiểm.
- Nếu sửa canonical data, cần quyết định có phát correction event hoặc rebuild projection không.
- Khi source owner bị outage, read cache có thể giúp hiển thị, nhưng command có tính đúng đắn phải xử lý theo hợp đồng, không để service khác tự ghi thay.

Một raw SQL UPDATE trong production có thể vượt qua validation, event publication và audit. Với hệ có nhiều projection, đó là cách dễ tạo drift không thể giải thích.

## 34. Quan sát độ nhất quán và data drift

Một hệ có source và nhiều projections cần metrics, không chỉ dashboard CPU.

| Metric/tín hiệu | Vì sao quan trọng |
|---|---|
| Owner API success/error rate | Khả năng phục vụ từ nguồn có thẩm quyền |
| Outbox backlog và oldest age | Event chưa được publish kịp |
| Broker consumer lag | Projection/consumer cập nhật chậm |
| Projection freshness age | Người dùng có thấy dữ liệu quá cũ? |
| Duplicate/stale event count | Redelivery hoặc ordered publication issue |
| Sequence gaps | Thiếu event cần thiết |
| Reconciliation mismatches | Source/projection bị lệch |
| Unknown external outcome backlog | Payment/booking chưa xác định |
| Schema compatibility errors | Producer/consumer thay đổi không đồng bộ |
| Cross-service synchronous dependencies | Mức coupling runtime |
| Unauthorized direct DB accesses | Vi phạm ranh giới ownership |
| Data deletion completion age | Yêu cầu privacy chưa hoàn tất |
| Query load by consumer | Một read consumer đang gây tải nguồn |
| Business invariant violation | Lỗi thực sự trong domain |

Ví dụ SLO:

~~~text
99.9% StockReservation commands hợp lệ
có outcome xác nhận (reserved/rejected)
trong <= 3 giây, đo trên cửa sổ 30 ngày.

99% OrderSummary projections cập nhật
trong <= 10 giây từ khi owner event được ghi nhận.
~~~

Các ngưỡng chỉ mang tính minh họa. Dựa vào business deadline, baseline và tải thực tế để chọn.

Một projection lag 20 giây có thể chấp nhận với dashboard, nhưng không thể dùng như bằng chứng cho phép capture payment lúc này nếu hợp đồng yêu cầu kiểm tra tức thời.

## 35. Contract testing và kiểm chứng dữ liệu xuyên service

Các kiểm thử cần chứng minh không ai vượt ownership:

1. **Domain invariant test:** Inventory không reserve vượt tồn.
2. **Authorization test:** Ordering không thể truy cập private payment table bằng credentials.
3. **API contract test:** ReserveStock request/response/errors đúng định nghĩa.
4. **Event compatibility test:** consumer cũ chịu được event field mới hợp lệ.
5. **Outbox crash test:** DB commit rồi dispatcher chết; event vẫn có thể publish, consumer idempotent.
6. **Inbox duplicate test:** cùng event đến hai lần không nhân side effect.
7. **Projection lag test:** UI/API đọc xử lý trạng thái chưa cập nhật đúng.
8. **Sequence gap test:** event v10 tới trước v9 không làm state đi lùi.
9. **Migration shadow-read:** bản cũ/bản mới so sánh trên key sample và edge cases.
10. **Cutover dual-write prevention:** chỉ một authoritative writer đang hoạt động.
11. **Data repair test:** sửa nguồn tạo đúng correction event/rebuild.
12. **Tenant isolation test:** consumer không xem/sửa dữ liệu tenant khác.
13. **Deletion propagation test:** dữ liệu cần xóa được xử lý ở các replicas theo policy.
14. **Unknown payment outcome test:** timeout sau provider side effect không tạo capture trùng.
15. **Recovery test:** restore owner DB có kế hoạch đối soát với event log và projections.

**Đối chiếu storage bytes hoặc số dòng bằng nhau chưa đủ** để khẳng định business semantics đúng. Hãy kiểm tra trạng thái, invariant và side effect trong các kịch bản quan trọng.

## 36. Anti-pattern thường gặp

### 36.1. Shared tables giữa nhiều service

Ordering và Payment cùng update orders.paid; không rõ ai là owner, phá business invariants.

**Cải thiện:** Payment công bố payment outcome, Ordering cập nhật lifecycle dựa trên contract.

### 36.2. Một service chỉ làm CRUD wrapper cho bảng

Service có endpoint setStatus, updateColumn, fetchRow, nhưng business rules nằm ở client.

**Cải thiện:** tổ chức theo commands/behaviors do service owner kiểm soát.

### 36.3. Data access library dùng chung private ORM entities

Mọi service import cùng model và tự query database, khiến schema change phải deploy đồng thời.

**Cải thiện:** công bố DTO/event contract riêng, không chia sẻ implementation entities.

### 36.4. API Gateway trở thành owner của mọi business rule

Gateway tự quyết định order paid, inventory reserved, refund allowed và ghi dữ liệu cho các service.

**Cải thiện:** gateway định tuyến/auth/rate limit; domain decisions thuộc owner.

### 36.5. Gửi toàn bộ bảng qua event

Mọi thay đổi cột tạo event schema lớn, rò rỉ PII và coupling consumer với private model.

**Cải thiện:** event theo business fact, dữ liệu tối thiểu cần thiết và versioning.

### 36.6. “Replica” được quyền ghi trở lại nguồn

Reporting chỉnh dữ liệu warehouse rồi mong owner DB tự đồng bộ, gây hai chiều không có conflict policy.

**Cải thiện:** command đến owner hoặc quy trình data repair được quản trị.

### 36.7. Distributed transaction giả bằng vài HTTP calls

Ordering ghi order=CONFIRMED, Payment có thể thất bại nhưng không có workflow/compensation.

**Cải thiện:** state machine, Saga/process manager, idempotency, reconciliation.

### 36.8. Tất cả reads phải gọi sync owner

Thay vì tận dụng projection cho báo cáo, mọi trang/BI query fan-out qua production services.

**Cải thiện:** chọn read model/caching phù hợp freshness và quyền.

### 36.9. Tách service theo từng entity nhỏ

ProductNameService, ProductStatusService và ProductDescriptionService chia cùng vòng đời một sản phẩm.

**Cải thiện:** gom theo capability/invariant, chỉ tách khi ranh giới thật sự độc lập.

### 36.10. Không có ownership matrix

Một field bị cập nhật từ nhiều nơi; incident mất nhiều ngày để tìm nguồn thay đổi.

**Cải thiện:** data catalog, role grants, API contracts, audit, owner/on-call.

## 37. Ví dụ tích hợp Java/Spring Boot

Giả sử service Inventory là owner của reservation. Application layer cung cấp hành vi ReserveStock, không cho client sửa một trường availableQuantity tùy ý.

### API DTO và controller

~~~java
import java.util.List;

public record ReserveStockRequest(
        String orderId,
        List<ReservationItem> items
) {}

public record ReservationItem(
        String sku,
        int quantity
) {}

public record ReservationResponse(
        String reservationId,
        String orderId,
        String status
) {}
~~~

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/inventory-reservations")
public final class ReservationController {
    private final ReserveStockUseCase reserveStockUseCase;

    public ReservationController(ReserveStockUseCase reserveStockUseCase) {
        this.reserveStockUseCase = reserveStockUseCase;
    }

    @PostMapping
    public ResponseEntity<ReservationResponse> reserve(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody ReserveStockRequest body) {
        ReservationResponse response = reserveStockUseCase.execute(
                key, body.orderId(), body.items()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Đây là mã minh họa, chưa hoàn chỉnh về authentication, authorization, validation, exception mapping, transaction và các tình huống replay. Production cần quyết định khi idempotency key cũ trả lại kết quả hiện có thì HTTP 200/201 theo contract nào.

### Use case sở hữu invariant

~~~java
public interface ReserveStockUseCase {
    ReservationResponse execute(
            String idempotencyKey,
            String orderId,
            List<ReservationItem> items
    );
}
~~~

Logic khái niệm:

~~~text
reserveStock(key, orderId, items):
  authenticate and authorize caller
  validate items and business rules
  lookup stable business operation key
  if already applied:
      return existing reservation outcome

  BEGIN transaction
      lock or atomically update stock buckets
      verify allocation constraints
      insert reservation
      insert outbox StockReserved event
      record idempotency outcome
  COMMIT

  return reservation result
~~~

Nếu Inventory dùng nhiều buckets hoặc cần atomicity khác, có thể cần một transaction strategy cụ thể. Điều quan trọng là mọi đường ghi vào stock/reservation đều phải qua cùng domain policy.

### Ordering chỉ gọi hợp đồng

~~~java
public interface InventoryPort {
    ReservationResponse reserveStock(
            String orderId,
            List<ReservationItem> items,
            String idempotencyKey
    );
}
~~~

Ordering dùng một adapter HTTP/gRPC/message, không import Inventory JPA repository để tự sửa DB. Contract error có thể trả OUT_OF_STOCK, INVALID_RESERVATION, timeout hoặc UNKNOWN_OUTCOME. Ordering phải hiểu chúng theo business workflow.

## 38. Bài thực hành: phân tích bảng products đang bị chia sẻ

Giả sử monolith có bảng:

~~~sql
CREATE TABLE products (
  product_id VARCHAR(100) PRIMARY KEY,
  name VARCHAR(255),
  description TEXT,
  current_price DECIMAL(18,2),
  available_qty INT,
  supplier_id VARCHAR(100),
  published BOOLEAN
);
~~~

Bốn ứng dụng đang trực tiếp UPDATE bảng:

- Catalog UI sửa name, description và published.
- Pricing job sửa current_price.
- Inventory job sửa available_qty.
- Procurement sửa supplier_id.

**Yêu cầu:** thiết kế ownership và đường chuyển đổi.

### Phương án

**Bước 1 — Bóc tách semantics:**

| Field | Owner gợi ý | Lý do |
|---|---|---|
| product_id | Catalog cấp identity/reference theo contract | Định danh sản phẩm |
| name/description/published | Catalog | Nội dung và trạng thái xuất bản |
| current_price | Pricing | Quy tắc giá hiện hành |
| available_qty | Inventory | Tồn khả dụng theo reservation |
| supplier_id | Procurement/Sourcing | Quan hệ cung ứng |

**Bước 2 — Chọn authority:** mỗi sự thật có một đường ghi có thẩm quyền. Có thể còn lưu legacy table như projection tạm, nhưng không cho bốn ứng dụng tiếp tục ghi độc lập vào những domain fields sau cutover.

**Bước 3 — Public contracts:** Catalog phát ProductPublished, Pricing công bố GetQuote/PriceChanged, Inventory công bố ReserveStock/AvailabilityChanged, Procurement công bố SupplierAssignmentChanged nếu consumer cần.

**Bước 4 — Read path:** Product detail page dùng BFF hoặc ProductSearch projection tổng hợp dữ liệu, có freshness contract. Checkout khi quyết định giao dịch hỏi đúng owner về quote và reservation.

**Bước 5 — Migration:** tạo storage theo owner, backfill, CDC có kiểm soát, shadow reads, traffic canary và thu hồi SQL writes cũ.

**Bước 6 — Failure:** khi Pricing unavailable, trang chi tiết có thể hiển thị một giá tham khảo với nhãn phù hợp nếu sản phẩm cho phép; không chốt thanh toán bằng giá stale nếu contract yêu cầu quote mới. Khi Inventory unavailable, không tự giảm stock trong Catalog.

Kết quả mong muốn không chỉ là bốn database mới, mà là **bốn capability có quyền ra quyết định và được bảo vệ bởi contract ổn định**.

## 39. Bài thực hành: dữ liệu bản sao có được sửa không?

Xét các trường hợp:

**A. OrderSummaryProjection lưu status=CANCELLED nhưng Ordering hiện là CONFIRMED.**  
Read model không được tự sửa Ordering. Nó cần kiểm tra event ordering, source-of-truth và reconciliation. Nếu projection stale/incorrect, rebuild hoặc áp correction event theo contract.

**B. Support cần sửa địa chỉ giao hàng trên một order đã tạo.**  
Không sửa Customer Profile hay Fulfillment DB trực tiếp. Xác định owner của shipment destination ở giai đoạn này và gọi ChangeDeliveryAddress command có authorization/state policy.

**C. Payment provider xác nhận refund sau khi Ordering đã trả PENDING.**  
Payment owner cập nhật refund state và công bố outcome. Ordering hoặc UI projection nhận event, chuyển trạng thái tổng hợp đúng nghĩa.

**D. Analytics phát hiện một đơn sai amount.**  
Warehouse không sửa transaction gốc. Gửi discrepancy/repair request tới Ordering/Pricing/Payment owners và có audit/reconciliation.

**E. Khách đổi tên trong profile nhưng hóa đơn cũ vẫn giữ tên tại thời điểm phát hành.**  
Không mặc nhiên là inconsistency. Snapshot lịch sử có semantics và retention riêng.

**F. Một team muốn query trực tiếp database service khác để giảm latency.**  
Đánh giá read API, projection, caching, batch, query contract. Nếu dùng direct read tạm, ghi owner, phạm vi, quyền, thời hạn loại bỏ và đánh giá schema coupling.

## 40. Checklist thiết kế data ownership

### Business boundary

- [ ] Mỗi business capability có owner rõ.
- [ ] Mỗi authoritative fact có một nơi quyết định và một đường ghi chuẩn.
- [ ] Invariants được bảo vệ bên trong boundary đủ lớn.
- [ ] Không chia service chỉ theo tên bảng/entity.
- [ ] Các thuật ngữ cùng tên nhưng khác semantics đã được phân biệt.
- [ ] Snapshot và source-of-truth được mô tả riêng.

### Storage và write access

- [ ] Database/schema/role phân tách quyền ghi theo service owner.
- [ ] Không có service khác UPDATE private tables.
- [ ] Migration do owner hoặc quy trình được ủy quyền thực hiện.
- [ ] Data repair có audit và giữ business invariants.
- [ ] Shared physical infrastructure có quota, failure domain và owner vận hành.
- [ ] Backup/restore và schema evolution có kế hoạch.

### API/event và nhất quán

- [ ] Cross-service changes đi qua command/API owner.
- [ ] Events diễn đạt business fact, không phải dump private tables.
- [ ] Contract có schema/version, identity, ordering và security.
- [ ] Consumer idempotent, chịu được duplicate và lag.
- [ ] Outbox/inbox được dùng khi cần bảo đảm reliable handoff.
- [ ] Có workflow state/compensation cho transaction xuyên service.
- [ ] Có cách xử lý external unknown outcome.
- [ ] Projection có freshness contract và reconciliation.
- [ ] Read path không biến thành N+1 synchronous dependencies không kiểm soát.

### Governance và vận hành

- [ ] Service catalog ghi owner, data categories, consumers và on-call.
- [ ] PII/tenant isolation, retention và deletion propagation được thiết kế.
- [ ] Có metrics outbox lag, projection drift, duplicate/gap và completion SLO.
- [ ] Contract tests và migration compatibility tests được chạy.
- [ ] Khi cutover, chỉ một authoritative writer còn hoạt động.
- [ ] Có runbook cho data mismatch, replay và restore.
- [ ] Data ownership thể hiện trong permissions, không chỉ slide.
- [ ] Quyết định kiến trúc được ghi và đánh giá lại khi capability đổi.

## 41. Mẫu ADR: chọn service owner cho một tập dữ liệu

~~~text
ADR: Ownership of Inventory Reservations

Context:
  Legacy orders table and stock table are written by multiple apps.
  Overselling and inconsistent cancellation occasionally occur.

Decision:
  Inventory capability owns stock bucket and reservation lifecycle.
  Inventory Service is the sole authoritative writer.
  Ordering can request ReserveStock/ReleaseReservation through API.
  Read consumers use GetAvailability or an event-driven projection.

Invariants:
  Allocations respect stock availability policy.
  Duplicate reservation commands do not allocate twice.
  Reservation release is idempotent.

Consistency:
  Inventory local transaction is atomic.
  Ordering-to-Inventory workflow is eventually consistent.
  Business state and pending transitions are explicit.

Contracts:
  Commands: ReserveStock, ReleaseReservation.
  Queries: GetReservation, GetAvailability.
  Events: StockReserved, ReservationRejected, StockReleased.

Failure:
  Timeout may have unknown outcome.
  Use idempotency and reconciliation.
  Retry bounded by business deadline.
  Compensation is managed by workflow owner.

Migration:
  Backfill, CDC bridge, shadow reads, controlled write cutover.
  Remove legacy SQL write grants after validation.

Security:
  Workload identity, tenant checks, least privilege.
  Minimize sensitive payloads.

Observability:
  Reservation completion SLO, outbox lag, reconciliation mismatches.

Owner:
  Inventory Domain Team

Rejected alternative:
  Shared table writes by Ordering, Payment and Inventory.
  Rejected due to invariant, deployment and schema coupling.
~~~

ADR không thay thế code, quyền truy cập và kiểm thử. Nó giải thích **vì sao ranh giới được chọn**, giả định nào đúng và điều kiện nào khiến team phải xem lại.

## 42. Các câu hỏi phỏng vấn và tự đánh giá

1. Vì sao database-per-service là câu chuyện quyền ghi/contract, không nhất thiết mỗi service một database server?
2. Nếu Pricing đổi giá hiện hành, Ordering có cần sửa giá của đơn cũ không? Vì sao?
3. Khi nào read model được phép phục vụ query thay owner API? Cần mô tả freshness thế nào?
4. Transactional outbox giải quyết lỗi nào và chưa giải quyết lỗi nào?
5. Vì sao một consumer nhận event hai lần có thể ghi sai dù event ordering đúng?
6. Nếu Customer Service “sở hữu tất cả customer data”, rủi ro bounded context nào có thể xảy ra?
7. Vì sao không nên dùng CDC raw row changes làm public domain events vĩnh viễn?
8. Nếu Payment timeout sau khi provider capture, Ordering có thể tự ghi payment=FAILED không?
9. Để migrate shared database, vì sao cần một authoritative writer tại từng thời điểm?
10. Khi xóa dữ liệu cá nhân, làm sao xử lý những copies ở cache, analytics, DLQ và logs?
11. Một sản phẩm có stock tại nhiều kho. Nên đặt inventory invariant ở mức SKU hay SKU-location?
12. Nếu Reporting phát hiện sai lệch, ai được quyền sửa source-of-truth và bằng cách nào?
13. Có trường hợp nào gộp hai service thành một boundary lại tốt hơn Saga phức tạp không?
14. Nếu hỗ trợ customer cần “đổi địa chỉ” sau khi đơn giao, context nào sở hữu hành động?
15. Làm sao kiểm chứng rằng quyền sở hữu dữ liệu không chỉ tồn tại trên sơ đồ mà đã được thực thi?

Trả lời tốt phải dựa trên **business invariants, semantics, authority, consistency và failure handling**, không chỉ lặp khẩu hiệu “mỗi service một DB”.

## 43. Kết luận

**Dữ liệu thuộc về dịch vụ sở hữu năng lực nghiệp vụ** nghĩa là dịch vụ có trách nhiệm với một quyết định nghiệp vụ phải kiểm soát dữ liệu có thẩm quyền, các bất biến và đường ghi liên quan. Các service khác hợp tác qua API, command, event hoặc read model có contract; không trực tiếp sửa private tables như một cách phối hợp.

Không phải mọi bản sao đều sai. Snapshot đơn hàng, cache, search index và analytics projection có thể phục vụ nhu cầu riêng, miễn nguồn sự thật, semantics, độ mới, quyền truy cập và quy trình cập nhật đều rõ. Khi thay đổi vượt nhiều owner, thiết kế workflow nhất quán cuối cùng, idempotency, outbox/inbox, compensation và reconciliation thay vì kỳ vọng nhiều database tự tạo một transaction.

Giá trị cuối cùng của ownership là **tính đúng đắn, khả năng phát triển độc lập và trách nhiệm vận hành minh bạch**. Hãy bắt đầu từ business capability và invariant, chọn một authoritative writer, bảo vệ bằng permissions và contracts, rồi dùng số đo và kiểm thử để xác minh dữ liệu vẫn đúng khi có lỗi phân tán, migration hoặc replay.
