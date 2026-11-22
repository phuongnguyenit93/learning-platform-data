# Nhóm dữ liệu cùng thay đổi và khái niệm aggregate

Trong thiết kế NoSQL, việc xác định **dữ liệu nào nên nằm cùng nhau** ảnh hưởng trực tiếp đến cách truy vấn, cập nhật, kiểm soát cạnh tranh và phân phối tải. Ta thường nghe lời khuyên “đặt dữ liệu thường đọc cùng nhau vào một document”. Điều đó có ích, nhưng còn một câu hỏi quan trọng hơn: **những dữ liệu nào phải thay đổi như một đơn vị để bất biến nghiệp vụ luôn đúng?**

Ví dụ, một đơn hàng gồm các dòng hàng, tổng tiền và trạng thái. Khi đổi số lượng của một dòng, tổng tiền phải được tính lại. Nếu chỉ lưu dòng hàng thành công mà cập nhật tổng tiền thất bại, đơn hàng trở nên mâu thuẫn. Trong khi đó, tồn kho của sản phẩm được rất nhiều đơn hàng cùng sử dụng; nhúng một bản sao tồn kho vào từng đơn không giúp ngăn bán vượt tồn.

Khái niệm **aggregate** trong Domain-Driven Design (DDD) giúp xác định những ranh giới như vậy. Aggregate là **nhóm đối tượng thuộc miền nghiệp vụ được quản lý như một đơn vị nhất quán**. Một **aggregate root** chịu trách nhiệm cho phép hoặc từ chối những thay đổi có thể ảnh hưởng đến các quy tắc nội bộ.

Trong NoSQL, ranh giới aggregate có liên hệ chặt với document, item, partition, transaction và atomic update. Tuy nhiên, aggregate là **khái niệm nghiệp vụ**, không phải tên gọi khác của một document. Bài học này trình bày cách nhóm dữ liệu cần thay đổi cùng nhau, cách chọn ranh giới hợp lý và cách xử lý một nghiệp vụ đi qua nhiều aggregate.

## 1. Bất biến nghiệp vụ là điểm xuất phát

**Bất biến (invariant)** là điều kiện phải đúng ở một thời điểm mà nghiệp vụ quy định. Hãy xét Order:

~~~text
Order
├── orderId
├── status
├── currency
├── total
├── version
└── items[]
    ├── sku
    ├── quantity
    └── unitPriceAtPurchase
~~~

Một số bất biến có thể là:

1. Mỗi OrderItem có số lượng dương.
2. Tổng tiền bằng tổng thành tiền của các dòng hàng sau quy tắc chiết khấu, thuế và làm tròn.
3. Đơn chỉ chuyển qua các trạng thái hợp lệ.
4. Đơn đã xác nhận không được thay đổi tùy tiện những giá trị đã chốt.
5. Một cập nhật thành công làm trạng thái và version nhất quán với nhau.

Để bảo vệ chúng, một thao tác AddItem không nên thêm item ở một nơi rồi hy vọng một job khác sẽ tính lại total sau đó nếu ứng dụng đã cam kết rằng đơn luôn có tổng tiền đúng ngay sau khi ghi.

### 1.1. Đúng ngay khi commit và đúng sau một quy trình

Không phải mọi sự liên hệ đều đòi hỏi transaction tức thời. Có thể phân loại:

| Quy tắc | Phạm vi | Thời điểm cần đúng |
|---|---|---|
| Total khớp items | Order aggregate | Ngay khi cập nhật Order được commit |
| Trạng thái Order hợp lệ | Order aggregate | Ngay khi commit |
| Không giữ quá tồn một SKU | Inventory aggregate | Khi chấp nhận reservation |
| Đơn mới hiện trong lịch sử khách | Read model OrdersByCustomer | Có thể trễ theo SLA sản phẩm |
| Báo cáo doanh thu cuối ngày | Projection phân tích | Theo lịch xử lý và đối soát |
| Email xác nhận đến khách | Workflow ngoài database | Theo cơ chế retry và theo dõi |

**Bất biến khi ghi** khác với **độ mới của dữ liệu khi đọc**. Cho phép một read model trễ vài giây không có nghĩa cho phép hệ thống bán vượt tồn trong vài giây.

### 1.2. Ranh giới của một quy tắc

Đơn giá đã chốt, số lượng và tổng tiền thuộc Order. Số tồn khả dụng của SKU được nhiều đơn cùng dùng; vì vậy nguồn quyết định số tồn nên thuộc Inventory. Dữ liệu thường được **đọc cùng nhau** chưa chắc thuộc cùng nơi **được thay đổi cùng nhau**.

## 2. Aggregate, root, entity và value object

