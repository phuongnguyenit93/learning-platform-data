# Nội dung sự kiện: định danh, dữ liệu cần thiết và tính bất biến

Trong Domain-Driven Design (DDD), **domain event (sự kiện miền)** mô tả một sự việc nghiệp vụ có ý nghĩa đã xảy ra. Ví dụ: đơn hàng đã được xác nhận, khoản thanh toán đã được ghi nhận hoặc hợp đồng đã hết hiệu lực. Một event tốt giúp người đọc hiểu sự việc nào đã xảy ra, đối tượng nào bị tác động, sự việc diễn ra khi nào và những dữ liệu nào cần thiết để diễn giải nó.

Thiết kế nội dung event cần cân bằng nhiều yêu cầu. Event phải có đủ thông tin để bên nhận hiểu sự kiện mà không phải đoán; đồng thời không nên mang toàn bộ object graph hoặc dữ liệu không cần thiết. Event cần có định danh để truy vết và chống xử lý trùng, có thời điểm và thông tin phiên bản phù hợp, và phải giữ nguyên ý nghĩa sau khi đã được công bố. Nếu một sự kiện đã xảy ra mà sau đó dữ liệu bị sửa trực tiếp, lịch sử sẽ không còn đáng tin cậy.

Bài học này tập trung vào cách thiết kế payload của domain event: định danh sự kiện và aggregate, dữ liệu nghiệp vụ cần thiết, thời gian và thứ tự, metadata phục vụ truy vết, tính bất biến, snapshot và reference, bảo vệ dữ liệu nhạy cảm, cũng như sự khác nhau giữa domain event nội bộ và integration event công bố cho hệ thống khác.

## 1. Một event cần trả lời những câu hỏi nào?

Khi đọc một event, người nhận cần hiểu ít nhất:

- **Điều gì đã xảy ra?** Tên event phải diễn đạt một sự việc nghiệp vụ cụ thể, thường ở thì quá khứ.
- **Đối tượng nào liên quan?** Cần biết aggregate hoặc đối tượng nghiệp vụ nào là nguồn phát sinh sự kiện.
- **Sự việc xảy ra khi nào?** Thời điểm nghiệp vụ xảy ra khác với thời điểm hệ thống ghi nhận hoặc chuyển event.
- **Những dữ liệu nào làm rõ sự việc?** Payload phải chứa các thông tin cần thiết để hiểu và xử lý event.
- **Event được nhận diện và truy vết ra sao?** Cần định danh sự kiện và có thể cần correlation, causation hoặc sequence.
- **Ý nghĩa của payload có ổn định không?** Bên nhận cần biết schema/version và cách diễn giải các trường.

Ví dụ, `OrderConfirmed` có ý nghĩa rõ hơn `OrderUpdated`. Tuy nhiên, chỉ tên event chưa đủ. Nếu event không có `orderId`, người nhận khó xác định đơn nào đã được xác nhận. Nếu event chỉ có `orderId` nhưng bên nhận cần biết tổng tiền đã xác nhận, họ có thể phải truy vấn ngược hoặc lấy dữ liệu hiện tại có thể đã thay đổi.

Một event thường có hai nhóm thông tin:

1. **Nội dung nghiệp vụ (payload):** các sự kiện và giá trị liên quan đến điều đã xảy ra.
2. **Metadata:** thông tin phục vụ định danh, thời gian, nguồn phát sinh, tương quan, phiên bản và vận chuyển.

Hai nhóm này có thể được biểu diễn trong cùng một object hoặc tách thành envelope tùy kiến trúc. Điều quan trọng là không trộn lẫn dữ liệu nghiệp vụ với chi tiết vận chuyển một cách tùy tiện.

## 2. Đặt tên event theo sự việc đã xảy ra

Tên event nên diễn đạt một sự thật nghiệp vụ đã xảy ra, thường dùng dạng quá khứ hoặc cụm từ biểu thị trạng thái đã đạt được.

| Tên event | Ý nghĩa |
| --- | --- |
| `OrderPlaced` | Đơn hàng đã được đặt |
| `OrderConfirmed` | Đơn hàng đã được xác nhận |
| `OrderCancelled` | Đơn hàng đã bị hủy theo chính sách |
| `PaymentCaptured` | Khoản thanh toán đã được thu/ghi nhận thành công theo định nghĩa của context |
| `StockReserved` | Tồn kho đã được giữ cho yêu cầu cụ thể |
| `ShipmentDispatched` | Kiện hàng đã được bàn giao để vận chuyển |
| `ContractExpired` | Hợp đồng đã hết hiệu lực do thời hạn hoặc điều kiện |

Không nên dùng tên command như `ConfirmOrder`, `CancelOrder` hoặc `ReserveStock` làm tên event. Command thể hiện ý định hoặc yêu cầu; event mô tả kết quả đã xảy ra. `ConfirmOrder` có thể bị từ chối, trong khi `OrderConfirmed` chỉ được phát ra khi đơn thực sự đã được xác nhận.

### 2.1. Tránh event quá chung chung

Tên như `EntityChanged`, `OrderUpdated`, `StatusChanged` hoặc `DataSaved` thường không nói rõ sự việc nghiệp vụ. Người nhận phải đọc thêm trạng thái hoặc so sánh dữ liệu trước/sau mới đoán được ý nghĩa.

Nếu một đơn hàng chuyển từ `DRAFT` sang `CONFIRMED`, event `OrderConfirmed` diễn đạt kết quả rõ ràng hơn `OrderStatusChanged`. Nếu có nhiều loại thay đổi thực sự cần được phân biệt, hãy tạo event có ý nghĩa tương ứng như `OrderAddressChanged`, `OrderLineRemoved` hoặc `OrderCancelled`.

### 2.2. Không biến mọi thay đổi kỹ thuật thành domain event

Không phải thao tác lưu database, cập nhật cache hoặc thay đổi một trường nội bộ nào cũng là sự kiện miền. Domain event cần có ý nghĩa đối với nghiệp vụ hoặc các phần khác của mô hình. Event `OrderRowUpdated` có thể chỉ là chi tiết persistence; `OrderConfirmed` là một sự kiện nghiệp vụ.

