# Sự kiện nghiệp vụ: diễn đạt điều đã xảy ra bằng ngôn ngữ quá khứ

Khi phân tích một quy trình nghiệp vụ, đội phát triển thường nghe những câu như “khách đặt hàng”, “hệ thống thu tiền”, “kho giữ hàng” hoặc “đơn đã được giao”. Những câu này có thể mô tả hành động đang được yêu cầu, một việc đang diễn ra hoặc một kết quả đã xảy ra. Nếu không phân biệt rõ, mô hình domain dễ trộn lẫn ý định với sự thật, khiến tên gọi và luồng xử lý khó hiểu.

Trong Domain-Driven Design (DDD), **sự kiện nghiệp vụ** (*Domain Event*) diễn đạt một điều có ý nghĩa đối với domain và đã xảy ra. Vì sự kiện ghi nhận một sự việc đã xảy ra, tên sự kiện thường được đặt ở thì quá khứ: `OrderPlaced`, `PaymentAuthorized`, `StockReserved`, `ShipmentDelivered`. Khi đọc tên, người tham gia có thể hiểu rằng một kết quả đã được ghi nhận, chứ không phải một yêu cầu đang chờ thực hiện.

Trong EventStorming, sự kiện nghiệp vụ thường được ghi trên giấy ghi chú màu cam và sắp xếp theo dòng thời gian. Chúng giúp chuyên gia nghiệp vụ và đội phát triển nhìn thấy điều gì đã xảy ra, những quyết định nào dẫn đến sự kiện và phần nào của quy trình cần được khám phá thêm.

Sau bài học này, bạn có thể:

- Giải thích sự kiện nghiệp vụ là gì và vì sao thường được đặt tên ở thì quá khứ.
- Phân biệt event với command, trạng thái, hành động và thông báo kỹ thuật.
- Viết tên sự kiện rõ nghĩa, gắn với ngôn ngữ của domain.
- Xác định nội dung tối thiểu cần có trong một sự kiện và thời điểm sự kiện được phát ra.
- Sử dụng sự kiện để đọc và phân tích một dòng thời gian trong EventStorming.

## 1. Sự kiện nghiệp vụ là gì?

Sự kiện nghiệp vụ là một sự việc đã xảy ra trong domain và có ý nghĩa đối với một hoặc nhiều bên liên quan. Nó có thể làm thay đổi cách doanh nghiệp hiểu về một đối tượng, kích hoạt một quy trình tiếp theo hoặc cung cấp thông tin để một bộ phận khác đưa ra quyết định.

Ví dụ trong hệ thống bán hàng:

- `OrderPlaced`: khách đã đặt đơn và hệ thống đã ghi nhận đơn theo quy tắc bán hàng.
- `OrderAccepted`: yêu cầu mua đã được chấp nhận.
- `PaymentAuthorized`: khoản thanh toán đã được nhà cung cấp hoặc quy trình thanh toán cho phép.
- `StockReserved`: số lượng hàng đã được giữ cho một mục đích cụ thể.
- `ShipmentDispatched`: lô hàng đã được bàn giao để vận chuyển.
- `ShipmentDelivered`: việc giao hàng đã được xác nhận thành công theo bằng chứng được chấp nhận.

Các sự kiện này không chỉ là những dòng log. Chúng mô tả những mốc có ý nghĩa trong hoạt động kinh doanh. Ví dụ, `PaymentAuthorized` có thể cho phép quy trình tiếp tục, nhưng không nhất thiết có nghĩa tiền đã được thu hoặc quyết toán. `ShipmentDispatched` không đồng nghĩa với `ShipmentDelivered`. Việc dùng tên cụ thể giúp giữ đúng sự khác biệt nghiệp vụ.

Một sự kiện thường có ba đặc điểm:

1. **Đã xảy ra:** sự kiện mô tả một sự việc được xem là đã diễn ra, không phải yêu cầu thực hiện trong tương lai.
2. **Có ý nghĩa trong domain:** chuyên gia nghiệp vụ có thể giải thích vì sao sự việc quan trọng và nó ảnh hưởng đến quy trình hoặc quyết định nào.
3. **Có thời điểm và ngữ cảnh:** ta có thể xác định sự kiện xảy ra khi nào, thuộc đối tượng hoặc giao dịch nào và trong phạm vi nghiệp vụ nào.

Không phải mọi thay đổi kỹ thuật đều là Domain Event. Một bản ghi được ghi vào bảng, một cache bị xóa hoặc một request HTTP kết thúc có thể quan trọng với vận hành, nhưng chỉ nên trở thành sự kiện domain nếu nó diễn đạt một sự việc có ý nghĩa nghiệp vụ.

## 2. Vì sao tên sự kiện dùng thì quá khứ?

Tên sự kiện ở thì quá khứ thể hiện rằng sự việc đã hoàn thành hoặc đã được xác nhận. Đây là cách đặt tên giúp người đọc phân biệt kết quả với ý định.

Hãy so sánh:

| Cách gọi | Nó diễn đạt điều gì? | Có phải event đã xảy ra? |
|---|---|---|
| `PlaceOrder` | Yêu cầu đặt đơn | Không, đây thường là command |
| `OrderPlaced` | Đơn hàng đã được đặt và ghi nhận | Có |
| `AuthorizePayment` | Yêu cầu cho phép thanh toán | Không, đây thường là command |
| `PaymentAuthorized` | Thanh toán đã được cho phép | Có |
| `ReserveStock` | Yêu cầu giữ hàng | Không, đây thường là command |
| `StockReserved` | Hàng đã được giữ | Có |
| `DeliverShipment` | Yêu cầu giao lô hàng | Không, đây có thể là command hoặc hành động được yêu cầu |
| `ShipmentDelivered` | Lô hàng đã được giao | Có |

Khi tên sự kiện bắt đầu bằng động từ ở dạng mệnh lệnh như `CreateOrder`, `SendInvoice` hoặc `CancelSubscription`, người đọc thường hiểu đó là yêu cầu. Nếu muốn mô tả kết quả, hãy dùng `OrderCreated`, `InvoiceSent` hoặc `SubscriptionCancelled` khi những sự việc đó thực sự đã xảy ra.

Thì quá khứ cũng giúp kể lại quy trình. Ta có thể đọc một chuỗi như sau:

```text
OrderPlaced
  -> PaymentAuthorized
  -> StockReserved
  -> ShipmentDispatched
  -> ShipmentDelivered
```

Chuỗi này mô tả các mốc đã diễn ra trong một hành trình. Nếu một bước thất bại, dòng thời gian có thể có `PaymentAuthorizationFailed` hoặc `StockReservationRejected`. Sự kiện thất bại vẫn là sự kiện vì lần thử hoặc quyết định từ chối đã thực sự xảy ra.

## 3. Phân biệt event, command, state và action

Đây là một trong những khác biệt quan trọng nhất khi làm EventStorming và thiết kế domain model.

### Command: yêu cầu điều gì đó xảy ra

Command diễn đạt ý định hoặc yêu cầu một hành vi. Nó thường được đặt bằng động từ mệnh lệnh, chẳng hạn:

- `PlaceOrder`
- `AuthorizePayment`
- `ReserveStock`
- `CancelSubscription`

Command có thể được chấp nhận hoặc từ chối. Việc gửi command không chứng minh hành vi đã hoàn thành.

Ví dụ, khách gửi `PlaceOrder`. Hệ thống có thể chấp nhận và phát `OrderPlaced`, hoặc từ chối vì giỏ hàng không hợp lệ. Nếu command bị từ chối, không có `OrderPlaced` tương ứng.

### Event: thông báo điều gì đã xảy ra

Event ghi nhận kết quả hoặc sự việc trong domain:

- `OrderPlaced`
- `PaymentAuthorized`
- `StockReserved`
- `SubscriptionCancelled`

Event không yêu cầu consumer phải làm một hành động cụ thể. Consumer có thể phản ứng với event, nhưng event tự nó mô tả một sự thật đã được ghi nhận.

### State: tình trạng hiện tại của một đối tượng

State mô tả đối tượng đang ở tình trạng nào tại một thời điểm. Ví dụ, Order có thể ở trạng thái `PendingPayment`, `Confirmed`, `Cancelled` hoặc `Fulfilled`.

State thường là kết quả của một hoặc nhiều event, nhưng state và event không phải cùng một khái niệm:

| Event | State có thể có sau khi xử lý |
|---|---|
| `OrderPlaced` | `PendingPayment` |
| `PaymentAuthorized` | `ReadyForReservation` hoặc `Confirmed`, tùy policy |
| `OrderCancelled` | `Cancelled` |
| `ShipmentDelivered` | `Delivered` hoặc `FulfillmentCompleted` |

Một trạng thái có thể tồn tại trong một khoảng thời gian; một sự kiện là mốc xảy ra tại một thời điểm. `Cancelled` là trạng thái. `OrderCancelled` là sự kiện ghi nhận việc đơn đã bị hủy.

### Action: hành động được thực hiện

Action là cách nói chung về việc một actor hoặc hệ thống làm điều gì đó. Một action có thể dẫn đến command, rồi command có thể tạo ra event. Không phải action nào cũng tạo thành event domain.

Ví dụ:

```text
Khách bấm nút "Đặt hàng"
       |
       v
Command: PlaceOrder
       |
       v
Sales kiểm tra chính sách
       |
       +---- bị từ chối: không phát OrderPlaced
       |
       +---- được chấp nhận
                 |
                 v
Event: OrderPlaced
```

Sơ đồ cho thấy thao tác bấm nút, command và event là ba thứ khác nhau. Tên nút giao diện có thể thay đổi mà không làm thay đổi ý nghĩa của event.

## 4. Một sự kiện phải nói rõ điều gì đã xảy ra

Tên sự kiện tốt giúp người đọc hình dung được sự việc mà không cần mở mã nguồn để đoán. Hãy ưu tiên động từ cụ thể và đối tượng nghiệp vụ cụ thể.

| Tên quá chung hoặc mơ hồ | Tên cụ thể hơn | Lý do |
|---|---|---|
| `OrderUpdated` | `ShippingAddressChanged` | Chỉ rõ phần nghiệp vụ đã thay đổi |
| `PaymentProcessed` | `PaymentAuthorized` hoặc `PaymentCaptured` | Phân biệt cho phép thanh toán và thu tiền |
| `StatusChanged` | `SubscriptionSuspended` | Nêu rõ trạng thái và đối tượng |
| `RequestCompleted` | `RefundIssued` | Nêu kết quả nghiệp vụ thực tế |
| `DataSaved` | `CustomerEmailChanged` | Tránh mô tả thao tác lưu dữ liệu kỹ thuật |
| `TaskFinished` | `ShipmentDelivered` | Dùng ngôn ngữ domain thay cho trạng thái công việc chung |

