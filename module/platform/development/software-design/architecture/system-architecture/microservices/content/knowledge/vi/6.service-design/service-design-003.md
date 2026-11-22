# Thiết kế API theo hành vi và trách nhiệm nghiệp vụ trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Thiết kế dịch vụ.  
> **Mục tiêu:** Thiết kế ranh giới API thể hiện đúng năng lực, hành vi, quy tắc và quyền sở hữu của từng dịch vụ; tránh biến Microservices thành các dịch vụ CRUD phụ thuộc lẫn nhau; xây dựng hợp đồng rõ ràng cho người gọi, cho dữ liệu và cho tình huống lỗi.

## 1. Từ “mỗi dịch vụ có bảng dữ liệu” đến “mỗi dịch vụ chịu trách nhiệm về một năng lực”

Trong Microservices, API không chỉ là tập URL truy cập dữ liệu. API là **hợp đồng nghiệp vụ** mà một dịch vụ công bố: dịch vụ có khả năng gì, chấp nhận yêu cầu nào, bảo đảm điều gì, từ chối khi nào và trả kết quả theo trạng thái nào.

Ví dụ ứng dụng bán hàng có các năng lực:

- **Catalog:** quản lý sản phẩm có thể bán, mô tả, phân loại, hiển thị.
- **Pricing:** xác định báo giá theo chính sách giá, chương trình khuyến mại và điều kiện khách hàng.
- **Inventory:** quản lý số lượng có thể cấp phát và giữ chỗ hàng hóa.
- **Ordering:** quản lý vòng đời đơn hàng, điều kiện xác nhận, hủy và trạng thái xử lý.
- **Payment:** quản lý yêu cầu thanh toán, kết quả giao dịch và đối soát.
- **Fulfillment:** tổ chức giao hàng, vận chuyển và hoàn tất đơn.

Nếu tạo service theo bảng như ProductService, OrderTableService, StatusService rồi mở các endpoint updateColumn, setStatus, fetchAllRows, client có thể phải tự ghép logic xuyên nhiều service. Hệ thống bị phân tán về triển khai nhưng **quy tắc nghiệp vụ lại nằm ở client hoặc gateway**. Mỗi thay đổi nhỏ có thể làm nhiều thành phần phải cập nhật cùng lúc.

Cách tiếp cận theo hành vi hỏi: **Ai có quyền quyết định khi một đơn hàng được xác nhận? Điều kiện xác nhận là gì? Dịch vụ nào chịu trách nhiệm bảo vệ điều kiện đó?** Từ đó API thể hiện các thao tác có ý nghĩa như **Tạo bản nháp**, **Gửi đơn để xử lý**, **Hủy đơn**, **Xác nhận giữ hàng**, **Yêu cầu hoàn tiền**, thay vì chỉ cho bên ngoài chỉnh các trường tùy ý.

Nguyên tắc cốt lõi:

> **Dịch vụ sở hữu một tập trách nhiệm nghiệp vụ rõ ràng; API cho phép consumer yêu cầu hành vi trong phạm vi trách nhiệm ấy; dịch vụ chịu trách nhiệm thực thi quy tắc và giữ các bất biến của mình.**

Không phải mọi endpoint phải có động từ. HTTP API có thể dùng resource và phương thức chuẩn để biểu diễn hành vi; điều quan trọng là hợp đồng biểu đạt đúng kết quả nghiệp vụ, không cho phép consumer vượt qua các quy tắc bên trong.

## 2. Phân biệt trách nhiệm, hành vi, dữ liệu và endpoint

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Business capability** | Tổ chức cần làm được việc gì? | Xử lý đơn hàng |
| **Bounded context** | Trong phạm vi nào thuật ngữ và quy tắc có một nghĩa thống nhất? | Ordering |
| **Service responsibility** | Ai quyết định và chịu trách nhiệm cho kết quả? | Ordering xác nhận/hủy đơn theo trạng thái |
| **Aggregate/invariant** | Quy tắc nào phải được bảo vệ khi dữ liệu thay đổi? | Đơn đã giao không thể hủy theo luồng thông thường |
| **Command** | Consumer muốn điều gì xảy ra? | Yêu cầu hủy đơn |
| **Query** | Consumer muốn biết điều gì? | Xem trạng thái đơn |
| **Domain event** | Sự thật nghiệp vụ nào đã xảy ra? | OrderCancelled |
| **API contract** | Cách gọi, điều kiện, phản hồi và lỗi là gì? | POST /orders/{id}/cancel |
| **Transport** | Truyền hợp đồng qua giao thức nào? | HTTP/JSON, gRPC, message broker |

Một endpoint không đồng nghĩa một capability. Một capability có thể cung cấp nhiều command/query/event. Ngược lại, việc có nhiều endpoint CRUD không chứng minh dịch vụ có trách nhiệm nghiệp vụ độc lập.

### Ví dụ phân định

**Ordering sở hữu:** mã đơn hàng, trạng thái vòng đời, item snapshot, tổng tiền đơn đã chốt theo quy tắc, quyền hủy và lịch sử chuyển trạng thái.

**Inventory sở hữu:** mức tồn khả dụng, reservation, release reservation và chính sách cấp phát.

**Payment sở hữu:** authorization/capture/refund, idempotency của giao dịch, trạng thái với payment provider và reconciliation.

Ordering có thể yêu cầu Inventory giữ hàng và Payment xử lý, nhưng **không được tự cập nhật bảng reservation hay transaction của hai service đó**. Quyền sở hữu dữ liệu và quy tắc luôn đi cùng quyền công bố hành vi.

## 3. Bắt đầu thiết kế từ use case, không bắt đầu từ URL hoặc bảng

Để thiết kế API của một service, hãy thu thập các tình huống nghiệp vụ thực sự:

1. **Actor:** ai/ hệ thống nào khởi tạo yêu cầu?
2. **Intent:** người gọi muốn đạt kết quả gì bằng ngôn ngữ nghiệp vụ?
3. **Preconditions:** những điều kiện nào phải đúng trước khi thao tác?
4. **Invariants:** quy tắc nào không được phá vỡ?
5. **Outcome:** khi thành công, điều gì chắc chắn đã xảy ra?
6. **Failure modes:** khi không thành công, lỗi có ý nghĩa gì và có thể thử lại không?
7. **Ownership:** service nào có đủ dữ liệu và quyền để ra quyết định?
8. **Consistency:** kết quả cần tức thời, hay có thể nhất quán cuối cùng?
9. **Observability:** làm sao xác nhận hành vi chạy đúng trong production?
10. **Consumers:** ai cần dùng contract, với nhịp thay đổi nào?

Ví dụ use case **Hủy đơn hàng**:

| Mục | Mô tả |
|---|---|
| Actor | Khách hàng sở hữu đơn hoặc nhân viên có quyền |
| Intent | Hủy một đơn chưa vượt điểm không thể hủy |
| Preconditions | Đơn tồn tại, actor có quyền, trạng thái còn hủy được |
| Invariant | Không thể hủy trực tiếp đơn đã giao thành công |
| Outcome | Ordering ghi trạng thái CANCELLED hoặc khởi tạo yêu cầu hủy theo workflow |
| Side effects | Có thể yêu cầu Inventory nhả reservation, Payment hoàn tiền |
| Failure | Không có quyền, không tìm thấy, xung đột trạng thái, dependency lỗi |
| Consistency | Trạng thái hủy đơn và hoàn tiền có thể có hai mốc riêng |
| Evidence | Order ID, actor, thời điểm, operation ID, domain event, trace |

Từ bảng này mới quyết định endpoint, request, response và cách phối hợp liên dịch vụ. Nếu chưa rõ “hủy thành công nghĩa là gì”, không thể thiết kế response đúng chỉ bằng việc chọn HTTP 200 hay 202.

## 4. Ranh giới service dựa trên khả năng quyết định

Một service có ranh giới tốt thường:

- Có **ngôn ngữ nghiệp vụ riêng**, ví dụ “giữ hàng” trong Inventory khác “xác nhận đơn” trong Ordering.
- Có quyền sở hữu dữ liệu và bất biến cần kiểm soát trong ranh giới của mình.
- Có thể thay đổi phần lớn quy tắc nội bộ mà không buộc consumer sửa theo.
- Có các hợp đồng công bố kết quả theo nghĩa nghiệp vụ, không để lộ transaction nội bộ.
- Có nhóm hoặc vai trò chịu trách nhiệm xây dựng, triển khai và vận hành.
- Có thể chấp nhận độ trễ/nhất quán của các luồng vượt qua ranh giới.

**Không đồng nhất service với một entity hay một database table.** Service Ordering có thể quản lý Order, OrderLine, AddressSnapshot, CancellationPolicy và state transitions trong cùng một boundary. Không cần tạo riêng từng service cho mỗi lớp domain.