Trong DDD, một aggregate thường gồm:

- **Aggregate root:** entity đầu mối điều phối các thay đổi và kiểm tra bất biến.
- **Entity con:** có danh tính trong ranh giới aggregate nhưng không được sửa bỏ qua root.
- **Value object:** biểu diễn một giá trị, ví dụ Money(amount, currency), ShippingAddress snapshot.

Một Order aggregate:

~~~text
Order Aggregate
├── Order (aggregate root)
│   ├── status
│   ├── total
│   └── version
├── OrderItem I-1 (entity con)
├── OrderItem I-2 (entity con)
└── ShippingAddress (value object)
~~~

Các command nên được biểu diễn thành ý định nghiệp vụ:

~~~text
Order.addItem(sku, quantity, capturedUnitPrice)
Order.changeQuantity(itemId, quantity)
Order.applyCoupon(coupon)
Order.confirm()
Order.cancel(reason)
~~~

Mã giả:

~~~text
Order.changeQuantity(itemId, newQuantity):
    require status == DRAFT
    require newQuantity > 0
    require itemId exists in this Order

    items[itemId].quantity = newQuantity
    total = calculateTotal(items, discount, tax)
    version = version + 1
~~~

Root giữ ý nghĩa thay đổi. Kho lưu trữ phải bảo vệ lần ghi trước race condition. Một hàm domain đúng nhưng được lưu bằng nhiều lệnh không nguyên tử vẫn có thể tạo trạng thái sai.

### 2.1. Aggregate không đồng nghĩa document

| Khái niệm | Vai trò |
|---|---|
| **Aggregate** | Ranh giới nhất quán của một nhóm quy tắc nghiệp vụ |
| **Aggregate root** | Điểm điều phối thay đổi hợp lệ |
| **Document/item** | Một đơn vị lưu trữ vật lý |
| **Collection/table** | Tập các bản ghi có cùng cách tổ chức |
| **Partition** | Dữ liệu được nhóm/phân phối bởi khóa |
| **Transaction** | Phạm vi thay đổi được commit nguyên tử theo hệ quản trị |

Một collection Orders có thể chứa hàng triệu Order aggregate. Một aggregate có thể được lưu trong một document, nhưng đó là lựa chọn ánh xạ vật lý. Một số NoSQL hỗ trợ transaction nhiều document; một số tập trung vào atomic update một item/partition. Khi cần transaction nhiều mục, phải xác minh giới hạn và mức cách ly của sản phẩm cụ thể.

### 2.2. Có ID không có nghĩa là aggregate riêng

OrderItem có itemId để sửa hoặc xóa riêng một dòng nhưng vẫn có thể thuộc Order aggregate, vì total và trạng thái của Order phải được bảo vệ cùng thay đổi đó. Inventory theo SKU có quyền cập nhật độc lập và được rất nhiều Order tham chiếu; đó là dấu hiệu mạnh hơn để tách aggregate.

## 3. Tìm ranh giới từ các thao tác thực tế

Chỉ nhìn quan hệ trong sơ đồ entity chưa đủ. Hãy lập ma trận **command × dữ liệu**:

| Command | Order | OrderItem | Inventory | Product | Customer |
|---|---|---|---|---|---|
| AddItem | Total, version | Thêm item | Không | Không | Không |
| ChangeQuantity | Total, version | Sửa quantity | Không | Không | Không |
| ConfirmOrder | Status, version | Thường giữ nguyên | Cần reservation hợp lệ | Không | Không |
| ReserveStock | Theo dõi kết quả | Không | Available, reservation | Không | Không |
| ChangeProductPrice | Không | Không | Không | Sửa catalog | Không |
| ChangeCustomerName | Không | Không | Không | Không | Sửa profile |

Từ ma trận:

- Order và OrderItem thường thay đổi qua cùng root.
- Inventory có writer và bất biến riêng.
- Product catalog và Customer profile có vòng đời độc lập.
- Order có thể tham chiếu SKU và Customer mà không cần nhúng toàn bộ dữ liệu hiện hành của chúng.

### 3.1. Những câu hỏi để quyết định

1. Một command phải thay đổi những phần dữ liệu nào để kết quả hợp lệ?
2. Nếu chỉ một phần được commit, invariant nào bị phá?
3. Các phần có vòng đời tạo, sửa, xóa giống nhau không?
4. Có writer độc lập nào thường xuyên cập nhật từng phần không?
5. Danh sách phần tử có giới hạn về số lượng và kích thước không?
6. Những truy vấn nào cần đọc tất cả, những truy vấn nào chỉ đọc từng phần?
7. Một aggregate có khả năng trở thành hot key không?
8. Ranh giới transaction của database có đáp ứng được invariant không?