## 3. Định danh sự kiện (Event ID)

Mỗi event nên có một định danh ổn định để có thể nhận diện chính event đó qua lưu trữ, truyền tải, retry và xử lý. Định danh này thường được gọi là `eventId`.

Event ID hữu ích cho:

- Nhận diện event trong log, trace và công cụ giám sát.
- Phát hiện cùng một event được gửi hoặc nhận nhiều lần.
- Xây dựng cơ chế idempotency ở consumer.
- Đối soát giữa event store, outbox, broker và hệ thống nhận.
- Tham chiếu event trong điều tra sự cố.

Ví dụ:

```text
eventId = 9d1a5a0d-9f6b-4c9c-9c5a-2a4b9b8f1d11
eventType = OrderConfirmed
```

### 3.1. Event ID khác Aggregate ID

`eventId` nhận diện một lần phát sinh sự kiện. `aggregateId` nhận diện aggregate mà sự kiện thuộc về. Một aggregate có thể phát sinh rất nhiều event trong vòng đời.

| Trường | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `eventId` | Đây là event cụ thể nào? | `EVT-9001` |
| `aggregateId` | Event thuộc aggregate nào? | `ORD-501` |
| `aggregateType` | Aggregate thuộc loại nào? | `Order` |
| `eventType` | Sự việc nào đã xảy ra? | `OrderConfirmed` |

Không dùng `orderId` làm `eventId`, vì một đơn có thể phát sinh `OrderPlaced`, `OrderConfirmed`, `OrderCancelled` hoặc nhiều event khác. Nếu dùng cùng ID cho tất cả, consumer không thể phân biệt từng sự kiện.

### 3.2. Chọn cách tạo Event ID

Các lựa chọn thường gặp gồm UUID, ULID hoặc một định danh do hệ thống phát sinh theo quy tắc riêng. Lựa chọn phụ thuộc nhu cầu phân tán, khả năng sắp xếp, mức độ duy nhất và công nghệ lưu trữ.

Event ID cần được tạo một lần cho một sự kiện logic và giữ nguyên khi event được gửi lại. Nếu retry tạo event ID mới cho cùng một sự việc, consumer khó nhận diện đó là bản gửi trùng.

Không nên coi thứ tự từ UUID hoặc ULID là thứ tự nghiệp vụ tuyệt đối. Nếu cần thứ tự trong một aggregate stream, hãy dùng sequence hoặc version riêng.

## 4. Định danh aggregate và nguồn phát sinh

Event thường cần chỉ ra aggregate đã tạo ra nó. Thông tin này giúp truy vết vòng đời, nhóm event theo một đối tượng và xử lý đúng thứ tự trong phạm vi aggregate.

Một envelope có thể chứa:

```json
{
  "eventId": "evt-9001",
  "eventType": "OrderConfirmed",
  "aggregateType": "Order",
  "aggregateId": "ORD-501",
  "aggregateVersion": 7
}
```

`aggregateId` nên là định danh thuộc mô hình sở hữu event. Khi event được công bố ra context khác, định danh này có thể trở thành external reference trong hợp đồng tích hợp. Bên nhận không nên giả định ID đó là khóa nội bộ của mô hình mình.

### 4.1. Aggregate version và event sequence

`aggregateVersion` thường biểu thị phiên bản aggregate sau một lần thay đổi. Nó hữu ích để phát hiện event cũ, event đến sai thứ tự hoặc cập nhật dựa trên snapshot không còn mới.

Tuy nhiên, một lần commit có thể phát ra nhiều event. Nếu hai event cùng được phát từ một aggregate version, chỉ dùng `aggregateVersion` có thể không phân biệt được thứ tự giữa chúng. Khi cần thứ tự duy nhất trong stream, có thể bổ sung `eventSequence` hoặc `streamPosition`.

Ví dụ:

| Event | Aggregate ID | Aggregate version | Event sequence |
| --- | --- | ---: | ---: |
| `OrderPlaced` | ORD-501 | 1 | 1 |
| `OrderLineAdded` | ORD-501 | 2 | 2 |
| `PromotionApplied` | ORD-501 | 3 | 3 |
| `OrderConfirmed` | ORD-501 | 4 | 4 |

Nếu một thay đổi ở version 4 phát ra hai event, sequence có thể là 5 và 6 trong khi cả hai cùng ghi nhận version 4, tùy cách hệ thống định nghĩa version. Nhóm cần ghi rõ semantics thay vì giả định mọi hệ thống dùng version giống nhau.

### 4.2. Source context và tenant

Trong hệ thống có nhiều bounded context, có thể cần `source` hoặc `producer` để biết context nào phát event, ví dụ `sales` hoặc `billing`. Với hệ thống multi-tenant, `tenantId` có thể cần thiết để xác định phạm vi dữ liệu và ngăn xử lý chéo tenant.

Chỉ thêm các trường này khi chúng có ý nghĩa cho hợp đồng, bảo mật hoặc vận hành. Không đưa metadata không được kiểm soát từ client vào event như thể đó là nguồn phát đáng tin cậy.

## 5. Dữ liệu nghiệp vụ trong payload

Payload cần chứa các sự kiện và giá trị cần thiết để hiểu ý nghĩa event. Không có một danh sách trường cố định cho mọi event; dữ liệu phụ thuộc vào câu hỏi mà event trả lời và cách các consumer cần sử dụng nó.

Ví dụ `OrderConfirmed` có thể cần:

- `orderId`: đơn nào đã được xác nhận.
- `customerId` hoặc buyer reference: chủ thể liên quan, nếu cần cho consumer.
- `confirmedAt`: thời điểm xác nhận theo nghiệp vụ.
- `total`: tổng tiền đã xác nhận, nếu cần cho downstream.
- `currency`: loại tiền của tổng tiền.
- Các dòng hàng hoặc snapshot cần thiết nếu consumer phải thực hiện hành động dựa trên nội dung đã xác nhận.

Một event khác như `OrderAddressChanged` có thể cần `orderId`, địa chỉ mới và thời điểm thay đổi. Nếu cần audit, có thể cần địa chỉ cũ hoặc người yêu cầu thay đổi. Nhưng không nên mặc định mọi event đều phải chứa toàn bộ dữ liệu trước và sau.

