# Đặt tên event trong thiết kế Spring Modulith

## 1. Đặt tên event là thiết kế một hợp đồng nghiệp vụ

Khi module **Orders** phát sự kiện `OrderConfirmed`, module **Notifications** có thể bắt đầu chuẩn bị thông báo, module **Fulfillment** có thể chuẩn bị công việc giao hàng và module **Reporting** có thể cập nhật báo cáo. Các module nhận không cần gọi vào mã nội bộ của Orders để biết kết quả xác nhận.

Cơ chế này là một phần của **SPRING_MODULITH_APPLICATION_EVENTS**: tổ chức giao tiếp giữa các module bằng application events để giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ. Tuy nhiên, một event đặt tên không rõ sẽ khiến các consumer hiểu sai cùng một thông tin. Chẳng hạn, `OrderProcessed` có thể được hiểu là đơn đã được tạo, đã thanh toán, đã đóng gói hoặc đã giao hoàn tất.

Vì vậy, **tên event phải mô tả một sự thật nghiệp vụ đủ cụ thể, đã xảy ra và được module phát bảo đảm**. Đây là một hợp đồng công khai: consumer có quyền sử dụng những gì tên và tài liệu của event khẳng định, nhưng không được suy diễn thêm những bước nghiệp vụ chưa hoàn tất.

Bài này thuộc phần **Thiết kế event**. Trọng tâm là quy trình chọn và rà soát tên event khi viết code Java/Spring Modulith, từ việc lựa chọn danh từ nghiệp vụ và động từ cho tới xử lý tên mơ hồ, sự kiện lỗi, tên công khai qua module và đổi tên khi đã có consumer.

### Kết quả mong đợi

Sau bài học, bạn có thể:

- Chuyển một yêu cầu nghiệp vụ thành tên event biểu đạt **một sự thật đã xảy ra**.
- Phân biệt tên event với tên command, tên state, callback kỹ thuật và hành động của consumer.
- Chọn mốc nghiệp vụ và từ vựng đủ chính xác để tránh hiểu nhầm giữa các module.
- Áp dụng một naming convention thống nhất trong Java, package và hợp đồng tích hợp.
- Nhận diện trường hợp không nên đổi tên tùy tiện vì event đã là API giữa các module.
- Đánh giá tên event bằng ví dụ, bảng kiểm và test cho điều kiện phát hành.

## 2. Quy tắc đầu tiên: gọi tên điều đã xảy ra

Một cấu trúc tên phổ biến trong Java là:

```text
<BusinessSubject><PastTenseOrPastParticiple>
```

Ví dụ:

| Tên event | Câu khẳng định mà event truyền đạt |
| --- | --- |
| `OrderPlaced` | Đơn hàng đã được khách đặt theo định nghĩa của hệ thống |
| `OrderConfirmed` | Đơn hàng đã được hệ thống xác nhận |
| `PaymentAuthorized` | Giao dịch đã được chấp thuận ở bước ủy quyền |
| `PaymentCaptured` | Thao tác thu tiền đã được hệ thống thanh toán xác nhận |
| `InventoryReserved` | Số lượng hàng yêu cầu đã được giữ thành công |
| `InvoiceIssued` | Hóa đơn đã được phát hành |
| `ShipmentDispatched` | Lô hàng đã được bàn giao cho khâu vận chuyển |
| `SubscriptionCancelled` | Đăng ký đã được hủy theo chính sách nghiệp vụ |

Tên của một type có thể dùng `PascalCase`, và phần động từ thường diễn đạt kết quả ở thì quá khứ. Đây là **quy ước dễ đọc**, không phải một ràng buộc ngôn ngữ Java hay Spring Modulith. Điều quan trọng là tên nhất quán với từ vựng miền nghiệp vụ (*ubiquitous language*) và đủ chính xác.

Hãy thử diễn đạt tên dưới dạng một câu đã hoàn tất:

> `InventoryReserved` nghĩa là số lượng tồn kho cần thiết đã được giữ thành công cho một yêu cầu xác định.

Nếu câu thật sự đúng sau khi event được phát, tên có cơ sở. Nếu lượng tồn kho mới chỉ **được yêu cầu giữ**, tên `InventoryReserved` là quá sớm.

### Đừng dựa vào hậu tố `Event` để tạo ngữ nghĩa

Cả `OrderConfirmed` và `OrderConfirmedEvent` đều có thể là tên type hợp lệ. Nhưng `OrderEvent`, `ProcessOrderEvent` và `DataChangedEvent` vẫn mơ hồ dù có hậu tố `Event`.

Một convention nên giải quyết sự nhất quán trong toàn module. Ví dụ, team có thể dùng `OrderConfirmed` cho mọi domain event và chỉ thêm `Event` ở các loại thông báo hạ tầng nếu thật sự cần. Không nên trộn `OrderConfirmed`, `PaymentCapturedEvent` và `ShipmentDispatchedMessage` nếu các hậu tố không mang ý nghĩa kỹ thuật khác nhau.