Không phải lúc nào cũng cần tên thật dài. Tên cần đủ cụ thể trong ngữ cảnh đang dùng. Nếu `Order` đã được hiểu rõ trong Bounded Context, `OrderPlaced` có thể là đủ. Trong một context khác, có thể cần tên đầy đủ hơn để tránh nhầm lẫn.

### Tránh dùng “đã xử lý” khi chưa biết kết quả

Các từ như `Processed`, `Completed`, `Handled` hoặc `Succeeded` thường che giấu câu hỏi: chính xác điều gì đã xảy ra?

Ví dụ, `PaymentProcessed` không cho biết:

- yêu cầu đã được gửi đến nhà cung cấp chưa,
- thanh toán đã được authorize chưa,
- tiền đã được capture chưa,
- giao dịch đã được settle chưa,
- hay chỉ có một worker xử lý xong message.

Hãy hỏi chuyên gia nghiệp vụ về mốc mà họ cần phân biệt, sau đó chọn tên phản ánh đúng mốc đó. Nếu một event chỉ mô tả consumer đã xử lý message thành công, đó có thể là thông tin vận hành hoặc kỹ thuật, không phải event domain.

## 5. Cách đặt tên event trong ngôn ngữ chung

Tên event nên xuất phát từ cách chuyên gia nghiệp vụ mô tả sự việc. Đội phát triển có thể đề xuất từ ngữ, nhưng cần kiểm tra xem tên đó có đúng với ý nghĩa nghiệp vụ hay không.

Một số nguyên tắc thực hành:

**Dùng dạng quá khứ.** `InvoiceIssued`, `CustomerRegistered`, `ContractSigned` cho biết sự việc đã xảy ra.

**Nêu rõ đối tượng hoặc chủ thể.** `AddressChanged` có thể đủ trong context quản lý khách hàng; `CustomerAddressChanged` rõ hơn khi hệ thống có nhiều loại địa chỉ.

**Chọn động từ có ý nghĩa nghiệp vụ.** `Approved`, `Rejected`, `Captured`, `Dispatched`, `Delivered` thường rõ hơn `Updated` hoặc `Processed`.

**Không đưa tên công nghệ vào event domain.** Tránh các tên như `KafkaMessagePublished`, `DatabaseRowInserted` hoặc `HttpRequestSucceeded` nếu điều cần mô tả là sự kiện nghiệp vụ.

**Giữ một thuật ngữ cho một ý nghĩa trong cùng context.** Nếu nhóm dùng `OrderAccepted`, đừng lúc khác gọi cùng sự việc là `OrderApproved` trừ khi hai khái niệm có ý nghĩa khác nhau.

**Không khẳng định nhiều hơn sự thật.** Nếu nhà cung cấp chỉ xác nhận authorize, không đặt tên `PaymentCompleted` hoặc `PaymentSettled`.

### Một số nhóm động từ hữu ích

| Ý nghĩa | Ví dụ tên event |
|---|---|
| Hình thành hoặc ghi nhận | `OrderPlaced`, `CustomerRegistered`, `InvoiceIssued` |
| Chấp thuận hoặc từ chối | `OrderAccepted`, `LoanApplicationRejected` |
| Thay đổi thông tin | `ShippingAddressChanged`, `CreditLimitAdjusted` |
| Thu hoặc hoàn tiền | `PaymentCaptured`, `RefundIssued` |
| Giữ hoặc giải phóng tài nguyên | `StockReserved`, `ReservationReleased` |
| Bàn giao hoặc hoàn tất | `ShipmentDispatched`, `ShipmentDelivered` |
| Tạm dừng hoặc kết thúc | `SubscriptionSuspended`, `ContractTerminated` |

Những ví dụ này chỉ là gợi ý. Tên chính thức cần theo ngôn ngữ và quy tắc của domain cụ thể.

## 6. Sự kiện phải gắn với thời điểm và điều kiện phát ra

Một event chỉ nên được phát khi điều được mô tả đã thực sự xảy ra theo quy tắc domain. Việc xác định thời điểm phát là rất quan trọng vì event có thể kích hoạt các quy trình khác.

Ví dụ, một hệ thống có các mốc thanh toán:

1. Khách gửi yêu cầu thanh toán.
2. Nhà cung cấp xác nhận có thể thu tiền sau này (*authorization*).
3. Doanh nghiệp yêu cầu capture khoản tiền.
4. Nhà cung cấp xác nhận capture thành công.
5. Giao dịch được đối soát hoặc settle theo quy trình tài chính.

Không nên phát `PaymentCaptured` ở bước 2 chỉ vì authorization thành công. Nếu Fulfillment dựa vào `PaymentCaptured` để bắt đầu giao hàng, tên sự kiện sai sẽ dẫn đến quyết định sai.

Hãy ghi rõ điều kiện phát event:

| Event | Điều kiện phát ví dụ |
|---|---|
| `OrderPlaced` | Sales đã chấp nhận yêu cầu đặt mua và ghi nhận Order |
| `PaymentAuthorized` | Kết quả authorization đã được xác nhận theo quy tắc Payment |
| `PaymentCaptured` | Việc capture đã được xác nhận thành công |
| `StockReserved` | Inventory đã giữ thành công số lượng được yêu cầu |
| `ShipmentDispatched` | Lô hàng đã được bàn giao cho đơn vị vận chuyển |
| `ShipmentDelivered` | Có bằng chứng giao hàng hợp lệ theo policy |

Nếu chưa đủ căn cứ để xác nhận một việc đã xảy ra, hãy dùng trạng thái chờ hoặc event phản ánh đúng sự việc đã biết. Ví dụ `PaymentAuthorizationRequested` có thể là event tích hợp ghi nhận việc yêu cầu đã được gửi, nhưng cần phân biệt nó với `PaymentAuthorized`.

## 7. Nội dung của một Domain Event

Một event thường có tên, dữ liệu nghiệp vụ cần thiết và thông tin giúp nhận diện ngữ cảnh của sự kiện. Không phải mọi event đều cần cùng một cấu trúc, nhưng có thể bắt đầu bằng các trường sau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Event name | Sự việc đã xảy ra | `OrderPlaced` |
| Event ID | Định danh duy nhất của event | `evt-1042` |
| Aggregate/entity ID | Đối tượng liên quan | `orderId = ORD-1042` |
| Occurred at | Thời điểm sự kiện xảy ra | `2026-11-18T09:30:00Z` |
| Business data | Dữ liệu cần để hiểu hoặc xử lý sự kiện | dòng hàng, số lượng, currency, giá đã chốt |
| Correlation/causation reference | Liên hệ với flow hoặc nguyên nhân trước đó | `correlationId`, `causationId` |
| Schema version (nếu cần) | Phiên bản hợp đồng event | `1` |

Ví dụ payload minh họa:

```json
{
  "eventId": "evt-1042",
  "eventType": "OrderPlaced",
  "occurredAt": "2026-11-18T09:30:00Z",
  "orderId": "ORD-1042",
  "customerId": "CUS-72",
  "currency": "VND",
  "totalAmount": 850000,
  "lines": [
    { "sku": "BOOK-01", "quantity": 2, "unitPrice": 300000 },
    { "sku": "BAG-03", "quantity": 1, "unitPrice": 250000 }
  ],
  "schemaVersion": 1
}
```

Payload này là ví dụ để giải thích cấu trúc, không phải một schema bắt buộc. Chỉ đưa dữ liệu mà consumer cần để phản ứng với sự kiện hoặc hiểu sự kiện. Tránh gửi toàn bộ aggregate, dữ liệu nhạy cảm không cần thiết hoặc các trường chỉ phản ánh chi tiết implementation.

### Event là một sự thật đã ghi nhận

Về mặt ngữ nghĩa, event đã xảy ra không nên bị sửa để biến thành một sự việc khác. Nếu địa chỉ giao hàng thay đổi sau khi đặt đơn, hãy ghi nhận `ShippingAddressChanged` thay vì sửa lại event `OrderPlaced` để giả vờ rằng đơn ban đầu được đặt với địa chỉ mới.

Điều này không có nghĩa hệ thống không bao giờ được sửa dữ liệu event do lỗi vận hành hoặc yêu cầu pháp lý. Những thao tác sửa chữa cần được quản lý riêng, có dấu vết và không làm mất lịch sử sự thật đã được ghi nhận.

## 8. Domain Event và Integration Event

Hai khái niệm này liên quan nhưng không hoàn toàn giống nhau.

**Domain Event** diễn đạt sự việc có ý nghĩa bên trong mô hình domain. Nó phục vụ logic và ngôn ngữ của Bounded Context phát sinh sự kiện.

**Integration Event** là thông điệp được công bố qua ranh giới để context hoặc hệ thống khác có thể phản ứng. Integration Event cần có hợp đồng ổn định, dữ liệu được chọn lọc và quy tắc tương thích phiên bản.

Một Domain Event có thể được chuyển thành Integration Event, nhưng không nhất thiết phải công bố mọi Domain Event ra bên ngoài.

Ví dụ, trong Sales Context:

```text
Domain Event nội bộ:
  OrderAccepted

Integration Event công bố:
  SalesOrderAccepted
  - orderId
  - acceptedAt
  - lines (sku, quantity)
  - deliveryAddressSnapshot
```

Tên và payload công bố có thể khác event nội bộ vì mục đích và người nhận khác nhau. Sales có thể cần nhiều event nội bộ để quản lý mô hình, trong khi Fulfillment chỉ cần thông tin tối thiểu để tạo yêu cầu thực hiện.

| Tiêu chí | Domain Event | Integration Event |
|---|---|---|
| Phạm vi | Bên trong một domain model/context | Qua ranh giới context hoặc hệ thống |
| Mục đích | Diễn đạt sự việc trong domain | Phối hợp và chia sẻ thông tin đã công bố |
| Người tiêu thụ | Domain/application logic liên quan | Consumer ở context hoặc hệ thống khác |
| Hợp đồng | Gắn với mô hình nội bộ | Cần được quản lý tương thích và versioning |
| Dữ liệu | Theo nhu cầu mô hình domain | Theo nhu cầu tích hợp, tránh lộ chi tiết nội bộ |