### 5.1. Payload cần đủ để diễn giải sự kiện

Hãy thử đọc payload mà không mở database của producer. Người nhận có thể hiểu:

- Sự việc nào đã xảy ra?
- Đối tượng nào bị tác động?
- Giá trị nào đã được xác nhận tại thời điểm đó?
- Có điều kiện hoặc ngữ cảnh nào cần thiết để xử lý không?

Nếu thiếu thông tin thiết yếu, consumer có thể phải truy vấn ngược. Việc truy vấn ngược đôi khi hợp lý, nhưng có rủi ro lấy trạng thái hiện tại thay vì trạng thái tại thời điểm event xảy ra.

Ví dụ, `OrderConfirmed` được phát lúc 10:00 với tổng tiền 500.000 VND. Đến 10:15, đơn được điều chỉnh hoặc có một thay đổi khác. Consumer xử lý event lúc 10:20 và truy vấn đơn hiện tại có thể nhận tổng tiền mới, không phải tổng tiền đã xác nhận lúc 10:00. Nếu consumer cần con số lịch sử, event nên mang snapshot tổng tiền tại thời điểm xác nhận.

### 5.2. Payload không nên là bản sao toàn bộ aggregate

Không nên serialize toàn bộ `Order` entity graph vào event chỉ vì nó có sẵn trong bộ nhớ. Aggregate có thể chứa dữ liệu nội bộ, quan hệ lazy, thông tin không liên quan và kiểu persistence. Việc gửi toàn bộ object graph khiến hợp đồng phụ thuộc cấu trúc nội bộ và thay đổi nhỏ cũng có thể phá consumer.

Thay vào đó, hãy tạo một payload có chủ đích với các trường phản ánh sự kiện. Payload là hợp đồng dữ liệu, không phải bản dump của object.

### 5.3. Tránh payload quá nghèo thông tin

Ngược lại, event chỉ có `orderId` có thể buộc mọi consumer phải gọi lại producer. Nếu producer không còn sẵn sàng hoặc trạng thái đã thay đổi, consumer khó xử lý event độc lập.

Hãy cân bằng giữa:

- Tính tự mô tả và khả năng xử lý của consumer.
- Kích thước payload và chi phí truyền tải.
- Mức độ ổn định của hợp đồng.
- Quyền sở hữu dữ liệu và chính sách bảo mật.
- Khả năng thay đổi mô hình nội bộ của producer.

## 6. Snapshot hay reference?

Một quyết định quan trọng là event nên mang giá trị tại thời điểm xảy ra (snapshot) hay chỉ mang ID để consumer tra cứu (reference).

**Snapshot** là bản ghi giá trị liên quan tại thời điểm event xảy ra. **Reference** là định danh hoặc khóa để truy cập đối tượng ở nguồn khác.

| Cách | Ưu điểm | Rủi ro hoặc chi phí |
| --- | --- | --- |
| Chỉ reference | Payload nhỏ, giảm lặp dữ liệu, producer giữ quyền sở hữu dữ liệu | Consumer phụ thuộc khả năng truy vấn; có thể đọc trạng thái mới thay vì trạng thái lịch sử |
| Snapshot | Consumer hiểu được dữ liệu tại thời điểm event; giảm truy vấn ngược | Payload lớn hơn, dữ liệu có thể lặp và cần quản lý schema |
| Kết hợp | Có ID để truy vết và snapshot các giá trị quan trọng | Cần xác định rõ trường nào là nguồn sự thật và trường nào chỉ phục vụ sự kiện |

Ví dụ, `OrderPlaced` có thể chứa `orderId` cùng snapshot tên sản phẩm, SKU, số lượng, đơn giá và tiền tệ đã chốt. Tên sản phẩm có thể thay đổi trong catalog sau đó, nhưng hóa đơn hoặc báo cáo lịch sử vẫn cần biết khách đã đặt mặt hàng nào với giá nào tại thời điểm đặt.

Ngược lại, nếu consumer chỉ cần biết một hồ sơ khách hàng đã được đánh dấu không hoạt động và sau đó sẽ truy vấn dữ liệu mới nhất, ID có thể đủ. Quyết định phải dựa trên ngữ nghĩa của sự kiện và nhu cầu consumer.

### 6.1. Snapshot không phải bản sao tùy tiện

Chỉ chụp những giá trị cần thiết để giải thích sự kiện hoặc thực hiện hợp đồng. Không sao chép toàn bộ hồ sơ cá nhân, thông tin thanh toán hoặc dữ liệu nội bộ nếu consumer không cần.

### 6.2. Reference cần chỉ rõ phạm vi

Một `customerId` có thể chỉ có ý nghĩa trong context bán hàng. Nếu event được gửi cho context khác, hợp đồng cần nói rõ nguồn hoặc loại ID. Có thể dùng `sourceCustomerId`, `buyerReference` hoặc một external reference có namespace để tránh nhầm với ID nội bộ của bên nhận.

## 7. Metadata: thời gian, tương quan và nguồn gốc

Metadata cung cấp thông tin để xử lý, truy vết và vận hành event. Nó thường được đặt trong envelope bên ngoài payload nghiệp vụ.

### 7.1. Phân biệt các mốc thời gian

Không nên dùng một trường `timestamp` cho mọi mục đích mà không định nghĩa. Có thể cần phân biệt:

- **`occurredAt`:** thời điểm sự việc nghiệp vụ thực sự xảy ra theo nguồn có thẩm quyền.
- **`recordedAt`:** thời điểm producer ghi nhận hoặc lưu event.
- **`publishedAt`:** thời điểm event được gửi ra broker hoặc kênh tích hợp.
- **`receivedAt`:** thời điểm consumer nhận event.
- **`processedAt`:** thời điểm consumer xử lý xong.

Các thời điểm này có thể khác nhau do xử lý bất đồng bộ, retry, nhập dữ liệu lịch sử hoặc chênh lệch đồng hồ giữa hệ thống. Nếu nghiệp vụ yêu cầu thời gian chính xác, cần xác định nguồn thời gian có thẩm quyền và quy tắc múi giờ.