### 3.2. Quan hệ một-nhiều không quyết định cách nhóm

~~~text
Order    1 ---- N OrderItem
Customer 1 ---- N Order
Post     1 ---- N Comment
Room     1 ---- N Message
~~~

OrderItem có thể có biên trên và được đọc cùng Order. Orders, Comments và Messages thường tăng không giới hạn theo thời gian, có nhiều writer và nhu cầu phân trang/retention riêng. Nhúng tất cả vào một document cha chỉ vì quan hệ một-nhiều có thể làm document lớn và nóng.

## 4. Ánh xạ Order aggregate vào document

Một cách lưu trong document database:

~~~json
{
  "tenantId": "T-1",
  "orderId": "O-1042",
  "customerId": "C-21",
  "status": "DRAFT",
  "version": 5,
  "currency": "VND",
  "items": [
    {
      "itemId": "I-1",
      "sku": "SKU-A",
      "quantity": 2,
      "unitPriceAtPurchase": 150000
    },
    {
      "itemId": "I-2",
      "sku": "SKU-B",
      "quantity": 1,
      "unitPriceAtPurchase": 230000
    }
  ],
  "total": 530000
}
~~~

Lưu Order cùng các items trong một document có thể giúp đọc chi tiết trong một truy vấn và cập nhật các trường liên quan bằng một thao tác nguyên tử nếu hệ hỗ trợ. Điều này phù hợp khi items có giới hạn, ít writer độc lập cùng sửa và các thay đổi chủ yếu đi qua Order root.

### 4.1. Reference, snapshot và projection khác nhau

Document lưu **customerId** và **sku** như tham chiếu. Nhưng **unitPriceAtPurchase** là giá đã chốt tại lúc mua; thay đổi giá Product sau này không được tự sửa tổng tiền lịch sử của Order.

- **Reference:** ID đến aggregate có thẩm quyền hiện tại.
- **Snapshot:** giá trị cần giữ cố định cho sự kiện nghiệp vụ đã xảy ra.
- **Projection:** bản sao dữ liệu để phục vụ một đường đọc, có cơ chế đồng bộ và có thể trễ.

Lẫn ba khái niệm này thường dẫn đến việc đồng bộ quá nhiều bản sao hoặc làm thay đổi lịch sử không đúng.

### 4.2. Vì sao không nhúng mọi Order vào Customer?

~~~json
{
  "customerId": "C-21",
  "orders": [
    {"orderId": "O-1", "total": 100000},
    {"orderId": "O-2", "total": 200000}
  ]
}
~~~

Mảng Orders của Customer có thể tăng qua nhiều năm, trong khi mỗi Order có vòng đời riêng. Một document Customer khổng lồ có thể chạm giới hạn kích thước, trở thành điểm ghi nóng, khó phân trang và khó đổi trạng thái của từng đơn.

Nên lưu mỗi Order riêng rồi dùng index hoặc read model **OrdersByCustomer** theo customerId và createdAt. Nếu profile chỉ cần ba đơn gần nhất, có thể giữ một preview giới hạn với quy tắc đồng bộ và khôi phục rõ ràng.

### 4.3. Một aggregate vẫn có thể nằm trên nhiều document

Nếu một ranh giới nghiệp vụ cần nhiều bản ghi, có thể dùng transaction đa mục khi sản phẩm hỗ trợ mức bảo đảm cần thiết. Nhưng phải xem phạm vi, isolation, số mục, kích thước, độ trễ và retry. Không nên tự suy từ nhãn NoSQL rằng transaction không tồn tại, hoặc suy từ tính năng transaction rằng mọi workflow đa hệ đều commit nguyên tử.

## 5. Cập nhật đồng thời: atomicity chưa đủ để chống mất cập nhật

Giả sử hai người cùng mở Order version 5:

~~~text
Writer A đọc Order v5 và thêm SKU-C.
Writer B đọc Order v5 và đổi quantity SKU-A.
Writer A ghi Order v6.
Writer B ghi toàn document dựa trên v5.
~~~

Nếu không có kiểm tra cạnh tranh, B có thể ghi đè thay đổi của A. Đây là **lost update**.

### 5.1. Optimistic concurrency bằng version

Một cơ chế:

~~~text
saveOrder(newState, expectedVersion=5):
    UPDATE Order
    SET state = newState, version = 6
    ONLY IF currentVersion == 5
~~~

Đây là mã giả. Điều kiện và cập nhật phải được DB xử lý nguyên tử. Khi A đã thành công thành version 6, B với expectedVersion 5 phải nhận conflict.