## 9. Domain Event không đồng nghĩa với Event Sourcing

Domain Event thường được dùng trong kiến trúc hướng sự kiện, nhưng việc có event không có nghĩa hệ thống đang dùng *Event Sourcing*.

Trong cách lưu trữ thông thường, ứng dụng có thể cập nhật trạng thái hiện tại của Order trong database và đồng thời phát event `OrderPlaced` để thông báo cho các thành phần khác. Database vẫn lưu state hiện tại làm nguồn truy vấn chính.

Trong Event Sourcing, các event được lưu như nguồn dữ liệu chính để tái dựng trạng thái của đối tượng. State hiện tại có thể được tính bằng cách áp dụng lần lượt các event đã ghi nhận. Ví dụ:

```text
OrderPlaced
  -> OrderLineAdded
  -> ShippingAddressChanged
  -> OrderAccepted
```

Từ chuỗi event này, hệ thống có thể dựng lại trạng thái Order tại thời điểm hiện tại hoặc tại một mốc trong quá khứ.

| Domain Event | Event Sourcing |
|---|---|
| Là mô hình hóa một sự việc có ý nghĩa trong domain | Là một cách tổ chức lưu trữ và dựng lại trạng thái từ event |
| Có thể được dùng dù database chỉ lưu state hiện tại | Dựa vào event store làm nguồn dữ liệu chính |
| Có thể chỉ phát để consumer phản ứng | Cần quản lý thứ tự, version, replay, snapshot và schema event |

Bạn có thể dùng Domain Event trong một ứng dụng CRUD hoặc modular monolith mà không áp dụng Event Sourcing. Chọn Event Sourcing khi có lý do nghiệp vụ và kỹ thuật đủ rõ, chẳng hạn cần lịch sử đầy đủ, tái dựng trạng thái hoặc audit theo chuỗi sự kiện.

## 10. Sự kiện trong EventStorming

EventStorming là workshop cộng tác để khám phá domain bằng cách đưa các sự kiện lên một dòng thời gian. Người tham gia thường bắt đầu bằng việc ghi lại những gì đã xảy ra theo ngôn ngữ nghiệp vụ, sau đó bổ sung command, actor, policy, aggregate, hệ thống bên ngoài và các câu hỏi cần làm rõ.

Trong cách dùng phổ biến:

- Giấy ghi chú **màu cam**: Domain Event.
- Giấy ghi chú **màu xanh dương**: Command.
- Giấy ghi chú **màu vàng**: Actor hoặc người thực hiện.
- Giấy ghi chú **màu tím**: Policy hoặc phản ứng tự động.
- Giấy ghi chú **màu hồng**: Hotspot, câu hỏi hoặc điểm chưa thống nhất.
- Giấy ghi chú **màu xanh lá**: Read model hoặc thông tin được đọc, tùy biến thể workshop.

Màu sắc là quy ước hỗ trợ trực quan và có thể được điều chỉnh theo workshop. Điều quan trọng là cả nhóm hiểu mỗi loại giấy ghi chú đang biểu diễn điều gì.

### Đọc một đoạn dòng thời gian

Ví dụ quy trình đặt hàng:

```text
Khách hàng
   |
   v
[PlaceOrder]  Command
   |
   v
[OrderPlaced]  Domain Event
   |
   v
[RequestPayment]  Command
   |
   v
[PaymentAuthorized]  Domain Event
   |
   v
[ReserveStock]  Command
   |
   v
[StockReserved]  Domain Event
```

Khi nhìn dòng thời gian, nhóm có thể hỏi:

- `OrderPlaced` xảy ra trước hay sau khi thanh toán?
- Nếu thanh toán thất bại thì có event nào được ghi nhận?
- `StockReserved` có thể xảy ra một phần không?
- Ai sở hữu quyết định chấp nhận Order?
- Có chính sách nào tự động phản ứng sau `PaymentAuthorized` không?

Những câu hỏi này giúp khám phá quy tắc và ngoại lệ. Đừng cố biến workshop thành việc liệt kê thật nhiều tên event. Một event hữu ích phải phản ánh một mốc mà chuyên gia nghiệp vụ nhận ra và có thể xác nhận.

## 11. Cách tìm sự kiện từ câu chuyện nghiệp vụ

Khi chuyên gia kể một quy trình, hãy lắng nghe những câu ở dạng “đã xảy ra”, “được chấp nhận”, “bị từ chối”, “được bàn giao”, “đã thay đổi” hoặc “đã hết hạn”. Đây thường là manh mối để tìm event.

Có thể thực hiện theo các bước:

1. Chọn một giao dịch hoặc tình huống thực tế.
2. Hỏi người tham gia: “Điều gì đã xảy ra tiếp theo?”
3. Ghi lại câu trả lời bằng ngôn ngữ của họ, ở dạng quá khứ.
4. Hỏi sự kiện đó có ý nghĩa gì và ai quan tâm đến nó.
5. Xác định điều kiện khiến sự kiện được xem là đã xảy ra.
6. Tìm ngoại lệ, trường hợp thất bại và những sự kiện có thể xảy ra trước hoặc sau nó.