Nên dùng định dạng thời gian có timezone hoặc UTC, chẳng hạn ISO 8601 với offset hoặc `Instant` trong Java. Không nên gửi một chuỗi ngày giờ không có thông tin múi giờ rồi để consumer tự đoán.

### 7.2. Correlation ID

`correlationId` liên kết các message hoặc event thuộc cùng một luồng nghiệp vụ hoặc yêu cầu cấp cao. Ví dụ, một yêu cầu đặt hàng có thể dẫn đến event xác nhận đơn, giữ hàng, thanh toán và giao hàng. Correlation ID giúp truy vết cả chuỗi.

Correlation ID không nhất thiết là event ID hoặc aggregate ID. Một correlation có thể bao gồm nhiều aggregate và nhiều event.

### 7.3. Causation ID

`causationId` chỉ ra command hoặc event trực tiếp gây ra event hiện tại, nếu hệ thống có thể xác định. Nó giúp lần theo quan hệ nguyên nhân trong chuỗi xử lý.

Ví dụ, `StockReserved` có thể có `causationId` trỏ đến command `ReserveStock` hoặc message đã kích hoạt việc giữ hàng. Nếu event phát sinh từ một quy trình không có message cụ thể, cách ghi causation cần được định nghĩa phù hợp.

### 7.4. Actor hoặc initiator

Trong một số miền, cần biết ai đã khởi tạo hành động: khách hàng, nhân viên, hệ thống tự động hoặc một service account. Thông tin này có thể thuộc payload nếu là sự kiện nghiệp vụ quan trọng, hoặc metadata nếu chỉ phục vụ audit và truy vết.

Không đưa thông tin xác thực bí mật như access token, mật khẩu hoặc session credential vào event. Nếu cần lưu chủ thể thực hiện, chỉ lưu định danh hoặc vai trò tối thiểu theo chính sách.

### 7.5. Schema version và event type

`eventType` xác định loại sự kiện. `schemaVersion` hoặc một cơ chế versioning tương đương cho biết cấu trúc payload theo phiên bản nào. Tên event và schema version có vai trò khác nhau: một event type có thể tiến hóa schema qua nhiều phiên bản nếu semantics tương thích.

Không nên dựa duy nhất vào tên class Java đã serialize làm hợp đồng lâu dài. Tên package hoặc class có thể đổi khi refactor dù ý nghĩa nghiệp vụ không đổi.

## 8. Ví dụ một event có payload và metadata

Một envelope JSON có thể được thiết kế như sau:

```json
{
  "eventId": "evt-9001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "source": "sales",
  "aggregate": {
    "type": "Order",
    "id": "ORD-501",
    "version": 4,
    "sequence": 4
  },
  "occurredAt": "2026-11-18T02:30:00Z",
  "recordedAt": "2026-11-18T02:30:00.120Z",
  "correlationId": "corr-771",
  "causationId": "cmd-441",
  "payload": {
    "orderId": "ORD-501",
    "buyerReference": "BUY-100",
    "confirmedTotal": {
      "amount": "1250000.00",
      "currency": "VND"
    },
    "lines": [
      {
        "sku": "SKU-01",
        "quantity": 2,
        "unitPrice": {
          "amount": "625000.00",
          "currency": "VND"
        }
      }
    ]
  }
}
```

Đây là ví dụ minh họa. Trong hệ thống thực tế, event envelope có thể do framework hoặc message platform quản lý; một số metadata có thể nằm trong message headers thay vì body. Các giá trị thời gian, ID và trường payload cần tuân theo hợp đồng thật.

Điểm cần chú ý:

- `eventId` nhận diện event cụ thể.
- `aggregate.id` chỉ ra nguồn aggregate.
- `aggregate.version` và `sequence` hỗ trợ kiểm tra phiên bản/thứ tự theo semantics đã định nghĩa.
- `occurredAt` khác `recordedAt`.
- `correlationId` và `causationId` giúp truy vết luồng.
- `confirmedTotal` là snapshot giá trị đã được xác nhận tại thời điểm event.
- Payload không chứa toàn bộ thông tin của buyer hoặc aggregate `Order`.

## 9. Tính bất biến của event

Một domain event mô tả một sự thật đã xảy ra. Sau khi được ghi nhận hoặc công bố, nội dung event không nên bị sửa để phản ánh trạng thái mới. Nếu dữ liệu cần được điều chỉnh, hệ thống nên ghi nhận một sự kiện mới thể hiện việc điều chỉnh.

Ví dụ:

1. `OrderConfirmed` ghi nhận đơn đã được xác nhận với tổng tiền 1.250.000 VND.
2. Sau đó phát hiện lỗi tính giá và nghiệp vụ chấp thuận điều chỉnh.
3. Hệ thống ghi nhận `OrderPriceAdjusted` hoặc một sự kiện điều chỉnh phù hợp.

Không sửa payload của `OrderConfirmed` thành 1.200.000 VND như thể đơn ban đầu đã được xác nhận với giá đó. Làm như vậy sẽ làm sai lịch sử và khiến consumer đã xử lý event cũ không thể biết điều gì đã thay đổi.

### 9.1. Event là fact, command là request

Command có thể bị từ chối, sửa đổi hoặc hết hiệu lực trước khi thực hiện. Event là điều đã xảy ra. Vì vậy, event không nên bị thay đổi sau khi công bố để làm cho nó giống một command mới.

### 9.2. Immutable object trong mã nguồn

Trong Java, có thể dùng `record` hoặc class bất biến để biểu diễn event. Các trường nên được khởi tạo đầy đủ và không cung cấp setter. Với collection, cần tạo bản sao bất biến thay vì chỉ khai báo trường `final` chứa một list mutable.

```java
public record OrderConfirmed(
        EventId eventId,
        OrderId orderId,
        BuyerId buyerId,
        Money confirmedTotal,
        Instant occurredAt,
        long aggregateVersion,
        List<ConfirmedOrderLine> lines
) implements DomainEvent {

    public OrderConfirmed {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(buyerId);
        Objects.requireNonNull(confirmedTotal);
        Objects.requireNonNull(occurredAt);
        lines = List.copyOf(lines);
    }
}

public record ConfirmedOrderLine(
        ProductId productId,
        int quantity,
        Money unitPrice
) {}
```