## 3. Phân biệt event, command, state và action của listener

Bốn dạng tên sau có thể cùng tồn tại nhưng đại diện cho các khái niệm khác nhau:

| Loại | Câu hỏi | Ví dụ | Đơn vị sở hữu |
| --- | --- | --- | --- |
| **Command** | “Hãy thực hiện điều gì?” | `ConfirmOrder` | Module xử lý yêu cầu xác nhận |
| **State** | “Đang ở trạng thái nào?” | `OrderStatus.CONFIRMED` | Aggregate Order |
| **Event** | “Điều gì đã xảy ra?” | `OrderConfirmed` | Module Orders |
| **Consumer action** | “Sau khi biết sự thật đó, tôi làm gì?” | `sendConfirmationEmail()` | Module Notifications |

Từ đó suy ra ba nguyên tắc:

1. **Event không ra lệnh cho consumer.** `SendConfirmationEmail` là lệnh/tác vụ; publisher nên phát `OrderConfirmed` khi sự thật nghiệp vụ là đơn đã được xác nhận.
2. **Event không đơn giản là trường state.** `CONFIRMED` chỉ là một giá trị hiện tại, còn `OrderConfirmed` ghi nhận một mốc đã xảy ra. Nếu sau đó đơn bị hủy, `OrderConfirmed` vẫn là một sự thật lịch sử.
3. **Event không được đặt theo một callback kỹ thuật vô nghĩa với nghiệp vụ.** `OrderRepositorySaved` không thay thế cho `OrderPlaced` hoặc `OrderConfirmed`.

Một tên dạng `OrderConfirmationRequested` **có thể** là event đúng nếu hệ thống đã ghi nhận thành công một yêu cầu xác nhận và chính sự thật “đã nhận yêu cầu” có ý nghĩa nghiệp vụ. Tuy nhiên, nó không đồng nghĩa `OrderConfirmed` và không cho phép consumer giả định yêu cầu đã được duyệt.

~~~mermaid
flowchart TD
    A["Command: ConfirmOrder"] --> B{"Điều kiện xác nhận hợp lệ?"}
    B -->|"Không"| C["Từ chối / phản hồi nghiệp vụ"]
    B -->|"Có"| D["Orders chuyển state sang CONFIRMED"]
    D --> E["Event: OrderConfirmed"]
    E --> F["Notifications: lên lịch thông báo"]
    E --> G["Fulfillment: chuẩn bị xử lý"]
~~~

## 4. Quy trình sáu bước để chọn tên event

Đặt tên trước khi định nghĩa rõ nghiệp vụ thường dẫn đến những tên tổng quát như `OrderUpdated`. Quy trình sau giúp đi từ câu chuyện nghiệp vụ tới tên có thể kiểm chứng.

### Bước 1 — Xác định module sở hữu sự thật

Tự hỏi: **module nào có quyền xác nhận điều đã xảy ra?**

- `OrderConfirmed`: module Orders.
- `PaymentCaptured`: module Payments hoặc module tích hợp thanh toán đã xác thực kết quả.
- `InventoryReserved`: module Inventory.
- `ShipmentDelivered`: module Shipping/Fulfillment, theo cách tổ chức domain thực tế.

Một consumer chỉ nên phản ứng với sự kiện thuộc quyền sở hữu của publisher. Ví dụ, module Notifications không nên phát `OrderConfirmed` chỉ vì nó đã gửi email xác nhận; nó không có quyền quyết định trạng thái đơn hàng.

### Bước 2 — Chọn mốc nghiệp vụ chính xác

Cần biết trạng thái **trước**, thao tác hoặc điều kiện **gây chuyển**, và trạng thái **sau**.

Ví dụ vòng đời đơn:

~~~text
DRAFT --(khách gửi đơn)--> PLACED
PLACED --(được chấp nhận)--> CONFIRMED
CONFIRMED --(đã giao đủ)--> COMPLETED
~~~

Nếu `OrderPlaced` đã được phát ở bước khách gửi đơn, không dùng lại `OrderPlaced` cho bước đơn được duyệt. Hai sự kiện này là hai mốc riêng có thể mang ý nghĩa khác nhau với Inventory, Payments và Notifications.

### Bước 3 — Viết một câu theo mẫu “đã xảy ra”

Mẫu kiểm tra:

> “Sau khi [điều kiện nghiệp vụ] thành công, [chủ thể] đã [kết quả], nên module [owner] phát [EventName].”

Ví dụ:

> “Sau khi cổng thanh toán xác nhận capture thành công, giao dịch đã được thu tiền, nên Payments phát `PaymentCaptured`.”