Ví dụ, thay vì hỏi “Hệ thống có những trạng thái nào?”, hãy hỏi “Khi đơn chuyển từ chờ xử lý sang được chấp nhận, điều gì đã xảy ra và ai đưa ra quyết định?”. Câu hỏi này thường giúp nhóm tìm ra `OrderAccepted` và quy tắc đi kèm.

### Dùng động từ quá khứ làm manh mối

Các cụm sau có thể gợi ý event:

- “Khách đã gửi yêu cầu” → `RequestSubmitted`.
- “Hồ sơ đã được duyệt” → `ApplicationApproved`.
- “Kho đã giữ đủ hàng” → `StockReserved`.
- “Hợp đồng đã được ký” → `ContractSigned`.
- “Giao dịch đã bị từ chối” → `TransactionDeclined`.
- “Thời hạn đã hết” → `PaymentWindowExpired`.

Đây chỉ là bản nháp ban đầu. Hãy xác nhận thuật ngữ, chủ thể và điều kiện với chuyên gia. Ví dụ “hồ sơ đã được duyệt” có thể cần phân biệt `ApplicationApproved` với `ApplicationVerified` nếu xác minh và phê duyệt là hai bước khác nhau.

## 12. Phân biệt sự kiện nghiệp vụ với log và notification

Log ghi lại hoạt động của phần mềm để hỗ trợ gỡ lỗi, giám sát và điều tra sự cố. Notification là thông báo gửi đến người hoặc hệ thống. Domain Event mô tả sự việc có ý nghĩa trong nghiệp vụ. Một sự kiện domain có thể dẫn đến log hoặc notification, nhưng ba khái niệm không thay thế nhau.

| Ví dụ | Phân loại | Vì sao? |
|---|---|---|
| `OrderPlaced` | Domain Event | Ghi nhận đơn hàng đã được đặt |
| `HTTP 200 returned` | Thông tin kỹ thuật/log | Mô tả kết quả giao tiếp HTTP |
| `EmailSent` | Có thể là event kỹ thuật hoặc nghiệp vụ tùy domain | Cần xác định việc gửi email có ý nghĩa nghiệp vụ hay chỉ là chi tiết thông báo |
| `InvoiceIssued` | Domain Event | Ghi nhận hóa đơn đã được phát hành |
| `CacheEvicted` | Log hoặc event kỹ thuật | Thường là chi tiết vận hành, không phải sự kiện domain |
| `CustomerNotifiedOfShipment` | Có thể là Domain Event nếu doanh nghiệp quan tâm việc thông báo đã được ghi nhận | Cần xác định ý nghĩa nghiệp vụ và bằng chứng gửi |

Không nên tạo Domain Event cho mọi thao tác trong code. Nếu event chỉ giúp ghi log, hãy dùng hệ thống logging hoặc telemetry phù hợp. Nếu việc thông báo có cam kết nghiệp vụ, hãy diễn đạt chính xác kết quả, chẳng hạn `PaymentReceiptEmailSent`, khi hệ thống thực sự có xác nhận gửi thành công.

## 13. Event có thể diễn đạt thất bại hoặc ngoại lệ

Sự kiện không chỉ ghi nhận kết quả thành công. Một sự việc bị từ chối hoặc thất bại cũng có thể có ý nghĩa nghiệp vụ.

Ví dụ:

- `LoanApplicationRejected`: hồ sơ vay đã bị từ chối theo một quyết định cụ thể.
- `PaymentAuthorizationFailed`: lần authorize thanh toán đã thất bại.
- `StockReservationRejected`: yêu cầu giữ hàng đã bị từ chối.
- `SubscriptionSuspended`: thuê bao đã bị tạm ngưng.
- `DeliveryAttemptFailed`: lần giao hàng đã thất bại.

Hãy phân biệt thất bại của một lần thử với trạng thái cuối cùng của toàn bộ quy trình. `PaymentAuthorizationFailed` không nhất thiết có nghĩa Payment đã thất bại vĩnh viễn; khách có thể thử phương thức khác. `DeliveryAttemptFailed` không nhất thiết có nghĩa Shipment đã bị hủy.

Nếu domain cần theo dõi nguyên nhân, event có thể chứa mã lý do hoặc thông tin phân loại đã được thống nhất. Không nên nhúng thông tin lỗi hạ tầng chi tiết vào event nghiệp vụ nếu consumer không cần hiểu nó.

## 14. Thời gian, thứ tự và ngữ cảnh của event

Event thường được sắp xếp theo dòng thời gian, nhưng hệ thống phân tán có thể nhận event không đúng thứ tự phát sinh. Cần phân biệt:

- **Occurred time:** thời điểm sự việc thực sự xảy ra theo nguồn nghiệp vụ.
- **Recorded time:** thời điểm hệ thống ghi nhận event.
- **Published time:** thời điểm event được công bố ra kênh tích hợp.
- **Consumed time:** thời điểm consumer nhận hoặc xử lý event.

Các mốc này có thể khác nhau. Ví dụ, hãng vận chuyển xác nhận giao hàng lúc 10:00 nhưng webhook chỉ đến hệ thống lúc 10:05. `occurredAt` có thể là 10:00, còn `recordedAt` là 10:05.