Đây là ví dụ minh họa. `List.copyOf` bảo vệ cấu trúc danh sách khỏi việc sửa từ bên ngoài, nhưng các phần tử bên trong cũng cần bất biến hoặc được sao chép phù hợp. Nếu `Money`, `ProductId` hoặc `ConfirmedOrderLine` là kiểu mutable, event vẫn có thể bị thay đổi gián tiếp.

### 9.3. Sửa sai bằng sự kiện bù hoặc sự kiện điều chỉnh

Event bất biến không có nghĩa hệ thống không thể sửa sai. Nó có nghĩa không sửa lịch sử đã ghi. Nếu một fact trước đó sai hoặc cần điều chỉnh, hãy ghi nhận fact mới như `PaymentReversed`, `InvoiceCorrected` hoặc `OrderPriceAdjusted`, tùy ngôn ngữ nghiệp vụ.

Các consumer có thể xử lý sự kiện mới để cập nhật projection hoặc trạng thái hiện tại. Cách này giữ được chuỗi sự kiện giải thích vì sao trạng thái hiện tại có giá trị như vậy.

## 10. Event bất biến và Event Sourcing không phải cùng một khái niệm

Domain event thường được thiết kế bất biến dù hệ thống không sử dụng Event Sourcing.

- Trong mô hình thông thường, domain event có thể được phát ra sau khi aggregate thay đổi để thông báo cho phần khác của ứng dụng hoặc context.
- Trong Event Sourcing, chuỗi event được lưu làm nguồn dữ liệu chính để tái dựng trạng thái aggregate.

Vì vậy, dùng domain event không có nghĩa hệ thống phải lưu mọi thay đổi thành event store hoặc xây dựng toàn bộ ứng dụng theo Event Sourcing. Event có thể chỉ tồn tại trong bộ nhớ, được lưu vào outbox hoặc được công bố qua broker tùy nhu cầu.

Nếu dùng Event Sourcing, yêu cầu về schema evolution, replay, thứ tự, khả năng tương thích ngược và bảo vệ dữ liệu trở nên quan trọng hơn vì event lịch sử có thể được đọc lại trong nhiều năm.

## 11. Domain event nội bộ và integration event

Hai khái niệm này có liên quan nhưng không nên mặc định là một.

**Domain event** diễn đạt sự việc có ý nghĩa trong mô hình của một bounded context. Nó có thể dùng kiểu miền nội bộ và được xử lý trong cùng ứng dụng.

**Integration event** là hợp đồng được công bố qua ranh giới để context hoặc hệ thống khác tiêu thụ. Nó cần ổn định, có schema rõ và không làm lộ cấu trúc nội bộ không cần thiết.

| Tiêu chí | Domain event | Integration event |
| --- | --- | --- |
| Phạm vi | Bên trong domain model/bounded context | Qua ranh giới context hoặc hệ thống |
| Mục đích | Thể hiện fact nghiệp vụ cho mô hình nội bộ | Thông báo fact cần thiết cho bên tiêu thụ |
| Ngôn ngữ | Ubiquitous Language nội bộ | Ngôn ngữ/hợp đồng công bố đã thống nhất |
| Cấu trúc | Có thể dùng kiểu miền nội bộ | Nên có schema độc lập và được quản lý phiên bản |
| Mức độ ổn định | Có thể thay đổi cùng mô hình nội bộ | Cần cân nhắc tương thích với consumer |
| Chuyển đổi | Không nhất thiết cần | Có thể cần mapping hoặc ACL tại ranh giới |

Ví dụ, context bán hàng có domain event `OrderConfirmed`. Khi công bố cho kho, nó có thể tạo integration event `SalesOrderConfirmationPublished` với các trường cần thiết theo hợp đồng kho. Hai event có liên quan nhưng không nhất thiết có cùng tên hoặc payload.

### 11.1. Không công bố trực tiếp mọi domain event

Một số event nội bộ chứa chi tiết phục vụ xử lý trong context, không có ý nghĩa hoặc không nên được tiết lộ cho bên ngoài. Nhóm nên chọn những fact cần chia sẻ và thiết kế integration contract riêng.

### 11.2. Không để consumer phụ thuộc class nội bộ

Consumer bên ngoài không nên phải import class Java hoặc package domain của producer. Hợp đồng cần được biểu diễn bằng schema hoặc message format độc lập, có quy tắc versioning và ví dụ rõ ràng.

## 12. Chọn payload: tối thiểu nhưng đủ nghĩa

Một payload tốt không phải payload có ít trường nhất, cũng không phải payload đầy đủ nhất. Nó là payload chứa đủ thông tin để bên nhận hiểu và thực hiện trách nhiệm của mình mà không phụ thuộc quá mức vào trạng thái nội bộ của producer.

Hãy xem xét từng trường theo các câu hỏi:

1. Trường này giúp xác định hoặc diễn giải sự kiện nào?
2. Consumer nào cần nó và để làm gì?
3. Giá trị cần phản ánh tại thời điểm event hay có thể truy vấn hiện tại?
4. Trường có thể thay đổi sau khi event xảy ra không?
5. Có thể tính lại từ các trường khác một cách chắc chắn không?
6. Trường có chứa dữ liệu cá nhân, bí mật hoặc thông tin nhạy cảm không?
7. Nếu bỏ trường này, consumer có phải gọi ngược producer không?
8. Khi schema thay đổi, trường này có thể được thêm, bỏ hoặc đổi ý nghĩa như thế nào?

### 12.1. Không đưa toàn bộ entity graph vào payload

Một event không nên mang mọi quan hệ của aggregate chỉ vì serializer có thể duyệt object graph. Việc này có thể:

- Tạo payload rất lớn.
- Làm lộ thông tin không liên quan.
- Tạo vòng tham chiếu hoặc serialization lỗi.
- Gắn hợp đồng bên ngoài với cấu trúc nội bộ.
- Khiến thay đổi nhỏ trong entity phá consumer.
- Tạo nhiều dữ liệu trùng lặp khó đồng bộ.