### Bounded context và ngữ nghĩa cùng một thuật ngữ

Từ “Customer” trong Sales có thể là người đang mua; trong Billing là chủ thể thanh toán; trong Support là người tạo ticket. Cố dùng một object Customer chung cho tất cả service khiến các nhóm khó thay đổi độc lập. Mỗi context nên định nghĩa model và API theo trách nhiệm của nó, kết nối qua hợp đồng rõ ràng và mapping khi cần.

Đôi khi một service phục vụ nhiều use case cùng một boundary; đôi khi một bounded context cần nhiều deployment unit. Không áp dụng quy tắc máy móc một bounded context = một process. Ranh giới cần cân nhắc yêu cầu vận hành, giao dịch, tổ chức và lifecycle.

## 5. Hành vi nghiệp vụ khác thao tác chỉnh trường

Xét yêu cầu **Xác nhận đơn**.

### Thiết kế thiên về dữ liệu và dễ mất quy tắc

~~~http
PATCH /orders/ord-1024
Content-Type: application/json

{
  "status": "CONFIRMED",
  "totalAmount": 850000,
  "inventoryReserved": true,
  "paymentApproved": true
}
~~~

Consumer tự cung cấp trạng thái cuối và các sự thật quan trọng. Nếu server chỉ ghi các trường, consumer có thể bỏ qua validation, giả mạo kết quả giữ hàng hoặc xác nhận khi payment chưa đạt.

### Thiết kế theo hành vi

~~~http
POST /orders/ord-1024/submit
Idempotency-Key: 29fc1e7d-e5f1-4a50-9221-51e3e58895b7
Content-Type: application/json

{
  "deliveryOption": "STANDARD",
  "expectedOrderVersion": 3
}
~~~

Ý nghĩa: **Tôi yêu cầu gửi đơn để xử lý theo chính sách hiện tại**. Ordering xác minh quyền, trạng thái, phiên bản, dữ liệu đầu vào và điều kiện phối hợp với các context khác. Consumer không tự gán các trường thuộc kết quả nội bộ.

Nếu toàn bộ thao tác đã hoàn tất trước response, có thể trả 200 với trạng thái kết quả. Nếu tạo một workflow dài, trả 202 Accepted kèm operation ID để theo dõi. Nếu state transition không hợp lệ, trả lỗi có cấu trúc, không âm thầm sửa trạng thái.

**Bài học:** endpoint nên biểu diễn ý định, đầu vào hợp lệ và cam kết kết quả. Dịch vụ giữ quyền quyết định cách đạt kết quả.

## 6. Command, Query và Event: ba loại hợp đồng khác nhau

### Command: yêu cầu thay đổi trạng thái hoặc thực thi hành vi

Ví dụ:

- CreateOrderDraft
- AddItemToDraft
- SubmitOrder
- CancelOrder
- ReserveStock
- AuthorizePayment
- RequestRefund

Command có thể bị từ chối vì quyền, state hoặc quy tắc; một command được chấp nhận chưa chắc workflow đã hoàn tất. Command thường cần idempotency và kiểm soát đồng thời, vì có thể phát sinh side effect.

### Query: hỏi về trạng thái hoặc một projection

Ví dụ:

- GetOrder
- ListOrdersForCustomer
- GetAvailability
- FindShipmentsByOrder

Query nên có semantics đọc rõ ràng, hỗ trợ pagination/filter phù hợp, không tạo side effect nghiệp vụ bất ngờ. Query không nhất thiết đọc trực tiếp database chính; read model có thể được xây từ events nếu hợp đồng cho phép dữ liệu cập nhật trễ.

### Domain event: thông báo một sự thật đã xảy ra

Ví dụ:

- OrderSubmitted
- StockReserved
- PaymentAuthorized
- OrderCancelled
- RefundCompleted

Tên event ở thì quá khứ và phản ánh **kết quả đã được ghi nhận**, không phải mệnh lệnh gửi đến consumer. Message kiểu “UpdateInventoryNow” là command gửi qua broker, không tự nhiên trở thành event chỉ vì truyền bất đồng bộ.

**CQRS** có thể tách model đọc/ghi khi thật sự có lợi, nhưng không bắt buộc phải dùng hai database hoặc hai service. Một API có thể phân biệt command và query một cách rõ ràng ngay trong một service.

## 7. Thiết kế HTTP API theo hành vi và semantics chuẩn

REST-style HTTP vẫn phù hợp với API hướng hành vi. Chọn URI thể hiện resource hoặc operation có nghĩa; dùng HTTP method đúng semantics.

| Tác vụ nghiệp vụ | Hình thức HTTP khả dĩ | Ý nghĩa |
|---|---|---|
| Tạo đơn nháp | POST /orders | Tạo resource; có thể trả 201 Created |
| Xem đơn | GET /orders/{orderId} | Lấy representation theo quyền |
| Liệt kê đơn của khách | GET /orders?customerId=... | Query có filter và pagination |
| Sửa thuộc tính được phép của bản nháp | PATCH /orders/{id} | Chỉ những field được sửa trong trạng thái đó |
| Gửi đơn để xử lý | POST /orders/{id}/submit | Command có quy tắc chuyển trạng thái |
| Hủy đơn | POST /orders/{id}/cancel | Command có điều kiện và side effect |
| Tra cứu tiến độ workflow | GET /operations/{operationId} | Xem trạng thái tác vụ dài |
| Yêu cầu hoàn tiền | POST /payments/{id}/refund-requests | Tạo yêu cầu hoàn tiền có vòng đời riêng |

Không cần biến mọi động từ thành endpoint mới khi một resource model tự nhiên giải quyết đủ ý nghĩa; ví dụ tạo đơn dùng POST /orders. Ngược lại, một business action có nhiều điều kiện không nên được che dưới một PATCH status tùy ý.

**Không dùng GET để thay đổi trạng thái.** GET phải an toàn về semantics; crawler, cache, prefetch hoặc retry có thể gọi lại mà không chờ người dùng xác nhận. PUT thường có semantics idempotent khi thay thế trạng thái resource; PATCH cần định nghĩa rõ phép cập nhật và có thể không idempotent. POST không mặc định idempotent, vì vậy command quan trọng thường cần idempotency key và cơ chế lưu kết quả.

### Tên, URI và tính ổn định

- Dùng thuật ngữ miền: orders, reservations, payment-authorizations; tránh table name và tên lớp kỹ thuật.
- Dùng resource ID ổn định ở public contract, không lộ khóa nội bộ hoặc giả định có quyền chỉ vì biết ID.
- Dùng các danh từ số nhiều và quy ước nhất quán cho collection.
- Chọn mức chi tiết URI theo ownership, không phản ánh mọi quan hệ join database.
- Đừng nhét trạng thái workflow vào các query parameter không rõ nghĩa như action=doSomething.
- Giữ nguyên semantics khi triển khai lại backend; consumer không cần biết service dùng Kafka hay database nào.

Ví dụ /orders/{id}/items thể hiện collection thuộc đơn. Nhưng chỉ cho chỉnh item khi đơn ở trạng thái DRAFT và áp đúng quy tắc giá/khuyến mại; URI đẹp không thay thế domain validation.

## 8. Thiết kế hợp đồng từ đầu ra, điều kiện và trạng thái

Một API có hành vi rõ phải mô tả ít nhất:

| Thành phần hợp đồng | Câu hỏi |
|---|---|
| Mục đích | Consumer đạt kết quả nghiệp vụ nào? |
| Actor/quyền | Ai được thực hiện, trên đối tượng nào? |
| Request | Field nào bắt buộc, giới hạn và meaning là gì? |
| Preconditions | State/version/resource phải đạt điều kiện gì? |
| Postconditions | Sau thành công, dữ liệu nào chắc chắn đúng? |
| Side effects | Event, external call, transaction, notification nào có thể phát sinh? |
| Idempotency | Gọi lại khi mất response có tạo thêm side effect không? |
| Response | Trả kết quả cuối hay trạng thái công việc? |
| Error model | Conflict, validation, auth, dependency failure biểu đạt thế nào? |
| Consistency | Kết quả nào đồng bộ, kết quả nào cuối cùng sẽ nhất quán? |
| Versioning | Consumer cũ còn hoạt động khi contract tiến hóa ra sao? |
| Observability | Làm sao tìm operation/trace và đo SLO? |

Không mô tả API chỉ bằng danh sách input/output. **Lời hứa nghiệp vụ** mới quyết định cách consumer xử lý response và retry.

### Mẫu hợp đồng cho SubmitOrder