Đừng mặc định timestamp nhận message là thời điểm sự kiện xảy ra. Nếu thứ tự có ý nghĩa, cần xác định thứ tự theo aggregate, version hoặc một cơ chế nghiệp vụ phù hợp; không chỉ dựa vào đồng hồ của nhiều máy.

Một event cũng nên có định danh đối tượng và ngữ cảnh đủ để consumer biết nó liên quan đến điều gì. Ví dụ `orderId`, `paymentId`, `shipmentId`, `correlationId` hoặc `causationId` có thể hữu ích tùy flow.

## 15. Event gắn với Aggregate và Domain Model như thế nào?

Trong tactical DDD, một Aggregate bảo vệ các invariant của một nhóm đối tượng. Khi một hành vi hợp lệ làm thay đổi domain, Aggregate có thể ghi nhận Domain Event để diễn đạt kết quả.

Ví dụ, `Order` có hành vi `place()` hoặc một application use case yêu cầu đặt đơn. Nếu các điều kiện được đáp ứng, domain model có thể ghi nhận `OrderPlaced`. Nếu điều kiện không đáp ứng, hành vi trả về lỗi hoặc kết quả từ chối và không ghi nhận event thành công.

Ví dụ minh họa:

```java
public class Order {
    private final OrderId id;
    private OrderStatus status;
    private final List<OrderLine> lines;

    public void place() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("Order must contain at least one line");
        }

        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be placed");
        }

        status = OrderStatus.PLACED;
        // Ghi nhận Domain Event OrderPlaced để application layer công bố sau commit.
    }
}
```

Đoạn code chỉ minh họa vị trí ghi nhận sự kiện. Trong một thiết kế thực tế, domain model có thể lưu event vào collection nội bộ, còn application/infrastructure layer chịu trách nhiệm lưu trạng thái và công bố event theo cơ chế đáng tin cậy.

### Khi nào phát event?

Event phải phản ánh một kết quả đã được xác nhận. Nếu trạng thái domain và event được lưu trong database, cần tránh trường hợp database commit thành công nhưng event bị mất hoặc event được gửi ra ngoài trong khi transaction cuối cùng rollback.

Một giải pháp phổ biến là *Transactional Outbox*: ghi thay đổi domain và bản ghi outbox trong cùng transaction; một publisher riêng đọc outbox và công bố message. Cơ chế này giải quyết một vấn đề giao nhận, nhưng không thay thế việc chọn đúng event và đúng thời điểm nghiệp vụ.

## 16. Những sai lầm thường gặp khi đặt tên sự kiện

**Dùng command làm event.** `CreateInvoice` là yêu cầu tạo hóa đơn; `InvoiceIssued` là việc hóa đơn đã được phát hành.

**Dùng tên trạng thái thay cho event.** `Paid` có thể là state; `PaymentCaptured` mô tả mốc sự việc đã xảy ra.

**Dùng tên quá chung.** `Updated`, `Processed` hoặc `Completed` không cho biết sự việc nào có ý nghĩa trong domain.

**Dùng tên kỹ thuật.** `RecordInserted` hoặc `KafkaPublished` mô tả implementation, không diễn đạt domain.

**Đặt tên thành công trước khi có bằng chứng.** `PaymentCaptured` không nên được phát khi chỉ mới gửi request capture.

**Gộp nhiều sự kiện vào một tên.** `OrderPaidAndShipped` gộp hai mốc có thể xảy ra ở thời điểm khác nhau và do hai context sở hữu. Nên tách thành `PaymentCaptured` và `ShipmentDispatched`.

**Dùng cùng một từ cho nhiều nghĩa trong cùng context.** Nếu `Approved` lúc thì là duyệt hồ sơ, lúc là chấp nhận giao dịch, cần tên rõ hơn.

**Đưa mọi thay đổi field thành event domain.** `CustomerRowUpdated` không giúp hiểu điều gì đã thay đổi về mặt nghiệp vụ. Hãy xác định sự kiện như `CustomerEmailChanged` nếu đó là điều domain quan tâm.

## 17. Quy trình chuyển câu nói thành Domain Event

Khi workshop hoặc thiết kế một use case, có thể dùng quy trình sau:

**Bước 1: Ghi câu nói tự nhiên.** Ví dụ: “Nhân viên đã xác nhận khách nhận hàng”.

**Bước 2: Xác định đối tượng và kết quả.** Đối tượng là Shipment; kết quả là đã được giao và xác nhận.

**Bước 3: Đặt tên ở thì quá khứ.** `ShipmentDelivered`.

**Bước 4: Làm rõ điều kiện.** Ai được quyền xác nhận? Bằng chứng nào được chấp nhận? Giao một phần có tạo event riêng không?

**Bước 5: Phân biệt với command và state.** Command có thể là `ConfirmDelivery`; state có thể là `DELIVERED`; event là `ShipmentDelivered`.

**Bước 6: Xác định consumer và ý nghĩa.** Sales có cần cập nhật tiến trình Order? Khách có cần được thông báo? Kế toán có cần ghi nhận doanh thu? Mỗi nhu cầu cần được đánh giá theo domain và context.

**Bước 7: Chọn payload tối thiểu.** Có thể cần `shipmentId`, `orderId`, `deliveredAt`, `recipientReference` và mã bằng chứng giao hàng. Chỉ đưa dữ liệu thực sự cần.

