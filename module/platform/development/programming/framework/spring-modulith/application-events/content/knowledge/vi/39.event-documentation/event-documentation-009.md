# Quy ước đặt tên

Tên event, Java type, topic, listener và metadata là một phần của hợp đồng giao tiếp giữa các module. Một tên rõ ràng giúp người đọc hiểu nghiệp vụ nào đã xảy ra, module nào sở hữu sự kiện và consumer cần phản ứng với điều gì. Một tên mơ hồ hoặc gắn chặt với chi tiết triển khai có thể khiến event khó tái sử dụng, khó quan sát và khó duy trì khi hệ thống thay đổi.

Trong Spring Modulith, application event thường được biểu diễn bằng Java type và được phát qua `ApplicationEventPublisher`. Khi cần đưa event ra broker, ứng dụng có thể dùng cơ chế externalization như `@Externalized`. Cần đặt tên nhất quán cho cả event nội bộ, hợp đồng tích hợp, destination/topic và listener, đồng thời hiểu rằng các tên này có phạm vi và vòng đời khác nhau.

## 1. Nguyên tắc đặt tên event

Một tên event tốt nên thể hiện một sự thật nghiệp vụ đã xảy ra. Tên cần ngắn gọn, dùng thuật ngữ mà domain expert và các module liên quan cùng hiểu, và không phụ thuộc vào cách event được lưu hoặc vận chuyển.

Các nguyên tắc chính:

- **Diễn đạt sự kiện đã xảy ra:** dùng tên quá khứ hoặc cụm danh từ mô tả fact, chẳng hạn `OrderPlaced`, `PaymentCaptured`, `ShipmentDispatched`.
- **Dùng ngôn ngữ nghiệp vụ:** chọn thuật ngữ trong domain glossary, tránh tên kỹ thuật như `OrderRowChanged` hoặc `KafkaMessageReceived`.
- **Nêu rõ ý nghĩa:** nếu `OrderUpdated` có thể chỉ nhiều thay đổi khác nhau, hãy dùng tên cụ thể như `OrderAddressChanged` hoặc `OrderCancelled`.
- **Một event, một fact:** event mô tả điều đã xảy ra; consumer quyết định phản ứng thế nào.
- **Ổn định theo thời gian:** tên event không đổi chỉ vì class, package, database table hoặc broker được tổ chức lại.
- **Không gắn tên người nhận vào event:** event mô tả fact của module sở hữu, không phải lệnh gửi riêng cho một listener.
- **Nhất quán số ít/số nhiều:** một event instance thường biểu diễn một fact; dùng danh từ số ít trong tên type.

Ví dụ:

| Tên nên dùng | Lý do |
| --- | --- |
| `OrderPlaced` | Nêu rõ đơn hàng đã được đặt. |
| `PaymentCaptured` | Phân biệt thanh toán đã thu tiền với yêu cầu thanh toán. |
| `OrderAddressChanged` | Nêu rõ trường nghiệp vụ đã thay đổi. |
| `ShipmentDispatched` | Diễn đạt sự kiện giao hàng đã được bàn giao. |
| `SubscriptionCancelled` | Nêu rõ trạng thái nghiệp vụ đã xảy ra. |

Tránh các tên như `OrderEvent`, `OrderChanged`, `ProcessOrder`, `UpdateOrderMessage` hoặc `HandlePayment`. Chúng không nói rõ fact, lẫn lộn event với command/handler hoặc phụ thuộc vào cách triển khai.

## 2. Phân biệt command, event và query

Command, event và query có mục đích khác nhau nên cần quy ước tên khác nhau:

| Loại | Ý nghĩa | Cách đặt tên thường dùng | Ví dụ |
| --- | --- | --- | --- |
| Command | Yêu cầu hệ thống thực hiện hành động. | Động từ mệnh lệnh. | `PlaceOrder`, `CapturePayment`, `CancelSubscription`. |
| Event | Sự thật nghiệp vụ đã xảy ra. | Quá khứ hoặc fact noun. | `OrderPlaced`, `PaymentCaptured`, `SubscriptionCancelled`. |
| Query | Yêu cầu đọc dữ liệu. | `Get`, `Find`, `Search`, `List`. | `GetOrderDetails`, `FindAvailableInventory`. |
| Handler/listener | Thành phần phản ứng với command/event. | Động từ mô tả hành động xử lý. | `reserveInventory`, `onOrderPlaced`. |

Ví dụ luồng:

```text
PlaceOrder (command)
    -> OrderManagement xử lý
    -> OrderPlaced (event)
    -> Inventory listener giữ hàng
    -> Payment listener tạo yêu cầu thanh toán
```

Không đặt tên event là `PlaceOrder`, vì tên đó mô tả yêu cầu cần thực hiện. `OrderPlaced` chỉ được phát sau khi nghiệp vụ tạo đơn đã thành công và transaction phù hợp đã commit theo thiết kế.

Tương tự, `PaymentAuthorizationRequested` có thể là một event nếu nó mô tả một yêu cầu đã được tạo và công bố như một fact trong workflow; nhưng nếu nó là yêu cầu consumer phải thực hiện, có thể đó là command/message. Hãy ghi rõ semantics trong tài liệu để người đọc không suy luận chỉ từ hậu tố.

## 3. Chọn tên theo ngôn ngữ domain

Tên event nên dùng thuật ngữ được thống nhất trong domain glossary. Nếu nhóm nghiệp vụ gọi trạng thái là “đã xác nhận”, đừng tự đổi thành “approved” ở một module và “accepted” ở module khác nếu chúng có cùng ý nghĩa.

Một glossary nhỏ có thể ghi:

| Thuật ngữ | Ý nghĩa | Tên event đề xuất |
| --- | --- | --- |
| Đặt đơn | Đơn hàng được tạo và chấp nhận. | `OrderPlaced` |
| Xác nhận thanh toán | Nhà cung cấp thanh toán đã xác nhận thu tiền. | `PaymentCaptured` |
| Từ chối thanh toán | Nhà cung cấp từ chối yêu cầu thanh toán theo kết quả nghiệp vụ. | `PaymentDeclined` |
| Giao hàng đi | Kiện hàng đã được bàn giao cho đơn vị vận chuyển. | `ShipmentDispatched` |
| Hủy đơn | Đơn hàng đã chuyển sang trạng thái hủy hợp lệ. | `OrderCancelled` |

Phân biệt kết quả nghiệp vụ với lỗi kỹ thuật. `PaymentDeclined` là kết quả từ chối thanh toán; timeout kết nối tới payment provider không có nghĩa thanh toán đã bị từ chối. Lỗi kỹ thuật có thể được retry và không nhất thiết tạo ra một domain event mới.

Nếu một thuật ngữ có nhiều nghĩa, hãy định nghĩa rõ trong glossary trước khi tạo event. Không dùng tên event để che giấu sự không thống nhất giữa các module.

## 4. Quy ước tên Java type

Java type của event thường là class hoặc record bất biến, dùng `UpperCamelCase` và danh từ/cụm fact ở dạng số ít. Ví dụ:

```java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        Instant occurredAt) {
}
```

Một số quy tắc:

- Dùng `UpperCamelCase` cho class/record, ví dụ `OrderPlaced`.
- Không thêm hậu tố `Event` nếu tên domain đã thể hiện rõ đó là event và package đã cung cấp ngữ cảnh.
- Nếu hậu tố `Event` giúp phân biệt với một type khác trong cùng package, có thể dùng nhưng phải nhất quán, ví dụ `OrderPlacedEvent`.
- Không dùng hậu tố kỹ thuật như `KafkaMessage`, `JpaEvent`, `Dto` cho domain event.
- Không đặt tên type theo listener, ví dụ `InventoryListenerOrderMessage`.
- Field dùng `lowerCamelCase` và diễn đạt đúng ý nghĩa nghiệp vụ.
- Ưu tiên record hoặc object bất biến để payload không bị thay đổi sau khi publish.

Không đưa toàn bộ dữ liệu entity hoặc object persistence vào event chỉ vì tên type thuận tiện. Event contract nên chứa snapshot/metadata cần thiết cho consumer và tránh phụ thuộc vào JPA mapping.

## 5. Quy ước package và vị trí event

Đặt event gần module sở hữu fact đó. Với Spring Modulith, package structure thể hiện ranh giới module; event công khai cho module khác cần nằm trong phần API mà module cho phép truy cập theo quy ước dự án.

Ví dụ:

```text
com.acme.shop
├── orders
│   ├── OrderManagement.java
│   ├── OrderPlaced.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   └── internal
│       └── InventoryOnOrderPlaced.java
└── notifications
    └── internal
        └── NotificationOnOrderPlaced.java
```

Trong ví dụ, `orders` sở hữu `OrderPlaced`. Module `inventory` và `notifications` có listener riêng để phản ứng. Không chuyển event sang package của consumer chỉ vì consumer cần import type đó; việc đó làm sai quyền sở hữu domain.