Hãy tạo một DTO/event payload riêng với các trường được chọn có chủ đích.

### 12.2. Tránh các trường không có định nghĩa

Các trường như `status`, `type`, `value`, `data`, `timestamp` hoặc `description` quá chung nếu không có schema giải thích. Nên đặt tên cụ thể như `paymentStatus`, `currency`, `occurredAt` hoặc `cancellationReason`.

Nếu một trường có đơn vị, tiền tệ hoặc phạm vi, hãy thể hiện rõ. `amount: 100` không đủ nếu consumer không biết đó là 100 VND, 100 USD, đồng hay đơn vị nhỏ nhất của tiền tệ.

### 12.3. Không dùng số thực cho tiền

Payload tiền nên biểu diễn số thập phân chính xác hoặc minor units kèm tiền tệ và quy tắc scale rõ. Tránh dùng floating-point như `double` cho giá trị tiền nếu có thể gây sai số. Ví dụ `"amount": "1250000.00", "currency": "VND"` hoặc một số nguyên minor unit theo hợp đồng đã định nghĩa.

## 13. Bảo vệ dữ liệu nhạy cảm trong event

Event có thể được lưu lâu, sao chép sang broker, log, data lake và nhiều consumer. Vì vậy, dữ liệu được đưa vào event có thể lan rộng hơn dữ liệu trong aggregate gốc.

Trước khi thêm trường, hãy xác định nó có thực sự cần cho consumer hay không. Không đưa mật khẩu, access token, session secret, thông tin thẻ đầy đủ hoặc bí mật xác thực vào payload.

Với dữ liệu cá nhân như email, số điện thoại, địa chỉ hoặc tên, cần xem xét:

- Consumer nào thật sự cần trường đó?
- Có thể dùng ID tham chiếu thay thế không?
- Có thể dùng snapshot tối thiểu thay vì toàn bộ hồ sơ không?
- Dữ liệu được lưu và giữ trong bao lâu?
- Ai có quyền đọc event và log?
- Khi có yêu cầu xóa hoặc ẩn danh, bản sao ở broker, event store, backup và consumer được xử lý thế nào?

Nếu event chứa dữ liệu cá nhân cần được giữ bất biến để kiểm toán, nhóm cần thiết kế chính sách phù hợp ngay từ đầu. Có thể cân nhắc mã hóa trường nhạy cảm, lưu dữ liệu ở kho riêng với tham chiếu, giới hạn retention hoặc cơ chế xóa khóa/ẩn danh theo yêu cầu đã được xác nhận. Không có một kỹ thuật duy nhất giải quyết mọi nghĩa vụ lưu trữ và bảo vệ dữ liệu.

## 14. Versioning và tiến hóa schema event

Consumer có thể triển khai độc lập và không cập nhật cùng lúc với producer. Vì vậy, thay đổi payload cần được quản lý như thay đổi hợp đồng.

### 14.1. Thay đổi thường có tính tương thích

Trong nhiều schema, thêm một trường optional với default rõ ràng có thể tương thích với consumer cũ, nhưng điều này phụ thuộc định dạng và quy tắc validation. Producer cũng cần biết consumer mới xử lý event cũ thiếu trường ra sao.

Các thay đổi rủi ro cao gồm:

- Đổi tên hoặc xóa trường đang được consumer sử dụng.
- Đổi kiểu dữ liệu hoặc đơn vị đo.
- Thay đổi ý nghĩa của một trường mà vẫn giữ nguyên tên.
- Đổi enum value hoặc loại bỏ trạng thái cũ.
- Chuyển trường từ optional thành required mà event lịch sử không có.
- Đổi semantics của event nhưng giữ nguyên `eventType`.

### 14.2. Thêm schema version

Có thể thêm `schemaVersion` hoặc version trong tên schema. Version nên mô tả cấu trúc và quy tắc diễn giải của payload. Không nên tăng version cho mọi thay đổi nội bộ không ảnh hưởng hợp đồng; cũng không nên giữ version cũ khi ý nghĩa đã thay đổi không tương thích.

### 14.3. Consumer cần chịu được event cũ

Nếu consumer phải đọc event lịch sử, cần có chiến lược cho schema cũ: giữ nhiều reader, chuyển đổi qua upcaster, migrate dữ liệu hoặc duy trì hợp đồng tương thích. Không nên giả định tất cả message trong broker hoặc event store đều được tạo bằng schema mới nhất.

### 14.4. Event type ổn định với ngôn ngữ nghiệp vụ

Tên class Java có thể đổi package hoặc refactor. Event type công bố nên là định danh hợp đồng ổn định, ví dụ `sales.order-confirmed.v1`, thay vì phụ thuộc vào tên class đầy đủ. Cách đặt tên cụ thể tùy nền tảng, nhưng phải có quy tắc nhất quán.

## 15. Thứ tự, trùng lặp và xử lý event

Event có thể được gửi nhiều lần, đến trễ hoặc sai thứ tự, đặc biệt trong hệ thống phân tán. Payload và metadata cần hỗ trợ consumer nhận biết tình huống đó.

### 15.1. Event delivery thường không bảo đảm exactly-once ở mọi tầng

Nhiều broker và hệ thống tích hợp cung cấp delivery semantics như at-most-once hoặc at-least-once; một số nền tảng có cơ chế gần exactly-once trong phạm vi nhất định. Nhưng hiệu quả cuối cùng còn phụ thuộc database, consumer và tác dụng phụ bên ngoài.

Thiết kế an toàn thường giả định consumer có thể nhận cùng event nhiều lần và cần idempotent handling. Consumer có thể lưu `eventId` đã xử lý trong inbox hoặc bảng deduplication cùng transaction cập nhật projection.

### 15.2. Kiểm tra sequence hoặc version

Nếu consumer cần áp dụng event theo thứ tự của một aggregate, có thể kiểm tra `aggregateId` cùng sequence. Event có sequence thấp hơn trạng thái đã xử lý có thể là bản trùng hoặc đến muộn; event có sequence nhảy có thể cho thấy bị thiếu event.