**Intent:** khách hàng gửi một đơn nháp hợp lệ để bắt đầu quy trình đặt hàng.

**Điều kiện:** order tồn tại; actor được phép; trạng thái DRAFT; item và delivery option hợp lệ; version phù hợp để tránh xác nhận bản nháp cũ.

**Kết quả tức thời:** request được chấp nhận và một operation đã được ghi bền, hoặc workflow hoàn tất và order đạt kết quả xác định.

**Kết quả cuối:** CONFIRMED nếu reservation/payment theo chính sách thành công; REJECTED hoặc một trạng thái cần xử lý nếu không. Không hứa thành công thanh toán ngay khi chỉ mới nhận yêu cầu.

**Retry:** idempotency key gắn với actor/tenant, operation và payload; cùng key và payload trả về cùng kết quả đã lưu hoặc trạng thái operation hiện hành.

**Lỗi:** không có quyền, không tồn tại, phiên bản sai, trạng thái sai, dữ liệu không hợp lệ, rate limit và lỗi tạm thời.

## 9. Mô hình trạng thái làm rõ hành vi hợp lệ

Một API hành vi tốt thường dựa trên state machine của aggregate.

Ví dụ vòng đời đơn:

~~~text
               create
                 |
                 v
               DRAFT
                 |
               submit
                 v
          PENDING_PAYMENT
             |        |
      authorized     rejected
             v        v
         CONFIRMED   REJECTED
             |
           fulfill
             v
         FULFILLED

DRAFT -------- cancel --------> CANCELLED
PENDING_PAYMENT -- cancel request --> CANCELLATION_PENDING
~~~

Đây là mô hình minh họa; trạng thái và transition thực tế phụ thuộc chính sách. Điều quan trọng là:

- Command được định nghĩa trên **trạng thái hiện tại**, không chỉ trên schema JSON.
- Chỉ một số transition được phép; ví dụ không CancelOrder như đơn thường sau khi Fulfilled.
- Có thể tồn tại trạng thái trung gian do giao dịch liên dịch vụ chưa hoàn tất.
- Trạng thái Payment và Inventory có lifecycle riêng; không ép mọi kết quả phụ thành một boolean của Order.
- Mỗi transition có postcondition và event rõ, đồng thời có thể yêu cầu kiểm tra version.

Ví dụ bảng quyết định:

| Trạng thái hiện tại | Command | Kết quả |
|---|---|---|
| DRAFT | SubmitOrder | Tạo workflow/operation, chuyển PENDING_PAYMENT |
| DRAFT | CancelOrder | CANCELLED |
| PENDING_PAYMENT | SubmitOrder cùng idempotency key | Trả operation đã có |
| PENDING_PAYMENT | SubmitOrder với ý định mới | Xung đột hoặc yêu cầu riêng theo hợp đồng |
| CONFIRMED | CancelOrder | Chỉ thực hiện nếu chính sách cho phép, có thể cần workflow hoàn tiền |
| FULFILLED | CancelOrder | Từ chối; hướng sang return/refund |
| CANCELLED | CancelOrder cùng key cũ | Không tạo thêm tác dụng; trả kết quả cũ |

**Từ chối một command không hợp lệ là giữ bất biến**, không phải lỗi hệ thống. API cần mô hình hóa conflict như một outcome dự kiến.

## 10. Bảo vệ bất biến ở đúng nơi sở hữu

Bất biến (invariant) là điều kiện phải luôn đúng trong ranh giới được bảo vệ. Ví dụ:

- Một order item có quantity dương, SKU hợp lệ theo chính sách.
- Tổng tiền được tính theo nguồn giá và quy tắc đã chốt.
- Không chuyển một đơn sang CONFIRMED khi điều kiện nghiệp vụ chưa đủ.
- Reservation không cấp phát nhiều hơn lượng hàng còn khả dụng theo mô hình Inventory.
- Một payment idempotency key không được tạo hai lần capture cùng giao dịch.

Client có thể pre-validate để cải thiện UX, nhưng **server sở hữu phải xác minh lại**. Không tin totalAmount, role, currentStatus hoặc paymentApproved do client đưa lên như sự thật.

Một service không nên cố bảo vệ invariants thuộc service khác bằng cách sửa database của họ. Khi cần kết quả xuyên ranh giới, phải phối hợp qua API/event và có trạng thái trung gian. Nếu yêu cầu nghiệp vụ thực sự đòi một transaction ACID bao phủ nhiều thuộc tính, cần xem lại boundary: có thể một phần đang bị tách quá nhỏ.

### Aggregate và đơn vị nhất quán

Trong DDD, aggregate là ranh giới để giữ một tập invariants cùng nhau trong transaction nội bộ. API command thường thao tác qua aggregate root hoặc application use case. Không bắt buộc mọi API map một-một tới một aggregate, nhưng việc nêu aggregate giúp xác định **ai được sửa gì, khi nào**.

Đừng để nhiều service ghi cùng bảng chỉ vì “tiện”. Shared write khiến ownership không rõ, schema change khó độc lập và quyền kiểm soát invariants bị phân tán.

## 11. Giao tiếp liên dịch vụ: hỏi đúng owner, không điều khiển nội bộ

Khi Ordering cần giữ hàng, nó gọi hành vi do Inventory sở hữu, ví dụ:

~~~http
POST /inventory-reservations
Idempotency-Key: order-ord-1024-reservation-v1
Content-Type: application/json

{
  "orderId": "ord-1024",
  "items": [
    {"sku": "sku-1", "quantity": 2},
    {"sku": "sku-2", "quantity": 1}
  ],
  "expiresAt": "2026-11-11T14:00:00Z"
}
~~~

Inventory quyết định có đủ tồn, áp chính sách và ghi reservation. Ordering không gửi lệnh “set availableQuantity = 14” hoặc tự cập nhật bảng stock. Cùng nguyên tắc, Ordering yêu cầu Payment authorize/capture bằng hợp đồng riêng, không tự ghi PaymentTransaction.

**Từ vựng API phải gắn với trách nhiệm:** reserve inventory, release reservation, authorize payment, refund payment, submit order. Một service biết cần kết quả gì nhưng không áp đặt thuật toán nội bộ của service khác.

### Tránh chuỗi gọi chéo để lấy từng field

Nếu API Checkout phải gọi nhiều service chỉ để thu thập từng field như customerName, productName, discountAmount, shippingCost, nó dễ tạo latency, coupling và rủi ro cascading failure. Cân nhắc:

- Thiết kế response theo nhu cầu client (projection), không đẩy client tự N+1 request.
- Dùng API composition ở tầng phù hợp cho read use case.
- Dùng read model cập nhật bằng event nếu chấp nhận eventual consistency.
- Cache/snapshot dữ liệu tham chiếu khi hợp đồng cho phép.
- Giữ dữ liệu và invariants cần transaction chung trong một boundary phù hợp.

Không biến gateway thành nơi sở hữu quy tắc nghiệp vụ. Gateway có thể định tuyến, xác thực, rate limit và tổng hợp read nhẹ, nhưng các quyết định như “đơn được hủy không” vẫn thuộc Ordering.

## 12. Khi nào chọn đồng bộ, khi nào chọn bất đồng bộ?

| Tình huống | Hướng giao tiếp phù hợp | Điều cần làm rõ |
|---|---|---|
| Cần kết quả ngay để quyết định response | HTTP/gRPC sync | Timeout, deadline, failure model |
| Ghi nhận yêu cầu xử lý lâu | Command async qua API + operation | 202, polling/callback, completion SLO |
| Thông báo sự thật đã xảy ra cho nhiều consumer | Domain/integration event | Schema version, dedup, ordering |
| Cập nhật projection tra cứu | Event-driven read model | Lag, replay, dữ liệu cũ |
| Đòi transaction ngay qua nhiều service | Xem lại boundary hoặc thiết kế workflow | Consistency, compensation, failure handling |
| Tác vụ có thể lặp, điều phối dài | Saga/process manager | Idempotency, trạng thái, recovery |

Không phải mọi command cần HTTP; không phải mọi event cần Kafka. Lựa chọn phải dựa trên hợp đồng nghiệp vụ, latency budget, độ tin cậy, khả năng theo dõi và hạ tầng thực tế.

### Một command chưa chắc hoàn tất trong một RPC

Nếu Order phải đợi Inventory, Payment và provider bên ngoài, có thể phản hồi:

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-558
Content-Type: application/json

{
  "operationId": "op-558",
  "orderId": "ord-1024",
  "status": "PENDING",
  "statusUrl": "/operations/op-558"
}
~~~

Sau đó consumer gọi:

~~~http
GET /operations/op-558