B nên đọc trạng thái mới, áp dụng lại **ý định** đổi quantity lên đó, kiểm tra bất biến rồi thử lại theo quy tắc. Không nên ghi đè cả document cũ.

### 5.2. Atomicity khác với isolation

Atomicity ngăn nhìn thấy một thay đổi trong trạng thái nửa hoàn tất thuộc phạm vi được bảo vệ. Concurrency control/isolation quyết định các writer đồng thời có mất cập nhật, write skew hoặc xung đột nào. Một lệnh update nguyên tử trên một document chưa tự bảo đảm mọi loại cạnh tranh nếu nhiều writer ghi state cũ.

### 5.3. Transaction nhiều mục có giá phải trả

Nếu invariant trải qua nhiều document, cần hỏi:

- DB có transaction đúng phạm vi và mức isolation yêu cầu không?
- Transaction có chạm nhiều partition hoặc region không?
- Giới hạn số record, kích thước và thời gian?
- Khi conflict hoặc client timeout, phải retry thế nào?
- Độ trễ p95/p99 có đáp ứng workload không?

Nếu không phù hợp, nên đánh giá lại ranh giới hoặc chuyển một phần workflow thành nhiều bước với invariant cục bộ, thay vì dùng transaction quá lớn.

## 6. Aggregate quá lớn và quá nhỏ

### 6.1. Ranh giới quá lớn

Ví dụ một Tenant aggregate chứa:

~~~text
Tenant
├── Users[]
├── Orders[]
├── Inventory[]
├── Messages[]
└── ActivityEvents[]
~~~

Rủi ro gồm mảng tăng vô hạn, hot document/partition, quá nhiều writer cùng tranh chấp root, khó phân trang/retention và transaction lớn. Dữ liệu thuộc cùng tenant là quan hệ **sở hữu và phân quyền**, không phải bằng chứng chúng phải thay đổi nguyên tử.

### 6.2. Ranh giới quá nhỏ

Nếu total, status và từng OrderItem là các aggregate riêng nhưng phải khớp ngay khi commit, mỗi AddItem cần nhiều transaction hoặc workflow để giữ invariant. Tách quá nhỏ có thể làm tính đúng đắn phụ thuộc vào đồng bộ phức tạp.

### 6.3. Ma trận cân bằng

| Tiêu chí | Nhóm khi… | Tách khi… |
|---|---|---|
| Vòng đời | Cùng tạo/sửa/xóa | Có vòng đời độc lập |
| Bất biến | Phải đúng cùng lần commit | Chỉ liên quan tham khảo |
| Kích thước | Có biên trên đáng tin | Có thể tăng vô hạn |
| Ghi đồng thời | Ít writer chạm root | Nhiều writer độc lập |
| Đọc | Thường lấy cả nhóm | Thường đọc từng phần |
| Transaction | Phù hợp phạm vi và SLA | Quá rộng, chậm hoặc nhiều conflict |
| Retention | Vòng đời dữ liệu gần giống | TTL/archive khác nhau rõ rệt |

Nguyên tắc thực hành: **giữ aggregate nhỏ nhất có thể mà vẫn đủ để bảo vệ những bất biến phải đúng cùng nhau**.

## 7. Case study: Order, Inventory và Payment

Một workflow checkout cần nhiều aggregate:

~~~mermaid
flowchart LR
    C["Customer Aggregate"] -. "customerId" .-> O["Order Aggregate"]
    O -. "reservationId" .-> I["Inventory Aggregate"]
    O -. "paymentId" .-> P["Payment Aggregate"]
    O --> R["OrdersByCustomer projection"]
~~~

### 7.1. Order sở hữu dữ liệu đơn

Order quản lý items, giá đã chốt, total, status, version và điều kiện chuyển trạng thái. Order có thể chứa reservationId/paymentId để biết workflow đang ở đâu, nhưng không tự quyết định toàn bộ tồn kho hoặc trạng thái gateway.

### 7.2. Inventory sở hữu bất biến tồn kho

Inventory theo SKU hoặc SKU + warehouse sở hữu available, reserved và các reservation. Giả sử tồn chỉ còn 5, hai yêu cầu đồng thời muốn giữ 4 và 3. Phải có thao tác có điều kiện được bảo vệ nguyên tử:

~~~text
reserve(sku, quantity, reservationId):
    if reservationId already processed:
        return priorResult

    atomically if available >= quantity:
        available = available - quantity
        record reservationId and quantity
        return RESERVED

    return INSUFFICIENT_STOCK
~~~