Không nên sắp xếp mọi event toàn hệ thống bằng timestamp rồi giả định đó là thứ tự nhân quả. Đồng hồ giữa máy chủ có thể lệch và nhiều aggregate hoạt động song song. Thứ tự thường chỉ được bảo đảm trong phạm vi stream hoặc partition mà hệ thống định nghĩa.

### 15.3. Event ID và idempotency

Consumer có thể dùng `eventId` làm khóa chống xử lý trùng. Nhưng nếu một sự kiện nghiệp vụ mới được phát lại với ID mới, deduplication theo event ID không nhận ra đó là cùng một yêu cầu nghiệp vụ. Vì vậy, cần phân biệt event identity với command idempotency key hoặc business key.

## 16. Tạo và công bố event trong ứng dụng

Trong một mô hình DDD thông thường, aggregate có thể ghi nhận domain event khi hành vi nghiệp vụ thành công. Application layer thu thập event và công bố sau khi transaction lưu aggregate được commit theo cơ chế đã chọn.

Một luồng khái quát:

```text
Command
  |
  v
Application Service
  |
  v
Load Aggregate
  |
  v
Aggregate Root executes behavior
  |
  +--> validates invariant
  +--> changes state
  +--> records Domain Event
  |
  v
Repository saves aggregate
  |
  v
Commit transaction
  |
  v
Publish event / write Outbox
```

Không nên công bố event ra broker trước khi thay đổi nghiệp vụ được xác nhận nếu điều đó có thể khiến consumer nhận một sự kiện mà transaction sau đó rollback. Với hệ thống cần độ tin cậy cao, Transactional Outbox thường được dùng để ghi thay đổi aggregate và bản ghi event trong cùng transaction database; publisher riêng gửi event sau đó.

### 16.1. Ví dụ aggregate ghi nhận event

```java
public final class Order {
    private final OrderId id;
    private final List<DomainEvent> domainEvents = new ArrayList<>();
    private OrderStatus status;

    public void confirm(Money total, Instant occurredAt) {
        if (status != OrderStatus.SUBMITTED) {
            throw new OrderCannotBeConfirmedException(id, status);
        }

        status = OrderStatus.CONFIRMED;
        domainEvents.add(new OrderConfirmed(
                EventId.generate(),
                id,
                total,
                occurredAt
        ));
    }

    public List<DomainEvent> domainEvents() {
        return List.copyOf(domainEvents);
    }

    public void clearDomainEvents() {
        domainEvents.clear();
    }
}
```

Đây là phác thảo. Trong triển khai thực tế, `occurredAt` có thể được cung cấp qua clock abstraction để kiểm thử; event cần snapshot đúng dữ liệu đã xác nhận; event collection chỉ được xóa sau khi application layer đã xử lý theo cơ chế tin cậy; và việc publish cần được phối hợp với transaction/outbox.

## 17. Ví dụ Java: tách event payload khỏi metadata envelope

Một cách tổ chức là để domain event chứa dữ liệu nghiệp vụ và dùng envelope khi lưu hoặc truyền event:

```java
public interface DomainEvent {}

public record OrderConfirmed(
        OrderId orderId,
        Money confirmedTotal,
        Instant confirmedAt
) implements DomainEvent {}

public record EventEnvelope<T>(
        EventId eventId,
        String eventType,
        int schemaVersion,
        String source,
        String aggregateType,
        String aggregateId,
        long aggregateVersion,
        String correlationId,
        String causationId,
        Instant recordedAt,
        T payload
) {}
```

Ở đây `OrderConfirmed` diễn đạt fact nghiệp vụ. `EventEnvelope` bổ sung thông tin để định danh, truy vết và vận chuyển. Khi event được chuyển thành integration event, adapter có thể ánh xạ sang một contract DTO khác thay vì gửi trực tiếp class domain.

Không nhất thiết phải tạo đúng hai lớp này trong mọi dự án. Một số framework quản lý metadata bằng message header; một số event store có stream position riêng. Hãy giữ rõ sự khác nhau về ý nghĩa dù cách lưu trữ có thể khác.

## 18. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Dùng aggregate ID làm event ID | Không phân biệt được nhiều event của cùng aggregate | Tạo event ID riêng cho từng sự kiện logic |
| Chỉ có ID mà không có payload cần thiết | Consumer phải truy vấn ngược và có thể đọc trạng thái hiện tại sai thời điểm | Thêm snapshot cho những giá trị lịch sử cần thiết |
| Serialize toàn bộ aggregate | Lộ dữ liệu, payload lớn và hợp đồng phụ thuộc cấu trúc nội bộ | Thiết kế payload riêng theo ý nghĩa event |
| Dùng tên `Updated` hoặc `Changed` cho mọi sự kiện | Consumer không hiểu thay đổi nào đã xảy ra | Đặt tên event cụ thể theo fact nghiệp vụ |
| Sửa event cũ khi dữ liệu thay đổi | Lịch sử mất tính đáng tin cậy | Ghi event điều chỉnh hoặc bù mới |
| Dùng `timestamp` không định nghĩa | Consumer nhầm thời điểm xảy ra với thời điểm gửi/nhận | Phân biệt `occurredAt`, `recordedAt`, `publishedAt` |
| Dùng aggregate version như event sequence trong mọi trường hợp | Không phân biệt được nhiều event trong cùng một commit | Định nghĩa sequence/stream position nếu cần |
| Công bố domain event nội bộ trực tiếp cho mọi consumer | Hợp đồng bên ngoài phụ thuộc mô hình nội bộ | Tạo integration event và schema phù hợp |
| Đưa dữ liệu nhạy cảm vào event không cần thiết | Dữ liệu lan sang broker, log và nhiều bản sao | Tối thiểu hóa payload và xác định retention/access |
| Không quản lý schema evolution | Consumer cũ bị lỗi khi producer thay đổi payload | Versioning, contract test và chiến lược tương thích |
| Giả định event chỉ được giao đúng một lần | Tác dụng phụ bị lặp khi retry | Dùng event ID, inbox/deduplication và xử lý idempotent |
| Công bố event trước khi transaction commit | Consumer thấy fact của thay đổi đã rollback | Dùng after-commit hoặc transactional outbox |

