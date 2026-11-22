# Fact event, notification event và dữ liệu mang theo sự kiện

Trong kiến trúc event-driven, một event mô tả điều đã xảy ra trong hệ thống. Nhưng việc xác định một event nói lên sự thật nghiệp vụ nào và event mang theo bao nhiêu dữ liệu là hai quyết định thiết kế khác nhau. Một event có thể chỉ thông báo rằng đơn hàng đã thay đổi để consumer tự truy vấn chi tiết; hoặc mang theo snapshot dữ liệu cần thiết để consumer xử lý mà không phải gọi ngược về dịch vụ phát sinh.

Với Apache Kafka, các quyết định này ảnh hưởng tới hợp đồng sự kiện, mức độ phụ thuộc giữa dịch vụ, khả năng replay, độ trễ, tính nhất quán và chi phí lưu trữ. Bài học thuộc phần thiết kế ứng dụng của module KAFKA, tập trung vào cách chọn fact event, notification event và event-carried data trong hệ thống Java/Spring Kafka.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích event như một sự thật nghiệp vụ đã xảy ra và phân biệt event với command.
- Phân biệt ý nghĩa nghiệp vụ của fact event với cách thiết kế payload kiểu notification hoặc event-carried state transfer.
- Chọn dữ liệu tối thiểu, dữ liệu snapshot hoặc dữ liệu thay đổi cần mang theo event.
- Hiểu ảnh hưởng của payload tới coupling, replay, consistency, privacy, retention và throughput.
- Thiết kế envelope, event ID, aggregate ID, version, timestamp và correlation metadata.
- Xây dựng event contract có khả năng tiến hóa và tương thích schema.
- Triển khai ví dụ phát và tiêu thụ event bằng Java/Spring Kafka.
- Tránh các lỗi như phát CRUD notification thiếu ngữ nghĩa, gửi payload quá lớn hoặc buộc consumer gọi API đồng bộ cho mọi event.

## 2. Event là sự thật đã xảy ra

Event là một thông điệp mô tả một điều đã xảy ra tại một thời điểm. Tên event thường dùng dạng quá khứ hoặc diễn đạt một trạng thái đã được xác lập, ví dụ:

- `OrderCreated`: đơn hàng đã được tạo.
- `PaymentAuthorized`: khoản thanh toán đã được cấp phép.
- `InventoryReserved`: hàng tồn kho đã được giữ.
- `ShipmentDispatched`: lô hàng đã được bàn giao để vận chuyển.
- `CustomerAddressChanged`: địa chỉ khách hàng đã thay đổi.

Một event tốt có ngữ nghĩa rõ ràng. Người đọc có thể hiểu điều gì đã xảy ra, đối tượng nghiệp vụ nào liên quan và hệ thống phát event chịu trách nhiệm về sự thật đó.

Event khác command:

| Đặc điểm | Event | Command |
|---|---|---|
| Ý nghĩa | Mô tả điều đã xảy ra | Yêu cầu một hành động xảy ra |
| Thời điểm | Sự việc đã được xác lập | Hành động có thể thành công hoặc thất bại trong tương lai |
| Cách đặt tên | Quá khứ: `OrderCreated` | Mệnh lệnh: `CreateOrder` |
| Người nhận | Có thể có nhiều consumer độc lập | Thường có một handler chịu trách nhiệm xử lý |
| Kết quả | Không thể làm cho sự kiện đã xảy ra trở thành chưa xảy ra; có thể phát sự kiện bù hoặc sự kiện mới | Handler trả kết quả chấp nhận, từ chối hoặc lỗi |

Ví dụ, `ReserveInventory` là command yêu cầu giữ hàng. Sau khi Inventory Service xử lý thành công, nó phát `InventoryReserved`. Nếu không đủ hàng, nó có thể trả kết quả từ chối hoặc phát một sự kiện như `InventoryReservationRejected`, tùy hợp đồng giao tiếp.

Không nên đặt tên command như thể hành động đã hoàn tất. Nếu phát `PaymentCompleted` trước khi thanh toán được xác nhận, consumer có thể đưa hệ thống vào trạng thái sai.

## 3. Fact event: xác định sự thật nghiệp vụ

Fact event diễn đạt một sự thật có ý nghĩa trong miền nghiệp vụ. Nó thường gắn với một aggregate hoặc thực thể, có định danh, thời điểm và phiên bản để consumer hiểu vị trí của sự kiện trong vòng đời đối tượng.

Ví dụ:

~~~text
OrderCreated
PaymentAuthorized
OrderCancelled
RefundIssued
~~~

Các event trên không chỉ nói rằng một bản ghi database vừa thay đổi. Chúng thể hiện ngữ nghĩa nghiệp vụ mà nhiều consumer có thể sử dụng cho những mục đích khác nhau.

### 3.1. Fact event không phải bản sao tên bảng và thao tác CRUD

Một event như `OrderRowUpdated` hoặc `CustomerTableChanged` thường phản ánh chi tiết triển khai database hơn là ý nghĩa nghiệp vụ. Consumer phải tự suy luận tại sao row thay đổi và trạng thái mới có ý nghĩa gì.

So sánh:

| Event thiên về CRUD | Fact event có ngữ nghĩa |
|---|---|
| `orders_updated` | `OrderAddressChanged` |
| `payment_status_update` | `PaymentAuthorized` |
| `inventory_row_changed` | `InventoryReserved` |
| `customer_deleted` | `CustomerAccountClosed` |

Không phải mọi event phát từ CDC đều sai. CDC hữu ích để đồng bộ dữ liệu hoặc xây dựng read model. Nhưng nếu các consumer cần hiểu nghiệp vụ, một lớp chuyển đổi từ change record sang domain event thường làm hợp đồng rõ ràng hơn.

### 3.2. Fact event là bất biến về ý nghĩa

Một event đã phát nên được xem là một sự thật lịch sử. Nếu đơn hàng được tạo rồi bị hủy, không sửa `OrderCreated` thành `OrderCancelled`. Hãy phát thêm `OrderCancelled` để thể hiện sự kiện mới.

Consumer có thể xây dựng trạng thái hiện tại bằng cách áp dụng lần lượt các fact event. Cách này giúp replay và audit dễ hiểu hơn, nhưng yêu cầu event có schema ổn định và logic xử lý lịch sử phù hợp.

Bất biến về ý nghĩa không có nghĩa mọi trường payload không bao giờ được sửa trong bất kỳ hệ thống lưu trữ nào. Nó có nghĩa không thay đổi diễn giải của một event đã công bố. Khi phát hiện sai dữ liệu, hãy thiết kế correction event, compensating event hoặc quy trình điều chỉnh có audit.

### 3.3. Một event có thể phục vụ nhiều consumer

Giả sử Order Service phát `OrderCreated`. Các consumer có thể:

- Inventory Service giữ hàng.
- Payment Service khởi tạo quy trình thanh toán.
- Notification Service gửi email xác nhận.
- Analytics Service cập nhật chỉ số bán hàng.
- Fraud Detection đánh giá rủi ro.

Mỗi consumer group đọc topic độc lập. Producer không cần biết từng consumer sẽ dùng event để làm gì. Điều quan trọng là event contract biểu đạt đúng sự thật và cung cấp đủ dữ liệu cho nhóm consumer được hỗ trợ.

~~~mermaid
flowchart LR
    O["Order Service"] --> E[("Topic: order-events")]
    E --> I["Inventory group"]
    E --> P["Payment group"]
    E --> N["Notification group"]
    E --> A["Analytics group"]
    I --> IDB[("Inventory DB")]
    P --> PDB[("Payment DB")]
    N --> Mail["Email provider"]
    A --> WH[("Data warehouse")]
~~~

## 4. Notification event: báo cho consumer biết có điều gì đã xảy ra

Notification event là kiểu thiết kế event mang lượng dữ liệu nhỏ, chủ yếu thông báo rằng một sự kiện đã xảy ra và cung cấp định danh hoặc thông tin cần thiết để consumer lấy phần chi tiết từ nguồn có thẩm quyền.

Ví dụ, Order Service phát thông báo:

~~~json
{
  "eventId": "evt-7f2a",
  "eventType": "OrderCreated",
  "aggregateId": "ORD-900",
  "occurredAt": "2026-11-20T09:30:00Z",
  "aggregateVersion": 1
}
~~~

Consumer nhận được thông báo, sau đó gọi Order Service hoặc đọc read API phù hợp để lấy chi tiết đơn hàng.

Notification event vẫn có thể là một fact event. Sự khác nhau nằm ở cách payload được thiết kế: event có ý nghĩa nghiệp vụ, nhưng phần dữ liệu chi tiết được giữ tại nguồn và consumer lấy khi cần.

### 4.1. Quy trình xử lý notification event

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant K as Kafka
    participant C as Inventory Service
    participant API as Order Query API
    participant DB as Order Database

    O->>DB: Commit đơn hàng
    O->>K: Publish OrderCreated notification
    K-->>C: Deliver notification
    C->>API: GET /orders/ORD-900
    API->>DB: Read order details
    DB-->>API: Order snapshot
    API-->>C: Return details
    C->>C: Process inventory reservation
~~~

Consumer chỉ nhận dữ liệu chi tiết sau khi gọi nguồn. Điều này có thể phù hợp nếu payload lớn, dữ liệu nhạy cảm hoặc consumer chỉ thỉnh thoảng cần chi tiết.

### 4.2. Ưu điểm

- Payload nhỏ, giảm dung lượng lưu trữ và băng thông Kafka.
- Nguồn dữ liệu chi tiết vẫn nằm tại dịch vụ sở hữu.
- Có thể tránh sao chép quá nhiều dữ liệu cá nhân hoặc dữ liệu nhạy cảm sang nhiều topic.
- Consumer chỉ lấy trường mình cần.
- Thay đổi dữ liệu chi tiết không nhất thiết phải đưa toàn bộ vào event contract.

### 4.3. Hạn chế và rủi ro

Notification event tạo phụ thuộc lúc chạy vào API hoặc nguồn dữ liệu của producer:

- Consumer phải có quyền truy cập nguồn dữ liệu và cần xử lý authentication/authorization.
- Producer service có thể bị quá tải do nhiều consumer cùng truy vấn.
- API chậm hoặc không sẵn sàng khiến consumer bị chậm dù Kafka vẫn hoạt động.
- Consumer có thể nhận notification nhưng truy vấn quá sớm, trước khi dữ liệu đọc được ở read replica hoặc read model.
- Khi replay event cũ, API thường trả trạng thái hiện tại chứ không trả snapshot tại thời điểm event được phát.
- Nhiều consumer có thể tạo hiệu ứng fan-out request và gây tải đột biến lên nguồn.

Điểm cuối về replay rất quan trọng. Nếu consumer xử lý `OrderAddressChanged` từ ba tháng trước rồi gọi API lấy đơn hàng, API có thể trả địa chỉ hiện tại. Consumer không thể tái tạo trạng thái tại thời điểm event xảy ra chỉ từ notification tối giản.

### 4.4. Khi nào notification event phù hợp?

Chọn notification event khi:

- Consumer chỉ cần biết có thay đổi và thường cần trạng thái mới nhất.
- Dữ liệu chi tiết lớn hoặc nhạy cảm, không nên nhân bản vào nhiều topic.
- Nguồn dữ liệu có API ổn định, đủ năng lực và có chính sách truy cập rõ ràng.
- Replay không yêu cầu tái tạo chính xác snapshot lịch sử.
- Consumer có thể chịu được độ trễ và lỗi khi gọi nguồn.

Nếu consumer cần lịch sử chính xác hoặc phải hoạt động độc lập khi producer service ngừng, notification tối giản có thể không đủ.

## 5. Event-carried state transfer: mang dữ liệu cần thiết theo event

Event-carried state transfer là cách thiết kế event chứa một snapshot hoặc phần dữ liệu đủ để consumer cập nhật trạng thái của mình mà không cần gọi ngược về producer cho mỗi event.

Ví dụ `OrderCreated` mang theo các trường cần thiết:

~~~json
{
  "eventId": "evt-7f2a",
  "eventType": "OrderCreated",
  "occurredAt": "2026-11-20T09:30:00Z",
  "aggregate": {
    "type": "Order",
    "id": "ORD-900",
    "version": 1
  },
  "data": {
    "customerId": "CUS-102",
    "currency": "VND",
    "totalAmount": 1250000,
    "items": [
      {
        "productId": "SKU-01",
        "quantity": 2,
        "unitPrice": 500000
      },
      {
        "productId": "SKU-07",
        "quantity": 1,
        "unitPrice": 250000
      }
    ],
    "shippingAddress": {
      "provinceCode": "79",
      "districtCode": "760",
      "addressLine": "..."
    }
  }
}
~~~

Consumer có thể sử dụng snapshot này để tạo read model hoặc bắt đầu quy trình mà không cần gọi Order Service để lấy từng trường.

### 5.1. Ưu điểm

- Consumer ít phụ thuộc vào API của producer trong lúc xử lý.
- Dữ liệu có thể được replay để tái tạo projection nếu payload chứa đủ thông tin.
- Giảm số request đồng bộ giữa các dịch vụ.
- Consumer có thể phát triển read model riêng, phù hợp với nhu cầu truy vấn của mình.
- Kafka trở thành kênh phân phối dữ liệu thay đổi, giúp producer và consumer tách biệt về thời gian triển khai.

### 5.2. Hạn chế và rủi ro

- Payload lớn hơn, tăng network traffic, disk usage, replication traffic và chi phí retention.
- Dữ liệu bị sao chép sang nhiều consumer hoặc topic; cần quản trị quyền truy cập và dữ liệu nhạy cảm.
- Schema trở thành hợp đồng dài hạn giữa producer và nhiều consumer.
- Consumer phải hiểu snapshot/version và cách xử lý event cũ đến muộn.
- Nếu payload mang quá nhiều trường không cần thiết, thay đổi nội bộ của producer có thể ảnh hưởng consumer.
- Snapshot không tự động là nguồn sự thật hiện tại; nó mô tả trạng thái tại thời điểm event được tạo.

### 5.3. Khi nào event-carried data phù hợp?

Chọn event-carried state transfer khi:

- Consumer cần xử lý độc lập và không nên gọi lại producer.
- Nhiều consumer cần cùng một tập dữ liệu cơ bản.
- Cần replay để xây dựng lại projection hoặc cache.
- API nguồn có thể không sẵn sàng trong lúc consumer xử lý.
- Payload có kích thước kiểm soát được và dữ liệu được phép chia sẻ.

Không nên gửi toàn bộ object graph hoặc entity database chỉ vì serializer có thể chuyển nó thành JSON. Hãy chọn dữ liệu theo nhu cầu của consumer và hợp đồng nghiệp vụ công bố.

## 6. Phân biệt ba khái niệm: sự thật, kiểu thông báo và dữ liệu mang theo

Fact event, notification event và event-carried state transfer không phải ba loại loại trừ lẫn nhau trên cùng một trục.

- **Fact event** trả lời: sự thật nghiệp vụ nào đã xảy ra?
- **Notification event** trả lời: consumer cần biết điều gì đã xảy ra để tự lấy dữ liệu?
- **Event-carried state transfer** trả lời: event mang theo dữ liệu nào để consumer có thể tự xử lý?