**Bước 8: Xác nhận với chuyên gia nghiệp vụ.** Đọc lại tên và ví dụ. Nếu chuyên gia nói “chưa, khách mới xác nhận đã nhận một phần”, event `ShipmentDelivered` có thể không đúng.

## 18. Ví dụ thực hành: quy trình hoàn tiền

Giả sử khách yêu cầu hoàn tiền cho một sản phẩm đã trả lại. Nhóm ghi nhận các sự kiện:

```text
ReturnRequested
ReturnApproved
ItemReceivedForReturn
RefundAuthorized
RefundIssued
RefundFailed
```

Không phải mọi quy trình đều phải đi qua tất cả sự kiện này. Tùy policy, một số bước có thể không cần, hoặc một sự kiện có thể có tên khác.

Hãy phân biệt:

| Command | Event | Ý nghĩa |
|---|---|---|
| `RequestReturn` | `ReturnRequested` | Yêu cầu trả hàng đã được ghi nhận |
| `ApproveReturn` | `ReturnApproved` | Yêu cầu trả hàng đã được chấp thuận |
| `ReceiveReturnedItem` | `ItemReceivedForReturn` | Hàng trả đã được tiếp nhận |
| `AuthorizeRefund` | `RefundAuthorized` | Khoản hoàn đã được cho phép theo quy trình |
| `IssueRefund` | `RefundIssued` | Giao dịch hoàn tiền đã được xác nhận phát hành |

Nếu `IssueRefund` được gửi nhưng nhà cung cấp timeout, hệ thống chưa thể kết luận `RefundIssued`. Có thể ghi nhận `RefundSubmissionTimedOut` như một sự kiện vận hành hoặc nghiệp vụ nếu domain quan tâm đến việc không xác định được kết quả, sau đó truy vấn/đối soát để xác định sự thật cuối cùng. Không nên phát một event thành công chỉ vì request đã được gửi.

## 19. Bài tập tự kiểm tra

Một hệ thống đặt lịch khám có các câu sau:

1. Bệnh nhân gửi yêu cầu đặt lịch.
2. Lịch hẹn được xác nhận.
3. Nhân viên tiếp nhận bệnh nhân.
4. Bác sĩ bắt đầu khám.
5. Kết quả xét nghiệm được trả về.
6. Bệnh nhân thanh toán phí khám.
7. Hệ thống gửi email nhắc lịch.

Hãy thực hiện:

- Viết command tương ứng cho từng hành động có thể được yêu cầu.
- Đặt tên event ở thì quá khứ cho những sự việc đã xảy ra.
- Chỉ ra state có thể tồn tại sau từng event.
- Xác định sự kiện nào chắc chắn là domain event, sự kiện nào có thể chỉ là thông tin kỹ thuật hoặc notification tùy domain.
- Viết điều kiện phát cho hai event bất kỳ.

Gợi ý:

| Câu mô tả | Command có thể có | Event có thể có | State liên quan |
|---|---|---|---|
| Bệnh nhân gửi yêu cầu | `RequestAppointment` | `AppointmentRequested` | `PENDING` |
| Lịch hẹn được xác nhận | `ConfirmAppointment` | `AppointmentConfirmed` | `CONFIRMED` |
| Nhân viên tiếp nhận bệnh nhân | `CheckInPatient` | `PatientCheckedIn` | `CHECKED_IN` |
| Bác sĩ bắt đầu khám | `StartConsultation` | `ConsultationStarted` | `IN_PROGRESS` |
| Kết quả xét nghiệm được trả về | `RecordLabResult` | `LabResultRecorded` | `RESULT_AVAILABLE` |
| Bệnh nhân thanh toán phí khám | `CollectConsultationFee` | `ConsultationFeePaid` | `PAID` |
| Email nhắc lịch được gửi | `SendAppointmentReminder` | `AppointmentReminderSent` nếu domain quan tâm kết quả gửi | Có thể không có state domain |

Tên event cuối cùng cần theo ngôn ngữ của tổ chức. Ví dụ, “thanh toán” có thể cần phân biệt khoản tiền đã authorize, capture hay settle. “Kết quả xét nghiệm được trả về” cũng có thể cần phân biệt kết quả đã được máy xét nghiệm tạo, đã được bác sĩ xác nhận hay đã được công bố cho bệnh nhân.

## Kết luận

Sự kiện nghiệp vụ diễn đạt một sự việc có ý nghĩa đã xảy ra trong domain. Tên sự kiện thường dùng thì quá khứ để phân biệt nó với command là yêu cầu, state là tình trạng hiện tại và action là hành động được thực hiện. Tên tốt phải cụ thể, đúng với ngôn ngữ nghiệp vụ và không khẳng định nhiều hơn điều đã được xác nhận.

Trong EventStorming, các sự kiện được đặt trên dòng thời gian để cả nhóm cùng nhìn thấy những mốc quan trọng, khám phá quyết định và ngoại lệ. Khi xác định đúng event, đội phát triển có cơ sở tốt hơn để thiết kế domain model, giao tiếp giữa Bounded Context và những luồng xử lý tiếp theo. Hãy luôn hỏi: “Điều gì thực sự đã xảy ra, và domain gọi sự việc đó là gì?”