Đây là mã giả. Nếu điều kiện trừ tồn và ghi reservation nằm trên hai record khác nhau, cần transaction phù hợp hoặc mô hình khác có bảo đảm tương đương. Chỉ đọc tồn rồi trừ ở ứng dụng không an toàn với concurrency.

### 7.3. Payment có nguồn trạng thái riêng

Payment quản lý khoản đã thu, đã hoàn, paymentId và refundId, cùng trạng thái từ gateway. Một API thanh toán bên ngoài không tự trở thành một phần transaction NoSQL. Cần idempotency, truy vấn trạng thái và đối soát khi request timeout.

### 7.4. Vì sao không gom thành một Checkout aggregate khổng lồ?

Gộp Order, tồn nhiều SKU và giao dịch gateway có thể tạo transaction dài, tranh chấp SKU, timeout và khó phục hồi nếu hệ ngoài thành công nhưng không trả response. Đặt bất biến cục bộ tại root sở hữu rồi điều phối các bước là một thiết kế thường dễ kiểm soát hơn.

## 8. Saga: phối hợp xuyên aggregate

Một workflow có thể:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Tạo đơn
    PENDING --> RESERVING: Bắt đầu giữ kho
    RESERVING --> RESERVED: Giữ đủ SKU
    RESERVING --> CANCELING: Không đủ kho
    RESERVED --> CHARGING: Yêu cầu thanh toán
    CHARGING --> CONFIRMED: Thanh toán thành công
    CHARGING --> CANCELING: Thanh toán lỗi/hết hạn
    CANCELING --> CANCELED: Đã bù trừ reservation
    CONFIRMED --> [*]
    CANCELED --> [*]
~~~

Đây là **saga** ở mức khái niệm: mỗi bước có thể commit độc lập và có hành động bù khi một bước sau thất bại.

### 8.1. Trạng thái trung gian được định nghĩa rõ

Order RESERVING chưa phải đơn hoàn tất. Order CANCELING có thể còn reservation cần release. API và UI phải phản ánh đúng trạng thái, không báo CONFIRMED trước khi các điều kiện đã được kiểm chứng.

### 8.2. Retry và idempotency

Worker có thể nhận ReserveStock hai lần vì timeout. Inventory cần nhận diện reservationId để không trừ hai lần. ReleaseReservation cũng phải idempotent, tránh cộng lại tồn hai lần.

### 8.3. TTL không tự động bù nghiệp vụ

Một reservation record hết TTL có thể không còn được trả về như dữ liệu sống, nhưng TTL **không tự cập nhật Inventory.available, hoàn tiền hoặc chuyển Order thành CANCELED**. Cần workflow timeout, nguồn dữ liệu bền, job đối soát và thao tác release an toàn.

### 8.4. Saga không cho phép phá mọi bất biến

Order có thể đang PENDING và Payment chưa xong, nhưng Inventory vẫn không được giữ vượt tồn trong thao tác reserve. Saga xử lý sự phối hợp nhiều ranh giới; nó không thay thế bảo đảm nguyên tử tại nơi sở hữu bất biến.

## 9. Idempotency, CAS và transactional outbox

Một request tạo đơn có thể commit thành công nhưng response bị mất; client gửi lại:

~~~text
POST /orders
Idempotency-Key: req-7281

Lần 1: tạo Order O-1042, response timeout.
Lần 2: cùng key, trả Order O-1042.
~~~

Ánh xạ giữa **tenantId + idempotencyKey** và kết quả phải được bảo vệ bởi uniqueness, conditional insert hoặc transaction đáng tin cậy. Hai request song song không được cùng vượt qua bước kiểm tra “chưa tồn tại”.

| Cơ chế | Rủi ro được giải quyết |
|---|---|
| Idempotency key | Request lặp tạo hiệu ứng nghiệp vụ lặp |
| Aggregate version/CAS | Nhiều writer ghi đè state cũ |
| Transaction | Nhóm thay đổi cần cùng commit |
| Outbox + consumer idempotent | Commit dữ liệu nhưng mất event, hoặc message được gửi lại |

### 9.1. Transactional outbox

Khi Order được xác nhận và OrdersByCustomer cần cập nhật:

~~~text
Trong cùng transaction tại nguồn:
    UPDATE Order status=CONFIRMED
    INSERT Outbox(OrderConfirmed, eventId)
COMMIT

Publisher:
    đọc Outbox và phát event

Consumer:
    cập nhật OrdersByCustomer idempotently
~~~

Outbox chỉ bảo đảm nếu **Order và Outbox nằm trong phạm vi nguyên tử thực sự của database**. Publisher có thể gửi trùng nếu chết sau publish nhưng trước khi đánh dấu tiến độ, nên consumer vẫn cần idempotency.

## 10. Aggregate và read model phục vụ hai mục tiêu