Nếu dự án dùng package `events`, có thể đặt event công khai trong package như `com.acme.shop.orders.events`. Hãy áp dụng nhất quán và kiểm tra package đó thuộc API công khai của module theo cấu hình Spring Modulith. Tránh tạo một package `common.events` toàn cục để mọi module tự do thêm event không có owner rõ ràng.

Tên package dùng chữ thường, không dùng dấu gạch ngang hoặc chữ hoa. Tên package thể hiện module/domain, không phản ánh broker hoặc môi trường triển khai.

## 6. Tên event nội bộ và event tích hợp bên ngoài

Không phải application event nào cũng cần trở thành hợp đồng tích hợp. Một event nội bộ có thể phục vụ điều phối trong module hoặc một phản ứng nội bộ; event externalized cần có schema và semantics ổn định hơn vì consumer có thể nằm ngoài ứng dụng.

| Loại | Phạm vi | Yêu cầu tên |
| --- | --- | --- |
| Internal application event | Trong ứng dụng hoặc module theo thiết kế. | Có thể dùng Java type gắn với domain và package sở hữu. |
| Cross-module event | Được module khác trong cùng ứng dụng lắng nghe. | Type công khai, thuật ngữ nghiệp vụ thống nhất, tránh lộ chi tiết nội bộ. |
| Integration event | Được externalize ra broker/hệ thống khác. | Có event type ổn định, schema version và metadata hợp đồng rõ ràng. |

Nếu một event nội bộ được externalize về sau, hãy đánh giá lại payload, tên wire-level, versioning, bảo mật và compatibility. Không mặc định mọi field của event nội bộ đều phù hợp để công bố ra ngoài.

## 7. Tên event type ổn định trên wire

Tên Java class và tên event trên wire có vòng đời khác nhau. Java class có thể được đổi package hoặc refactor; consumer bên ngoài không nên phải đổi theo tên class Java.

Một event type ổn định có thể dùng dạng:

```text
<domain>.<fact-name>
```

Ví dụ:

```text
orders.order-placed
payments.payment-captured
inventory.stock-reserved
shipping.shipment-dispatched
```

Quy ước này dùng chữ thường và kebab-case cho phần fact. Event type là định danh hợp đồng, không phải tên class hay topic bắt buộc. Nếu sử dụng CloudEvents, trường `type` có thể mang định danh này, còn `source`, `id`, `subject` và `time` mang các metadata tương ứng theo hợp đồng CloudEvents.

Không dùng FQCN như `com.acme.shop.orders.OrderPlaced` làm event type công khai nếu consumer không cần phụ thuộc vào Java package. Khi package thay đổi, wire contract sẽ bị đổi theo dù ý nghĩa event không đổi.

## 8. Quy ước version trong tên và schema

Schema version cho biết cách diễn giải payload. Có thể biểu diễn version bằng field `schemaVersion` trong envelope, hoặc gắn suffix vào event type như `.v1`. Chọn một quy tắc chính và tránh lặp version ở nhiều nơi nếu không có lý do rõ.

Ví dụ envelope:

```json
{
  "id": "c8d7f9e0-4f0b-4f44-a5c8-3c8b3e2b1c10",
  "type": "orders.order-placed",
  "schemaVersion": 2,
  "source": "orders",
  "occurredAt": "2026-11-25T10:15:30Z",
  "data": {
    "orderId": "e2a1c5a4-3d62-4d0e-8e65-2a7a2c7a9c10"
  }
}
```

Nếu chọn version trong event type, ví dụ `orders.order-placed.v2`, hãy duy trì quy tắc đó ở mọi producer/consumer và ghi rõ version tương thích. Không tăng version chỉ vì Java class được refactor hoặc đổi tên field nội bộ không xuất hiện trong payload.

Thay đổi ngữ nghĩa, kiểu dữ liệu hoặc cấu trúc không tương thích cần được đánh giá như một thay đổi contract. Thêm field tùy chọn có thể tương thích với nhiều consumer, nhưng vẫn phải xác minh serializer và schema compatibility policy.

## 9. Quy ước tên topic và destination

Topic là tài nguyên vận chuyển do broker quản lý; nó không đồng nghĩa với event type. Một topic có thể chứa nhiều event type cùng domain hoặc một luồng event cụ thể tùy thiết kế partitioning, retention và consumer.

Ví dụ tên topic:

```text
orders.events
payments.events
inventory.stock-events
```

Quy tắc thường dùng:

- Dùng chữ thường.
- Dùng dấu chấm hoặc dấu gạch ngang theo một quy ước nhất quán của nền tảng.
- Không dùng dấu cách, ký tự có dấu hoặc tên môi trường hard-code trong mã nguồn.
- Không đưa tên class Java vào topic.
- Không tạo topic riêng cho từng event type nếu topology, throughput và vận hành không cần điều đó.
- Xác định rõ topic có chứa nhiều loại event hay một loại event; ghi rõ trong tài liệu contract.
- Tên môi trường, tenant hoặc version chỉ thêm khi kiến trúc triển khai thật sự yêu cầu.

Với Kafka, tên topic hỗ trợ chữ và số cùng một số ký tự như `.`, `_` và `-`; dùng chữ thường cùng một separator thống nhất giúp dễ đọc và tránh nhầm lẫn. Không nên đổi topic chỉ vì tên event class thay đổi.

Trong Spring Modulith, `@Externalized` xác định target externalization theo cơ chế tích hợp được cấu hình. Ví dụ:

```java
import org.springframework.modulith.events.Externalized;

@Externalized("orders.events")
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}
```

Chuỗi target là tên/định danh đích theo adapter đang dùng; không mặc định mọi adapter đều ánh xạ trực tiếp chuỗi này thành Kafka topic. Hãy ghi rõ mapping target-to-topic/queue trong cấu hình tích hợp và tránh lặp mapping khác nhau giữa môi trường.

## 10. Tên listener và handler

Tên listener nên thể hiện event mà nó nhận và hành động mà nó thực hiện. Tên class có thể theo mẫu `<Action><Domain>On<Event>` hoặc `<Domain>On<Event>` tùy quy ước nhóm.

Ví dụ:

```java
@Component
class ReserveInventoryOnOrderPlaced {

    @ApplicationModuleListener
    void onOrderPlaced(OrderPlaced event) {
        // Giữ hàng cho đơn hàng.
    }
}
```

Hoặc nếu nhóm dùng tên class theo module:

```java
@Component
class InventoryEventListener {

    @ApplicationModuleListener
    void reserveFor(OrderPlaced event) {
        // Giữ hàng cho đơn hàng.
    }
}
```

Chọn một phong cách và dùng nhất quán. Method name nên là động từ hành động như `reserveFor`, `updateProjection`, `sendConfirmation` hoặc `onOrderPlaced`; tránh tên chung chung như `handle`, `process` nếu không có ngữ cảnh đủ rõ.

Không đặt listener theo công nghệ vận chuyển nếu nó thực sự là application event listener, ví dụ `KafkaOrderPlacedListener` cho một `@ApplicationModuleListener` nội bộ. Chỉ dùng tên Kafka consumer khi thành phần đó trực tiếp nhận record từ Kafka.

## 11. Tên consumer group và subscription

Với broker như Kafka, consumer group biểu diễn một nhóm consumer cùng chia tải cho một logical subscription. Các replica của cùng một ứng dụng xử lý cùng subscription thường dùng chung group ID; hai ứng dụng cần đọc độc lập thường dùng group ID khác nhau.

Một mẫu dễ hiểu:

```text
<application-or-module>-<purpose>
```

Ví dụ:

```text
inventory-reservation
order-search-projection
customer-notifications
```

Không thêm pod ID, hostname hoặc UUID mỗi lần khởi động vào group ID nếu mục tiêu là các replica chia tải cùng một subscription. Nếu group ID thay đổi mỗi lần deploy, consumer có thể tạo group mới và đọc lại dữ liệu theo offset policy, làm tăng tải hoặc phát sinh tác dụng phụ lặp.

Nếu hai read model cần nhận toàn bộ event độc lập, hãy dùng group ID khác nhau. Không dùng chung group chỉ vì chúng thuộc cùng một module.

## 12. Quy ước tên field và metadata

Tên field nên dùng `lowerCamelCase` trong JSON nếu đó là convention của contract. Header của broker thường dùng chữ thường và dấu gạch ngang để dễ đọc, nhưng cần tuân theo chuẩn tích hợp đã chọn.

Một bộ metadata thường gặp:

| Field/header | Ý nghĩa |
| --- | --- |
| `eventId` hoặc CloudEvents `id` | Định danh event ổn định. |
| `eventType` hoặc CloudEvents `type` | Định danh fact nghiệp vụ. |
| `schemaVersion` | Phiên bản schema payload. |
| `occurredAt` hoặc CloudEvents `time` | Thời điểm fact xảy ra. |
| `aggregateId` / `subject` | Aggregate hoặc đối tượng được event mô tả. |
| `aggregateVersion` | Phiên bản thay đổi của aggregate nếu cần ordering. |
| `correlationId` | Liên kết các bước cùng một luồng nghiệp vụ. |
| `causationId` | Event/command trực tiếp gây ra event hiện tại. |
| `traceparent` | Trace context theo W3C Trace Context khi sử dụng. |
| `content-type` | Định dạng payload nếu được truyền qua header. |

Không đặt tên cùng một metadata bằng nhiều biến thể như `event_id`, `eventId`, `EventID` trong cùng một hợp đồng. Nếu tích hợp CloudEvents, ưu tiên các attribute chuẩn của CloudEvents thay vì tạo bản sao cùng ý nghĩa với tên khác.

Giá trị ID không nên mã hóa thông tin nhạy cảm hoặc mang ý nghĩa nghiệp vụ có thể thay đổi. `eventId` nên là định danh opaque; không dùng email, số điện thoại hoặc tên khách hàng làm event ID.

## 13. Quy ước partition key và routing key

Partition key hoặc routing key quyết định event được phân phối tới đâu. Key cần phản ánh ranh giới ordering và tải của nghiệp vụ.

Ví dụ:

| Event stream | Key thường phù hợp | Lý do |
| --- | --- | --- |
| Vòng đời đơn hàng | `orderId` | Giữ event của cùng đơn hàng trong một partition. |
| Giao dịch tài khoản | `accountId` | Duy trì thứ tự cập nhật theo tài khoản. |
| Tồn kho sản phẩm | `sku` hoặc `warehouseId + sku` | Phù hợp với phạm vi tồn kho cần cập nhật tuần tự. |

Đặt tên metadata key nhất quán như `aggregateId` hoặc `partitionKey`, nhưng không nhầm tên field với giá trị key. Tránh key ngẫu nhiên nếu các event của cùng aggregate cần thứ tự. Đồng thời, xem xét hot key: một aggregate có lưu lượng quá lớn có thể làm một partition quá tải.

## 14. Quy ước tên error, retry và dead-letter

Tên lỗi nên phân biệt lỗi kỹ thuật với kết quả nghiệp vụ. Không phải mọi exception đều là event và không phải mọi event có chữ `Failed` đều cần retry.

Ví dụ:

- `PaymentDeclined`: kết quả nghiệp vụ từ chối thanh toán.
- `PaymentProviderUnavailable`: trạng thái kỹ thuật của dependency nếu cần công bố như fact vận hành.
- `OrderCancellationRequested`: yêu cầu hủy, chưa khẳng định đơn đã hủy.
- `OrderCancelled`: đơn đã được hủy thành công.

Tên retry topic/DLT nên gắn với luồng nguồn và có thể nhận diện rõ vai trò:

```text
orders.events.retry
orders.events.dlt
```

Hoặc theo quy ước nền tảng hiện có. Không đặt tên `orders.failed` nếu không rõ đây là event nghiệp vụ, topic lỗi hay metric. Tài liệu cần nêu rõ retention, ai xử lý DLT và cách replay.

## 15. Tên module, API và tài liệu

Tên module nên là danh từ domain, thường dùng chữ thường và số ít/số nhiều theo ngôn ngữ nghiệp vụ đã thống nhất: `orders`, `inventory`, `payments`, `shipping`. Không đặt module theo framework hoặc loại database như `kafka-module` hay `order-postgres` nếu module thực sự sở hữu nghiệp vụ đơn hàng.

API công khai của module nên dùng tên thể hiện use case:

```java
public interface OrderManagement {
    UUID placeOrder(PlaceOrder command);
    void cancelOrder(CancelOrder command);
}
```

Tài liệu event nên có tiêu đề mô tả fact, ví dụ `OrderPlaced`, thay vì tiêu đề chung `Order Event`. Mỗi trang nên ghi owner module, producer, consumer, event type, schema version, key, delivery semantics, retry policy và ví dụ payload.

## 16. Những tên cần tránh