{
  "operationId": "op-558",
  "status": "SUCCEEDED",
  "result": {
    "orderId": "ord-1024",
    "orderStatus": "CONFIRMED"
  }
}
~~~

Nếu workflow thất bại, operation có thể trả status FAILED kèm mã lỗi nghiệp vụ và tình trạng đã bù trừ hay cần đối soát. Contract phải có policy về thời gian giữ operation, trạng thái timeout, webhook hoặc polling, và idempotency. 202 chỉ là **đã nhận xử lý**, không có nghĩa công việc đã thành công.

## 13. Thiết kế request và response để phản ánh ngôn ngữ miền

### Request chỉ chứa dữ liệu người gọi có quyền cung cấp

Ví dụ tạo Order Draft:

~~~http
POST /orders
Content-Type: application/json
Idempotency-Key: 48a1f99e-687a-4a70-b551-adf29f9800e1

{
  "customerReference": "cust-271",
  "items": [
    {"sku": "book-21", "quantity": 2},
    {"sku": "pen-3", "quantity": 5}
  ],
  "deliveryAddressId": "addr-12"
}
~~~

Client mô tả intent và các lựa chọn; không truyền status=PAID hoặc inventoryReserved=true. Server kiểm tra actor có quyền dùng customer/address, tính snapshot cần thiết, ghi bản nháp và trả resource.

~~~http
HTTP/1.1 201 Created
Location: /orders/ord-1024
ETag: "3"
Content-Type: application/json

{
  "id": "ord-1024",
  "status": "DRAFT",
  "version": 3,
  "items": [
    {"sku": "book-21", "quantity": 2},
    {"sku": "pen-3", "quantity": 5}
  ],
  "allowedActions": ["ADD_ITEM", "REMOVE_ITEM", "SUBMIT", "CANCEL"]
}
~~~

Trường allowedActions là tùy chọn giúp UI hiển thị hành động khả dụng. Server vẫn phải kiểm tra quyền và trạng thái lúc command thực thi; allowedActions có thể cũ ngay khi được trả về.

### Response bộc lộ trạng thái nghiệp vụ, không bộc lộ schema nội bộ

Ưu tiên các field có nghĩa cho consumer: orderId, lifecycleStatus, totals theo currency, version, actions/statusUrl. Tránh trả nguyên entity ORM, lazy loading graph, tên cột database, thông tin nhà cung cấp bí mật hay trạng thái kỹ thuật khó ổn định.

Có thể dùng public enum **DRAFT, PENDING_PAYMENT, CONFIRMED, CANCELLED** với định nghĩa và quy tắc tiến hóa rõ. Không trả một mã số 17 khó hiểu và yêu cầu client tra bảng nội bộ.

### Kiểu dữ liệu

- Tiền: dùng decimal string kèm currency hoặc đơn vị nhỏ nhất được mô tả rõ; tránh float nhị phân cho phép tính tiền.
- Thời gian: dùng ISO 8601/RFC 3339 với offset hoặc UTC, định nghĩa múi giờ khi nghiệp vụ cần.
- ID: dùng định dạng ổn định và opaque, không dựa vào thứ tự tăng khi có yêu cầu bảo mật.
- Enumeration: ghi rõ giá trị, khả năng xuất hiện giá trị mới và hành vi consumer khi không nhận diện.
- Field optional/null: phân biệt “không cung cấp”, “chưa biết” và “không áp dụng”.
- Collection: ghi giới hạn số phần tử, pagination, sort và tính ổn định của cursor.
- Precision: quy định rounding, unit và validation, nhất là quantity, weight, price.

## 14. Hợp đồng lỗi phải nói được consumer nên làm gì

Một lỗi API không chỉ là status code. Nó cần phân biệt input, quyền, trạng thái, rủi ro retry và sự cố dependency.

| HTTP status | Tình huống thường gặp | Hành vi consumer |
|---|---|---|
| 200 OK | Command/query hoàn tất và có representation | Dùng kết quả |
| 201 Created | Tạo resource thành công | Theo Location hoặc representation |
| 202 Accepted | Đã nhận xử lý, chưa hoàn tất | Theo dõi operation |
| 204 No Content | Thành công, không có body | Hoàn tất theo hợp đồng |
| 400 Bad Request | Cú pháp/định dạng request sai | Sửa request |
| 401 Unauthorized | Chưa xác thực hợp lệ | Đăng nhập/cấp token theo flow |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền | Không retry tự động |
| 404 Not Found | Không có hoặc không được phép tiết lộ resource | Theo chính sách quyền và lỗi |
| 409 Conflict | Xung đột trạng thái, idempotency hoặc quy tắc | Refresh state/đổi thao tác |
| 412 Precondition Failed | Version/ETag không còn hợp lệ | Đọc lại và quyết định lại |
| 422 Unprocessable Content | Input hợp lệ về cú pháp nhưng vi phạm ngữ nghĩa | Hiển thị lỗi nghiệp vụ |
| 429 Too Many Requests | Vượt rate limit | Retry theo policy/Retry-After |
| 500 Internal Server Error | Lỗi máy chủ không dự kiến | Báo lỗi, quan sát trace |
| 502/503/504 | Lỗi upstream/service unavailable/timeout | Retry có điều kiện, deadline và idempotency |

Việc chọn 400/409/422 phụ thuộc quy ước được công bố và phải nhất quán. Không nên ép toàn bộ lỗi vào HTTP 200 với body success=false nếu làm mất semantics với observability, cache, client library và cơ chế retry.

Ví dụ lỗi có cấu trúc:

~~~json
{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Order cannot be submitted",
  "status": 409,
  "code": "ORDER_NOT_SUBMITTABLE",
  "detail": "The order is already cancelled.",
  "instance": "/orders/ord-1024/submit",
  "correlationId": "2e4d77c9026c"
}
~~~

Có thể tuân theo hướng Problem Details (RFC 9457) và thêm extension field phù hợp. Giữ **machine-readable error code** ổn định; mô tả detail phục vụ người dùng/điều tra và có thể được bản địa hóa. Không đưa stack trace, SQL, secret hoặc thông tin của tenant khác ra public response.

## 15. Idempotency cho hành vi có side effect

Client có thể retry vì kết nối mất sau khi gửi request, mặc dù server đã xử lý. Nếu mỗi POST tạo side effect mới, có thể tạo hai đơn, hai reservation hoặc hai khoản thanh toán.

**Idempotency** ở mức nghiệp vụ nghĩa là thực hiện lại cùng một ý định theo một định danh ổn định không tạo thêm tác dụng không mong muốn. Một cách triển khai API command:

1. Client tạo **Idempotency-Key** đủ ngẫu nhiên, ổn định cho cùng một ý định.
2. Server xác định scope theo tenant/actor, operation và key.
3. Server tính fingerprint của request được chuẩn hóa theo hợp đồng.
4. Khi key mới: atomically lưu record xử lý và bảo đảm chỉ một command được thực thi theo policy.
5. Khi cùng key + cùng fingerprint: trả lại kết quả đã lưu hoặc trạng thái operation đã được tạo.
6. Khi cùng key + khác fingerprint: trả conflict, không âm thầm tạo thao tác mới.
7. Quy định retention, replay window, recovery khi crash và cách xử lý request đang chạy dở.
8. Với side effect downstream, dùng stable operation ID/idempotency key xuyên hệ thống và đối soát trạng thái chưa rõ.

### Ví dụ

~~~http
POST /payments/pay-901/refund-requests
Idempotency-Key: refund-ord-1024-v1
Content-Type: application/json

{
  "amount": "150000.00",
  "currency": "VND",
  "reason": "CUSTOMER_RETURN"
}
~~~

Lần đầu tạo refund request; nếu response bị mất, retry cùng key không được tạo khoản refund thứ hai. **Một transaction DB nội bộ không tự bảo đảm exactly-once qua network và payment provider.** Cần kết hợp idempotency, transaction, outbox/inbox hoặc cơ chế provider cung cấp, rồi reconciliation khi cần.

Không dùng key cố định chung cho mọi lần refund; nó phải phân biệt các **ý định nghiệp vụ** hợp lệ khác nhau. Retention của key phải tương ứng với cửa sổ retry và rủi ro tác dụng kép.

## 16. Kiểm soát đồng thời và phiên bản trạng thái

Hai consumer có thể cùng thay đổi một Order Draft:

- Thiết bị A đọc version 3.
- Thiết bị B sửa item, tạo version 4.
- Thiết bị A cố SubmitOrder dựa trên version 3.

Nếu không kiểm tra concurrency, A có thể xác nhận nội dung không còn đúng với điều người dùng đã nhìn thấy. Các cách thường dùng:

- **Optimistic locking** trong aggregate và database.
- ETag/If-Match trên HTTP resource khi contract phù hợp.
- expectedVersion trong command có định nghĩa rõ.
- Idempotency key để chống xử lý lặp cùng ý định, **không thay thế** version check.
- Pessimistic lock hoặc serialized command processing khi cần và có thể chịu chi phí.

Ví dụ:

~~~http
POST /orders/ord-1024/submit
If-Match: "3"
Idempotency-Key: 29fc1e7d-e5f1-4a50-9221-51e3e58895b7
~~~

Nếu order hiện là version 4, trả 412 Precondition Failed hoặc conflict theo hợp đồng. Consumer đọc lại đơn và quyết định có tiếp tục không; không tự thay If-Match thành version 4 rồi gửi lại nếu người dùng chưa chấp nhận thay đổi.

## 17. Quyền truy cập gắn với hành vi nghiệp vụ

API cần phân biệt **đã xác thực** và **được thực hiện thao tác**. Quyền hủy đơn có thể phụ thuộc vào:

- Actor là chủ đơn hay nhân viên được phân quyền.
- Tenant, chi nhánh, pháp nhân hoặc phạm vi dữ liệu.
- Trạng thái và tuổi đời đơn.
- Giá trị giao dịch hoặc điều kiện yêu cầu phê duyệt.
- Loại hàng hóa, khu vực và chính sách hoàn tiền.
- Quan hệ giữa actor và resource cụ thể.

Không bảo vệ API chỉ bằng role chung như ROLE_USER rồi cho sửa mọi orderId. Đó là nguy cơ broken object-level authorization.

Kiểm soát ở nhiều lớp:

1. Gateway xác thực token, giới hạn traffic và truyền identity đã xác minh.
2. Service đích kiểm tra authorization cho từng resource và hành vi.
3. Domain/application layer đảm bảo người gọi không vượt qua chính sách trong use case.
4. Truy cập service-to-service có workload identity, scope tối thiểu và secrets được quản lý.
5. Audit ghi actor, hành vi, resource, kết quả và correlation ID, không ghi dữ liệu nhạy cảm quá mức.

**BFF, API gateway và frontend không phải ranh giới tin cậy cho invariant.** Service sở hữu vẫn phải kiểm tra.

## 18. Ranh giới dữ liệu: dữ liệu riêng, hợp đồng công khai

Một dịch vụ sở hữu dữ liệu không có nghĩa tất cả thông tin phải giữ kín và không chia sẻ. Nó có nghĩa quyền **thay đổi có kiểm soát** dữ liệu và quyết định invariants thuộc dịch vụ đó.

Ví dụ:

- Ordering sở hữu Order và lifecycle, công bố GET /orders/{id}, command SubmitOrder và event OrderSubmitted.
- Inventory sở hữu StockReservation, công bố ReserveStock, ReleaseReservation và event StockReservationSucceeded.
- Payment sở hữu Transaction/Refund, công bố AuthorizePayment và PaymentAuthorized/PaymentFailed.

Nếu Reporting cần xem doanh thu/đơn, không nên tự join database nội bộ của ba service. Có thể xây projection từ event hoặc API composition theo nhu cầu đọc.

### Contract DTO khác entity database

Tránh trả một entity ORM nguyên vẹn. Thay đổi cột nội bộ, lazy relationship, transaction boundary hoặc một field mới có thể vô tình trở thành breaking change. Public DTO nên được thiết kế theo consumer needs và ổn định trong vòng đời contract.

Trong event, chỉ công bố dữ liệu cần thiết, có schema/version và bảo vệ thông tin cá nhân. Không biến event thành ảnh chụp toàn bộ bảng để mọi consumer lệ thuộc vào layout dữ liệu của producer.

## 19. Workflow xuyên service và Saga

Một use case có thể cần nhiều service cùng tham gia:

~~~text
SubmitOrder
   |
   v
Ordering creates order PENDING
   |
   v
Inventory reserves stock
   |
   v
Payment authorizes amount
   |
   v
Ordering confirms order
~~~

Nếu Payment thất bại sau khi Inventory đã giữ hàng, Ordering phải yêu cầu release reservation hoặc kích hoạt compensation theo contract. Nếu yêu cầu release cũng lỗi, workflow có thể ở trạng thái COMPENSATION_PENDING và cần retry/reconciliation.

**Saga** là cách tổ chức chuỗi local transactions và các hành động bù trừ, không phải một distributed ACID transaction tự động rollback. Cần phân biệt:

- **Orchestration:** một process manager nắm trạng thái và quyết định bước tiếp theo.
- **Choreography:** service phản ứng với event và cùng hình thành workflow.
- **Compensation:** hành động nghiệp vụ bù trừ tác động trước, không luôn khôi phục được thế giới về y nguyên như ban đầu.
- **Timeout/unknown:** không biết một bước đã thực thi hay chưa; cần tra cứu và reconciliation.
- **Idempotency:** message trùng không tạo side effect trùng.
- **Versioning:** event và command thay đổi theo thời gian nhưng workflow đang chạy vẫn xử lý được.

API của từng service nên biểu diễn hành vi mà service đó sở hữu, còn điều phối nên ở boundary có trách nhiệm với toàn use case. Không xây một God Gateway chứa tất cả logic điều phối và business rules chỉ vì nó đứng trước mọi service.

## 20. Event contract phải mô tả sự thật nghiệp vụ

Một integration event minh họa:

~~~json
{
  "eventId": "evt-8411",
  "eventType": "OrderSubmitted",
  "eventVersion": 1,
  "occurredAt": "2026-11-11T08:00:00Z",
  "aggregateId": "ord-1024",
  "aggregateVersion": 4,
  "correlationId": "req-a615",
  "payload": {
    "orderId": "ord-1024",
    "customerReference": "cust-271",
    "amount": {
      "value": "850000.00",
      "currency": "VND"
    }
  }
}
~~~

Hợp đồng phải quy định:

- Event phát sau khi sự kiện nghiệp vụ thực sự được ghi nhận, thường dùng transactional outbox để tránh DB commit thành công mà message bị mất.
- Consumer có thể nhận trùng, trễ và đôi khi sai thứ tự; cần deduplication, idempotent handler hoặc version/sequence phù hợp.
- Event ID dùng xác định message; correlation ID nối bối cảnh; business operation ID phục vụ đối soát.
- Một event thuộc bounded context; consumer không được giả định có thể trực tiếp chỉnh aggregate gốc.
- Schema event cần quy tắc tiến hóa tương thích, không đổi nghĩa event cũ âm thầm.
- Có chính sách retention, replay, PII và quyền đọc topic/queue.
- Eventual consistency và thời gian trễ dữ liệu phải được thể hiện trong API đọc nếu người dùng có thể thấy dữ liệu chưa đồng bộ.

**Event không thay thế contract.** Chỉ có message broker và tên topic không đủ để biết consumer nên làm gì khi nhận bản cũ, nhận trùng hoặc thiếu message.

## 21. OpenAPI làm hợp đồng có thể kiểm tra

OpenAPI mô tả đường dẫn, phương thức, schema, auth, lỗi và response để client/server/tooling cùng hiểu. Ví dụ rút gọn cho một command được xử lý bất đồng bộ:

~~~yaml
openapi: 3.0.3
info:
  title: Ordering API
  version: 1.0.0
paths:
  /v1/orders/{orderId}/submit:
    post:
      operationId: submitOrder
      summary: Submit a draft order for processing
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
        - name: If-Match
          in: header
          required: true
          schema:
            type: string
      responses:
        '202':
          description: Command accepted for asynchronous processing
          headers:
            Location:
              description: Status resource for this operation
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OperationAccepted'
        '409':
          description: Invalid business state or idempotency conflict
        '412':
          description: Order version precondition failed
        '422':
          description: Business input rejected
        '401':
          description: Authentication required
        '403':
          description: Action forbidden
components:
  schemas:
    OperationAccepted:
      type: object
      required: [operationId, orderId, status, statusUrl]
      properties:
        operationId:
          type: string
        orderId:
          type: string
        status:
          type: string
          enum: [PENDING]
        statusUrl:
          type: string
~~~

Ví dụ OpenAPI này cố ý chỉ minh họa một operation; trong hệ thống thật phải bổ sung request schema nếu có body, auth schemes, error representations, security requirements, 404/429/5xx và mô tả đầy đủ workflow. Đặc biệt phải định nghĩa **các bảo đảm nghiệp vụ** bằng mô tả operation và tài liệu kiến trúc, không kỳ vọng schema type tự chuyển tải mọi quy tắc.

### Contract-first hữu ích ở đâu?

Thiết kế contract trước hoặc cùng implementation giúp:

- Product, engineering và consumer xác nhận ý nghĩa thao tác.
- Tránh để lộ schema nội bộ do framework tự serialize.
- Mock client và thử tích hợp trước khi backend hoàn chỉnh.
- Sinh tài liệu và kiểm tra schema drift.
- Review breaking change như một thay đổi có tác động consumer.

Contract-first không có nghĩa mọi endpoint phải được chốt vĩnh viễn trước khi hiểu domain. Đặc tả vẫn cần tiến hóa từ use case và bằng chứng vận hành.

## 22. Ví dụ Java/Spring Boot: Controller mỏng, use case sở hữu hành vi

Một cách phân lớp trong service Ordering:

~~~text
HTTP Controller
    |
    v
Application Use Case (SubmitOrder)
    |
    v
Domain Model / Aggregate (Order)
    |
    +--> Repository interface
    +--> Outbox/Event publisher interface
    +--> External capability ports
~~~

Controller giải mã HTTP, nhận identity, idempotency key, version và chuyển thành command. Application use case quản lý transaction, điều phối local operations và gọi domain. Aggregate kiểm tra invariants. Adapter thực hiện persistence và integration.

Ví dụ minh họa cấu trúc (lược bỏ các loại domain, exception mapping và cấu hình bảo mật):

~~~java
@RestController
@RequestMapping("/v1/orders")
final class OrderController {
    private final SubmitOrderUseCase submitOrderUseCase;

    OrderController(SubmitOrderUseCase submitOrderUseCase) {
        this.submitOrderUseCase = submitOrderUseCase;
    }

    @PostMapping("/{orderId}/submit")
    ResponseEntity<OperationAccepted> submit(
            @PathVariable String orderId,
            @RequestHeader("Idempotency-Key") String key,
            @RequestHeader("If-Match") String expectedVersion,
            Principal principal) {

        SubmitOrderCommand command = new SubmitOrderCommand(
                orderId,
                principal.getName(),
                key,
                expectedVersion
        );

        OperationAccepted accepted = submitOrderUseCase.execute(command);

        return ResponseEntity
                .accepted()
                .location(URI.create(accepted.statusUrl()))
                .body(accepted);
    }
}
~~~

Các type cần có trong service, ví dụ:

~~~java
record SubmitOrderCommand(
        String orderId,
        String actorId,
        String idempotencyKey,
        String expectedVersion
) {}

record OperationAccepted(
        String operationId,
        String orderId,
        String status,
        String statusUrl
) {}

interface SubmitOrderUseCase {
    OperationAccepted execute(SubmitOrderCommand command);
}
~~~

Cốt lõi không nằm ở annotation của Spring:

- Use case kiểm tra identity/authorization theo resource và business rules.
- Idempotency record được xử lý an toàn trước concurrent duplicate calls.
- Repository dùng optimistic locking hoặc cơ chế điều phối nhất quán.
- Domain từ chối transition không hợp lệ.
- Transaction lưu state và outbox atomically nếu phát event.
- Bước async có operation state, retry policy, reconciliation và observability.
- Exception handler ánh xạ lỗi có nghĩa sang HTTP đúng contract.

Đừng đặt tất cả điều kiện, gọi sang Payment, thao tác DB và đổi status trực tiếp trong Controller. HTTP adapter cần mỏng để nghiệp vụ có thể được gọi từ REST, consumer event hoặc batch job mà vẫn giữ cùng quy tắc.

## 23. Đặt API theo “hành vi” nhưng tránh endpoint cho từng nút bấm

Một sai lầm ngược lại là tạo một endpoint cho mỗi nút trên UI: /clickPay, /onBlueButton, /doCheckoutFromMobile. UI thay đổi liên tục và nhiều client có thể có trải nghiệm khác nhau.

Hành vi nghiệp vụ phải là **ngữ nghĩa ổn định**, không phụ thuộc bố cục giao diện. Ví dụ:

- “Gửi yêu cầu thanh toán” có thể xuất phát từ web, mobile hoặc back-office.
- “Hủy đơn” có rule dựa trên order lifecycle, không dựa trên màn hình nào mở.
- “Tạo shipment” là capability Fulfillment, không phải “nút In phiếu” của giao diện quản trị.

Khi các client cần biểu diễn dữ liệu khác nhau, có thể dùng BFF/projection để tối ưu read response. Dù vậy command cốt lõi nên được xác định theo business intent, có contract thống nhất và được service owner kiểm soát.

## 24. Tách read API theo nhu cầu nhưng không xóa ownership

Read request thường quan tâm trải nghiệm tổng hợp: trang đơn hàng muốn hiển thị item, giá, trạng thái thanh toán, vận chuyển. Có vài cách:

| Phương án | Khi phù hợp | Đổi lại |
|---|---|---|
| API composition đồng bộ | Số dependency nhỏ, latency đủ, dữ liệu cần mới | Fan-out, timeout và lỗi dây chuyền |
| BFF | UI clients khác nhau cần representation khác nhau | Thêm lớp mapping và vận hành |
| CQRS read model | Query phức tạp, tải đọc lớn, chấp nhận trễ | Event lag, replay, monitoring |
| Cache/snapshot | Dữ liệu ít đổi hoặc có policy freshness | Invalidation, stale information |
| Đặt dữ liệu cùng boundary | Bất biến và lifecycle gắn chặt | Service lớn hơn nhưng bớt distributed transaction |

Không nên để consumer làm N+1 calls qua service chỉ để dựng một màn hình. Nhưng cũng không nên hợp nhất mọi dữ liệu vào một API khổng lồ vô chủ. Cần xác định consumer, freshness, nguồn sở hữu và cách duy trì projection.

Với query dùng event-driven projection, response có thể ghi updatedAt hoặc dataVersion để consumer hiểu dữ liệu đang trễ. Không để UI tưởng toàn bộ dữ liệu đều cập nhật tức thời nếu backend là eventually consistent.

## 25. Chiến lược phiên bản và tương thích

Một API sẽ tiến hóa. Khả năng thay đổi độc lập là lợi ích quan trọng của Microservices, nhưng chỉ đạt được khi provider và consumer có quy tắc tương thích.

### Thay đổi thường tương thích hơn

- Thêm field response có tính tùy chọn và consumer chịu được field lạ.
- Thêm endpoint/query mới.
- Nới một số ràng buộc request khi vẫn giữ semantics cũ.
- Cải tiến implementation, dữ liệu nội bộ mà không đổi contract.

### Thay đổi có nguy cơ phá consumer

- Đổi tên/xóa field hiện được dùng.
- Đổi kiểu dữ liệu, unit, precision hoặc nghĩa nghiệp vụ.
- Thêm giá trị enum mà consumer đang xử lý kiểu exhaustive không có fallback.
- Đổi thời điểm thành công từ “đã hoàn tất” sang “đã nhận yêu cầu” mà không có phiên bản/contract mới.
- Đổi từ lỗi 409 sang 200 khi state conflict nhưng client dựa vào mã lỗi.
- Bắt field request mới không có mặc định hoặc gỡ phiên bản cũ quá sớm.
- Đổi semantics idempotency, retry hoặc ordering của event.

### Cách tiến hóa an toàn

1. Công bố contract và bảng consumer đang sử dụng.
2. Thêm schema/field/endpoint mới, duy trì nghĩa cũ trong giai đoạn chuyển.
3. Với event, công bố phiên bản/compatibility policy và cách consumer xử lý unknown fields.
4. Dùng contract tests và canary để xác minh người gọi vẫn hoạt động.
5. Thu telemetry về mức sử dụng phiên bản cũ.
6. Công bố chính sách deprecation/sunset và thời gian di chuyển.
7. Gỡ hợp đồng cũ sau khi không còn consumer cần nó và đã có bằng chứng.

URL /v1 không tự bảo đảm tương thích. Những thay đổi có ý nghĩa lớn cần phiên bản rõ, nhưng nhiều thay đổi có thể thực hiện theo hướng additive. Hãy ưu tiên ổn định semantics và có giao ước tiến hóa, thay vì tạo phiên bản mỗi lần thêm field.

## 26. Contract testing và kiểm thử hành vi

Unit test Controller với HTTP 200 chưa đủ để xác nhận API theo trách nhiệm nghiệp vụ. Các mức kiểm thử:

| Loại test | Điều phải chứng minh |
|---|---|
| Domain test | Invariant và state transitions đúng |
| Application use-case test | Quyền, idempotency, transaction và event đúng |
| HTTP API test | Method, status, schema, headers và error mapping |
| Consumer-driven contract test | Provider đáp ứng kỳ vọng thực của consumer |
| Integration test | DB, broker, auth và upstream adapters tương tác đúng |
| Workflow/Saga test | Thành công, lỗi từng bước, compensation và retry |
| Concurrency test | Hai command song song không phá invariant |
| Resilience test | Timeout, lost response, duplicate event, queue lag |
| Security test | Resource authorization, tenant isolation, secret exposure |
| Observability test | Mã lỗi, trace, metrics và operation IDs có thể điều tra |