Nếu chưa có bằng chứng capture thành công, không phát sự kiện đó, kể cả khi đã gửi HTTP request hoặc thấy kết quả timeout.

### Bước 4 — Chọn danh từ và động từ theo ubiquitous language

- **Danh từ** thường là `Order`, `Payment`, `Invoice`, `Shipment`, `Subscription`.
- **Động từ/kết quả** là `Placed`, `Confirmed`, `Captured`, `Issued`, `Dispatched`, `Cancelled`.
- Dùng tiếng Anh nhất quán nếu tên class của codebase dùng tiếng Anh; tài liệu tiếng Việt giải thích nghiệp vụ nhưng không thay tên class liên tục.
- Nếu domain có nhiều loại đơn hàng hoặc nhiều khái niệm cùng tên, thêm một qualifier **có ý nghĩa** như `PurchaseOrderApproved`, `ReturnRequestApproved`.

Không cần đặt mọi event theo một danh từ kỹ thuật như `Entity` hoặc `Record`. Người đọc cần nhận ra **đối tượng nghiệp vụ** ngay trong tên.

### Bước 5 — Loại bỏ suy diễn hoặc hành động chưa được xác nhận

Hỏi:

- Tên này có vô tình tuyên bố thanh toán đã hoàn tất trong khi mới authorize?
- Nó có mô tả một tác vụ của consumer thay vì sự thật của publisher?
- Nó có nói quá kết quả sau một timeout hay một kết quả “pending”?
- Nó có khiến consumer nghĩ rằng mọi module khác đã xử lý xong?

Nếu có, hãy đổi tên hoặc chia thành các event của các mốc khác nhau.

### Bước 6 — Thử tên với ít nhất hai consumer

Giả sử Orders phát `OrderConfirmed`. Hãy hỏi một lập trình viên Fulfillment và một lập trình viên Reporting họ hiểu gì. Nếu cả hai đều hiểu “Orders đã chấp nhận đơn” và không cho rằng đơn đã giao hoặc đã thanh toán, tên có khả năng tái sử dụng cao.

Một tên như `StartShippingEvent` có thể hợp lý với Shipping nhưng vô nghĩa với Reporting; nó cũng khiến Orders quyết định công việc của Shipping. Sử dụng `OrderReadyForFulfillment` chỉ khi **sẵn sàng giao hàng** là một mốc nghiệp vụ do Orders xác định, với điều kiện rõ ràng.

## 5. Naming convention đề xuất cho team

Có thể đưa các quy ước sau vào chuẩn code review của module:

| Quy tắc | Nên | Tránh | Lý do |
| --- | --- | --- | --- |
| Tên type Java | `OrderConfirmed` | `order_confirmed` | Theo convention PascalCase |
| Mốc đã xảy ra | `PaymentCaptured` | `CapturePayment` | Phân biệt event với command |
| Nghĩa cụ thể | `InvoiceIssued` | `InvoiceProcessed` | Tránh động từ đa nghĩa |
| Chủ thể rõ | `SubscriptionCancelled` | `Cancelled` | Không thiếu danh từ nghiệp vụ |
| Không gắn consumer | `OrderConfirmed` | `SendOrderMail` | Publisher không điều khiển listener |
| Không gắn transport | `InventoryReserved` | `KafkaInventoryReserved` | Event là contract nghiệp vụ |
| Không dùng chi tiết ORM | `CustomerAddressChanged` | `CustomerRowUpdated` | Tránh rò rỉ persistence |
| Không rút gọn khó hiểu | `PaymentCaptured` | `PmtCptdEvt` | Dễ đọc và tra cứu |
| Tên phải đồng nghĩa điều kiện phát | `RefundCompleted` khi đã hoàn tiền | `RefundCompleted` ngay lúc gửi yêu cầu | Ngăn consumer xử lý sai |

### Có nên thêm suffix `Event`?

Nếu team muốn, cả `OrderConfirmedEvent` và `OrderConfirmed` đều có thể dùng. Điều cần thống nhất là:

- Suffix không thay thế phần tên diễn tả sự thật.
- Hậu tố có thể giúp phân biệt type khi một codebase đã có class tên giống nhau, nhưng không nên dùng để che lấp ranh giới package.
- Khi các module đã import tên type công khai, đổi convention đồng loạt có thể tạo công việc migration không cần thiết. Ưu tiên consistency, lợi ích thực tế và tương thích contract.

### Có nên dùng `Created`, `Updated` hoặc `Deleted`?

Các tên này **không sai về cú pháp**. Chúng có thể đủ nếu sự kiện thực sự dùng cho audit kỹ thuật hoặc một event bao quát việc thay đổi dữ liệu. Tuy nhiên, đối với giao tiếp nghiệp vụ giữa module, nên cố gắng mô tả biến cố cụ thể hơn:

- `OrderCreated` có thể chỉ mang nghĩa tạo row hoặc khởi tạo đơn nháp; `OrderPlaced` nói rõ khách đã đặt đơn.
- `CustomerUpdated` không cho biết địa chỉ, email hay trạng thái khách thay đổi; `CustomerAddressChanged` rõ hơn khi đó là mốc cần phản ứng.
- `InvoiceDeleted` có thể là thao tác dữ liệu; trong nhiều quy trình kế toán, khái niệm nghiệp vụ phù hợp có thể là `InvoiceVoided`, tùy chính sách thực tế.

Đừng đổi tên thành từ “nghe có vẻ nghiệp vụ” nếu team chưa xác định chính xác điều kiện phát. Cần hỏi chủ sở hữu domain để chọn đúng thuật ngữ.

## 6. Bảng sửa tên theo tình huống thực tế

| Tên đang được đề xuất | Cần làm rõ | Tên đề xuất theo tình huống đã làm rõ |
| --- | --- | --- |
| `OrderProcessing` | Đơn đã được chấp nhận hay mới vào hàng đợi? | `OrderAcceptedForProcessing` hoặc `OrderQueued` |
| `OrderCompleted` | “Hoàn tất” nghĩa là giao hàng hay đóng hồ sơ? | `ShipmentDelivered` hoặc `OrderClosed` nếu domain xác nhận đúng như vậy |
| `PaymentSuccess` | Auth, capture hay settlement? | `PaymentAuthorized`, `PaymentCaptured`, `PaymentSettled` |
| `StockUpdated` | Hàng đã được giữ, xuất hay hoàn lại? | `InventoryReserved`, `InventoryDeducted`, `InventoryReleased` |
| `CustomerEvent` | Khách đã làm điều gì? | `CustomerRegistered`, `CustomerEmailChanged` |
| `CreateShipment` | Chỉ ra lệnh tạo shipment? | `OrderReadyForFulfillment` nếu thực sự đã đủ điều kiện |
| `InvoiceSaveEvent` | Chỉ save dữ liệu hay phát hành hóa đơn? | `InvoiceIssued` nếu đã phát hành |
| `PaymentFailed` | Bị từ chối hay chỉ timeout chưa biết kết quả? | `PaymentDeclined` khi có xác nhận bị từ chối |
| `SendEmailDone` | Được đưa vào queue, email provider chấp nhận hay thực sự delivered? | `EmailQueued`, `EmailAcceptedByProvider` hoặc `EmailDelivered` theo bằng chứng |
| `RetryOrderEvent` | Retry là thao tác kỹ thuật, đang retry việc gì? | Giữ nguyên event gốc và retry publication; chỉ tạo event nghiệp vụ mới nếu có một sự thật mới |

Một tên mới chỉ hợp lệ khi **nghĩa thực tế của sự kiện** khớp tên. Bảng trên là gợi ý để phân tích, không phải phép đổi tên tự động theo chuỗi ký tự.

## 7. Ví dụ xuyên suốt: đặt tên các mốc thanh toán đơn hàng

Giả sử khách mua một sản phẩm với quy trình: đặt đơn, yêu cầu thanh toán, cổng thanh toán ủy quyền, thu tiền, giữ hàng và giao hàng.

~~~mermaid
flowchart TD
    A["Orders: OrderPlaced"] --> B["Payments: PaymentInitiated"]
    B --> C{"Nhà cung cấp thanh toán xác nhận?"}
    C -->|"Authorized"| D["Payments: PaymentAuthorized"]
    D --> E["Payments: PaymentCaptured"]
    C -->|"Declined"| F["Payments: PaymentDeclined"]
    E --> G["Orders: OrderPaid"]
    G --> H["Inventory: InventoryReserved"]
    H --> I["Fulfillment: ShipmentPrepared"]
    I --> J["Fulfillment: ShipmentDispatched"]
~~~

Sơ đồ chỉ biểu diễn một hành trình có thể xảy ra. Không nên giả định mọi nhà cung cấp thanh toán hoặc mọi doanh nghiệp đều đi qua đúng các mốc này, hoặc toàn bộ chúng luôn được xử lý tự động theo thứ tự.

### Tên nào phản ánh sự thật của module nào?

- `OrderPlaced` thuộc Orders và diễn tả việc đặt đơn.
- `PaymentInitiated` thuộc Payments và chỉ khẳng định yêu cầu thanh toán đã được khởi tạo/ghi nhận.
- `PaymentAuthorized` và `PaymentCaptured` là **hai mốc khác nhau** của quy trình thanh toán.
- `OrderPaid` có thể thuộc Orders, nếu Orders định nghĩa việc “đã thanh toán” dựa trên dữ liệu thanh toán được xác nhận; nó không tự đồng nghĩa với `PaymentSettled`.
- `InventoryReserved` thuộc Inventory và chỉ khẳng định việc giữ hàng, không tự đồng nghĩa đã giao.
- `ShipmentDispatched` chỉ nên phát khi hoạt động bàn giao vận chuyển thực sự hoàn tất theo định nghĩa của Fulfillment.