| Tên không rõ | Vấn đề | Tên rõ hơn |
| --- | --- | --- |
| `OrderEvent` | Không nói fact nào xảy ra. | `OrderPlaced`, `OrderCancelled`. |
| `OrderUpdated` | Không biết trường hoặc ý nghĩa thay đổi. | `OrderAddressChanged`, `OrderStatusChanged`. |
| `ProcessOrder` | Có vẻ là command/handler, không phải fact. | `OrderPlaced` nếu đơn đã được tạo. |
| `OrderMessage` | Không phân biệt event, command hay payload vận chuyển. | Tên fact cụ thể. |
| `KafkaOrderPlacedEvent` | Gắn domain event với broker. | `OrderPlaced`; mapping broker nằm ở adapter. |
| `OrderEntityUpdated` | Lộ chi tiết persistence. | Tên fact nghiệp vụ. |
| `PaymentFailed` | Không phân biệt decline nghiệp vụ với lỗi kỹ thuật. | `PaymentDeclined` hoặc tên lỗi cụ thể. |
| `CommonEvent` | Không có owner domain. | Event thuộc module sở hữu fact. |

## 17. Quản lý thay đổi tên đã được công bố

Sau khi event type, topic hoặc header đã được consumer sử dụng, tên đó trở thành một phần của hợp đồng. Đổi tên có thể làm consumer không nhận ra event dù payload không đổi.

Khi cần đổi tên:

1. Xác định mọi producer, listener, consumer group, topic và tài liệu đang dùng tên cũ.
2. Phân biệt đổi tên nội bộ Java với đổi tên wire-level. Nếu chỉ refactor class, giữ event type bên ngoài ổn định.
3. Nếu wire contract buộc phải đổi, hỗ trợ song song tên cũ và mới trong giai đoạn chuyển tiếp.
4. Định nghĩa mapping và thời hạn hỗ trợ tên cũ.
5. Theo dõi consumer đã chuyển đổi và số message còn dùng tên cũ.
6. Chỉ ngừng tên cũ sau khi hết thời gian tương thích, retry và replay.

Không đổi topic chỉ để đồng bộ với tên class mới. Nếu đổi destination, cần kế hoạch chuyển dữ liệu, offset, consumer group, retry/DLT và rollback riêng.

## 18. Quy trình đề xuất khi tạo event mới

Trước khi tạo event, người phát triển và owner module có thể thống nhất theo trình tự:

1. Viết một câu mô tả fact đã xảy ra bằng ngôn ngữ nghiệp vụ.
2. Kiểm tra glossary để dùng thuật ngữ đã tồn tại.
3. Phân biệt đây là command, event hay query.
4. Xác định module sở hữu fact và vị trí package của event.
5. Chọn Java type name theo `UpperCamelCase`.
6. Nếu externalize, chọn event type ổn định độc lập với Java FQCN.
7. Xác định schema version và metadata cần thiết.
8. Chọn target/topic, partition key và consumer group theo topology thực tế.
9. Đặt tên listener theo hành động và event nhận vào.
10. Ghi contract, owner, consumer, retry và ví dụ payload vào tài liệu.

Quy trình này giúp tên nhất quán trước khi consumer bên ngoài phụ thuộc vào hợp đồng.

## Checklist quy ước đặt tên

- [ ] Event name mô tả fact đã xảy ra bằng thuật ngữ domain.
- [ ] Tên event phân biệt rõ với command, query và handler.
- [ ] Java type dùng `UpperCamelCase`, field dùng convention đã thống nhất.
- [ ] Event thuộc package và module sở hữu fact.
- [ ] Internal event được phân biệt với cross-module/integration contract.
- [ ] Wire-level event type ổn định và không phụ thuộc Java FQCN.
- [ ] Schema version có một quy tắc biểu diễn rõ ràng.
- [ ] Topic/destination được phân biệt với event type và có mapping được tài liệu hóa.
- [ ] Listener name mô tả event nhận và hành động thực hiện.
- [ ] Consumer group đại diện cho logical subscription ổn định.
- [ ] Header/metadata có tên nhất quán, không trùng chuẩn đã chọn.
- [ ] Partition key phản ánh ranh giới ordering của aggregate.
- [ ] Error, retry và DLT name không mơ hồ giữa fact nghiệp vụ và hạ tầng.
- [ ] Thay đổi tên đã công bố có compatibility window và kế hoạch chuyển đổi.

Quy ước đặt tên tốt giúp event trở thành hợp đồng dễ hiểu và ổn định giữa các module. Khi tên thể hiện đúng fact, owner domain, wire type, destination và listener có quy tắc riêng nhưng nhất quán, ứng dụng Spring Modulith dễ phát triển, quan sát và tích hợp mà không bị phụ thuộc vào chi tiết triển khai nhất thời.