Một ứng dụng cần:

~~~text
GET /orders/O-1042
GET /customers/C-21/orders?limit=20
GET /orders?status=PENDING
GET /revenue?month=2026-11
~~~

Không nên nhúng mọi Order vào Customer aggregate chỉ để phục vụ trang lịch sử. Có thể giữ:

~~~text
OrdersById:
    key = (tenantId, orderId)
    value = Order Aggregate

OrdersByCustomer:
    partition = (tenantId, customerId, monthBucket)
    sort = (createdAt DESC, orderId)
    value = orderSummary

OrdersByStatus:
    partition = (tenantId, status, timeBucket)
    sort = (updatedAt, orderId)
    value = orderId
~~~

Các index hoặc projection này phục vụ truy vấn đọc. Chúng không nhất thiết được quyền thay đổi Order gốc độc lập.

~~~mermaid
flowchart TD
    CMD["ConfirmOrder command"] --> ROOT["Order Aggregate"]
    ROOT --> SRC[("Authoritative store")]
    SRC --> EVT["Outbox / CDC / event"]
    EVT --> LIST[("OrdersByCustomer")]
    EVT --> STATUS[("OrdersByStatus")]
    Q1["Lịch sử khách"] --> LIST
    Q2["Đơn đang chờ"] --> STATUS
~~~

Đây là một hướng của **CQRS**: command và query có mô hình phù hợp với nhu cầu của chúng. Nó không bắt buộc dùng hai hệ database riêng.

### 10.1. Projection có thể trễ

Nếu Order mới được commit nhưng OrdersByCustomer cập nhật bất đồng bộ, danh sách có thể chưa thấy Order ngay. Đó có thể là projection lag. Nếu người dùng cần đọc lại trạng thái mới nhất, ứng dụng có thể đọc nguồn có thẩm quyền hoặc dùng cơ chế read-your-writes phù hợp.

### 10.2. Chi phí của read model

Mỗi projection tạo thêm dung lượng, index, ghi, lag, retry, migration và đối soát. Chỉ nên tạo khi access pattern đủ quan trọng. Cần ghi rõ nguồn có thẩm quyền, mức trễ cho phép và khả năng rebuild.

## 11. Aggregate, partition key và điểm nóng

Aggregate có ranh giới rõ không tự phân phối tải đều trên các node.

### 11.1. Hot Inventory SKU

Một SKU trong flash sale có thể nhận hàng nghìn yêu cầu giữ hàng mỗi giây. Nếu mọi request chạm cùng Inventory record, nó trở thành hot key.

Các phương án gồm:

- Queue hoặc rate limit theo SKU.
- Conditional update với retry/backoff.
- Cấp trước quota cho các bucket/shard, có cơ chế đảm bảo tổng quota không vượt tồn.
- Hàng chờ mua hoặc giới hạn đỉnh lưu lượng.

Không thể chỉ chia ngẫu nhiên số tồn thành nhiều shard rồi để mỗi shard bán độc lập nếu không có quy tắc bảo vệ tổng số lượng.

### 11.2. Tenant key và aggregate key

Nếu mọi Order của tenant nằm dưới một partition key tenantId, tenant lớn có thể tạo partition rộng và nóng. Dùng khóa kết hợp **tenantId + orderId** hoặc bucket phù hợp có thể phân tán tốt hơn, đổi lại truy vấn toàn tenant cần đường đọc riêng.

Ranh giới Order aggregate không thay đổi chỉ vì ta đổi partition key vật lý.

### 11.3. Tách dữ liệu nhưng vẫn giữ hot counter

Tách Comment thành record riêng giúp Post không chứa mảng tăng mãi. Nhưng nếu mọi bình luận đều cập nhật **Post.commentCount**, một bài rất nổi tiếng vẫn có hot document. Nếu sản phẩm cho phép số đếm trễ, có thể dùng projection hoặc counter phân tán. Nếu bắt buộc chính xác tức thời, cần kiểm chứng cơ chế ghi tương ứng.

### 11.4. Multi-region và xung đột

Nếu hai region cùng sửa một aggregate bằng last-write-wins, một cập nhật hợp lệ có thể bị ghi đè. Với tồn kho hoặc số dư, cần chọn single writer, quota vùng được kiểm soát hoặc giao thức phối hợp có bảo đảm thích hợp. Multi-region không tự đồng nghĩa transaction mạnh toàn cầu.

## 12. Ví dụ khác ngoài thương mại điện tử

### 12.1. Đặt phòng khách sạn