Một fact event có thể được triển khai theo kiểu notification hoặc event-carried state transfer. Điều này giúp tránh nhầm lẫn giữa ý nghĩa event và kích thước payload.

| Thiết kế | Ngữ nghĩa | Payload | Consumer thường làm gì? |
|---|---|---|---|
| Fact event dạng notification | Sự thật nghiệp vụ đã xảy ra | ID, loại event, version, timestamp và reference | Gọi API hoặc nguồn dữ liệu để lấy chi tiết |
| Fact event mang state | Sự thật nghiệp vụ đã xảy ra | Snapshot hoặc dữ liệu đủ cho consumer | Xử lý trực tiếp và cập nhật read model |
| Change notification kỹ thuật | Một row hoặc resource đã thay đổi | Primary key, operation, metadata thay đổi | Đọc nguồn hoặc áp dụng change record |
| Domain event giàu ngữ nghĩa | Một chuyển đổi nghiệp vụ đã xảy ra | Dữ liệu theo hợp đồng nghiệp vụ | Phản ứng theo ý nghĩa nghiệp vụ |

Không có quy tắc rằng event-carried state phải chứa toàn bộ trạng thái aggregate. Có thể mang một phần snapshot được chọn lọc, miễn là hợp đồng nói rõ phần dữ liệu đó có nghĩa gì.

## 7. Chọn dữ liệu nào nên mang theo event?

Hãy bắt đầu từ các consumer đã biết và các use case cần hỗ trợ. Đừng bắt đầu bằng việc serialize toàn bộ entity database.

### 7.1. Dữ liệu định danh và metadata

Một event thường cần các trường chung:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh duy nhất của lần phát event, hỗ trợ deduplication và tracing |
| `eventType` | Tên loại sự kiện, ví dụ `OrderCreated` |
| `occurredAt` | Thời điểm sự kiện xảy ra theo đồng hồ của nguồn |
| `aggregateId` | Định danh đối tượng nghiệp vụ liên quan |
| `aggregateVersion` | Phiên bản hoặc số thứ tự của aggregate sau thay đổi |
| `producer` hoặc `source` | Dịch vụ phát event |
| `correlationId` | Liên kết event với yêu cầu hoặc luồng nghiệp vụ lớn hơn |
| `causationId` | Tham chiếu command/event dẫn tới event hiện tại |
| `traceparent` | Trace context để liên kết distributed tracing |

Không phải mọi event đều cần tất cả trường. Hãy xác định envelope dùng chung của tổ chức và tránh thêm metadata trùng lặp hoặc không có người sử dụng.

### 7.2. Dữ liệu nghiệp vụ

Chỉ mang trường có ý nghĩa đối với consumer hoặc cần thiết để diễn giải sự thật đã xảy ra.

Ví dụ, `PaymentAuthorized` có thể mang:

~~~json
{
  "eventId": "evt-pay-884",
  "eventType": "PaymentAuthorized",
  "occurredAt": "2026-11-20T09:32:10Z",
  "aggregateId": "PAY-884",
  "aggregateVersion": 3,
  "data": {
    "orderId": "ORD-900",
    "authorizedAmount": 1250000,
    "currency": "VND",
    "paymentMethodType": "CARD",
    "authorizationReference": "AUTH-73A"
  }
}
~~~

Consumer có thể cần orderId, số tiền và currency để cập nhật projection. Consumer không nhất thiết cần số thẻ đầy đủ, CVV, token bí mật hoặc toàn bộ hồ sơ khách hàng. Không đưa dữ liệu thanh toán nhạy cảm vào event chỉ để tiện cho một consumer.

### 7.3. Snapshot và delta event

Có hai kiểu dữ liệu thường gặp:

- **Snapshot event:** mang trạng thái hoặc phần trạng thái tại thời điểm event xảy ra.
- **Delta event:** mang thay đổi đã diễn ra, ví dụ `quantityChangedBy=-2` hoặc `shippingAddressChanged`.

Ví dụ snapshot:

~~~json
{
  "eventType": "InventoryLevelChanged",
  "aggregateId": "SKU-01",
  "aggregateVersion": 18,
  "data": {
    "availableQuantity": 42,
    "reservedQuantity": 8
  }
}
~~~

Ví dụ delta:

~~~json
{
  "eventType": "InventoryReserved",
  "aggregateId": "SKU-01",
  "aggregateVersion": 18,
  "data": {
    "reservationId": "RSV-31",
    "orderId": "ORD-900",
    "quantity": 2
  }
}
~~~

Snapshot tiện cho consumer cần trạng thái mới nhất và có thể cập nhật projection trực tiếp. Delta giàu ngữ nghĩa nghiệp vụ và hỗ trợ tái dựng chuỗi thay đổi, nhưng consumer cần xử lý đúng thứ tự và có trạng thái ban đầu phù hợp.

Một event `InventoryReserved` là sự thật nghiệp vụ. Nó có thể mang delta về số lượng đã giữ, hoặc kèm snapshot tồn kho sau thay đổi. Hãy xác định rõ trường nào là fact, trường nào là trạng thái tham chiếu tại thời điểm phát.