Nếu chỉ có một mốc thanh toán mà hệ thống kinh doanh coi là “thu tiền thành công”, có thể đơn giản hóa các event, nhưng phải tài liệu hóa rõ **mốc duy nhất đó là gì**.

### Ba sự kiện tên giống nhau nhưng nghĩa khác nhau

```text
PaymentRequested    : yêu cầu xử lý thanh toán đã được ghi nhận
PaymentAuthorized   : nguồn tiền/ủy quyền được xác nhận theo quy tắc provider
PaymentCaptured     : việc capture được provider xác nhận thành công
```

Nếu listener của Logistics chuẩn bị xuất hàng khi nghe `PaymentRequested`, nó có thể xuất hàng trước khi khách thanh toán. Vì thế, naming convention giúp bảo vệ business invariant, không chỉ giúp code đẹp.

## 8. Event type đặt ở đâu trong Spring Modulith?

Với quy ước phát hiện module mặc định, một module thường tương ứng một package trực tiếp dưới package gốc của ứng dụng. Type event cho module khác sử dụng nên thuộc **API công khai của module** hoặc một named interface được công bố rõ ràng.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderConfirmed.java             # contract công khai
│   └── internal
│       ├── OrderApplicationService.java
│       ├── Order.java
│       └── OrderRepository.java
├── notifications
│   └── internal
│       └── OrderConfirmedListener.java
└── fulfillment
    └── internal
        └── OrderConfirmedListener.java
```

Tên type `com.example.shop.orders.OrderConfirmed` cho biết **module sở hữu contract**. Không cần đặt class trong `orders.internal` rồi cho Notifications import; như vậy consumer đã phụ thuộc vào implementation detail của module khác.

Nếu team thích đưa event vào package `orders.events`, có thể công bố package này bằng `@NamedInterface` của Spring Modulith ở `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
```

Khi đó `OrderConfirmed` nằm trong package công khai có tên `events`. Cách tổ chức package phải thống nhất với cấu hình module thực tế; không phải mọi package con tự động thuộc API public của Spring Modulith.

### Tên sự kiện và tên Java package không có cùng nhiệm vụ

Tên **class** trả lời “sự thật gì vừa xảy ra?”. Tên **package** trả lời “sự thật do ai sở hữu, API nằm ở đâu?”. Cả hai cùng cần thiết để thể hiện ranh giới.

Ví dụ một event không cần đổi tên thành `OrdersOrderConfirmed` nếu package `orders` đã xác định rõ ngữ cảnh. Tuy nhiên, nếu có hai ngữ cảnh đều có `OrderConfirmed` nhưng nghĩa khác nhau, dùng package/namespace riêng là điều cần thiết; không ép chúng dùng chung một contract chỉ vì cùng tên đơn giản.

## 9. Mô hình event Java với tên phản ánh nghiệp vụ

Ví dụ cho event “đơn đã được xác nhận”:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
```

Tách biệt ba tầng định danh:

- **Tên type** `OrderConfirmed`: loại sự thật nghiệp vụ.
- **`eventId`**: định danh một lần phát sinh event; khi giao lại đúng event đó phải giữ cùng ID.
- **`orderId`**: định danh aggregate liên quan; một Order có thể phát nhiều loại sự kiện qua các mốc nghiệp vụ khác nhau.

`occurredAt` ghi thời điểm publisher ghi nhận sự kiện. Nó hữu ích cho truy vết, nhưng không tự bảo đảm thứ tự xử lý giữa các listener bất đồng bộ. Khi thực sự cần ordering theo aggregate, thiết kế thêm cơ chế version/sequence phù hợp với nguồn sở hữu state.

Tất cả trường cần có định nghĩa: `confirmedAmount` là số tiền đã chốt ở mốc xác nhận, không được dùng như giá trị tổng tiền hiện tại luôn đồng bộ. Payload là dữ liệu của một sự thật tại thời điểm phát sinh; tránh gửi nguyên entity JPA hoặc object mutable sang module khác.

## 10. Tên phải khớp vị trí phát event và transaction

Hãy nhìn vào publisher:

```java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isConfirmed()) {
            return; // Không có chuyển trạng thái mới.
        }

        order.confirm(); // Có thể từ chối nếu điều kiện domain chưa hợp lệ.
        orders.save(order);

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(), order.getId(), Instant.now(clock)
        ));
    }
}
```