Ví dụ cho SubmitOrder:

- DRAFT hợp lệ → tạo đúng một operation và state transition mong muốn.
- DRAFT thiếu item → lỗi theo contract, không phát OrderSubmitted.
- CANCELLED → 409, không thay đổi dữ liệu.
- Key trùng + payload giống → trả cùng operation, không tạo side effect mới.
- Key trùng + payload khác → conflict.
- Version cũ → 412/409 theo định nghĩa, không xác nhận nhầm snapshot.
- Inventory timeout sau khi reserve thành công → có tra cứu và bù trừ/đối soát.
- Payment event nhận hai lần → không xác nhận đơn hai lần.
- Người dùng tenant khác → không truy cập hoặc sửa được đơn.
- Consumer phiên bản cũ → không hỏng khi response thêm field.

Chỉ kiểm thử happy path thường bỏ sót chính các điều kiện làm Microservices khó vận hành.

## 27. Đo lường API bằng hành vi, không chỉ HTTP throughput

Metrics hệ thống như request count, p95, p99 và tỷ lệ 5xx là cần thiết, nhưng không nói hết mức đúng đắn nghiệp vụ. API command nên có thêm signal:

- Số SubmitOrder được chấp nhận, thành công, bị từ chối do rule và thất bại kỹ thuật.
- Thời gian từ accepted đến confirmed/rejected.
- Tỷ lệ idempotency replay, conflict key và retry.
- Số operation PENDING quá lâu, compensation chờ xử lý.
- Tỷ lệ payment unknown outcome, số case reconciliation, thời gian đóng case.
- Tỷ lệ cancel bị từ chối vì trạng thái không hợp lệ.
- Event publish lag, consumer lag và dead-letter volume.
- Số contract violations/breaking changes.
- Phân phối lỗi theo tenant/operation **với kiểm soát cardinality và dữ liệu riêng tư**.
- Tỷ lệ consumer còn dùng phiên bản deprecated.

Một SLO hữu ích có thể là “99,9% SubmitOrder hợp lệ được nhận bền vững” và một SLO khác là “99% workflow được xác nhận hoặc từ chối rõ ràng trong 10 giây”. Không gộp accepted latency và business completion latency thành cùng một con số.

**Trace ID** giúp điều tra đường đi kỹ thuật; **operation ID** và **domain object ID** giúp truy tìm kết quả nghiệp vụ. Nên ghi cả ba khi phù hợp, tránh dùng thông tin cá nhân làm nhãn metric độ phân giải cao.

## 28. Phân quyền thay đổi giữa các nhóm

Trong tổ chức có nhiều nhóm:

- Service team sở hữu domain rules, API contract, schema nội bộ và vận hành.
- Consumer team có thể đề xuất contract hoặc nêu nhu cầu, nhưng không tự sửa DB của provider.
- Platform team cung cấp chuẩn chung cho auth, tracing, deployment, rate limit, SDK hoặc schema registry.
- Architecture review tập trung vào thay đổi xuyên boundary, breaking changes và rủi ro lớn; tránh trở thành nút thắt cho mọi field.
- Product owner quyết định semantics của workflow, partial success và chính sách xử lý lỗi có tác động người dùng.

Các thông tin nên có trong service catalog: trách nhiệm, owner/on-call, upstream/downstream, API/event contracts, version, SLO, security scope, deprecation policy và tài liệu sự cố.

Một tiêu chuẩn chung nên quy định các khía cạnh liên dịch vụ như error shape, correlation ID, authorization, retry semantics, idempotency và versioning. Bên trong boundary, nhóm có quyền chọn implementation miễn giữ đúng contract.

## 29. So sánh thiết kế dựa trên bảng với thiết kế dựa trên hành vi

| Vấn đề | Thiết kế dễ gây coupling | Thiết kế gắn trách nhiệm |
|---|---|---|
| Xác nhận đơn | PATCH status=CONFIRMED bất kỳ | SubmitOrder, domain kiểm tra rule và state |
| Giữ hàng | Client sửa quantity DB | Inventory ReserveStock có contract |
| Thanh toán | Ordering ghi paymentSuccess=true | Payment AuthorizePayment và xác nhận outcome |
| Hủy đơn | DELETE /orders/{id} để “hủy” | CancelOrder với state, refund, audit |
| Query màn hình | UI gọi từng service để lấy từng field | BFF/read projection theo use case |
| Lỗi | HTTP 200 và chuỗi text tùy ý | Mã lỗi ổn định, status đúng nghĩa |
| Retry | Retry mọi POST sau timeout | Idempotency key, deadline và reconciliation |
| Phân quyền | Chỉ kiểm tra role ở gateway | Service kiểm tra actor + resource + action |
| Schema | Serialize nguyên entity ORM | Public DTO độc lập storage |
| Event | “UpdateOrderNow” qua queue | OrderSubmitted/OrderCancelled là fact |
| Thay đổi | Sửa DB chung, deploy đồng bộ | Contract versioning, migration và test consumer |

Thiết kế theo hành vi không có nghĩa tối đa số operation. Nó làm rõ **ý định, quyền và kết quả** để phần implementation có thể thay đổi mà consumer không cần hiểu logic nội bộ.

## 30. Anti-pattern cần nhận diện

### 30.1. Anemic CRUD services

Service chỉ wrap database, mọi business rule nằm ở API gateway hoặc client. Hậu quả: khó bảo vệ invariants, nhiều network calls và thay đổi liên nhóm liên tục.

**Hướng xử lý:** gom trách nhiệm theo capability, đặt command/use case ở service owner, cho server quyết định state transition.

### 30.2. Shared database và shared writes

Hai service cùng sửa bảng Order/Payment vì “tiện join”. Hậu quả: quyền sở hữu không rõ và schema migration buộc deploy cùng lúc.

**Hướng xử lý:** xác định owner cho từng dữ liệu, chia sẻ qua API/event/projection, di chuyển dần quyền ghi theo kế hoạch an toàn.

### 30.3. God Gateway hoặc orchestration vô chủ

Gateway biết mọi điều kiện nghiệp vụ của Order, Payment, Shipping. Mỗi sửa đổi domain đều phải sửa một nơi chung.

**Hướng xử lý:** đưa invariant về service có trách nhiệm, đặt orchestration vào process manager/owner của use case, giữ gateway ở vai trò hạ tầng.

### 30.4. Chatty APIs

Một màn hình hoặc command đòi hàng chục RPC để lấy field, gây fan-out, tail latency và dependency chain dài.

**Hướng xử lý:** thiết kế projection/read model, chọn granularity theo use case, batch dữ liệu hoặc chuyển async khi contract cho phép.

### 30.5. API trực tiếp lộ ORM/database

Consumer phụ thuộc vào tên cột, quan hệ lazy load hoặc schema SQL nội bộ.

**Hướng xử lý:** DTO và contract rõ, mapping trong service, versioning độc lập storage.

### 30.6. Fake success trên workflow chưa hoàn tất

API trả 200 “paid” chỉ vì đã publish message, dù provider chưa xử lý.

**Hướng xử lý:** 202/PENDING với operation tracking, công bố riêng completion semantics.

### 30.7. Async không có idempotency

Một event bị nhận trùng làm reserve/capture/refund hai lần.

**Hướng xử lý:** event ID, inbox dedup, stable business key, outbox và reconciliation.

### 30.8. Mơ hồ quyền và khả năng hủy

Client biết ID là hủy được, hoặc DELETE bị dùng cho giao dịch phải lưu audit.

**Hướng xử lý:** resource authorization + domain state machine; CancelOrder hoặc CancellationRequest với semantics rõ.

### 30.9. One endpoint per UI button

Tên operation bám layout frontend, không bám nghiệp vụ.

**Hướng xử lý:** dùng ubiquitous language, business capabilities và API representation phù hợp nhiều client.

### 30.10. Quy ước version chỉ nằm trong đầu một người

Provider thay đổi contract, consumer phát hiện ở production.

**Hướng xử lý:** contract registry, consumer tests, deprecation policy và telemetry mức dùng phiên bản.

## 31. Phương pháp thiết kế API theo hành vi từng bước

### Bước 1 — Thu thập tình huống nghiệp vụ

Phỏng vấn domain expert, product, support và operations. Viết các câu “ai muốn làm gì, trong điều kiện nào, thế nào là thành công”. Có thể dùng Event Storming để xác định commands/events và điểm quyết định.

### Bước 2 — Xác định ranh giới và owner