## 8. Thiết kế envelope và event contract

Một hợp đồng event nên tách metadata chung khỏi payload nghiệp vụ. Điều này giúp các dịch vụ có cách đọc thống nhất và cho phép thay đổi payload theo từng event type.

Ví dụ envelope JSON:

~~~json
{
  "specVersion": "1.0",
  "eventId": "evt-7f2a",
  "eventType": "OrderCreated",
  "source": "order-service",
  "occurredAt": "2026-11-20T09:30:00Z",
  "aggregate": {
    "type": "Order",
    "id": "ORD-900",
    "version": 1
  },
  "correlationId": "req-5c10",
  "causationId": "cmd-4b22",
  "data": {
    "customerId": "CUS-102",
    "currency": "VND",
    "totalAmount": 1250000
  }
}
~~~

Có thể đặt các metadata này trong payload JSON hoặc dùng Kafka record headers cho một số metadata kỹ thuật. Dù chọn cách nào, hãy quy định rõ để consumer không phải đoán. Kafka key thường nên chứa định danh dùng cho partitioning, ví dụ `aggregateId`, nếu cần giữ thứ tự theo aggregate.

### 8.1. Event ID và deduplication

`eventId` định danh một lần phát event. Consumer có thể lưu event ID đã xử lý trong inbox table hoặc bảng deduplication cùng transaction với cập nhật nghiệp vụ.

Không dùng riêng `aggregateId` làm event ID vì một aggregate có thể phát nhiều event. Cũng không nên chỉ dựa vào payload hash: hai sự kiện nghiệp vụ khác nhau có thể có payload giống nhau.

Nếu producer retry cùng một batch trong một producer session, Kafka idempotence giúp tránh duplicate do retry protocol. Event ID vẫn hữu ích khi event được phát lại qua một producer session mới, được nhập từ nguồn khác hoặc consumer phải chống xử lý lặp ở tầng nghiệp vụ.

### 8.2. Aggregate version và ordering

`aggregateVersion` hoặc sequence number nghiệp vụ giúp consumer nhận biết thứ tự và phát hiện event thiếu hoặc đến muộn.

Ví dụ:

~~~text
Order ORD-900
  version 1: OrderCreated
  version 2: PaymentAuthorized
  version 3: OrderPacked
  version 4: OrderShipped
~~~

Producer nên dùng `aggregateId` làm Kafka key để các event của aggregate được ánh xạ nhất quán vào một partition. Consumer có thể kiểm tra version kỳ vọng trước khi áp dụng event.

Version không tự thay thế Kafka offset. Offset là vị trí record trong partition; aggregateVersion là thứ tự thay đổi của một đối tượng nghiệp vụ. Một partition có thể chứa event của nhiều aggregate, mỗi aggregate có chuỗi version riêng.

### 8.3. Timestamp

`occurredAt` nên thể hiện thời điểm sự kiện nghiệp vụ xảy ra tại nguồn. Kafka record timestamp có thể là CreateTime do producer cung cấp hoặc LogAppendTime do broker gán, tùy cấu hình topic/broker.

Không dùng timestamp như bằng chứng duy nhất về thứ tự. Đồng hồ giữa các máy có thể lệch; hai event từ nhiều producer có thể có timestamp không phản ánh thứ tự append. Khi cần thứ tự theo aggregate, dùng partition ordering và version/sequence.

## 9. Quản trị schema và tiến hóa event

Event contract là giao diện giữa producer và consumer. Một thay đổi payload có thể ảnh hưởng nhiều dịch vụ đang triển khai ở các thời điểm khác nhau.

Các nguyên tắc quan trọng:

- Thêm field mới nên có default hoặc quy tắc xử lý khi field vắng mặt.
- Tránh đổi ý nghĩa hoặc kiểu dữ liệu của field đang được consumer sử dụng.
- Không xóa field ngay khi producer đã ngừng ghi; consumer cũ có thể vẫn cần field đó.
- Quy định rõ nullable, default, enum và đơn vị đo.
- Dùng versioning có chiến lược; không tạo version mới cho mọi thay đổi nhỏ nếu schema format hỗ trợ tương thích.
- Kiểm thử producer với consumer cũ và consumer mới trước khi rollout.
- Theo dõi schema compatibility bằng Schema Registry hoặc cơ chế kiểm tra hợp đồng tương đương.

JSON dễ đọc và thuận tiện khi bắt đầu. Avro, Protobuf hoặc JSON Schema có thể phù hợp khi cần schema rõ ràng, kiểm soát tương thích và hiệu quả serialization. Lựa chọn phụ thuộc hệ sinh thái, tooling và cách tổ chức quản lý schema.

### 9.1. Ví dụ tiến hóa schema

Phiên bản đầu của `OrderCreated`:

~~~json
{
  "eventType": "OrderCreated",
  "data": {
    "orderId": "ORD-900",
    "totalAmount": 1250000
  }
}
~~~

Sau đó producer cần bổ sung currency:

~~~json
{
  "eventType": "OrderCreated",
  "data": {
    "orderId": "ORD-900",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

Consumer cũ phải tiếp tục xử lý event khi không có field currency. Nếu consumer mặc định mọi số tiền là VND, hãy ghi rõ quy tắc này trong hợp đồng hoặc bổ sung default an toàn. Nếu không thể xác định đơn vị tiền tệ một cách chắc chắn, cần thiết kế migration thay vì âm thầm đoán.

## 10. Dữ liệu nhạy cảm, bảo mật và quyền riêng tư

Event được giữ theo retention, có thể được nhiều consumer group đọc và thường được sao chép trên nhiều broker. Vì vậy, dữ liệu trong event có thể tồn tại ở nhiều nơi hơn dữ liệu trong database gốc.

Trước khi thêm field, hãy hỏi:

- Consumer nào thực sự cần field này?
- Field có phải dữ liệu cá nhân, thông tin thanh toán, bí mật hoặc dữ liệu bị hạn chế không?
- Có thể dùng ID tham chiếu thay cho dữ liệu đầy đủ không?
- Topic có ACL, TLS, authentication và audit phù hợp không?
- Chính sách retention có đáp ứng yêu cầu lưu trữ/xóa dữ liệu không?
- Nếu cần xóa hoặc chỉnh sửa dữ liệu cá nhân, các bản sao trong Kafka, archive và downstream được xử lý như thế nào?

Không đưa mật khẩu, access token, secret key, CVV hoặc dữ liệu xác thực vào event. Với thông tin cá nhân, chỉ phát trường tối thiểu cần thiết và đánh giá nghĩa vụ lưu trữ, xóa, masking hoặc tokenization. Retention hoặc compaction không phải cơ chế tự động đáp ứng mọi yêu cầu xóa dữ liệu.

Một notification event chứa ID có thể giảm sao chép dữ liệu, nhưng consumer truy vấn API phải được xác thực và chỉ truy cập đúng phạm vi dữ liệu mà nó được phép xem. ID không thay thế authorization.

## 11. Chọn notification hay event-carried data?

Có thể dùng các câu hỏi sau để chọn payload:

| Câu hỏi | Nghiêng về notification | Nghiêng về event-carried data |
|---|---|---|
| Consumer chỉ cần trạng thái mới nhất? | Có thể phù hợp | Không bắt buộc |
| Consumer cần snapshot đúng tại thời điểm event? | Khó nếu API chỉ trả trạng thái hiện tại | Phù hợp hơn |
| Nguồn dữ liệu có thể bị gián đoạn? | Consumer phụ thuộc API nguồn | Consumer có thể tiếp tục từ payload |
| Payload chứa dữ liệu nhạy cảm hoặc rất lớn? | Có lợi thế vì chỉ gửi reference | Cần lọc trường và đánh giá rủi ro |
| Nhiều consumer cần cùng dữ liệu cơ bản? | Có thể tạo nhiều request tới producer | Có thể giảm truy vấn lặp |
| Cần replay để dựng lại projection? | Khó nếu dữ liệu lịch sử không còn | Phù hợp nếu event đủ thông tin |
| Dữ liệu thay đổi thường xuyên? | Consumer có thể lấy phiên bản hiện tại | Cần xác định snapshot/delta và version |
| Consumer cần xử lý độc lập với producer? | Phụ thuộc API lúc xử lý | Ít phụ thuộc hơn |

Một giải pháp trung gian thường tốt: event mang định danh, version, timestamp và một tập trường nghiệp vụ cần thiết; consumer chỉ truy vấn API khi cần phần dữ liệu bổ sung. Đây là payload chọn lọc, không nhất thiết là notification tối giản hoặc snapshot toàn bộ.

## 12. Triển khai event trong Java/Spring Kafka

Giả sử Order Service phát `OrderCreated` và Inventory Service tiêu thụ để xây dựng projection hoặc bắt đầu giữ hàng.

### 12.1. Định nghĩa event DTO

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderCreated(
    String eventId,
    String orderId,
    long aggregateVersion,
    Instant occurredAt,
    String customerId,
    String currency,
    BigDecimal totalAmount,
    List<OrderItem> items
) {
    public record OrderItem(
        String productId,
        int quantity,
        BigDecimal unitPrice
    ) {}
}
~~~

DTO chỉ chứa dữ liệu được công bố theo event contract. Không nên dùng trực tiếp JPA entity làm payload vì entity có thể chứa lazy relation, field nội bộ, dữ liệu nhạy cảm hoặc cấu trúc thay đổi theo schema database.

### 12.2. Phát event bằng KafkaTemplate

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

Dùng `orderId` làm key giúp các event của cùng order đi vào cùng partition theo partitioner mặc định trong điều kiện partition count và quy tắc partitioning không đổi. Cần cấu hình serializer phù hợp với DTO, ví dụ JSON serializer hoặc serializer dùng schema registry.

Trong hệ thống cần tính nhất quán giữa database và Kafka, không chỉ gọi `publish` sau khi commit rồi giả định hai thao tác luôn thành công cùng nhau. Hãy xem xét transactional outbox hoặc CDC để tránh mất event khi database commit nhưng publish thất bại.

### 12.3. Consumer xử lý event-carried data

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryOrderListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "inventory-projection"
    )
    public void onOrderCreated(OrderCreated event) {
        // Validate event version and required fields.
        // Apply the event idempotently to the inventory projection.
    }
}
~~~