Ví dụ giả định các type `Order`, `OrderRepository` và bean `Clock` đã tồn tại. `Order.confirm()` chịu trách nhiệm kiểm tra nghiệp vụ trước khi đổi state. Publisher chỉ tạo `OrderConfirmed` sau khi lời gọi domain xác nhận thành công.

**Điểm cần nhớ:** `events.publishEvent(...)` xảy ra trong transaction đang mở, nên lời gọi publish chưa đồng nghĩa transaction đã commit. Nếu consumer cần phản ứng **sau khi state của Orders đã commit**, có thể dùng transactional event listener ở phase `AFTER_COMMIT` hoặc `@ApplicationModuleListener`.

Ví dụ listener thuộc Notifications:

```java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedListener {
    private final NotificationService notifications;

    OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.scheduleIfAbsent(event.orderId(), event.eventId());
    }
}
```

`@ApplicationModuleListener` hỗ trợ listener chạy bất đồng bộ, sau commit và trong transaction riêng. `scheduleIfAbsent` là phương thức minh họa phải được triển khai theo quy tắc của Notifications, có bảo vệ idempotency và trạng thái gửi phù hợp.

Nếu Orders rollback, transactional listener sau commit không nên xử lý `OrderConfirmed` như một sự thật đã được commit. Nếu Orders đã commit nhưng Notifications lỗi, tên `OrderConfirmed` vẫn đúng: lỗi gửi thông báo không thay đổi sự thật đơn đã được xác nhận.

### Đừng đặt tên dựa trên kết quả của listener

Một listener nhận `OrderConfirmed` để **lên lịch** email. Không nên gọi event đầu vào là `OrderConfirmationEmailSent` vì tên ấy khẳng định một hành động chưa xảy ra. Khi Notifications thật sự hoàn thành một mốc, nó mới có thể phát event thuộc domain của mình, ví dụ `OrderConfirmationEmailQueued` hoặc `OrderConfirmationEmailAcceptedByProvider`, với tiêu chí phát rõ ràng.

## 11. Tên event trong xử lý lỗi, retry và công bố lại

Event là lời khẳng định về nghiệp vụ; publication là một tiến trình kỹ thuật. Hai vấn đề có tên gọi khác nhau:

| Thực thể | Ví dụ | Tương ứng câu hỏi |
| --- | --- | --- |
| Domain event | `OrderConfirmed` | Đơn hàng đã được xác nhận chưa? |
| Publication record | Một publication đang chờ Notifications xử lý | Event đã được consumer đó xử lý hoàn tất chưa? |
| Retry attempt | Lần thử giao lại `OrderConfirmed` | Có cần thử xử lý lại publication đang lỗi? |
| Consumer state | `Notification.status = PENDING` | Module Notifications đang ở bước nào? |

**Không tạo event mới mang tên `OrderConfirmedRetry` chỉ vì một consumer xử lý thất bại.** Hãy xử lý lại publication của **cùng** sự kiện, giữ `eventId` cũ và bảo vệ consumer trước việc nhận trùng.

Trong Spring Modulith, **Event Publication Registry** có thể giúp theo dõi publication tới transactional listener và những publication chưa hoàn thành khi cấu hình cơ chế lưu trữ phù hợp. Hệ thống có thể vận hành retry/republication theo khả năng và cấu hình của phiên bản đang dùng. Registry không tự bảo đảm exactly-once, vì consumer vẫn có thể nhận lại sự kiện sau khi đã hoàn tất một phần xử lý.

Nếu Payments cần thông báo rằng một giao dịch **bị từ chối vì lý do nghiệp vụ**, `PaymentDeclined` có thể là một event riêng. Nếu HTTP call timeout và chưa biết giao dịch thành công hay thất bại, không nên phát `PaymentFailed` như một khẳng định chắc chắn khi chưa đối soát kết quả.

Tên `PaymentFailed` chỉ phù hợp khi team định nghĩa rõ failure là kết quả cuối cùng nào và có bằng chứng rằng kết quả ấy đã xảy ra. Tương tự, `ShipmentDeliveryFailed` cần phân biệt nỗ lực giao thất bại với toàn bộ đơn hàng không thể giao.

## 12. Xử lý thay đổi ý nghĩa, đổi tên và version

Khi một event đã được module khác subscribe, tên, payload và điều kiện phát trở thành API. Đổi tên một Java class làm thay đổi import và có thể ảnh hưởng dữ liệu serialized của các publication đã lưu.

### Trường hợp chỉ cần làm rõ tài liệu

`OrderPlaced` được phát sau khi Orders tiếp nhận thành công một đơn. Team thêm consumer mới để xây báo cáo nhưng không thay mốc nghiệp vụ. Có thể giữ nguyên tên và làm rõ tài liệu contract, field và test.

### Trường hợp phải phân tách mốc