Lập capability map và bounded context. Ghi service nào có quyền quyết định, sở hữu dữ liệu, ràng buộc transaction và các downstream dependencies. Nếu không rõ owner, chưa nên chốt endpoint.

### Bước 3 — Mô hình hóa state và invariants

Cho mỗi aggregate/use case, vẽ state transition và validation. Phân biệt invariant nội bộ (có thể bảo vệ atomic) với quy trình xuyên service (cần eventual consistency, orchestration, compensation).

### Bước 4 — Viết contract ở mức nghiệp vụ

Dùng mẫu: intent, actor, precondition, request, outcome, errors, idempotency, consistency, latency và security. Đặt tên command, query, event theo ngôn ngữ miền trước khi chọn phương thức vận chuyển.

### Bước 5 — Chọn transport và schema

Chọn HTTP/gRPC/event theo tương tác. Đặt URI/method/status; thiết kế DTO, error codes, pagination, authentication, resource IDs, versioning, correlation IDs.

### Bước 6 — Chốt failure semantics

Nếu timeout, side effect có thể đã xảy ra chưa? Nếu dependency lỗi, có fallback hợp lệ không? Nếu message trùng/sai thứ tự, consumer phải làm gì? Nếu workflow dài, client theo dõi operation thế nào? Đưa các trường hợp này vào contract.

### Bước 7 — Kiểm chứng với consumer

Consumer thử các tình huống tạo, sửa, state conflict, retry, duplicate call, auth và dữ liệu stale. Chạy contract tests, tích hợp theo sandbox hoặc stub. Bảo đảm client có thể xử lý response mà không cần hiểu DB hoặc thuật toán nội bộ.

### Bước 8 — Triển khai và đo

Đưa domain validation vào service owner; deploy với metrics, traces, business outcome metrics, feature flag và migration plan. Theo dõi tỷ lệ lỗi contract, latency, completion SLO và thay đổi consumer. Tái đánh giá khi capability hoặc workflow biến đổi.

## 32. Mẫu API responsibility card

Dùng cho mỗi behavior quan trọng:

~~~text
Service: Ordering
Owner: Order domain team
Capability: Order lifecycle management
Operation: SubmitOrder
Actor: Customer / authorized staff
Business intent: Start order confirmation workflow
Endpoint: POST /v1/orders/{orderId}/submit
Preconditions:
  - Actor may submit this order
  - Order is DRAFT
  - Items and delivery choices are valid
  - Version/precondition matches
Inputs:
  - orderId
  - delivery option (when needed)
  - idempotency key
  - expected version
Immediate outcome:
  - 202 PENDING with operationId, or a documented final result
Final outcomes:
  - CONFIRMED
  - REJECTED
  - REQUIRES_RECONCILIATION
Errors:
  - Not found / forbidden
  - Invalid state / stale version
  - Invalid business input
  - Dependency temporary failure
Consistency:
  - Local state atomic
  - Cross-service steps eventually consistent
Idempotency:
  - Replay same intent does not create duplicate side effects
Events:
  - OrderSubmitted
  - OrderConfirmed / OrderRejected
Observability:
  - requestId, operationId, orderId
  - accepted rate, completion time, business outcome
Versioning:
  - additive contract evolution, consumer tests
~~~

Card này có thể đi kèm OpenAPI và ADR. Nó tránh trường hợp một API trông hợp lệ về HTTP nhưng không nêu rõ lời hứa nghiệp vụ.

## 33. Bài tập: sửa thiết kế sai

Một đội thiết kế các endpoint sau:

~~~http
GET   /order-service/getOrderRow?id=123
POST  /order-service/setStatus
POST  /payment-service/updatePaymentFlag
POST  /inventory-service/updateQuantity
GET   /gateway/checkoutAndChangeEverything
~~~

Frontend gọi updateQuantity để giảm tồn, updatePaymentFlag để đánh dấu thanh toán, rồi setStatus CONFIRMED. Nếu call thứ ba lỗi, trạng thái bị lệch.

**Yêu cầu:** đề xuất ranh giới và contract an toàn hơn.

### Gợi ý phương án

**Bước A — xác định owner:** Inventory quản lý reservation, Payment quản lý authorization/capture và Ordering quản lý trạng thái đơn. Không cho frontend chỉnh trực tiếp trạng thái hoặc quantity thuộc domain khác.

**Bước B — command theo hành vi:** frontend chỉ yêu cầu Ordering SubmitOrder. Ordering tạo operation và phối hợp ReserveStock/AuthorizePayment qua hợp đồng của các owner.

**Bước C — workflow:** nếu Payment lỗi, Ordering yêu cầu release reservation hoặc đặt trạng thái cần đối soát. Dùng idempotency key và outbox/inbox ở nơi cần. Không giả định network call thành công tuyệt đối.

**Bước D — trải nghiệm:** frontend nhận 202 PENDING và theo dõi operation, hoặc nhận kết quả cuối nếu hệ thống có thể bảo đảm trong deadline. Không hiển thị “đã thanh toán” khi còn UNKNOWN.

**Bước E — đọc dữ liệu:** GET /orders/{id} trả state có nghĩa; nếu cần tổng hợp thông tin từ Payment/Shipment có thể dùng projection được thiết kế cho trang đơn.

**Bước F — kiểm thử:** hai lần SubmitOrder trùng, timeout provider sau side effect, xung đột phiên bản, actor tenant khác và compensation thất bại.

Câu hỏi mở để tự trao đổi: trong trường hợp nghiệp vụ yêu cầu Payment và Order phải commit atomically dưới 100 ms, có nên tách chúng thành hai database/service không? Hãy kiểm chứng lại consistency requirement, domain boundary và chi phí distributed coordination trước khi quyết định.

## 34. Checklist trước khi phê duyệt API mới

### Ranh giới và hành vi

- [ ] Operation thể hiện ý định của actor bằng ngôn ngữ nghiệp vụ.
- [ ] Đã xác định owner có quyền quyết định kết quả.
- [ ] Các invariants được kiểm tra tại service/aggregate phù hợp.
- [ ] Public contract không phơi bày entity ORM và schema nội bộ.
- [ ] Không yêu cầu consumer tự thao tác trạng thái hoặc DB của service khác.
- [ ] Đã xem xét granularity để tránh chatty calls và God service.
- [ ] State machine định nghĩa command hợp lệ và bất hợp lệ.

### Contract và dữ liệu

- [ ] HTTP method/URI/status đúng semantics.
- [ ] Request chỉ chứa input mà actor có quyền cung cấp.
- [ ] Response phân biệt accepted, completed, rejected và unknown.
- [ ] Có error codes ổn định cho rule conflict, quyền và lỗi tạm thời.
- [ ] Có version/concurrency precondition khi cần.
- [ ] Idempotency rõ cho command có side effect.
- [ ] Money, time, ID, enum, optional/null và pagination được định nghĩa.
- [ ] API/event schema có quy tắc tiến hóa và deprecation.

### Phân tán và bảo mật

- [ ] Dependency sync/async được lựa chọn theo contract.
- [ ] Retry, deadline, timeout và cancellation không tạo side effect trùng.
- [ ] Workflow xuyên service có trạng thái, compensation và reconciliation.
- [ ] Event xử lý duplicate, lag, ordering, replay và version.
- [ ] Resource-level authorization và tenant isolation được kiểm tra.
- [ ] Service-to-service identity, secret handling và audit phù hợp.

### Vận hành và người sử dụng

- [ ] Có OpenAPI/event contract dễ truy cập.
- [ ] Có contract tests và test các state transition quan trọng.
- [ ] Có metrics cho outcome nghiệp vụ ngoài HTTP 2xx/5xx.
- [ ] Có correlation ID, operation ID và runbook cho trạng thái chưa rõ.
- [ ] Consumer hiểu polling/callback, partial result và retry semantics.
- [ ] Owner chịu trách nhiệm triển khai, sự cố và phiên bản.

## 35. Ghi nhớ

Thiết kế API theo hành vi và trách nhiệm nghiệp vụ là **thiết kế hợp đồng về năng lực và kết quả**, không chỉ đặt tên endpoint. Bắt đầu bằng use case, bounded context, owner và invariants; để service sở hữu quyết định trạng thái, công bố commands/queries/events phù hợp và che giấu dữ liệu nội bộ.

Một API tốt giúp consumer hiểu **cần yêu cầu điều gì, khi nào thao tác được phép, kết quả nào đã chắc chắn xảy ra, và phải làm gì khi lỗi hoặc timeout**. Đó là nền tảng để các nhóm thay đổi và triển khai độc lập mà vẫn giữ tính đúng đắn, khả năng quan sát và độ tin cậy của toàn hệ thống.