Consumer nên kiểm tra event ID, aggregate version và các field bắt buộc. Khi cập nhật database, lưu dấu event đã xử lý và thay đổi projection trong cùng transaction database để xử lý lại an toàn.

### 12.4. Consumer xử lý notification event

Nếu payload chỉ có orderId, consumer có thể truy vấn API:

~~~java
import java.time.Instant;

public record OrderCreatedNotification(
    String eventId,
    String orderId,
    long aggregateVersion,
    Instant occurredAt
) {}
~~~

Consumer gọi Order Query API bằng client được cấu hình timeout, authentication và retry có giới hạn. Nếu API trả lỗi tạm thời, consumer cần quyết định retry theo chính sách phù hợp. Không nên giữ partition bị chặn vô thời hạn vì một API downstream đang lỗi; có thể cần retry topic hoặc cơ chế xử lý lỗi có kiểm soát, đồng thời giữ ordering nếu nghiệp vụ yêu cầu.

Nếu consumer cần trạng thái lịch sử tại version cụ thể, API phải hỗ trợ truy vấn theo version hoặc event cần mang snapshot. Một endpoint chỉ trả trạng thái hiện tại không đủ để replay chính xác lịch sử.

## 13. Outbox, CDC và thời điểm phát fact event

Một fact event phải phản ánh thay đổi đã được xác lập trong nguồn nghiệp vụ. Nếu Order Service cập nhật database rồi publish Kafka bằng hai thao tác độc lập, có thể xảy ra:

- Database commit thành công nhưng ứng dụng lỗi trước khi publish.
- Kafka publish thành công nhưng database transaction rollback.
- Ứng dụng không nhận ACK và retry, khiến kết quả gửi không rõ.

Transactional outbox ghi thay đổi nghiệp vụ và event cần phát trong cùng transaction database. Một relay hoặc CDC connector đọc outbox rồi phát event sang Kafka.

~~~mermaid
flowchart LR
    S["Order Service"] --> TX["Database transaction"]
    TX --> O[("Orders table")]
    TX --> B[("Outbox table")]
    B --> R["Outbox relay / CDC"]
    R --> K[("Kafka topic")]
    K --> C["Consumer groups"]
~~~

Outbox giúp bảo đảm event được ghi nhận cùng transaction nghiệp vụ trong database. Tuy nhiên, relay có thể phát lại cùng outbox record khi retry hoặc restart. Consumer vẫn cần idempotency và event ID ổn định.

Thời điểm `occurredAt` nên phản ánh lúc sự kiện nghiệp vụ được xác lập theo quy tắc của domain. Thời điểm relay phát vào Kafka có thể muộn hơn; không nên dùng thời điểm publish làm thời điểm nghiệp vụ nếu hai khái niệm khác nhau.

## 14. Những lỗi thiết kế thường gặp

- **Chỉ phát `EntityUpdated`:** consumer không biết điều gì đã xảy ra về mặt nghiệp vụ. Hãy dùng event name có ngữ nghĩa hoặc công bố rõ change type.
- **Gửi toàn bộ entity database:** payload dễ chứa field nội bộ, quan hệ không cần thiết hoặc dữ liệu nhạy cảm. Hãy định nghĩa DTO theo event contract.
- **Notification chỉ có ID nhưng yêu cầu replay lịch sử:** API hiện tại có thể không trả trạng thái tại thời điểm event. Cân nhắc snapshot hoặc API truy vấn theo version.
- **Payload quá lớn:** tăng băng thông, replication và retention. Chỉ mang dữ liệu cần thiết; file hoặc object lớn nên nằm ở object storage và event chứa reference có kiểm soát.
- **Dùng event như command:** tên event nói rằng việc đã xảy ra trong khi thực tế mới chỉ yêu cầu xử lý. Tách command và fact event.
- **Không có event ID:** consumer khó deduplicate khi relay hoặc nguồn phát lại event.
- **Không có version hoặc quy tắc thứ tự:** consumer khó phát hiện event thiếu, trùng hoặc đến muộn.
- **Thay đổi schema không tương thích:** consumer cũ có thể lỗi khi producer rollout trước. Quản lý schema và kiểm thử tương thích.
- **Cho rằng Kafka exactly-once bảo vệ side effect ngoài Kafka:** database hoặc API bên ngoài vẫn cần idempotency hoặc transaction boundary riêng.
- **Đưa dữ liệu bí mật vào topic:** retention, replica và nhiều consumer làm phạm vi lộ dữ liệu rộng hơn dự kiến.

## 15. Checklist thiết kế event trước khi publish

Trước khi tạo topic hoặc triển khai producer, hãy xác nhận:

- [ ] Tên event mô tả sự thật nghiệp vụ đã xảy ra.
- [ ] Phân biệt rõ event với command và change notification kỹ thuật.
- [ ] Xác định consumer và use case cần hỗ trợ.
- [ ] Chọn payload notification, snapshot, delta hoặc payload kết hợp.
- [ ] Chỉ đưa trường cần thiết và không chứa secret hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Có event ID ổn định và aggregate ID phù hợp.
- [ ] Xác định aggregate version/sequence nếu cần kiểm soát thứ tự.
- [ ] Có timestamp và correlation/trace metadata phù hợp.
- [ ] Chọn Kafka key theo phạm vi ordering nghiệp vụ.
- [ ] Định nghĩa schema, default, nullability và quy tắc tiến hóa.
- [ ] Xác định retention, replay, ACL và quyền truy cập.
- [ ] Thiết kế outbox/CDC nếu cần nhất quán giữa database và Kafka.
- [ ] Consumer có thể xử lý duplicate, event cũ và lỗi downstream.
- [ ] Đã kiểm thử producer mới với consumer hiện tại và ngược lại.

## 16. Tình huống tổng hợp

Một Order Service phát event khi đơn hàng được tạo. Inventory Service cần orderId, danh sách sản phẩm và số lượng để giữ hàng. Notification Service chỉ cần orderId và customerId để gửi email xác nhận. Analytics Service cần tổng tiền, currency và timestamp để cập nhật báo cáo.

Có thể chọn một trong hai cách:

**Cách A: một event giàu dữ liệu cho mọi consumer.**

`OrderCreated` chứa orderId, customerId, items, totalAmount, currency và occurredAt. Inventory và Analytics dùng trực tiếp. Notification chỉ lấy một phần. Cách này giảm truy vấn API nhưng phải kiểm soát quyền truy cập và tránh gửi field nhạy cảm.

**Cách B: notification tối giản và API chi tiết.**

Event chỉ chứa eventId, orderId, version và timestamp. Cả ba consumer gọi Order API để lấy dữ liệu cần thiết. Cách này giảm payload nhưng tăng phụ thuộc vào API, số request và độ khó replay lịch sử.

**Cách C: payload chọn lọc theo hợp đồng event.**

Event chứa orderId, customerId, items, totalAmount, currency, version và timestamp; không chứa địa chỉ đầy đủ hoặc thông tin thanh toán nhạy cảm. Consumer có thể xử lý use case chính mà không cần gọi API. Chỉ những trường hợp thật sự cần dữ liệu bổ sung mới truy vấn nguồn.

Trong nhiều hệ thống, cách C cân bằng tốt giữa tự chủ của consumer và kiểm soát dữ liệu. Nhưng quyết định cuối cùng phụ thuộc quyền sở hữu dữ liệu, số consumer, yêu cầu replay, quy mô payload và chính sách bảo mật.

## 17. Tự kiểm tra

**Câu 1.** Fact event trả lời câu hỏi gì?

**Đáp án:** Nó mô tả sự thật nghiệp vụ nào đã xảy ra, ví dụ `OrderCreated` hoặc `PaymentAuthorized`.

**Câu 2.** Notification event khác event-carried state transfer ở điểm nào?

**Đáp án:** Notification chủ yếu báo có thay đổi và cung cấp reference để consumer tự lấy chi tiết. Event-carried state transfer mang snapshot hoặc dữ liệu đủ để consumer xử lý mà không phải gọi producer cho mỗi event.

**Câu 3.** Fact event có nhất thiết phải là notification event không?

**Đáp án:** Không. Fact event là khái niệm về ngữ nghĩa; nó có thể được triển khai bằng payload notification hoặc payload mang dữ liệu.

**Câu 4.** Vì sao không nên serialize trực tiếp JPA entity làm event payload?

**Đáp án:** Entity có thể chứa quan hệ lazy, field nội bộ, dữ liệu nhạy cảm và cấu trúc phụ thuộc database. DTO riêng giúp kiểm soát event contract và tiến hóa schema.

**Câu 5.** Khi nào notification tối giản gây khó khăn cho replay?

**Đáp án:** Khi consumer phải tái tạo trạng thái tại thời điểm event nhưng API chỉ trả trạng thái hiện tại hoặc dữ liệu lịch sử đã không còn. Khi đó cần snapshot, delta đủ dữ liệu hoặc API truy vấn theo version.

**Câu 6.** Event ID và aggregate version có cùng ý nghĩa không?

**Đáp án:** Không. Event ID định danh một lần phát event; aggregate version biểu diễn thứ tự phiên bản thay đổi của một aggregate.

**Câu 7.** Vì sao event-carried data cần được kiểm soát về privacy?

**Đáp án:** Event được lưu theo retention, replication và có thể được nhiều consumer đọc. Dữ liệu nhạy cảm bị sao chép rộng hơn, nên cần tối thiểu hóa payload, ACL và chính sách lưu trữ/xóa phù hợp.

---

Hãy bắt đầu thiết kế bằng câu hỏi “sự thật nghiệp vụ nào đã xảy ra?”, rồi quyết định consumer cần biết sự thật đó qua một notification hay cần dữ liệu đi kèm để xử lý độc lập. Tách rõ ngữ nghĩa event khỏi chiến lược payload giúp Kafka event contract ổn định, dễ replay và phù hợp với ranh giới sở hữu dữ liệu của từng dịch vụ.