Reservation quản lý mã đặt, khách, ngày lưu trú và trạng thái. Quy tắc không đặt trùng phòng trong cùng đêm thuộc nguồn quản lý RoomAvailability hoặc slot allocation. Hai khách cùng nhìn thấy phòng trống trong cache không được xem là hai reservation chắc chắn được chấp nhận.

### 12.2. Ví điện tử

Account có quy tắc số dư; LedgerEntry là lịch sử giao dịch có thể tăng rất lớn. Chuyển tiền giữa hai tài khoản cần transaction thích hợp hoặc workflow bền có idempotency và đối soát. Hai lệnh trừ A và cộng B độc lập không đủ để bảo vệ nghiệp vụ.

### 12.3. Nền tảng học tập

Course chứa metadata và cấu trúc chương. Progress của hàng triệu học viên có vòng đời ghi độc lập, thường không nên nhúng vào Course. Enrollment/Progress theo học viên và khóa học là ứng viên ranh giới cập nhật riêng.

### 12.4. Mạng xã hội

Post sở hữu nội dung, tác giả và visibility. Comments/Likes tăng không giới hạn và do nhiều người ghi, nên thường được tách. Có thể giữ preview nhỏ có giới hạn trong Post với cơ chế cập nhật rõ ràng.

## 13. Quy trình lựa chọn aggregate cho một tính năng mới

1. **Liệt kê command**, ví dụ CreateOrder, AddItem, ConfirmOrder, ReserveStock, CapturePayment.
2. **Viết invariant** và thời điểm phải đúng, phân biệt quy tắc tức thời với độ trễ cho phép.
3. **Lập ma trận command × dữ liệu**, tìm các phần thực sự thay đổi cùng nhau.
4. **Chọn owner/root** có quyền chấp nhận hoặc từ chối thay đổi.
5. **Kiểm tra kích thước và lifecycle**, tránh mảng vô hạn, nhiều writer không liên quan và retention xung đột.
6. **Ánh xạ sang NoSQL**, chọn document/item, partition key, index, transaction, CAS/version.
7. **Thiết kế workflow xuyên aggregate**, nêu trạng thái trung gian, timeout, saga, idempotency và bù trừ.
8. **Tạo read model nếu cần**, không kéo thêm aggregate chỉ vì API đọc cùng.
9. **Kiểm chứng dưới concurrency và lỗi**, gồm retry, duplicate, crash và hot key.
10. **Ghi điều kiện đánh giá lại**, ví dụ p99, kích thước aggregate, conflict rate và số writer.

Một bản ghi quyết định:

~~~text
Aggregate: Order
Root: Order
Identity: (tenantId, orderId)
Owned fields: status, items, total, currency, version
References: customerId, sku, reservationId, paymentId

Invariants:
  - total matches items and captured prices
  - state transitions are valid
  - concurrent updates are guarded by version

Storage:
  - one bounded document per Order
  - atomic conditional update

Cross-aggregate workflow:
  - Inventory owns stock invariant
  - Payment owns external payment state
  - saga coordinates reservation and payment

Read model:
  - detail from authoritative Order
  - OrdersByCustomer may lag within accepted SLO

Monitoring:
  - document size, write conflict rate, p99
  - stuck reservations, outbox lag, mismatches
~~~

Đây là mô hình minh họa, không phải bảo đảm của một sản phẩm NoSQL cụ thể. Những hệ có Order rất lớn, ghi đa region hoặc transaction xuyên nhiều mục cần kiểm chứng riêng.

## 14. Kiểm chứng ranh giới và bất biến

| Tình huống | Điều cần đảm bảo |
|---|---|
| Hai tab cùng sửa Order version 5 | Không mất cập nhật đã commit |
| Tồn 5, hai request giữ 4 và 3 | Không giữ quá tồn cho phép |
| Tạo Order rồi retry cùng request key | Không tạo Order thứ hai |
| Saga chết giữa giữ SKU-A và SKU-B | Có thể tiếp tục hoặc bù trừ |
| ReleaseReservation được gọi hai lần | Không cộng tồn hai lần |
| OrdersByCustomer trễ vài giây | API/UI xử lý đúng SLA |
| Một SKU/tenant tạo phần lớn tải | Phát hiện hot key và điều tiết |

Các chỉ số có ích gồm kích thước aggregate p95/p99/max, conflict và retry rate, p99 write latency, throughput theo partition, reservation quá hạn, saga stuck, outbox lag và projection mismatch.

## 15. Những ngộ nhận thường gặp

### “Quan hệ một-nhiều thì luôn nhúng hết vào cha”

OrderItem có thể phù hợp với Order, nhưng Customer có mọi Order hoặc Post có hàng triệu Comment thường cần lưu riêng vì kích thước và vòng đời khác.