## 19. Quy trình thiết kế payload event

Khi tạo một domain event mới, nhóm có thể đi theo các bước sau.

### Bước 1: Xác định fact nghiệp vụ

Viết một câu mô tả điều đã xảy ra. Xác nhận với chuyên gia rằng sự việc có ý nghĩa và thời điểm phát sinh rõ ràng.

### Bước 2: Xác định aggregate nguồn

Làm rõ aggregate hoặc đối tượng miền nào sở hữu hành vi tạo event. Xác định loại và ID của nó. Nếu event phát sinh từ một quy trình không thuộc riêng một aggregate, ghi rõ source context và chủ thể phù hợp.

### Bước 3: Xác định người tiêu thụ và mục đích

Liệt kê phần nào trong ứng dụng hoặc context khác cần event. Với mỗi consumer, xác định nó cần biết gì để thực hiện trách nhiệm.

### Bước 4: Chọn dữ liệu payload

Chọn các trường đủ để diễn giải fact và hỗ trợ consumer. Quyết định trường nào cần snapshot, trường nào chỉ cần reference và trường nào không nên công bố.

### Bước 5: Bổ sung định danh và metadata

Xác định event ID, aggregate ID/type, thời điểm nghiệp vụ, version hoặc sequence nếu cần, source, correlation và causation. Phân biệt metadata nghiệp vụ với metadata vận chuyển.

### Bước 6: Bảo đảm tính bất biến

Dùng kiểu dữ liệu bất biến, không cung cấp setter và bảo vệ collection lồng nhau. Khi có điều chỉnh, tạo event mới thay vì sửa fact đã ghi nhận.

### Bước 7: Xác định ranh giới domain/integration event

Nếu event đi qua bounded context, định nghĩa hợp đồng công bố riêng khi cần. Không để consumer bên ngoài phụ thuộc class hoặc object graph nội bộ.

### Bước 8: Xem xét bảo mật và retention

Kiểm tra dữ liệu cá nhân, bí mật, quyền truy cập, nơi lưu và thời hạn giữ. Chỉ thêm dữ liệu cần thiết cho mục đích đã xác định.

### Bước 9: Quản lý schema và delivery

Định nghĩa version, khả năng tương thích, thứ tự cần thiết, idempotency và cơ chế publish đáng tin cậy. Kiểm thử consumer với event cũ, event trùng và event đến muộn nếu các trường hợp đó có thể xảy ra.

## 20. Nguyên tắc thực hành

Khi thiết kế nội dung domain event, nhóm nên nhớ:

- **Mô tả fact cụ thể.** Tên event thể hiện điều đã xảy ra, không phải yêu cầu thực hiện.
- **Định danh riêng từng event.** Event ID khác aggregate ID, command ID và correlation ID.
- **Ghi rõ nguồn và phạm vi.** Aggregate type/ID và source context giúp diễn giải event đúng mô hình.
- **Chọn payload có chủ đích.** Đủ thông tin để hiểu fact, không serialize toàn bộ aggregate.
- **Quyết định snapshot hay reference.** Dùng snapshot khi cần giữ nghĩa tại thời điểm xảy ra; dùng reference khi truy vấn hiện tại là phù hợp.
- **Phân biệt các mốc thời gian.** `occurredAt` không đồng nghĩa `recordedAt`, `publishedAt` hoặc `receivedAt`.
- **Định nghĩa version và thứ tự.** Aggregate version và event sequence có thể có semantics khác nhau.
- **Giữ event bất biến.** Sửa sai bằng event điều chỉnh hoặc bù, không viết lại lịch sử.
- **Tách domain event và integration event khi cần.** Hợp đồng bên ngoài cần ổn định và độc lập với cấu trúc nội bộ.
- **Bảo vệ dữ liệu nhạy cảm.** Event có thể được sao chép và lưu lâu ở nhiều hệ thống.
- **Thiết kế consumer idempotent.** Event có thể được gửi lại hoặc đến trễ.
- **Công bố sau khi thay đổi được xác nhận.** Dùng after-commit hoặc outbox để tránh phát fact của transaction đã rollback.

Payload event là một phần của mô hình và hợp đồng giao tiếp. Khi định danh, dữ liệu nghiệp vụ, thời gian, metadata và schema được thiết kế rõ, event có thể được diễn giải chính xác, truy vết qua nhiều thành phần và xử lý an toàn ngay cả khi hệ thống hoạt động bất đồng bộ. Tính bất biến giúp lịch sử giữ nguyên ý nghĩa, còn snapshot/reference và versioning giúp cân bằng giữa tính tự mô tả, khả năng tiến hóa và quyền sở hữu dữ liệu.

## 21. Câu hỏi tự kiểm tra

1. Một domain event cần trả lời những câu hỏi nào để người nhận hiểu đúng sự việc đã xảy ra?
2. Vì sao `OrderConfirmed` thường có ý nghĩa rõ hơn `OrderUpdated`?
3. Phân biệt `eventId`, `aggregateId`, `commandId` và `correlationId`.
4. Vì sao aggregate version chưa chắc đủ để xác định thứ tự của nhiều event được phát trong cùng một commit?
5. Payload cần chứa những dữ liệu nào để consumer không phải truy vấn trạng thái hiện tại sai thời điểm?
6. Khi nào nên dùng snapshot, khi nào reference là đủ?
7. Vì sao không nên serialize toàn bộ aggregate vào event?
8. Phân biệt `occurredAt`, `recordedAt`, `publishedAt` và `receivedAt`.
9. Tính bất biến của event có nghĩa gì? Làm thế nào để ghi nhận một điều chỉnh mà không sửa event cũ?
10. Domain event khác integration event ở phạm vi và yêu cầu ổn định như thế nào?
11. Vì sao event ID và idempotent consumer quan trọng khi message có thể được giao nhiều lần?
12. Hãy thiết kế payload cho `PaymentCaptured`, nêu event ID, aggregate/source identity, thời điểm, correlation, dữ liệu snapshot và những thông tin không nên đưa vào payload.