Ban đầu hệ thống dùng `OrderCompleted` cho lúc đơn được đóng gói. Sau đó nghiệp vụ bổ sung khâu giao hàng và “completed” nay được hiểu là đã giao. Giữ cùng tên cho hai ý nghĩa khác nhau sẽ phá vỡ các consumer đang nghe.

Có thể chọn:

- `OrderPacked` khi đóng gói hoàn tất.
- `ShipmentDelivered` khi giao hàng được xác nhận thành công.
- `OrderCompleted` chỉ khi điều kiện hoàn tất của Orders thỏa mãn và được định nghĩa công khai.

Việc chuyển đổi nên bao gồm phân tích consumer hiện có, thời gian tồn tại của publication cũ, dữ liệu event được lưu, serialization và chiến lược chuyển tiếp phù hợp. Không đổi tên máy móc theo một bảng find/replace rồi coi contract đã được migration an toàn.

### Tên event với version trong integration event

Với event chỉ dùng nội bộ, thường ưu tiên tên theo nghiệp vụ ổn định và quản lý schema thay vì thêm hậu tố phiên bản vào mọi type. Nếu event được phát ra Kafka/broker cho hệ thống khác, convention như `order.confirmed.v1` ở message type hoặc metadata có thể hữu ích tùy contract liên hệ; **transport schema version khác với ý nghĩa nghiệp vụ**.

Không tạo `OrderConfirmedV2` chỉ để thêm một field trong Java nếu cơ chế tương thích còn có thể được giữ. Nhưng khi **ý nghĩa mốc nghiệp vụ thay đổi**, cần xem lại contract, có thể phải đặt tên khác chứ không chỉ tăng số version.

## 13. Đặt tên cho event tổng quát và event audit

Không phải event nào cũng cần nhiều ngữ nghĩa domain. Một hệ thống audit có thể cần ghi lại mọi thay đổi state:

```java
public record OrderStatusChanged(
        UUID eventId,
        UUID orderId,
        String previousStatus,
        String newStatus
) {}
```

Tên `OrderStatusChanged` mô tả một thay đổi tổng quát và có thể phù hợp cho audit hoặc read model. Nhưng nếu Fulfillment cần biết “đã được thanh toán”, đừng ép nó tự so sánh `newStatus.equals("PAID")` rồi suy ra tất cả quy tắc. Một event cụ thể như `OrderPaid` thường truyền ý nghĩa đúng hơn cho nghiệp vụ phụ thuộc mốc đó.

Có thể dùng hai loại event khác nhau nếu thực sự có hai mục đích:

- Event tổng quát phục vụ audit hoặc đồng bộ dữ liệu.
- Event nghiệp vụ cụ thể phục vụ giao tiếp có ý nghĩa với các module khác.

Đây là lựa chọn thiết kế, không phải yêu cầu phát **hai event cho mọi thay đổi**. Quan trọng là tránh trùng lặp không cần thiết và định nghĩa rõ publisher sở hữu mỗi contract.

### Domain event khác technical event

Một event kỹ thuật như `DatabaseConnectionLost` có thể dùng cho giám sát, còn `OrderConfirmed` là sự thật nghiệp vụ. Không nên đặt cả hai vào cùng một namespace mang nghĩa “domain events” nếu các consumer và policy của chúng khác nhau.

Cũng không đổi `OrderConfirmed` thành `KafkaOrderConfirmed` chỉ vì đổi cách vận chuyển. Spring application event mặc định nằm trong tiến trình; nếu cần externalization ra ngoài ứng dụng, có thể dùng các cơ chế integration bổ sung nhưng vẫn nên bảo toàn ngữ nghĩa tên.

## 14. Kiểm thử sự đúng đắn của tên event

Một tên chỉ có giá trị khi code phát event đúng thời điểm. Test nên kiểm tra **cả điều kiện nghiệp vụ lẫn sự kiện đã publish**:

| Tình huống | Kỳ vọng |
| --- | --- |
| Đơn đủ điều kiện xác nhận và transaction commit | Có `OrderConfirmed` tương ứng với lần xác nhận thành công |
| Đơn không hợp lệ | Không phát `OrderConfirmed` như một sự thật đã xảy ra |
| Gọi `confirm` lần hai nhưng không đổi state | Không phát lần xác nhận mới |
| Hai request cạnh tranh xác nhận | Cơ chế đồng thời bảo vệ invariant, tránh sự kiện nghiệp vụ trùng |
| Transaction rollback | Listener `AFTER_COMMIT` không xử lý việc xác nhận bị rollback |
| Publication được giao lại | Listener idempotent, không nhân đôi side effect |
| Event đến trễ sau `OrderCancelled` | Consumer không suy diễn trạng thái hiện tại chỉ từ event cũ |
| Thay đổi tên hoặc trigger | Test hợp đồng giữa các module được cập nhật cùng chiến lược migration |