### “Một collection bằng một aggregate”

Collection Orders có thể chứa hàng triệu Order aggregate. Aggregate là ranh giới domain, không phải tên bảng.

### “Dữ liệu đọc cùng nhau phải ghi trong một transaction”

Trang Product có thể đọc catalog, stock và review cùng lúc. Quyền cập nhật và invariant của chúng khác nhau.

### “Atomic update chống được mọi lost update”

Hai writer ghi state cũ có thể ghi đè nhau nếu không có version/CAS hoặc kiểm soát cạnh tranh phù hợp.

### “NoSQL không có transaction nên mọi thứ đều eventual”

Phạm vi transaction khác nhau theo sản phẩm. Những invariant chặt cần được bảo vệ bằng cơ chế ghi thích hợp.

### “Có transaction nhiều document thì nên gom mọi thực thể”

Transaction lớn dễ tăng contention, latency và retry. Aggregate cần dựa trên nghiệp vụ và khả năng vận hành.

### “Saga cho phép bán âm kho để bù sau”

Saga phối hợp các bước xuyên aggregate; nó không thay thế invariant không oversell của Inventory.

### “Idempotency thay được CAS”

Idempotency xử lý request bị gửi lại, còn CAS xử lý nhiều writer cùng cập nhật state cũ.

### “Tách document là hết hotspot”

Một counter hoặc SKU vẫn có thể nhận tất cả write. Cần xem cả đường ghi phụ và partition.

### “Read model có thể quyết định thay nguồn”

Projection có thể trễ. Các command bảo vệ invariant phải đi qua owner có thẩm quyền hoặc cơ chế tương đương đã được kiểm chứng.

## 16. Bài tập thực hành

### Bài 1 — Giỏ hàng

Cart có 20 dòng, coupon, subtotal và total. Hai tab trình duyệt cùng sửa.

Hãy xác định aggregate root, các bất biến, cách lưu nhúng hợp lý, cơ chế version và lý do Product/Inventory không nhất thiết thuộc Cart.

### Bài 2 — Flash sale

SKU-A còn 5 sản phẩm, ba khách đặt mua 2, 3 và 4.

Hãy mô tả nguồn sở hữu invariant, conditional reserve, reservationId chống retry và rủi ro khi mỗi Order có một bản sao stock.

### Bài 3 — Customer document tăng vô hạn

Một document Customer chứa mọi Order, LoginEvent và Notification trong 5 năm.

Hãy đề xuất các ranh giới mới, thiết kế truy vấn 20 Order gần nhất và nêu ảnh hưởng về hot document, TTL và phân trang.

### Bài 4 — Đặt phòng

Hai người muốn đặt một phòng cùng đêm, reservation có TTL 10 phút.

Hãy xác định aggregate sở hữu availability, cách chống đặt trùng, workflow hết hạn và lý do TTL không tự giải phóng phòng.

### Bài 5 — Xác nhận đơn

Order đã CONFIRMED nhưng OrdersByCustomer chưa cập nhật do consumer lỗi.

Hãy phân biệt bất biến nguồn với projection lag, thiết kế outbox/CDC, idempotency và cách rebuild.

### Bài 6 — Hai writer

Order version 10. Service A đổi địa chỉ, Service B áp coupon; cả hai đọc v10.

Hãy mô tả lost update, expectedVersion và cách retry theo ý định nghiệp vụ.

### Bài 7 — Saga nhiều SKU

Đơn cần giữ SKU-A và SKU-B. Giữ A thành công, giữ B thất bại, worker chết trước khi release A.

Hãy thiết kế trạng thái bền, bù trừ, timeout và đối soát để không giữ kho mãi hoặc release hai lần.

### Bài 8 — Multi-region inventory

Hai region tiếp nhận mua hàng cho một SKU hữu hạn và đôi khi mất kết nối.

Hãy giải thích rủi ro last-write-wins, so sánh single writer với quota theo region và trình bày tradeoff latency/availability.

---

**Kết luận:** Aggregate là ranh giới nơi **dữ liệu và bất biến được quản lý cùng nhau**. Trong NoSQL, hãy bắt đầu từ command và quy tắc nghiệp vụ, rồi chọn document/item, transaction, version/CAS, partition key và đường đọc phù hợp. Aggregate nên đủ chặt để bảo vệ những thay đổi cần nguyên tử, nhưng đủ nhỏ để tránh dữ liệu vô hạn và tranh chấp. Khi workflow phải đi qua nhiều aggregate, dùng trạng thái bền, idempotency và cơ chế phục hồi có kiểm soát thay vì giả định mọi thực thể liên quan thuộc một giao dịch duy nhất.