Một cách để kiểm tra ranh giới module là dùng Spring Modulith:

```java
import com.example.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {
    @Test
    void dependenciesStayWithinModuleAPIs() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra kiến trúc giúp phát hiện một số dạng phụ thuộc sai ranh giới (ví dụ consumer import type nội bộ). Nhưng nó **không** chứng minh `OrderConfirmed` chỉ được phát khi xác nhận thành công. Cần thêm test nghiệp vụ và integration test.

Với xử lý sau commit và bất đồng bộ, hãy dùng test chờ **điều kiện cuối cùng với timeout hữu hạn**. Đừng giả định listener đã xử lý xong ngay khi `publishEvent` trả về. Nếu test bọc trong một transaction tự rollback thì listener `AFTER_COMMIT` có thể không chạy.

## 15. Bài thực hành: đặt tên từ mô tả nghiệp vụ

### Bài 1 — Hệ thống đăng ký khóa học

Quy trình:

1. Học viên gửi yêu cầu đăng ký.
2. Nền tảng chấp nhận đăng ký.
3. Thanh toán được xác nhận.
4. Học viên được cấp quyền truy cập.
5. Học viên hoàn thành khóa học.

Đề xuất các tên như `EnrollmentRequested`, `EnrollmentAccepted`, `PaymentCaptured`, `CourseAccessGranted`, `CourseCompleted`, **nhưng chỉ dùng tên tương ứng khi mốc đúng như mô tả**. Viết cho mỗi tên: module sở hữu, điều kiện phát, một điều consumer không được suy ra.

### Bài 2 — Sửa tên mơ hồ

Cho danh sách:

```text
UpdateOrderEvent
PaymentDoneEvent
NotifyCustomerEvent
InventoryUpdatedEvent
ShipmentProcessEvent
```

Với mỗi tên, hãy chỉ ra: đây là command hay event? Điều gì thực tế đã xảy ra? Consumer nào quan tâm? Sau đó đề xuất một hoặc nhiều tên mới dựa trên các mốc đã xác định, tránh đổi tên theo phỏng đoán.

### Bài 3 — Có nên phát event “thất bại”?

Một provider trả HTTP timeout khi hệ thống gọi capture thanh toán. Thảo luận vì sao **không thể kết luận** `PaymentCaptureFailed` chỉ từ timeout; đề xuất state theo dõi kết quả chưa rõ và một cơ chế đối soát. Khi provider trả kết quả từ chối chắc chắn, tên event nào phù hợp hơn?

### Bài 4 — Thêm consumer mới

Orders phát `OrderConfirmed` cho Notifications. Nay team muốn module Loyalty cộng điểm khi đơn thanh toán xong. Loyalty có nên dựa trên `OrderConfirmed`? Điều kiện được cộng điểm là gì? Có cần một event từ Payments hoặc `OrderPaid` từ Orders không? Câu trả lời phải dựa trên nghiệp vụ, không dựa trên mong muốn tái sử dụng tên có sẵn.

## 16. Checklist để review tên event

Trước khi merge một event contract mới, người review có thể dùng danh sách sau:

- [ ] Tên thể hiện một sự thật nghiệp vụ **đã xảy ra**, không ra lệnh cho consumer.
- [ ] Có danh từ/chủ thể nghiệp vụ rõ ràng.
- [ ] Động từ/kết quả được dùng nhất quán với thuật ngữ của domain.
- [ ] Mốc phát hành cụ thể, có thể viết câu “chỉ phát khi…” và viết test cho câu đó.
- [ ] Publisher đúng module sở hữu sự thật; consumer không import repository/entity nội bộ.
- [ ] Không đánh đồng “đã yêu cầu”, “đang xử lý”, “đã chấp thuận” và “đã hoàn tất”.
- [ ] Tên không tự gắn vào email, broker, retry hay implementation detail không thuộc sự thật nghiệp vụ.
- [ ] Payload chỉ chứa thông tin cần thiết và nêu rõ nghĩa của dữ liệu tại thời điểm phát.
- [ ] Điều kiện rollback, duplicate delivery, xử lý muộn được hiểu đúng.
- [ ] Nếu đã có consumer, thay đổi tên/ý nghĩa đã được đánh giá tương thích và migration.

**Ghi nhớ:** `OrderConfirmed` không có nghĩa “hãy xác nhận đơn”, “đơn hiện vẫn được xác nhận” hay “email đã gửi”. Nó có nghĩa: **Orders đã xác nhận đơn ở một mốc nghiệp vụ xác định**. Một tên event rõ ràng giúp Spring Modulith giữ các module ít phụ thuộc, còn transaction sau commit, registry, retry, idempotency và kiểm thử giúp thông điệp ấy được xử lý đáng tin cậy.
